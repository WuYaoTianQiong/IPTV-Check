"""
定时检测任务调度器

基于 apscheduler.AsyncIOScheduler 实现（替代此前每任务 while+sleep 轮询）：
- 使用 interval 触发器，由 apscheduler 内部高效调度，无空转轮询；
- 支持暂停/恢复/移除；任务执行失败按 interval 自然重试。
"""
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from datetime import timedelta
from enum import Enum

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from iptv_check.infra.cn_time import cn_now

logger = logging.getLogger(__name__)


class ScheduleStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ScheduledTask:
    """apscheduler 作业的薄封装：维护前端依赖的状态/运行计数。"""

    def __init__(self, task_id: str, name: str, interval_seconds: int, callback: Callable):
        self.task_id = task_id
        self.name = name
        self.interval_seconds = interval_seconds
        self.callback = callback
        self.status = ScheduleStatus.PENDING
        self.last_run: Optional[Any] = None
        self.next_run: Optional[Any] = None
        self.run_count = 0
        self.error_count = 0
        self._job = None

    async def _run(self):
        """apscheduler 回调：包装执行并维护状态/计数。"""
        self.status = ScheduleStatus.RUNNING
        self.last_run = cn_now()
        self.run_count += 1
        try:
            await self.callback()
            self.status = ScheduleStatus.PENDING
            logger.info("定时任务 [%s] 执行成功, 运行次数: %d", self.name, self.run_count)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.error_count += 1
            self.status = ScheduleStatus.FAILED
            logger.error("定时任务 [%s] 执行失败: %s", self.name, e)
        finally:
            # 前端展示的下次执行时间（真实调度由 apscheduler 计算）
            self.next_run = cn_now() + timedelta(seconds=self.interval_seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "status": self.status.value,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
        }


class TaskScheduler:
    """基于 apscheduler 的定时任务调度器。"""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._tasks: Dict[str, ScheduledTask] = {}

    def _ensure_running(self):
        if not self._scheduler.running:
            self._scheduler.start()

    def add_task(self, task_id: str, name: str, interval_seconds: int, callback: Callable) -> ScheduledTask:
        self._ensure_running()
        if task_id in self._tasks:
            self.remove_task(task_id)
        task = ScheduledTask(task_id, name, interval_seconds, callback)
        job = self._scheduler.add_job(
            task._run,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=task_id,
            name=name,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        task._job = job
        self._tasks[task_id] = task
        return task

    def remove_task(self, task_id: str):
        task = self._tasks.pop(task_id, None)
        if task:
            try:
                self._scheduler.remove_job(task_id)
            except Exception as e:
                logger.debug("移除定时任务 [%s] 失败: %s", task_id, e)
            task.status = ScheduleStatus.COMPLETED

    def pause_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if task:
            self._scheduler.pause_job(task_id)
            task.status = ScheduleStatus.PAUSED

    def resume_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if task:
            self._scheduler.resume_job(task_id)
            task.status = ScheduleStatus.PENDING
            task.next_run = cn_now()

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, Dict]:
        return {tid: task.to_dict() for tid, task in self._tasks.items()}

    async def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._tasks.clear()
        logger.info("所有定时任务已停止")
