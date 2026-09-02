import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sources"])


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


class SubscriptionRequest(BaseModel):
    name: str = ""
    url: str = ""


def _get_subscriptions(state) -> list:
    subs = state.settings.get("subscriptions", [])
    return subs if isinstance(subs, list) else []


@router.get("/subscriptions")
async def get_subscriptions():
    state = _get_state()
    return {"subscriptions": _get_subscriptions(state)}


@router.post("/subscriptions")
async def add_subscription(req: SubscriptionRequest):
    state = _get_state()
    if not req.url or not req.url.strip():
        raise HTTPException(400, "订阅 URL 不能为空")
    subs = _get_subscriptions(state)
    sub_id = f"sub_{int(time.time() * 1000)}"
    subs.append({"id": sub_id, "name": req.name.strip() or req.url.strip(), "url": req.url.strip()})
    state.settings.set("subscriptions", subs)
    return {"subscriptions": subs}


@router.delete("/subscriptions/{sub_id}")
async def delete_subscription(sub_id: str):
    state = _get_state()
    subs = _get_subscriptions(state)
    subs = [s for s in subs if s.get("id") != sub_id]
    state.settings.set("subscriptions", subs)
    return {"subscriptions": subs}


@router.post("/subscriptions/sync")
async def sync_subscriptions():
    """拉取所有订阅 URL 的 M3U 内容并解析，返回各订阅的频道统计与样本（仅预览，不写入检测库）"""
    state = _get_state()
    subs = _get_subscriptions(state)
    if not subs:
        raise HTTPException(400, "暂无订阅，请先添加")
    import asyncio
    import aiohttp
    from iptv_check.core.parser import PlaylistParser

    async def fetch_one(sub):
        try:
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
            async with state._async_session.get(sub["url"], timeout=timeout, ssl=False) as resp:
                if resp.status != 200:
                    return {"name": sub["name"], "ok": False, "channels": 0, "error": f"HTTP {resp.status}"}
                text = await resp.text()
            channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, text, sub["name"], "")
            return {
                "name": sub["name"], "ok": True, "channels": len(channels),
                "sample": [c.name for c in channels[:20]],
            }
        except Exception as e:
            return {"name": sub["name"], "ok": False, "channels": 0, "error": str(e)[:100]}

    results = await asyncio.gather(*[fetch_one(s) for s in subs])
    total = sum(r["channels"] for r in results if r["ok"])
    return {"results": results, "total_channels": total}


def _compute_quality_score(source, local_isp: str) -> str:
    score = 0
    if source.has_epg:
        score += 2
    if source.has_logo_support:
        score += 1
    if source.protocol in ("hls", "http"):
        score += 1
    if source.is_isp_compatible(local_isp):
        score += 2
    if source.channel_count > 100:
        score += 1
    if score >= 5:
        return "S"
    elif score >= 3:
        return "A"
    elif score >= 1:
        return "B"
    return "C"


@router.get("/online-sources")
async def get_online_sources():
    state = _get_state()

    def _source_to_dict(s):
        return {
            "id": s.id, "name": s.name, "url": s.url,
            "isp": s.isp, "protocol": s.protocol,
            "features": s.features, "description": s.description,
            "category": s.category, "disabled": s.disabled,
            "epg_url": s.epg_url, "logo_base_url": s.logo_base_url,
            "update_frequency": s.update_frequency,
            "quality_rating": _compute_quality_score(s, state.local_isp),
            "channel_count": s.channel_count,
            "isp_compatible": s.is_isp_compatible(state.local_isp),
            "has_epg": s.has_epg, "has_logo_support": s.has_logo_support,
            "mirror_url": s.mirror_url,
            "last_updated": s.last_updated,
        }

    sources_with_score = []
    for s in state.online_sources:
        if s.disabled:
            continue
        d = _source_to_dict(s)
        score_order = {"S": 0, "A": 1, "B": 2, "C": 3}
        isp_priority = 0 if d["isp_compatible"] else 1
        sources_with_score.append((isp_priority, score_order.get(d["quality_rating"], 3), s))

    sources_with_score.sort(key=lambda x: (x[0], x[1]))

    return {
        "sources": [_source_to_dict(s) for _, _, s in sources_with_score],
        "local_isp": state.local_isp,
    }


@router.get("/isp")
async def get_isp():
    state = _get_state()
    state.ensure_isp_detection_started()
    return {"local_isp": state.local_isp}


@router.post("/isp/refresh")
async def refresh_isp():
    state = _get_state()
    await state.detect_isp()
    return {"local_isp": state.local_isp}


@router.get("/info")
async def get_info():
    from iptv_check.infra.config.settings import APP_VERSION, APP_TITLE
    state = _get_state()
    # ISP 检测在后台运行，不阻塞请求；完成后通过 SSE 推送 isp_updated
    state.ensure_isp_detection_started()
    return {
        "version": APP_VERSION,
        "title": APP_TITLE,
        "local_isp": state.local_isp,
        "is_checking": state.is_checking,
        "online_sources_count": len(state.online_sources),
    }


@router.get("/settings")
async def get_user_settings():
    state = _get_state()
    return state.settings.all


@router.post("/settings")
async def update_user_settings(req: dict):
    state = _get_state()
    for key, value in req.items():
        state.settings.set(key, value)
    return {"saved": True}


# ============================================================
# 风险源黑名单管理
# ============================================================


class BlockedDomainRequest(BaseModel):
    domain: str = ""
    reason: str = "手动添加"


@router.get("/blocked-domains")
async def get_blocked_domains():
    from iptv_check.infra.config import source_filter
    return source_filter.all_entries()


@router.post("/blocked-domains")
async def add_blocked_domain(req: BlockedDomainRequest):
    from iptv_check.infra.config import source_filter
    if not req.domain.strip():
        raise HTTPException(400, "域名不能为空")
    created = source_filter.add_manual(req.domain, req.reason)
    return {"created": created, **source_filter.all_entries()}


@router.delete("/blocked-domains/{domain}")
async def remove_blocked_domain(domain: str):
    from iptv_check.infra.config import source_filter
    removed = source_filter.remove(domain)
    return {"removed": removed, **source_filter.all_entries()}
