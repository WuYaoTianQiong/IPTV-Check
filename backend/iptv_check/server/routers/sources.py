import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sources"])


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


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
    if state.local_isp == "未知":
        await state.detect_isp()
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
    # 如果 ISP 检测未完成，触发检测并等待完成
    if state.local_isp == "未知":
        await state.detect_isp()
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
