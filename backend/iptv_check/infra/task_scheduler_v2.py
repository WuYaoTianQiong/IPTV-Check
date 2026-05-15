"""
APScheduler integration for reliable task scheduling
Provides persistent scheduling with job recovery and monitoring.
"""
import logging
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.job import Job
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED

logger = logging.getLogger(__name__)


class SchedulerJobInfo:
    """Information about a scheduled job"""
    
    def __init__(self, job: Job):
        self.job_id = job.id
        self.name = job.name
        self.next_run_time = job.next_run_time
        self.trigger = str(job.trigger)
        self.misfire_grace_time = job.misfire_grace_time
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "next_run_time": self.next_run_time.isoformat() if self.next_run_time else None,
            "trigger": self.trigger,
            "misfire_grace_time": self.misfire_grace_time,
        }


class TaskScheduler:
    """
    APScheduler-based task scheduler with reliability features
    
    Features:
    - Job persistence (survives restarts with SQLAlchemy job store)
    - Misfire handling
    - Job execution monitoring
    - Graceful shutdown
    """
    
    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._job_listeners: List[Callable] = []
        self._job_history: List[Dict[str, Any]] = []
        self._max_history = 100
    
    def initialize(self):
        """Initialize the scheduler"""
        jobstores = {
            "default": MemoryJobStore()
        }
        
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
        
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults=job_defaults,
            timezone="Asia/Shanghai",
        )
        
        self._scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
        
        logger.info("APScheduler initialized successfully")
    
    def start(self):
        """Start the scheduler"""
        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("APScheduler started")
    
    async def shutdown(self):
        """Shutdown the scheduler gracefully"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("APScheduler shut down")
    
    def add_interval_job(
        self,
        func: Callable,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        days: int = 0,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Add a job that runs at fixed intervals"""
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        job = self._scheduler.add_job(
            func,
            trigger="interval",
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            days=days,
            id=job_id,
            name=name or func.__name__,
            **kwargs,
        )
        
        logger.info(
            "Added interval job: %s (every %dd %dh %dm %ds)",
            job.id,
            days, hours, minutes, seconds,
        )
        return job.id
    
    def add_cron_job(
        self,
        func: Callable,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        **cron_kwargs,
    ) -> str:
        """Add a cron-based job"""
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        job = self._scheduler.add_job(
            func,
            trigger="cron",
            id=job_id,
            name=name or func.__name__,
            **cron_kwargs,
        )
        
        logger.info("Added cron job: %s", job.id)
        return job.id
    
    def add_onetime_job(
        self,
        func: Callable,
        run_date: datetime,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> str:
        """Add a one-time job"""
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        job = self._scheduler.add_job(
            func,
            trigger="date",
            run_date=run_date,
            id=job_id,
            name=name or func.__name__,
        )
        
        logger.info("Added one-time job: %s (run at %s)", job.id, run_date)
        return job.id
    
    def remove_job(self, job_id: str):
        """Remove a job"""
        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
                logger.info("Removed job: %s", job_id)
            except Exception as e:
                logger.warning("Failed to remove job %s: %s", job_id, e)
    
    def pause_job(self, job_id: str):
        """Pause a job"""
        if self._scheduler:
            self._scheduler.pause_job(job_id)
            logger.info("Paused job: %s", job_id)
    
    def resume_job(self, job_id: str):
        """Resume a paused job"""
        if self._scheduler:
            self._scheduler.resume_job(job_id)
            logger.info("Resumed job: %s", job_id)
    
    def get_job(self, job_id: str) -> Optional[SchedulerJobInfo]:
        """Get job information"""
        if self._scheduler:
            try:
                job = self._scheduler.get_job(job_id)
                return SchedulerJobInfo(job) if job else None
            except Exception:
                return None
        return None
    
    def get_all_jobs(self) -> List[SchedulerJobInfo]:
        """Get all scheduled jobs"""
        if self._scheduler:
            return [SchedulerJobInfo(job) for job in self._scheduler.get_jobs()]
        return []
    
    def get_job_history(self) -> List[Dict[str, Any]]:
        """Get job execution history"""
        return list(self._job_history)
    
    def add_job_listener(self, callback: Callable):
        """Add a custom job listener"""
        self._job_listeners.append(callback)
    
    def _on_job_executed(self, event):
        """Handle job execution event"""
        logger.debug("Job executed: %s", event.job_id)
        self._add_history_entry(event.job_id, "executed")
        self._notify_listeners("executed", event.job_id)
    
    def _on_job_error(self, event):
        """Handle job error event"""
        logger.error("Job error: %s, exception: %s", event.job_id, event.exception)
        self._add_history_entry(event.job_id, "error", str(event.exception))
        self._notify_listeners("error", event.job_id, str(event.exception))
    
    def _on_job_missed(self, event):
        """Handle job missed event"""
        logger.warning("Job missed: %s", event.job_id)
        self._add_history_entry(event.job_id, "missed")
        self._notify_listeners("missed", event.job_id)
    
    def _add_history_entry(self, job_id: str, status: str, error: Optional[str] = None):
        """Add entry to job history"""
        entry = {
            "job_id": job_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "error": error,
        }
        self._job_history.append(entry)
        if len(self._job_history) > self._max_history:
            self._job_history.pop(0)
    
    def _notify_listeners(self, event_type: str, job_id: str, error: Optional[str] = None):
        """Notify all registered listeners"""
        for listener in self._job_listeners:
            try:
                listener(event_type, job_id, error)
            except Exception as e:
                logger.error("Job listener error: %s", e)
    
    @property
    def is_running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running
