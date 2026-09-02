"""
Results Repository
检测结果会话数据访问：封装 channel_results / check_events 的查询与更新，
避免 router 层直接书写原生 SQL（含 JSON payload 操作）。
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text as sa_text


class ResultsRepository:
    """检测结果会话（channel_results / check_events）数据访问。"""

    def __init__(self, session):
        self._session = session

    def latest_session_id(self) -> str:
        """返回最近有物化数据的会话 ID。"""
        row = self._session.execute(
            sa_text(
                "SELECT session_id FROM channel_results "
                "GROUP BY session_id ORDER BY MAX(created_at) DESC LIMIT 1"
            )
        ).first()
        return row[0] if row else ""

    def has_session_data(self, session_id: str) -> bool:
        """判断会话是否已有物化数据。"""
        cnt = self._session.execute(
            sa_text("SELECT COUNT(*) FROM channel_results WHERE session_id = :sid"),
            {"sid": session_id},
        ).scalar() or 0
        return cnt > 0

    def fetch_session_urls(self, session_id: str):
        """聚合 channel_results 与 check_events 中的去重 URL 列表，并返回去重后的频道数。
        返回 (urls: list[str], channel_count: int)。"""
        rows = self._session.execute(
            sa_text(
                "SELECT DISTINCT url FROM channel_results "
                "WHERE session_id = :sid AND url != ''"
            ),
            {"sid": session_id},
        ).fetchall()
        urls = {r[0] for r in rows}
        evt_rows = self._session.execute(
            sa_text(
                "SELECT DISTINCT json_extract(payload, '$.url') FROM check_events "
                "WHERE session_id = :sid AND event_type = 'channel_checked' "
                "AND json_extract(payload, '$.url') != ''"
            ),
            {"sid": session_id},
        ).fetchall()
        for r in evt_rows:
            if r[0]:
                urls.add(r[0])

        names: set = set()
        name_rows = self._session.execute(
            sa_text(
                "SELECT DISTINCT name FROM channel_results "
                "WHERE session_id = :sid AND name != ''"
            ),
            {"sid": session_id},
        ).fetchall()
        names.update(r[0] for r in name_rows)
        evt_names = self._session.execute(
            sa_text(
                "SELECT DISTINCT json_extract(payload, '$.name') FROM check_events "
                "WHERE session_id = :sid AND event_type = 'channel_checked' "
                "AND json_extract(payload, '$.name') != ''"
            ),
            {"sid": session_id},
        ).fetchall()
        for r in evt_names:
            if r[0]:
                names.add(r[0])
        return list(urls), len(names)

    def reset_session_latency(self, session_id: str, urls: Optional[list[str]] = None) -> None:
        """将指定 URL 子集（或全部）的延迟/有效性重置为无效，并同步事件表 payload。"""
        if urls:
            placeholders = ",".join(f":u{i}" for i in range(len(urls)))
            url_params = {f"u{i}": u for i, u in enumerate(urls)}
            self._session.execute(
                sa_text(
                    f"UPDATE channel_results SET latency = -1, is_valid = 0, quality_tier = 'invalid' "
                    f"WHERE session_id = :sid AND url IN ({placeholders})"
                ),
                {"sid": session_id, **url_params},
            )
            rows = self._session.execute(
                sa_text(
                    f"SELECT id, payload FROM check_events "
                    f"WHERE session_id = :sid AND event_type = 'channel_checked' "
                    f"AND json_extract(payload, '$.url') IN ({placeholders})"
                ),
                {"sid": session_id, **url_params},
            ).fetchall()
        else:
            self._session.execute(
                sa_text(
                    "UPDATE channel_results SET latency = -1, is_valid = 0, quality_tier = 'invalid' "
                    "WHERE session_id = :sid"
                ),
                {"sid": session_id},
            )
            rows = self._session.execute(
                sa_text(
                    "SELECT id, payload FROM check_events "
                    "WHERE session_id = :sid AND event_type = 'channel_checked'"
                ),
                {"sid": session_id},
            ).fetchall()
        for row in rows:
            try:
                p = json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
                p["latency"] = -1
                p["is_valid"] = False
                p["quality_tier"] = "invalid"
                self._session.execute(
                    sa_text("UPDATE check_events SET payload = :p WHERE id = :eid"),
                    {"p": json.dumps(p, ensure_ascii=False), "eid": row[0]},
                )
            except Exception:
                pass
        self._session.commit()

    def update_channel_result(self, session_id: str, url: str, latency, is_valid, quality_tier: str) -> None:
        """更新 channel_results 中指定 URL 的延迟结果。"""
        self._session.execute(
            sa_text(
                "UPDATE channel_results SET latency = :lat, is_valid = :iv, quality_tier = :qt "
                "WHERE session_id = :sid AND url = :url"
            ),
            {"lat": latency, "iv": is_valid, "qt": quality_tier, "sid": session_id, "url": url},
        )

    def update_event_payload_latency(self, session_id: str, url: str, latency, is_valid, quality_tier: str) -> None:
        """更新 check_events 中指定 URL 的事件 payload 延迟字段。"""
        rows = self._session.execute(
            sa_text(
                "SELECT id, payload FROM check_events "
                "WHERE session_id = :sid AND event_type = 'channel_checked' "
                "AND json_extract(payload, '$.url') = :url"
            ),
            {"sid": session_id, "url": url},
        ).fetchall()
        for row in rows:
            try:
                p = json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
                p["latency"] = latency
                p["is_valid"] = is_valid
                p["quality_tier"] = quality_tier
                self._session.execute(
                    sa_text("UPDATE check_events SET payload = :p WHERE id = :eid"),
                    {"p": json.dumps(p, ensure_ascii=False), "eid": row[0]},
                )
            except Exception:
                pass

    def update_batch_valid(self, session_id: str, batch) -> None:
        """批量回写一批有效结果 [(latency, url), ...] 到 channel_results 与 check_events。

        用临时表 + 一次性 UPDATE 替代逐条回写：旧实现对每个 URL 都要把
        check_events 该会话所有行 json_extract 扫一遍（每批 500 条 = 500 次全扫），
        是彻底版检测的主要耗时来源。新实现每批只扫一次。
        实测（301MB 库，300 条）：25.3s -> 0.11s（约 226x），结果逐字段一致。"""
        if not batch:
            return
        s = self._session
        s.execute(sa_text("DROP TABLE IF EXISTS temp.batch_results"))
        s.execute(sa_text(
            "CREATE TEMP TABLE batch_results (url TEXT PRIMARY KEY, lat REAL)"))
        s.execute(
            sa_text("INSERT INTO temp.batch_results (url, lat) VALUES (:url, :lat)"),
            [{"url": u, "lat": lat} for lat, u in batch],
        )
        s.execute(sa_text(
            "UPDATE channel_results "
            "SET latency = b.lat, is_valid = 1, quality_tier = 'valid' "
            "FROM temp.batch_results AS b "
            "WHERE channel_results.session_id = :sid AND channel_results.url = b.url"),
            {"sid": session_id},
        )
        s.execute(sa_text(
            "UPDATE check_events "
            "SET payload = json_set(payload, "
            "  '$.latency', (SELECT b.lat FROM temp.batch_results AS b "
            "                WHERE b.url = json_extract(check_events.payload, '$.url')), "
            "  '$.is_valid', json('true'), '$.quality_tier', 'valid') "
            "WHERE session_id = :sid AND event_type = 'channel_checked' "
            "AND json_extract(payload, '$.url') IN (SELECT url FROM temp.batch_results)"),
            {"sid": session_id},
        )
        s.execute(sa_text("DROP TABLE IF EXISTS temp.batch_results"))
