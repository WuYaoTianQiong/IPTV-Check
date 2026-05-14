import logging
from typing import List

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/logos", tags=["logos"])


class LogoBatchRequest(BaseModel):
    channels: List[dict] = []
    source_id: str = ""


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.get("/{channel_name}")
async def get_logo(channel_name: str, tvg_logo: str = "", source_id: str = ""):
    state = _get_state()
    if not state._logo_service:
        raise HTTPException(503, "台标服务未初始化")
    logo_data = await state._logo_service.get_logo(channel_name, tvg_logo, source_id)
    if not logo_data:
        raise HTTPException(404, "台标未找到")
    return Response(content=logo_data, media_type="image/png")


@router.post("/download")
async def batch_download_logos(req: LogoBatchRequest):
    state = _get_state()
    if not state._logo_service:
        raise HTTPException(503, "台标服务未初始化")
    if not req.channels:
        raise HTTPException(400, "频道列表为空")
    results = await state._logo_service.batch_download_logos(req.channels, req.source_id)
    success = sum(1 for v in results.values() if v)
    return {"total": len(results), "success": success, "failed": len(results) - success}


@router.get("/stats")
async def get_logo_stats():
    state = _get_state()
    if not state._logo_service:
        return {"enabled": False}
    return state._logo_service.get_stats()


@router.post("/cleanup")
async def cleanup_stale_logos(max_age_days: int = 30):
    state = _get_state()
    if not state._logo_service:
        raise HTTPException(503, "台标服务未初始化")
    removed = state._logo_service._cache.cleanup_stale(max_age_days)
    return {"removed": removed}
