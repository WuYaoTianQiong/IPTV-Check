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


class CheckFromFetchedRequest(BaseModel):
    timeout_connect: int = 5
    timeout_read: int = 15
    max_threads: int = 80
    run_speed_test: bool = False
    use_cache: bool = True
    max_latency_ms: int = 10000
    enable_recheck: bool = False


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
    channels = fetch_svc.get_fetched_channels()
    return {
        "count": len(channels),
        "channels": [
            {"name": ch.name, "url": ch.url, "group": ch.group, "url_key": ch.url_key}
            for ch in channels[:200]
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


@router.post("/check/from-fetched")
async def check_from_fetched(req: CheckFromFetchedRequest):
    state = _get_state()
    fetch_svc = state._fetch_service
    check_svc = state._check_service
    if not fetch_svc or not check_svc:
        raise HTTPException(500, "服务未初始化")
    if check_svc.is_running:
        raise HTTPException(400, "检测正在进行中")
    if not fetch_svc.has_fetched_channels():
        raise HTTPException(400, "没有已拉取的频道数据，请先执行拉取")

    channels = fetch_svc.get_fetched_channels()
    if not channels:
        raise HTTPException(400, "已拉取的频道列表为空")

    from iptv_check.models.settings import CheckConfig
    config = CheckConfig(
        timeout_connect=req.timeout_connect,
        timeout_read=req.timeout_read,
        max_threads=req.max_threads,
        run_speed_test=req.run_speed_test,
        use_cache=req.use_cache,
        max_latency_ms=req.max_latency_ms,
        enable_recheck=req.enable_recheck,
    )

    await check_svc.start_check_from_channels(channels, config)
    return {"status": "started", "session_id": check_svc.session_id, "channel_count": len(channels)}
