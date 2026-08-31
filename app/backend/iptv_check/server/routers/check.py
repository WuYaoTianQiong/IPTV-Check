import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["check"])


class CheckRequest(BaseModel):
    file_paths: List[str] = []
    online_source_ids: List[str] = []
    timeout_connect: int = 5
    timeout_read: int = 8
    max_threads: int = 120
    run_speed_test: bool = False
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
