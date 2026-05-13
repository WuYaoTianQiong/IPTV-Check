import threading
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CheckState:
    """线程安全的检测状态容器"""
    is_running: bool = False
    total_count: int = 0
    checked_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    started_at: Optional[datetime] = None
    task_id: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_running": self.is_running,
                "total_count": self.total_count,
                "checked_count": self.checked_count,
                "valid_count": self.valid_count,
                "invalid_count": self.invalid_count,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "task_id": self.task_id,
            }


@dataclass
class ServiceState:
    """服务级全局状态，线程安全"""
    is_checking: bool = False
    local_isp: str = "未知"
    use_media_probe: bool = False
    ffmpeg_available: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_checking": self.is_checking,
                "local_isp": self.local_isp,
                "use_media_probe": self.use_media_probe,
                "ffmpeg_available": self.ffmpeg_available,
            }


class WebSocketManager:
    """WebSocket 客户端管理器，线程安全"""

    def __init__(self):
        self._clients: List = []
        self._lock = threading.Lock()
        self._event_queue: Optional[asyncio.Queue] = None
        self._broadcast_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动广播工作协程"""
        self._event_queue = asyncio.Queue()
        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_worker())
        logger.info("WebSocketManager 已启动")

    async def stop(self):
        """停止广播并清理客户端"""
        self._running = False
        if self._event_queue:
            await self._event_queue.put(None)
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        with self._lock:
            self._clients.clear()
        logger.info("WebSocketManager 已停止")

    def register(self, ws):
        with self._lock:
            if ws not in self._clients:
                self._clients.append(ws)

    def unregister(self, ws):
        with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def broadcast(self, event: str, data: Dict[str, Any] = None):
        """将事件放入广播队列"""
        if self._event_queue and self._running:
            msg = {"event": event}
            if data:
                msg.update(data)
            await self._event_queue.put(msg)

    async def _broadcast_worker(self):
        """从队列取消息并广播给所有 WebSocket 客户端"""
        while True:
            msg = await self._event_queue.get()
            if msg is None:
                break

            dead = []
            with self._lock:
                clients = list(self._clients)

            for ws in clients:
                try:
                    await ws.send_json(msg)
                except Exception:
                    dead.append(ws)

            if dead:
                with self._lock:
                    for ws in dead:
                        if ws in self._clients:
                            self._clients.remove(ws)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)


class TaskTracker:
    """任务追踪器，用于追踪当前检测任务"""

    def __init__(self):
        self._current_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        self._task_id_counter = 0

    def set_task(self, task: asyncio.Task):
        with self._lock:
            self._current_task = task

    def cancel_current_task(self):
        with self._lock:
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()
                logger.info("已取消当前检测任务")

    def get_task(self) -> Optional[asyncio.Task]:
        with self._lock:
            return self._current_task

    def generate_task_id(self) -> str:
        with self._lock:
            self._task_id_counter += 1
            return f"task_{self._task_id_counter}_{int(datetime.utcnow().timestamp())}"
