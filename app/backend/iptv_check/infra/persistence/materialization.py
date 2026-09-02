import json
import logging
import asyncio
import re
import threading
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select
from sqlalchemy import text as sa_text

from iptv_check.infra.persistence.event_store import (
    EventStore,
    ChannelResultModel,
    SessionSummaryModel,
)
from iptv_check.infra.cn_time import cn_now

logger = logging.getLogger(__name__)


def _parse_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            pass
    return None


class MaterializationService:
    def __init__(self, event_store: EventStore):
        self._store = event_store
        self._materialized_sessions: set[str] = set()
        # 物化互斥锁：后台物化（检测完成）与按需物化（查询兜底）可能并发，
        # 避免同一会话被两个线程同时物化导致 channel_results 重复行
        self._lock = threading.Lock()
        self._load_materialized_sessions()

    def _load_materialized_sessions(self):
        try:
            with self._store.engine.connect() as conn:
                # 物化表索引：加速按 session 过滤、频道分组/去重计数与延迟排序
                for idx_sql in (
                    "CREATE INDEX IF NOT EXISTS idx_chr_session ON channel_results(session_id)",
                    "CREATE INDEX IF NOT EXISTS idx_chr_session_name ON channel_results(session_id, name)",
                    "CREATE INDEX IF NOT EXISTS idx_chr_session_valid_latency ON channel_results(session_id, is_valid, latency)",
                ):
                    try:
                        conn.execute(sa_text(idx_sql))
                    except Exception:
                        logger.debug("创建物化索引失败（可能已存在）: %s", idx_sql[:80])
                conn.commit()
                rows = conn.execute(
                    sa_text("SELECT DISTINCT session_id FROM channel_results")
                ).fetchall()
                self._materialized_sessions = {r[0] for r in rows}
                logger.info("已物化会话数: %d", len(self._materialized_sessions))
        except Exception as e:
            logger.warning("加载物化会话失败，重置为空: %s", e)
            self._materialized_sessions = set()

    def is_materialized(self, session_id: str) -> bool:
        return session_id in self._materialized_sessions

    def materialize_session(self, session_id: str) -> int:
        with self._lock:
            return self._materialize_session_impl(session_id)

    def _materialize_session_impl(self, session_id: str) -> int:
        if session_id in self._materialized_sessions:
            return 0

        with Session(self._store.engine) as session:
            count = session.exec(
                sa_text("""
                    SELECT COUNT(*) FROM channel_results WHERE session_id = :sid
                """).bindparams(sid=session_id)
            ).scalar()

            if count and count > 0:
                self._materialized_sessions.add(session_id)
                return 0

            events = session.exec(
                sa_text("""
                    SELECT
                        json_extract(payload, '$.name'),
                        json_extract(payload, '$.url'),
                        json_extract(payload, '$.url_key'),
                        json_extract(payload, '$.is_valid'),
                        json_extract(payload, '$.is_radio'),
                        json_extract(payload, '$.latency'),
                        json_extract(payload, '$.speed'),
                        json_extract(payload, '$.details'),
                        json_extract(payload, '$.group'),
                        json_extract(payload, '$.sources'),
                        json_extract(payload, '$.language'),
                        json_extract(payload, '$.country'),
                        json_extract(payload, '$.content_type'),
                        json_extract(payload, '$.source_name'),
                        json_extract(payload, '$.quality_tier'),
                        json_extract(payload, '$.resolution'),
                        json_extract(payload, '$.tvg_name'),
                        json_extract(payload, '$.clean_name'),
                        json_extract(payload, '$.frequency'),
                        json_extract(payload, '$.media_type'),
                        created_at
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                    ORDER BY created_at ASC
                """).bindparams(sid=session_id)
            ).all()

            if not events:
                return 0

            recheck_events = session.exec(
                sa_text("""
                    SELECT
                        json_extract(payload, '$.url_key'),
                        json_extract(payload, '$.is_valid'),
                        json_extract(payload, '$.latency'),
                        json_extract(payload, '$.speed'),
                        json_extract(payload, '$.details'),
                        json_extract(payload, '$.quality_tier'),
                        json_extract(payload, '$.resolution')
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_rechecked'
                    ORDER BY created_at ASC
                """).bindparams(sid=session_id)
            ).all()

            recheck_map = {}
            for r in recheck_events:
                key = r[0]
                if key:
                    recheck_map[key] = r

            for evt in events:
                try:
                    lat_val = evt[5]
                    try:
                        latency = float(lat_val) if lat_val is not None and lat_val != "-" and float(lat_val) >= 0 else -1
                    except (ValueError, TypeError):
                        latency = -1

                    is_valid = 1 if evt[3] else 0
                    is_radio = 1 if evt[4] else 0
                    # 检测事实优先：流首包/Content-Type 判定的媒体类型是电视/电台的权威依据
                    media_type = (evt[19] or "").lower()
                    if media_type == "audio":
                        is_radio = 1
                    elif media_type == "video":
                        is_radio = 0

                    quality_tier = evt[14] or ""
                    if not quality_tier:
                        quality_tier = "valid" if is_valid else "invalid"
                    elif is_valid == 0 and quality_tier in ("valid", "likely_valid"):
                        # 防御：明细中 is_valid 与 quality_tier 必须一致，
                        # 否则"无效却标记有效"的脏组合会污染统计与导出
                        quality_tier = "invalid"

                    url_key = evt[2] or ""
                    recheck = recheck_map.get(url_key)
                    rc_speed = evt[6] or "-"
                    rc_details = evt[7] or ""
                    rc_resolution = evt[15] or ""
                    if recheck:
                        is_valid = 1 if recheck[1] else 0
                        rc_lat = recheck[2]
                        try:
                            latency = float(rc_lat) if rc_lat is not None and rc_lat != "-" and float(rc_lat) >= 0 else -1
                        except (ValueError, TypeError):
                            latency = -1
                        rc_speed = recheck[3] or "-"
                        rc_details = recheck[4] or ""
                        quality_tier = recheck[5] or ""
                        if not quality_tier:
                            quality_tier = "valid" if is_valid else "invalid"
                        elif is_valid == 0 and quality_tier in ("valid", "likely_valid"):
                            quality_tier = "invalid"
                        rc_resolution = recheck[6] or ""

                    name_val = evt[0] or ""
                    if name_val == "N/A":
                        sources_raw = evt[9]
                        if sources_raw:
                            try:
                                src_list = sources_raw if isinstance(sources_raw, list) else json.loads(sources_raw)
                                if src_list and isinstance(src_list, list):
                                    name_val = str(src_list[0])
                            except (json.JSONDecodeError, TypeError):
                                if isinstance(sources_raw, str) and sources_raw and sources_raw != "[]":
                                    name_val = sources_raw

                    result = ChannelResultModel(
                        session_id=session_id,
                        name=name_val,
                        url=evt[1] or "",
                        url_key=evt[2] or "",
                        is_valid=is_valid,
                        is_radio=is_radio,
                        quality_tier=quality_tier,
                        latency=latency,
                        speed=rc_speed,
                        details=rc_details,
                        channel_group=evt[8] or "",
                        sources=json.dumps(evt[9]) if evt[9] else "[]",
                        language=evt[10] or "",
                        country=evt[11] or "",
                        content_type=evt[12] or "",
                        source_name=evt[13] or "",
                        resolution=rc_resolution,
                        tvg_name=evt[16] or "",
                        clean_name=evt[17] or "",
                        frequency=evt[18] or "",
                        created_at=_parse_dt(evt[20]) or cn_now(),
                    )
                    session.add(result)
                except Exception as e:
                    logger.warning("物化单条结果失败: %s", e)

            session.commit()

        # 汇总计数一律从明细聚合，保证明细与汇总同源
        # （避免 recheck 覆盖明细后 summary 仍按原始事件计算导致的长期漂移）
        self._refresh_summary(session_id)

        self._materialized_sessions.add(session_id)
        logger.info("会话 %s 物化完成: %d 条结果", session_id, len(events))
        return len(events)

    def incremental_append(self, session_id: str, payload: dict) -> None:
        try:
            with Session(self._store.engine) as session:
                lat_val = payload.get("latency", -1)
                try:
                    latency = float(lat_val) if lat_val is not None and lat_val != "-" and float(lat_val) >= 0 else -1
                except (ValueError, TypeError):
                    latency = -1

                is_valid = 1 if payload.get("is_valid") else 0
                is_radio = 1 if payload.get("is_radio") else 0
                media_type = (payload.get("media_type") or "").lower()
                if media_type == "audio":
                    is_radio = 1
                elif media_type == "video":
                    is_radio = 0

                ch = payload.get("channel", {})
                name_val = ch.get("name", "")
                if name_val == "N/A":
                    ch_sources = ch.get("sources", [])
                    if ch_sources and isinstance(ch_sources, list):
                        name_val = str(ch_sources[0])
                    elif isinstance(ch_sources, str) and ch_sources and ch_sources != "[]":
                        name_val = ch_sources

                result = ChannelResultModel(
                    session_id=session_id,
                    name=name_val,
                    url=ch.get("url", ""),
                    url_key=ch.get("url_key", ""),
                    is_valid=is_valid,
                    is_radio=is_radio,
                    quality_tier=payload.get("quality_tier", "valid" if is_valid else "invalid"),
                    latency=latency,
                    speed=payload.get("speed", "-"),
                    details=payload.get("details", ""),
                    channel_group=ch.get("group", ""),
                    sources=json.dumps(ch.get("sources", [])),
                    language=ch.get("language", ""),
                    country=ch.get("country", ""),
                    content_type=ch.get("content_type", ""),
                    source_name=payload.get("source_name", ""),
                    resolution=ch.get("resolution", ""),
                    tvg_name=ch.get("tvg_name", ""),
                    clean_name=ch.get("clean_name", ""),
                    frequency=payload.get("frequency", "") or ch.get("frequency", ""),
                )
                session.add(result)
                session.commit()
        except Exception as e:
            logger.warning("增量物化失败: %s", e)

    def cleanup_old_sessions(self, keep_recent: int = 5) -> int:
        with Session(self._store.engine) as session:
            sessions = session.exec(
                sa_text("""
                    SELECT DISTINCT session_id FROM channel_results
                    ORDER BY session_id DESC
                """)
            ).all()

            if len(sessions) <= keep_recent:
                return 0

            to_remove = sessions[keep_recent:]
            removed = 0
            for sid in to_remove:
                session.exec(
                    sa_text("DELETE FROM channel_results WHERE session_id = :sid").bindparams(sid=sid)
                )
                session.exec(
                    sa_text("DELETE FROM session_summaries WHERE session_id = :sid").bindparams(sid=sid)
                )
                self._materialized_sessions.discard(sid)
                removed += 1

            session.commit()
            logger.info("清理旧物化数据: %d 个会话", removed)
            return removed

    async def materialize_session_async(self, session_id: str) -> int:
        return await asyncio.to_thread(self.materialize_session, session_id)

    def _refresh_summary(self, session_id: str) -> None:
        """从 channel_results 明细聚合该会话的汇总统计。

        明细写入与汇总必须同源，否则 recheck 覆盖明细后 summary 仍按
        原始事件计算，长期漂移（表现为 valid_count 与明细对不上）。
        """
        with Session(self._store.engine) as session:
            row = session.exec(
                sa_text("""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) AS valid,
                        SUM(CASE WHEN is_valid = 0 THEN 1 ELSE 0 END) AS invalid,
                        SUM(CASE WHEN IFNULL(is_radio, 0) = 0 THEN 1 ELSE 0 END) AS tv,
                        SUM(CASE WHEN is_radio = 1 THEN 1 ELSE 0 END) AS radio,
                        AVG(CASE WHEN latency >= 0 THEN latency END) AS avg_lat
                    FROM channel_results WHERE session_id = :sid
                """).bindparams(sid=session_id)
            ).one()

            total = row[0] or 0
            valid_count = row[1] or 0
            invalid_count = row[2] or 0
            tv_count = row[3] or 0
            radio_count = row[4] or 0
            avg_latency = row[5] if row[5] is not None else 0

            existing = session.exec(
                select(SessionSummaryModel).where(SessionSummaryModel.session_id == session_id)
            ).first()

            now = cn_now()
            if existing:
                existing.total_count = total
                existing.valid_count = valid_count
                existing.invalid_count = invalid_count
                existing.tv_count = tv_count
                existing.radio_count = radio_count
                existing.avg_latency = avg_latency
                existing.status = "completed"
                existing.updated_at = now
            else:
                summary = SessionSummaryModel(
                    session_id=session_id,
                    total_count=total,
                    valid_count=valid_count,
                    invalid_count=invalid_count,
                    tv_count=tv_count,
                    radio_count=radio_count,
                    avg_latency=avg_latency,
                    status="completed",
                    created_at=now,
                    updated_at=now,
                )
                session.add(summary)
            session.commit()

    def repair_is_radio(self) -> int:
        with Session(self._store.engine) as session:
            # 修复 channel_results: 根据 channel_group / name / url 关键词推断
            session.exec(sa_text("""
                UPDATE channel_results SET is_radio = 1 WHERE is_radio = 0 AND (
                    lower(channel_group) LIKE '%广播%' OR
                    lower(channel_group) LIKE '%电台%' OR
                    lower(channel_group) LIKE '%radio%' OR
                    lower(name) LIKE '%广播%' OR
                    lower(name) LIKE '%电台%' OR
                    lower(name) LIKE '%radio%' OR
                    lower(url) LIKE '%qingting.fm%' OR
                    lower(url) LIKE '%xmcdn.com%' OR
                    lower(url) LIKE '%ximalaya%' OR
                    lower(url) LIKE '%lrc.la%' OR
                    lower(url) GLOB '*://radio[0-9.:]*' OR
                    lower(url) GLOB '*.radio[0-9.:]*'
                )
            """))
            fixed = session.exec(sa_text("SELECT changes()")).scalar()

            # 修复 check_events 事件表中的 is_radio
            event_rows = session.exec(sa_text(
                """SELECT id, payload FROM check_events
                   WHERE event_type IN ('channel_checked', 'channel_rechecked')
                   AND COALESCE(json_extract(payload, '$.is_radio'), 0) = 0
                   AND (
                       lower(json_extract(payload, '$.group')) LIKE '%广播%' OR
                       lower(json_extract(payload, '$.group')) LIKE '%电台%' OR
                       lower(json_extract(payload, '$.group')) LIKE '%radio%' OR
                       lower(json_extract(payload, '$.name')) LIKE '%广播%' OR
                       lower(json_extract(payload, '$.name')) LIKE '%电台%' OR
                       lower(json_extract(payload, '$.name')) LIKE '%radio%' OR
                       lower(json_extract(payload, '$.url')) LIKE '%qingting.fm%' OR
                       lower(json_extract(payload, '$.url')) LIKE '%xmcdn.com%' OR
                       lower(json_extract(payload, '$.url')) LIKE '%ximalaya%' OR
                       lower(json_extract(payload, '$.url')) LIKE '%lrc.la%' OR
                       lower(json_extract(payload, '$.url')) GLOB '*://radio[0-9.:]*' OR
                       lower(json_extract(payload, '$.url')) GLOB '*.radio[0-9.:]*'
                   )"""
            )).all()

            event_fixed = 0
            _RADIO_KEYWORDS = {"广播", "电台", "radio", "fm", "am", "broadcast"}
            _RADIO_URL_KEYWORDS = {"qingting.fm", "xmcdn.com", "ximalaya", "lrc.la"}
            for row in event_rows:
                eid, payload_str = row
                try:
                    payload = json.loads(payload_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                name = payload.get("name", "")
                group = payload.get("group", "")
                url = payload.get("url", "")
                text_lower = f"{name} {group}".lower()
                url_lower = (url or "").lower()
                media_type = (payload.get("media_type") or "").lower()
                if media_type in ("audio", "video"):
                    # 已有检测事实（流首包/Content-Type 判定），无需启发式修复
                    continue
                if (any(kw in text_lower for kw in _RADIO_KEYWORDS) or
                    any(kw in url_lower for kw in _RADIO_URL_KEYWORDS) or
                    re.search(r"://[^/]*radio(?:\d|\.|:)", url_lower)):
                    payload["is_radio"] = True
                    session.exec(sa_text(
                        "UPDATE check_events SET payload = :p WHERE id = :id"
                    ).bindparams(p=json.dumps(payload, ensure_ascii=False), id=eid))
                    event_fixed += 1

            if fixed or event_fixed:
                session.commit()

            # 更新 session_summaries
            sessions_to_update = session.exec(sa_text(
                "SELECT DISTINCT session_id FROM channel_results WHERE is_radio = 1"
            )).all()
            for sid_row in sessions_to_update:
                sid = sid_row[0]
                rc = session.exec(sa_text(
                    "SELECT COUNT(*) FROM channel_results WHERE session_id = :sid AND is_radio = 1"
                ).bindparams(sid=sid)).scalar()
                tc = session.exec(sa_text(
                    "SELECT COUNT(*) FROM channel_results WHERE session_id = :sid"
                ).bindparams(sid=sid)).scalar()
                session.exec(sa_text(
                    "UPDATE session_summaries SET radio_count = :rc, tv_count = :tc WHERE session_id = :sid"
                ).bindparams(rc=rc, tc=tc - rc, sid=sid))

            if fixed or event_fixed:
                session.commit()

            logger.info("is_radio修复完成: 物化表修正 %d 条, 事件表修正 %d 条", fixed, event_fixed)
            return fixed + event_fixed
