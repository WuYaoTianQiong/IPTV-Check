"""
定时检测任务调度器
使用 asyncio 实现，无需额外依赖
"""
import logging
import asyncio
import time
from typing import Optional, Callable, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from iptv_check.infra.cn_time import cn_now

logger = logging.getLogger(__name__)


class ScheduleStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ScheduledTask:
    def __init__(self, task_id: str, name: str, interval_seconds: int, callback: Callable):
        self.task_id = task_id
        self.name = name
        self.interval_seconds = interval_seconds
        self.callback = callback
        self.status = ScheduleStatus.PENDING
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count = 0
        self.error_count = 0
        self._task: Optional[asyncio.Task] = None

    def start(self):
        self.status = ScheduleStatus.PENDING
        self.next_run = cn_now()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("定时任务 [%s] 已启动, 间隔: %ds", self.name, self.interval_seconds)

    async def _run_loop(self):
        while True:
            if self.status == ScheduleStatus.PAUSED:
                await asyncio.sleep(1)
                continue
            
            if self.status == ScheduleStatus.COMPLETED or self.status == ScheduleStatus.FAILED:
                break

            if self.next_run and cn_now() < self.next_run:
                await asyncio.sleep(1)
                continue

            self.status = ScheduleStatus.RUNNING
            self.last_run = cn_now()
            self.run_count += 1
            
            try:
                await self.callback()
                self.status = ScheduleStatus.PENDING
                self.next_run = cn_now() + timedelta(seconds=self.interval_seconds)
                logger.info("定时任务 [%s] 执行成功, 运行次数: %d", self.name, self.run_count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error_count += 1
                self.status = ScheduleStatus.FAILED
                logger.error("定时任务 [%s] 执行失败: %s", self.name, e)
                await asyncio.sleep(min(self.interval_seconds / 2, 60))
                if self.status == ScheduleStatus.FAILED:
                    self.status = ScheduleStatus.PENDING
                    self.next_run = cn_now() + timedelta(seconds=self.interval_seconds)

    def pause(self):
        if self.status == ScheduleStatus.RUNNING:
            self.status = ScheduleStatus.PAUSED
        else:
            self.status = ScheduleStatus.PAUSED
        logger.info("定时任务 [%s] 已暂停", self.name)

    def resume(self):
        if self.status == ScheduleStatus.PAUSED:
            self.status = ScheduleStatus.PENDING
            self.next_run = cn_now()
        logger.info("定时任务 [%s] 已恢复", self.name)

    def stop(self):
        self.status = ScheduleStatus.COMPLETED
        if self._task:
            self._task.cancel()
        logger.info("定时任务 [%s] 已停止", self.name)

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
    """定时任务调度器"""

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}

    def add_task(self, task_id: str, name: str, interval_seconds: int, callback: Callable) -> ScheduledTask:
        if task_id in self._tasks:
            self.remove_task(task_id)
        task = ScheduledTask(task_id, name, interval_seconds, callback)
        self._tasks[task_id] = task
        task.start()
        return task

    def remove_task(self, task_id: str):
        task = self._tasks.pop(task_id, None)
        if task:
            task.stop()

    def pause_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if task:
            task.pause()

    def resume_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if task:
            task.resume()

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, Dict]:
        return {tid: task.to_dict() for tid, task in self._tasks.items()}

    async def shutdown(self):
        for task in self._tasks.values():
            task.stop()
        self._tasks.clear()
        logger.info("所有定时任务已停止")
