import asyncio
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["fetch"])


class FetchRequest(BaseModel):
    online_source_ids: List[str] = []
    use_cache: bool = True
    min_valid_rate: float = 0


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.post("/fetch/start")
async def start_fetch(req: FetchRequest):
    state = _get_state()
    fetch_svc = state._fetch_service
    if not fetch_svc:
        raise HTTPException(500, "拉取服务未初始化")
    if fetch_svc.is_fetching:
        raise HTTPException(400, "拉取正在进行中")
    if state._check_service and state._check_service.is_running:
        raise HTTPException(400, "检测正在进行中，请先停止检测")

    try:
        await fetch_svc.start_fetch(req.online_source_ids, use_cache=req.use_cache, min_valid_rate=req.min_valid_rate)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"status": "completed", "fetched_channels": fetch_svc._fetched_count}


@router.get("/fetch/progress")
async def get_fetch_progress():
    state = _get_state()
    fetch_svc = state._fetch_service
    if not fetch_svc:
        return {"is_fetching": False, "total_sources": 0, "done_sources": 0, "fetched_channels": 0}
    return fetch_svc.fetch_progress


@router.get("/fetch/channels")
async def get_fetched_channels():
    state = _get_state()
    fetch_svc = state._fetch_service
    if not fetch_svc:
        return {"channels": [], "count": 0}
    # get_fetched_channels 会对每条频道做名称翻译（拼音/城市/正则），
    # 全量执行可阻塞事件循环达 20s+；丢到线程池执行并只翻译前 200 条
    channels = await asyncio.to_thread(fetch_svc.get_fetched_channels, None, 200)
    return {
        "count": len(channels),
        "channels": [
            {"name": ch.name, "url": ch.url, "group": ch.group, "url_key": ch.url_key}
            for ch in channels
        ],
    }


@router.delete("/fetch/channels")
async def clear_fetched_channels():
    state = _get_state()
    fetch_svc = state._fetch_service
    if not fetch_svc:
        raise HTTPException(500, "拉取服务未初始化")
    if fetch_svc.is_fetching:
        raise HTTPException(400, "拉取正在进行中")
    fetch_svc.clear_fetched_channels()
    return {"status": "cleared"}
