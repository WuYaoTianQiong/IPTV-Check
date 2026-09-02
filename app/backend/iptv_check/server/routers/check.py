import asyncio
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["check"])


class CheckRequest(BaseModel):
    file_paths: List[str] = []
    online_source_ids: List[str] = []
    custom_source_urls: List[str] = []
    timeout_connect: int = 5
    timeout_read: int = 8
    max_threads: int = 80
    check_mode: str = "standard"  # quick | standard | deep
    run_speed_test: bool = False
    use_cache: bool = True
    max_latency_ms: int = 10000
    enable_recheck: bool = False
    # 细筛场景：非空时跳过在线源下载/解析，直接从该历史会话的有效结果构建检测输入
    source_session_id: str = ""


class DetailCheckRequest(BaseModel):
    """基于历史会话的有效频道发起细筛检测（默认 DEEP 深度，含测速）。"""
    source_session_id: str
    check_mode: str = "deep"  # quick | standard | deep
    timeout_connect: int = 5
    timeout_read: int = 15
    max_threads: int = 80
    use_cache: bool = True
    max_latency_ms: int = 10000
    enable_recheck: bool = False


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


def _get_check_service():
    from iptv_check.server.app import app_state
    return app_state._check_service


@router.post("/check/start")
async def start_check(req: CheckRequest):
    state = _get_state()
    service = _get_check_service()
    if not service:
        raise HTTPException(500, "检测服务未初始化")
    if service.is_running:
        raise HTTPException(400, "检测正在进行中")

    try:
        await service.start_check(req)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"status": "started", "session_id": service.session_id}


@router.post("/check/detail")
async def start_detail_check(req: DetailCheckRequest):
    """基于历史会话的有效频道发起细筛检测。

    跳过在线源下载/解析，直接复用该会话物化结果中 is_valid=1 的 URL 集合
    作为输入，走完整检测引擎（支持 DEEP 测速），生成独立的新历史会话。
    """
    state = _get_state()
    service = _get_check_service()
    if not service:
        raise HTTPException(500, "检测服务未初始化")
    if service.is_running:
        raise HTTPException(400, "检测正在进行中")
    if not req.source_session_id:
        raise HTTPException(400, "缺少来源会话 source_session_id")

    def _has_data():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            return ResultsRepository(s).has_session_data(req.source_session_id)
    if not await asyncio.to_thread(_has_data):
        raise HTTPException(400, "来源会话没有可细筛的数据")

    check_req = CheckRequest(
        source_session_id=req.source_session_id,
        check_mode=req.check_mode,
        timeout_connect=req.timeout_connect,
        timeout_read=req.timeout_read,
        max_threads=req.max_threads,
        use_cache=req.use_cache,
        max_latency_ms=req.max_latency_ms,
        enable_recheck=req.enable_recheck,
        run_speed_test=(req.check_mode == "deep"),
    )
    try:
        await service.start_check(check_req)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"status": "started", "session_id": service.session_id, "source_session_id": req.source_session_id}


@router.post("/check/stop")
async def stop_check():
    service = _get_check_service()
    if not service or not service.is_running:
        raise HTTPException(400, "没有正在进行的检测")
    await service.stop_check()
    return {"status": "stopped"}


@router.get("/check/state")
async def get_check_state():
    service = _get_check_service()
    if not service:
        return {"phase": "idle", "metrics": {}}
    return service.get_full_state()


@router.get("/check/health")
async def get_source_health():
    state = _get_state()
    return state._health_checker.to_dict()


@router.get("/settings/media-probe")
async def get_media_probe_status():
    from iptv_check.infra.media_probe import MediaProbe
    state = _get_state()
    return {"enabled": state._use_media_probe, "ffmpeg_available": MediaProbe.is_ffmpeg_available()}


@router.post("/settings/media-probe")
async def set_media_probe(enabled: bool):
    state = _get_state()
    state._use_media_probe = enabled
    return {"enabled": state._use_media_probe}


@router.get("/settings/media-probe/status")
async def get_media_probe_full_status():
    state = _get_state()
    return {
        "enabled": state._use_media_probe,
        "ffmpeg_available": state._ffmpeg_available,
        "usable": state._use_media_probe and state._ffmpeg_available,
    }


@router.post("/scheduler/start")
async def start_scheduled_check(interval_hours: float = 24, file_paths: List[str] = [], online_source_ids: List[str] = []):
    state = _get_state()
    if state._task_scheduler.get_task("auto_check"):
        raise HTTPException(400, "定时检测已在运行")
    interval_seconds = int(interval_hours * 3600)

    async def run_auto_check():
        req = CheckRequest(
            file_paths=file_paths or state._scheduled_check_config.get("file_paths", []),
            online_source_ids=online_source_ids or state._scheduled_check_config.get("online_source_ids", []),
        )
        service = _get_check_service()
        if service:
            await service.start_check(req)

    state._scheduled_check_config = {"file_paths": file_paths, "online_source_ids": online_source_ids, "interval_hours": interval_hours}
    state._task_scheduler.add_task("auto_check", "自动检测", interval_seconds, run_auto_check)
    return {"status": "started", "interval_hours": interval_hours}


@router.post("/scheduler/stop")
async def stop_scheduled_check():
    state = _get_state()
    state._task_scheduler.remove_task("auto_check")
    return {"status": "stopped"}


@router.get("/scheduler/state")
async def get_scheduler_state():
    state = _get_state()
    return {"tasks": state._task_scheduler.get_all_tasks(), "config": state._scheduled_check_config}
