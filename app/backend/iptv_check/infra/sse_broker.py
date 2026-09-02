"""
SSE (Server-Sent Events) Broker with backpressure management
Provides reliable event broadcasting with subscriber lifecycle management.
"""
import asyncio
import logging
import time
from typing import Dict, Optional
from dataclasses import field

logger = logging.getLogger(__name__)


class SSESubscriber:
    """Represents a single SSE subscriber with backpressure handling"""
    
    def __init__(self, subscriber_id: str, max_queue_size: int = 100):
        self.subscriber_id = subscriber_id
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.created_at = time.time()
        self.last_activity = time.time()
        self.messages_sent = 0
        self.messages_dropped = 0
    
    async def put(self, message: str, timeout: float = 0.1) -> bool:
        """Put message to queue with backpressure handling"""
        try:
            await asyncio.wait_for(self.queue.put(message), timeout=timeout)
            self.last_activity = time.time()
            self.messages_sent += 1
            return True
        except asyncio.TimeoutError:
            self.messages_dropped += 1
            # 队列满属于正常背压（事件密度高于前端消费速度时必然发生），
            # 降为 debug 避免刷屏；前端会收到 queue_overflow 事件自行修正
            logger.debug(
                "SSE subscriber %s queue full, message dropped (sent=%d, dropped=%d)",
                self.subscriber_id,
                self.messages_sent,
                self.messages_dropped,
            )
            return False
    
    async def get(self, timeout: float = 30.0) -> Optional[str]:
        """Get message from queue with timeout"""
        try:
            message = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            self.last_activity = time.time()
            return message
        except asyncio.TimeoutError:
            return None
    
    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if subscriber is stale (no activity for too long)"""
        return (time.time() - self.last_activity) > timeout_seconds
    
    def queue_size(self) -> int:
        """Current queue size"""
        return self.queue.qsize()
    
    def stats(self) -> dict:
        """Get subscriber statistics"""
        return {
            "subscriber_id": self.subscriber_id,
            "queue_size": self.queue_size(),
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
            "age_seconds": round(time.time() - self.created_at, 1),
            "last_activity_seconds_ago": round(time.time() - self.last_activity, 1),
        }


class SSEBroker:
    """
    SSE Broker with backpressure and subscriber lifecycle management
    
    Features:
    - Maximum subscriber limit
    - Per-subscriber queue with backpressure
    - Automatic stale subscriber cleanup
    - Broadcast with drop statistics
    """
    
    def __init__(
        self,
        max_subscribers: int = 50,
        max_queue_size: int = 100,
        stale_timeout: int = 300,
    ):
        self.max_subscribers = max_subscribers
        self.max_queue_size = max_queue_size
        self.stale_timeout = stale_timeout
        
        self._subscribers: Dict[str, SSESubscriber] = {}
        self._counter = 0
        self._lock = asyncio.Lock()
        
        logger.info(
            "SSE Broker initialized (max_subscribers=%d, max_queue_size=%d)",
            max_subscribers,
            max_queue_size,
        )
    
    async def subscribe(self) -> SSESubscriber:
        """Subscribe to SSE events"""
        async with self._lock:
            if len(self._subscribers) >= self.max_subscribers:
                self._cleanup_stale()
            
            if len(self._subscribers) >= self.max_subscribers:
                logger.warning(
                    "SSE subscriber limit reached (%d), rejecting new subscriber",
                    self.max_subscribers,
                )
                raise RuntimeError(f"Subscriber limit reached ({self.max_subscribers})")
            
            self._counter += 1
            subscriber_id = f"sub_{self._counter}_{int(time.time())}"
            subscriber = SSESubscriber(subscriber_id, self.max_queue_size)
            self._subscribers[subscriber_id] = subscriber
            
            logger.info(
                "New SSE subscriber: %s (total: %d)",
                subscriber_id,
                len(self._subscribers),
            )
            return subscriber
    
    async def unsubscribe(self, subscriber: SSESubscriber):
        """Unsubscribe from SSE events"""
        async with self._lock:
            if subscriber.subscriber_id in self._subscribers:
                del self._subscribers[subscriber.subscriber_id]
                logger.info(
                    "SSE subscriber unsubscribed: %s (total: %d)",
                    subscriber.subscriber_id,
                    len(self._subscribers),
                )
    
    @staticmethod
    def _format_sse(event: str, message: dict) -> str:
        """按 SSE 规范序列化帧：data 含换行时拆为多行 `data:` 前缀。"""
        import json
        counter = message.get("id", "")
        data_lines = json.dumps(message, ensure_ascii=False).splitlines() or [""]
        data_block = "\n".join(f"data: {line}" for line in data_lines)
        return f"id: {counter}\nevent: {event}\n{data_block}\n\n"

    async def broadcast(self, event: str, data: dict):
        """Broadcast event to all subscribers with backpressure handling"""
        self._counter += 1
        message = {
            "id": self._counter,
            "event": event,
            **data,
        }
        sse_message = self._format_sse(event, message)
        
        dead_subscribers = []
        overflow_subscribers = []
        
        async with self._lock:
            subs = list(self._subscribers.items())
        
        logger.debug("[SSE-BROKER] broadcast event=%s subscribers=%d", event, len(subs))
        
        for sub_id, subscriber in subs:
            try:
                success = await subscriber.put(sse_message)
                if success:
                    logger.debug("[SSE-BROKER] message sent to %s", sub_id)
                else:
                    # 已通过 queue_overflow 事件通知前端，不再逐条打 warning
                    logger.debug("[SSE-BROKER] message dropped for %s (queue full)", sub_id)
                    overflow_subscribers.append(subscriber)
                    if subscriber.is_stale(self.stale_timeout):
                        dead_subscribers.append(sub_id)
            except Exception as e:
                logger.error("[SSE-BROKER] broadcast error for %s: %s", sub_id, e)
        
        if overflow_subscribers:
            self._counter += 1
            overflow_msg = {
                "id": self._counter,
                "event": "queue_overflow",
                "message": "部分实时更新因处理速度不足被跳过，数据将在下次轮询时自动修正",
            }
            overflow_sse = self._format_sse("queue_overflow", overflow_msg)
            for subscriber in overflow_subscribers:
                try:
                    await subscriber.put(overflow_sse)
                except Exception:
                    pass
        
        for sub_id in dead_subscribers:
            await self._remove_subscriber(sub_id)
    
    async def broadcast_raw(self, raw_message: str):
        """Broadcast pre-formatted SSE message"""
        dead_subscribers = []
        
        async with self._lock:
            subs = list(self._subscribers.items())
        
        for sub_id, subscriber in subs:
            try:
                success = await subscriber.put(raw_message)
                if not success:
                    if subscriber.is_stale(self.stale_timeout):
                        dead_subscribers.append(sub_id)
            except Exception as e:
                logger.error("[SSE-BROKER] broadcast_raw 投递异常 %s: %s", sub_id, e)
        
        for sub_id in dead_subscribers:
            await self._remove_subscriber(sub_id)
    
    def _cleanup_stale(self):
        """Remove stale subscribers"""
        stale_ids = [
            sub_id for sub_id, sub in self._subscribers.items()
            if sub.is_stale(self.stale_timeout)
        ]
        for sub_id in stale_ids:
            logger.info("Removing stale SSE subscriber: %s", sub_id)
            del self._subscribers[sub_id]
    
    async def _remove_subscriber(self, sub_id: str):
        """Remove a subscriber"""
        async with self._lock:
            if sub_id in self._subscribers:
                del self._subscribers[sub_id]
    
    def get_stats(self) -> dict:
        """Get broker statistics"""
        return {
            "total_subscribers": len(self._subscribers),
            "max_subscribers": self.max_subscribers,
            "max_queue_size": self.max_queue_size,
            "subscribers": [sub.stats() for sub in self._subscribers.values()],
        }
