import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/epg", tags=["epg"])


class EpgRefreshRequest(BaseModel):
    source_id: str = ""


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.get("/channel/{channel_name}")
async def get_channel_epg(channel_name: str, tvg_id: str = "", tvg_name: str = "", source_id: str = ""):
    state = _get_state()
    if not state._epg_service:
        raise HTTPException(503, "EPG服务未初始化")
    epg_channel = state._epg_service.get_channel_epg(source_id, channel_name, tvg_id, tvg_name)
    if not epg_channel:
        return {"channel_name": channel_name, "epg": None}
    return {"channel_name": channel_name, "epg": epg_channel.to_dict()}


@router.get("/search")
async def search_epg(channel_name: str, tvg_id: str = "", tvg_name: str = ""):
    state = _get_state()
    if not state._epg_service:
        raise HTTPException(503, "EPG服务未初始化")
    epg_channel = state._epg_service.get_channel_epg("", channel_name, tvg_id, tvg_name)
    if not epg_channel:
        return {"channel_name": channel_name, "epg": None, "matched_source_id": ""}
    return {"channel_name": channel_name, "epg": epg_channel.to_dict(), "matched_source_id": ""}


@router.get("/now")
async def get_current_programs(source_id: str = ""):
    state = _get_state()
    if not state._epg_service:
        raise HTTPException(503, "EPG服务未初始化")
    return {"current": state._epg_service.get_current_programs(source_id)}


@router.post("/refresh")
async def refresh_epg(req: EpgRefreshRequest):
    state = _get_state()
    if not state._epg_service:
        raise HTTPException(503, "EPG服务未初始化")
    source = None
    for s in state.online_sources:
        if s.id == req.source_id:
            source = s
            break
    if not source or not source.has_epg:
        raise HTTPException(400, f"源 {req.source_id} 不支持EPG")
    success = await state._epg_service.refresh_epg(source)
    return {"success": success, "source_id": req.source_id}


@router.get("/stats")
async def get_epg_stats():
    state = _get_state()
    if not state._epg_service:
        return {"loaded_sources": 0, "total_channels": 0, "total_programs": 0, "is_loading": False}
    return state._epg_service.get_stats()


@router.post("/load")
async def load_all_epg():
    state = _get_state()
    if not state._epg_service:
        raise HTTPException(503, "EPG服务未初始化")
    asyncio = __import__("asyncio")
    asyncio.create_task(state._epg_service.load_epg_for_sources(state.online_sources))
    return {"status": "started"}
