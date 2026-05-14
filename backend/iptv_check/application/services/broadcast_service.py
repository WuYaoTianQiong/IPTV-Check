import logging
import threading
from typing import List, Optional

from fastapi import WebSocket
from iptv_check.application.services.base import BaseService

logger = logging.getLogger(__name__)


class BroadcastService(BaseService):
    def __init__(self):
        super().__init__(name="BroadcastService")
        self._ws_clients: List[WebSocket] = []
        self._ws_lock = threading.Lock()
        self._event_queue: Optional[object] = None
        self._broadcast_task: Optional[object] = None

    async def _do_initialize(self) -> None:
        import asyncio
        self._event_queue = asyncio.Queue()
        self._broadcast_task = asyncio.create_task(self._broadcast_worker())

    async def _do_shutdown(self) -> None:
        if self._broadcast_task:
            await self._event_queue.put(None)
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except Exception:
                pass

    async def broadcast(self, event: str, data: dict) -> None:
        if self._event_queue:
            await self._event_queue.put({"event": event, **data})

    async def _broadcast_worker(self) -> None:
        import asyncio
        while True:
            msg = await self._event_queue.get()
            if msg is None:
                break
            dead = []
            with self._ws_lock:
                clients = list(self._ws_clients)
            for ws in clients:
                try:
                    await ws.send_json(msg)
                except Exception:
                    dead.append(ws)
            if dead:
                with self._ws_lock:
                    for ws in dead:
                        if ws in self._ws_clients:
                            self._ws_clients.remove(ws)

    def register_ws(self, ws: WebSocket) -> None:
        with self._ws_lock:
            self._ws_clients.append(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        with self._ws_lock:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)

    @property
    def client_count(self) -> int:
        with self._ws_lock:
            return len(self._ws_clients)
