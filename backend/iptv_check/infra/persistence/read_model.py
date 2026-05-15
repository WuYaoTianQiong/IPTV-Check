import logging
import threading
from typing import Optional
from datetime import datetime

from sqlmodel import Session, select, func
from sqlalchemy import text as sa_text

from iptv_check.infra.persistence.event_store import EventStore, CheckEventModel

logger = logging.getLogger(__name__)

_CN_COUNTRY_CODES = {
    "CN", "CHN", "HK", "HKG", "MO", "MAC", "TW", "TWN",
}

_COUNTRY_NAME_ZH = {
    "CN": "中国", "HK": "中国香港", "MO": "中国澳门", "TW": "中国台湾",
    "US": "美国", "UK": "英国", "GB": "英国", "JP": "日本", "KR": "韩国",
    "FR": "法国", "DE": "德国", "IT": "意大利", "ES": "西班牙", "PT": "葡萄牙",
    "RU": "俄罗斯", "IN": "印度", "BR": "巴西", "CA": "加拿大", "AU": "澳大利亚",
    "SG": "新加坡", "MY": "马来西亚", "TH": "泰国", "VN": "越南", "PH": "菲律宾",
    "ID": "印尼", "TR": "土耳其", "SA": "沙特", "AE": "阿联酋", "EG": "埃及",
    "NG": "尼日利亚", "ZA": "南非", "AR": "阿根廷", "MX": "墨西哥", "CL": "智利",
    "CO": "哥伦比亚", "PE": "秘鲁", "PL": "波兰", "NL": "荷兰", "SE": "瑞典",
    "CH": "瑞士", "AT": "奥地利", "BE": "比利时", "DK": "丹麦", "NO": "挪威",
    "FI": "芬兰", "IE": "爱尔兰", "NZ": "新西兰", "IL": "以色列", "IQ": "伊拉克",
    "IR": "伊朗", "PK": "巴基斯坦", "BD": "孟加拉", "LK": "斯里兰卡", "MM": "缅甸",
    "KH": "柬埔寨", "LA": "老挝", "NP": "尼泊尔", "UA": "乌克兰", "CZ": "捷克",
    "RO": "罗马尼亚", "HU": "匈牙利", "GR": "希腊", "HR": "克罗地亚", "RS": "塞尔维亚",
    "BG": "保加利亚", "SK": "斯洛伐克", "SI": "斯洛文尼亚", "LT": "立陶宛",
    "LV": "拉脱维亚", "EE": "爱沙尼亚", "IS": "冰岛", "LU": "卢森堡",
    "MT": "马耳他", "CY": "塞浦路斯", "GE": "格鲁吉亚", "AM": "亚美尼亚",
    "AZ": "阿塞拜疆", "KZ": "哈萨克斯坦", "UZ": "乌兹别克斯坦",
}

_CONTENT_TYPE_KEYWORDS = {
    "央视": ["CCTV", "cctv", "央视"],
    "卫视": ["卫视"],
    "地方": [],
    "4K": ["4K", "4k", "UHD", "uhd", "超清"],
    "IPv6": ["IPv6", "ipv6"],
}


def _country_to_flag(code: str) -> str:
    if not code or len(code) != 2:
        return ""
    try:
        offset = 0x1F1E5 - ord('A')
        c1 = chr(ord(code[0]) + offset)
        c2 = chr(ord(code[1]) + offset)
        return c1 + c2
    except Exception:
        return ""


def _scalar(session, query):
    result = session.execute(query)
    return result.scalar()


