import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/source-sync", tags=["source-sync"])


class SyncTriggerRequest(BaseModel):
    remote_url: Optional[str] = None


class SyncSchedulerRequest(BaseModel):
    interval_hours: float = 6


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.post("/trigger")
async def trigger_sync(req: SyncTriggerRequest = SyncTriggerRequest()):
    state = _get_state()
    if not state._source_sync_service:
        raise HTTPException(500, "源同步服务未初始化")
    if state._source_sync_service.is_syncing:
        raise HTTPException(400, "源同步正在进行中")

    def on_sync_complete(result):
        if result.success:
            async def _reload_and_fetch():
                await state._load_online_sources_async()
                if state._fetch_service and state._fetch_service.is_fetching:
                    logger.info("拉取正在进行中，跳过自动拉取")
                    return
                all_source_ids = [s.id for s in state.online_sources]
                if all_source_ids:
                    try:
                        await state._fetch_service.start_fetch(all_source_ids, use_cache=True)
                    except Exception as e:
                        logger.warning("同步后自动拉取频道失败: %s", e)
            asyncio.create_task(_reload_and_fetch())

    started = state._source_sync_service.start_sync_async(remote_url=req.remote_url, on_complete=on_sync_complete)
    if not started:
        raise HTTPException(400, "源同步启动失败")
    return {"status": "started"}


@router.get("/progress")
async def get_sync_progress():
    state = _get_state()
    if not state._source_sync_service:
        return {"is_syncing": False, "stage": "", "current_url_index": 0, "total_urls": 0}
    return state._source_sync_service.get_progress()


@router.get("/status")
async def get_sync_status():
    state = _get_state()
    if not state._source_sync_service:
        return {"is_syncing": False, "local_sources_count": 0, "upstream_registry_count": 0, "last_sync": None}
    return state._source_sync_service.get_status()


@router.post("/scheduler/start")
async def start_sync_scheduler(req: SyncSchedulerRequest = SyncSchedulerRequest()):
    state = _get_state()
    if not state._source_sync_service:
        raise HTTPException(500, "源同步服务未初始化")
    if state._task_scheduler.get_task("source_sync"):
        raise HTTPException(400, "源同步定时任务已在运行")

    interval_seconds = int(req.interval_hours * 3600)

    async def run_sync():
        if state._source_sync_service:
            result = await state._source_sync_service.sync()
            if result.success:
                await state._load_online_sources_async()
                logger.info("定时源同步完成: 新增=%d, 更新=%d", result.added, result.updated)
                if state._fetch_service and not state._fetch_service.is_fetching:
                    all_source_ids = [s.id for s in state.online_sources]
                    if all_source_ids:
                        try:
                            await state._fetch_service.start_fetch(all_source_ids, use_cache=True)
                            logger.info("定时同步后自动拉取频道完成")
                        except Exception as e:
                            logger.warning("定时同步后自动拉取频道失败: %s", e)
            else:
                logger.warning("定时源同步失败: %s", result.errors)

    state._task_scheduler.add_task("source_sync", "源同步", interval_seconds, run_sync)
    return {"status": "started", "interval_hours": req.interval_hours}


@router.post("/scheduler/stop")
async def stop_sync_scheduler():
    state = _get_state()
    task = state._task_scheduler.get_task("source_sync")
    if not task:
        raise HTTPException(400, "源同步定时任务未运行")
    state._task_scheduler.remove_task("source_sync")
    return {"status": "stopped"}


@router.get("/scheduler/state")
async def get_sync_scheduler_state():
    state = _get_state()
    task = state._task_scheduler.get_task("source_sync")
    if not task:
        return {"running": False, "task": None}
    return {"running": True, "task": task.to_dict()}
