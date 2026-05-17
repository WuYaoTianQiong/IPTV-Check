import json
import logging
import asyncio
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
        self._load_materialized_sessions()

    def _load_materialized_sessions(self):
        try:
            with self._store.engine.connect() as conn:
                rows = conn.execute(
                    sa_text("SELECT DISTINCT session_id FROM channel_results")
                ).fetchall()
                self._materialized_sessions = {r[0] for r in rows}
                logger.info("已物化会话数: %d", len(self._materialized_sessions))
        except Exception:
            self._materialized_sessions = set()

    def is_materialized(self, session_id: str) -> bool:
        return session_id in self._materialized_sessions

    def materialize_session(self, session_id: str) -> int:
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

                    quality_tier = evt[14] or ""
                    if not quality_tier:
                        quality_tier = "valid" if is_valid else "invalid"

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
                        created_at=_parse_dt(evt[16]) or cn_now(),
                    )
                    session.add(result)
                except Exception as e:
                    logger.warning("物化单条结果失败: %s", e)

            self._upsert_summary(session, session_id, events)
            session.commit()

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

    def _upsert_summary(self, session: Session, session_id: str, events: list) -> None:
        total = len(events)
        valid_count = sum(1 for e in events if e[3])
        invalid_count = total - valid_count
        tv_count = sum(1 for e in events if not e[4])
        radio_count = sum(1 for e in events if e[4])

        latencies = []
        for e in events:
            try:
                lat = float(e[5]) if e[5] is not None and float(e[5]) >= 0 else None
                if lat is not None:
                    latencies.append(lat)
            except (ValueError, TypeError):
                pass
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

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