class ReadModel:
    def __init__(self, event_store: EventStore):
        self._store = event_store
        self._lock = threading.Lock()

    def _session(self) -> Session:
        return self._store.get_session()

    def get_check_progress(self, session_id: str = None) -> dict:
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"total": 0, "checked": 0, "valid": 0, "invalid": 0, "is_running": False, "progress_percent": 0.0}

        with self._session() as session:
            total_result = _scalar(session,
                sa_text("SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_submitted'").bindparams(sid=sid)
            )

            checked_result = _scalar(session,
                sa_text("SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked'").bindparams(sid=sid)
            )

            valid_result = _scalar(session,
                sa_text("SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.is_valid') = 1").bindparams(sid=sid)
            )

            started = session.exec(
                sa_text("SELECT 1 FROM check_events WHERE session_id = :sid AND event_type = 'check_started' LIMIT 1").bindparams(sid=sid)
            ).first()

            completed = session.exec(
                sa_text("SELECT event_type FROM check_events WHERE session_id = :sid AND event_type IN ('check_completed', 'check_stopped', 'check_failed') ORDER BY created_at DESC LIMIT 1").bindparams(sid=sid)
            ).first()

            is_running = started is not None and completed is None

            progress = (checked_result / total_result * 100) if total_result > 0 else 0.0

            return {
                "total": total_result,
                "checked": checked_result,
                "valid": valid_result,
                "invalid": checked_result - valid_result,
                "is_running": is_running,
                "progress_percent": round(progress, 1),
            }

    def get_phase(self, session_id: str = None) -> str:
        sid = session_id or self._store.current_session_id
        if not sid:
            return "idle"

        with self._session() as session:
            completed = session.exec(
                sa_text("SELECT event_type FROM check_events WHERE session_id = :sid AND event_type IN ('check_completed', 'check_stopped', 'check_failed') ORDER BY created_at DESC LIMIT 1").bindparams(sid=sid)
            ).first()

            if completed:
                etype = completed[0] if isinstance(completed, tuple) else completed
                if etype == "check_completed":
                    return "completed"
                if etype == "check_stopped":
                    return "stopped"
                if etype == "check_failed":
                    return "failed"
                return "completed"

            started = session.exec(
                sa_text("SELECT 1 FROM check_events WHERE session_id = :sid AND event_type = 'check_started' LIMIT 1").bindparams(sid=sid)
            ).first()

            if started is None:
                return "idle"

            checking = session.exec(
                sa_text("SELECT 1 FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' LIMIT 1").bindparams(sid=sid)
            ).first()

            if checking:
                return "checking"

            return "downloading"

    def get_source_download_stats(self, session_id: str = None) -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            results = session.exec(
                sa_text("""
                    SELECT
                        json_extract(payload, '$.source_name') as source_name,
                        json_extract(payload, '$.channel_count') as channel_count,
                        json_extract(payload, '$.success') as success
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'source_downloaded'
                    ORDER BY created_at ASC
                """).bindparams(sid=sid)
            ).all()

            return [
                {"source_name": r[0] or "unknown", "channel_count": r[1] or 0, "success": bool(r[2])}
                for r in results
            ]

    def get_full_state(self, session_id: str = None) -> dict:
        progress = self.get_check_progress(session_id)
        phase = self.get_phase(session_id)
        sources = self.get_source_download_stats(session_id)
        return {
            "phase": phase,
            **progress,
            "sources": sources,
        }

    def get_checked_channels(self, session_id: str = None, tab: str = "all",
                             page: int = 1, per_page: int = 50, search: str = "",
                             media_type: str = "all", language: str = "") -> dict:
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"total": 0, "page": page, "per_page": per_page, "items": []}

        with self._session() as session:
            # Build parameterized query
            params = {"sid": sid}
            conditions = ["session_id = :sid", "event_type = 'channel_checked'"]

            if tab == "valid":
                conditions.append("json_extract(payload, '$.is_valid') = 1")
            elif tab == "invalid":
                conditions.append("json_extract(payload, '$.is_valid') = 0")

            if media_type == "tv":
                conditions.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
            elif media_type == "radio":
                conditions.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")

            if language:
                conditions.append("LOWER(json_extract(payload, '$.language')) = LOWER(:language)")
                params["language"] = language

            where_sql = " AND ".join(conditions)

            total = _scalar(session,
                sa_text(f"SELECT COUNT(*) FROM check_events WHERE {where_sql}").bindparams(**params)
            ) or 0

            search_conditions = list(conditions)
            search_params = dict(params)
            if search:
                search_conditions.append(
                    "(LOWER(json_extract(payload, '$.name')) LIKE :search OR LOWER(json_extract(payload, '$.url')) LIKE :search)"
                )
                search_params["search"] = f"%{search.lower()}%"

            search_where = " AND ".join(search_conditions)
            total_with_search = _scalar(session,
                sa_text(f"SELECT COUNT(*) FROM check_events WHERE {search_where}").bindparams(**search_params)
            ) or 0

            offset = (page - 1) * per_page
            query_params = dict(search_params)
            query_params["limit"] = per_page
            query_params["offset"] = offset

            results = session.exec(
                sa_text(f"""
                    SELECT
                        json_extract(payload, '$.name') as name,
                        json_extract(payload, '$.url') as url,
                        json_extract(payload, '$.is_valid') as is_valid,
                        json_extract(payload, '$.latency') as latency,
                        json_extract(payload, '$.speed') as speed,
                        json_extract(payload, '$.details') as details,
                        json_extract(payload, '$.group') as grp,
                        json_extract(payload, '$.sources') as sources
                    FROM check_events
                    WHERE {search_where}
                    ORDER BY created_at ASC
                    LIMIT :limit OFFSET :offset
                """).bindparams(**query_params)
            ).all()

            items = []
            for idx, r in enumerate(results):
                is_valid = bool(r[2])
                items.append({
                    "index": offset + idx + 1,
                    "name": r[0] or "",
                    "url": r[1] or "",
                    "group": r[6] or "",
                    "sources": r[7] or "",
                    "is_valid": is_valid,
                    "status": "有效" if is_valid else "无效",
                    "latency": str(int(r[3])) if r[3] and r[3] != "-" and int(r[3]) >= 0 else "-",
                    "speed": r[4] or "-",
                    "details": r[5] or "",
                })

            return {"total": total_with_search, "page": page, "per_page": per_page, "items": items}

    def get_checked_results_raw(self, session_id: str = None) -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            results = session.exec(
                sa_text("""
                    SELECT
                        json_extract(payload, '$.name'),
                        json_extract(payload, '$.url'),
                        json_extract(payload, '$.is_valid'),
                        json_extract(payload, '$.latency'),
                        json_extract(payload, '$.speed'),
                        json_extract(payload, '$.details'),
                        json_extract(payload, '$.group'),
                        json_extract(payload, '$.sources'),
                        json_extract(payload, '$.url_key')
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                    ORDER BY created_at ASC
                """).bindparams(sid=sid)
            ).all()

            return [
                {
                    "channel": {
                        "name": r[0] or "",
                        "url": r[1] or "",
                        "group": r[6] or "",
                        "sources": [r[7]] if r[7] else [],
                        "url_key": r[8] or "",
                    },
                    "is_valid": bool(r[2]),
                    "latency": float(r[3]) if r[3] and r[3] != "-" and float(r[3]) >= 0 else -1,
                    "speed": r[4] or "-",
                    "details": r[5] or "",
                }
                for r in results
            ]

    def get_grouped_channels(self, session_id: str = None, tab: str = "all",
                             group_path: str = "", page: int = 1, per_page: int = 50,
                             search: str = "", sort: str = "best", media_type: str = "all",
                             language: str = "") -> dict:
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"total": 0, "page": page, "per_page": per_page, "items": []}

        with self._session() as session:
            having_clauses = []
            if tab == "valid":
                having_clauses.append("valid_count > 0")
            elif tab == "invalid":
                having_clauses.append("valid_count = 0")

            params = {"sid": sid}
            filters = ["session_id = :sid", "event_type = 'channel_checked'"]

            if group_path:
                filters.append("json_extract(payload, '$.group') = :group_path")
                params["group_path"] = group_path

            if search:
                filters.append("LOWER(json_extract(payload, '$.name')) LIKE :search")
                params["search"] = f"%{search.lower()}%"

            if media_type == "tv":
                filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
            elif media_type == "radio":
                filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")

            if language:
                filters.append("LOWER(json_extract(payload, '$.language')) = LOWER(:language)")
                params["language"] = language

            having_sql = (" HAVING " + " AND ".join(having_clauses)) if having_clauses else ""
            where_sql = " AND ".join(filters)

            base = f"""
                SELECT
                    json_extract(payload, '$.name') as ch_name,
                    json_extract(payload, '$.group') as ch_group,
                    COUNT(*) as source_count,
                    SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid_count,
                    MIN(CASE WHEN json_extract(payload, '$.is_valid') = 1 AND CAST(json_extract(payload, '$.latency') AS REAL) > 0 THEN CAST(json_extract(payload, '$.latency') AS REAL) END) as best_latency
                FROM check_events
                WHERE {where_sql}
                GROUP BY ch_name
                {having_sql}
            """

            total = _scalar(session, sa_text(f"SELECT COUNT(*) FROM ({base}) sub").bindparams(**params)) or 0

            order_sql = "best_latency ASC, valid_count DESC" if sort == "best" else "ch_name ASC"
            offset = (page - 1) * per_page
            page_params = {**params, "limit": per_page, "offset": offset}

            groups = session.exec(sa_text(f"""
                SELECT ch_name, ch_group, source_count, valid_count, best_latency FROM ({base}) sub
                ORDER BY {order_sql}
                LIMIT :limit OFFSET :offset
            """).bindparams(**page_params)).all()

            items = []
            for idx, g in enumerate(groups):
                name = g[0] or ""
                grp = g[1] or ""
                source_count = g[2] or 0
                valid_count = g[3] or 0
                best_latency = g[4]

                detail_params = {"sid": sid, "ch_name": name}
                sources_rows = session.exec(sa_text("""
                    SELECT
                        json_extract(payload, '$.url'),
                        json_extract(payload, '$.is_valid'),
                        json_extract(payload, '$.latency'),
                        json_extract(payload, '$.speed'),
                        json_extract(payload, '$.details'),
                        json_extract(payload, '$.sources')
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                      AND json_extract(payload, '$.name') = :ch_name
                    ORDER BY CASE WHEN json_extract(payload, '$.latency') IS NULL THEN 1 ELSE 0 END, CAST(json_extract(payload, '$.latency') AS REAL) ASC
                """).bindparams(**detail_params)).all()

                sources = []
                recommended_idx = -1
                best_score = -1
                for si, sr in enumerate(sources_rows):
                    is_valid = bool(sr[1])
                    try:
                        lat = float(sr[2]) if sr[2] else None
                    except (ValueError, TypeError):
                        lat = None
                    lat = lat if lat is not None and lat >= 0 else 9999
                    score = (1000 if is_valid else 0) + max(0, 1000 - lat)
                    sources.append({
                        "url": sr[0] or "",
                        "is_valid": is_valid,
                        "latency": str(int(sr[2])) if sr[2] and sr[2] != "-" else "-",
                        "speed": sr[3] or "-",
                        "details": sr[4] or "",
                        "source_name": sr[5] or "",
                    })
                    if score > best_score:
                        best_score = score
                        recommended_idx = si

                items.append({
                    "index": offset + idx + 1,
                    "name": name,
                    "group": grp,
                    "source_count": source_count,
                    "valid_count": valid_count,
                    "best_latency": str(int(best_latency)) if best_latency and str(best_latency) != "-" and best_latency > 0 else "-",
                    "has_valid": valid_count > 0,
                    "sources": sources,
                    "recommended_source_idx": recommended_idx,
                })

            return {"total": total, "page": page, "per_page": per_page, "items": items}

    def get_category_tree(self, session_id: str = None, media_type: str = "all") -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            params = {"sid": sid}
            filters = ["session_id = :sid", "event_type = 'channel_checked'"]

            if media_type == "tv":
                filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
            elif media_type == "radio":
                filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")

            where_sql = " AND ".join(filters)

            rows = session.exec(sa_text(f"""
                SELECT
                    json_extract(payload, '$.group') as grp,
                    json_extract(payload, '$.country') as country,
                    json_extract(payload, '$.is_radio') as is_radio,
                    COALESCE(json_extract(payload, '$.content_type'), '其他') as content_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid
                FROM check_events
                WHERE {where_sql}
                GROUP BY grp, country, is_radio, content_type
                ORDER BY valid DESC, total DESC
            """).bindparams(**params)).all()

            tree = {
                "央视": {"count": 0, "valid": 0, "children": {}},
                "卫视": {"count": 0, "valid": 0, "children": {}},
                "地方": {"count": 0, "valid": 0, "children": {}},
                "4K": {"count": 0, "valid": 0, "children": {}},
                "IPv6": {"count": 0, "valid": 0, "children": {}},
                "国际电视": {"count": 0, "valid": 0, "children": {}},
                "广播": {"count": 0, "valid": 0, "children": {}},
                "未分类": {"count": 0, "valid": 0, "children": {}},
            }

            for g in rows:
                grp_name = g[0] or "未分组"
                country_code = (g[1] or "").strip().upper()
                is_radio = bool(g[2])
                content_type = g[3] or "其他"
                total = g[4] or 0
                valid = g[5] or 0

                codes = [c.strip() for c in country_code.split(";") if c.strip()]
                is_cn = any(c in _CN_COUNTRY_CODES for c in codes) if codes else False

                primary_code = codes[0] if codes else ""
                flag_emoji = _country_to_flag(primary_code)
                country_zh = _COUNTRY_NAME_ZH.get(primary_code, "")

                grp_display = grp_name
                if country_zh and not is_cn:
                    grp_display = f"{flag_emoji} {grp_name}"

                if content_type in tree:
                    region = content_type
                elif is_radio:
                    region = "广播"
                elif is_cn:
                    region = "地方"
                elif codes:
                    region = "国际电视"
                else:
                    region = "未分类"

                tree[region]["count"] += total
                tree[region]["valid"] += valid
                existing = tree[region]["children"].get(grp_display, {"count": 0, "valid": 0, "country": primary_code, "flag": flag_emoji, "country_zh": country_zh})
                tree[region]["children"][grp_display] = {
                    "count": existing["count"] + total,
                    "valid": existing["valid"] + valid,
                    "country": primary_code,
                    "flag": flag_emoji,
                    "country_zh": country_zh,
                }

            result = []
            region_order = ["央视", "卫视", "地方", "4K", "IPv6", "国际电视", "广播", "未分类"]
            for region_name in region_order:
                region_data = tree[region_name]
                if region_data["count"] == 0:
                    continue
                children = []
                for grp_name, grp_data in sorted(region_data["children"].items(), key=lambda x: x[1]["valid"], reverse=True):
                    child = {
                        "name": grp_name,
                        "count": grp_data["count"],
                        "valid": grp_data["valid"],
                    }
                    if grp_data.get("flag"):
                        child["flag"] = grp_data["flag"]
                    if grp_data.get("country_zh"):
                        child["country_zh"] = grp_data["country_zh"]
                    children.append(child)
                result.append({
                    "name": region_name,
                    "count": region_data["count"],
                    "valid": region_data["valid"],
                    "children": children,
                })

            return result

    def get_available_languages(self, session_id: str = None) -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            rows = session.exec(sa_text("""
                SELECT
                    json_extract(payload, '$.language') as lang,
                    COUNT(*) as total,
                    SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid
                FROM check_events
                WHERE session_id = :sid AND event_type = 'channel_checked'
                  AND json_extract(payload, '$.language') IS NOT NULL
                  AND json_extract(payload, '$.language') != ''
                GROUP BY lang
                ORDER BY total DESC
            """).bindparams(sid=sid)).all()

            return [
                {"language": r[0] or "", "count": r[1] or 0, "valid": r[2] or 0}
                for r in rows
                if r[0]
            ]
