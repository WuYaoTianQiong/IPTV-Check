import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cache", tags=["cache"])


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.get("/stats")
async def get_cache_stats():
    state = _get_state()
    cache = state.cache
    detection_stats = cache.stats() if hasattr(cache, "stats") else {"count": 0}
    result = {"detection": detection_stats}
    if state._epg_service:
        result["epg"] = state._epg_service.get_stats().get("cache", {})
    if state._logo_service:
        result["logos"] = state._logo_service.get_stats()
    return result


@router.post("/clear")
async def clear_cache(namespace: str = ""):
    state = _get_state()
    cleared = []
    if namespace in ("", "detection"):
        state.cache.clear()
        cleared.append("detection")
    if namespace in ("", "epg") and state._epg_service:
        state._epg_service._cache.clear()
        cleared.append("epg")
    if namespace in ("", "logos") and state._logo_service:
        state._logo_service._cache.cleanup_stale(0)
        cleared.append("logos")
    return {"cleared": cleared}
