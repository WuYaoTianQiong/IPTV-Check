import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sources"])


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.get("/online-sources")
async def get_online_sources():
    state = _get_state()
    return {
        "sources": [
            {
                "id": s.id, "name": s.name, "url": s.url,
                "isp": s.isp, "protocol": s.protocol,
                "features": s.features, "description": s.description,
                "category": s.category, "disabled": s.disabled,
                "epg_url": s.epg_url, "logo_base_url": s.logo_base_url,
                "update_frequency": s.update_frequency, "quality_rating": s.quality_rating,
                "channel_count": s.channel_count,
                "isp_compatible": s.is_isp_compatible(state.local_isp),
                "has_epg": s.has_epg, "has_logo_support": s.has_logo_support,
            }
            for s in state.online_sources if not s.disabled
        ],
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
    return {
        "version": APP_VERSION,
        "title": APP_TITLE,
        "local_isp": state.local_isp,
        "is_checking": state.is_checking,
        "online_sources_count": len(state.online_sources),
    }
