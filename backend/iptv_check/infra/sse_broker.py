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
    
    async def put(self, message: str, timeout: float = 1.0) -> bool:
        """Put message to queue with backpressure handling"""
        try:
            await asyncio.wait_for(self.queue.put(message), timeout=timeout)
            self.last_activity = time.time()
            self.messages_sent += 1
            return True
        except asyncio.TimeoutError:
            self.messages_dropped += 1
            logger.warning(
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
    
    async def broadcast(self, event: str, data: dict):
        """Broadcast event to all subscribers with backpressure handling"""
        import json
        
        self._counter += 1
        message = {
            "id": self._counter,
            "event": event,
            **data,
        }
        sse_message = f"id: {self._counter}\nevent: {event}\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
        
        dead_subscribers = []
        
        async with self._lock:
            for sub_id, subscriber in list(self._subscribers.items()):
                success = await subscriber.put(sse_message)
                if not success:
                    if subscriber.is_stale(self.stale_timeout):
                        dead_subscribers.append(sub_id)
        
        for sub_id in dead_subscribers:
            await self._remove_subscriber(sub_id)
    
    async def broadcast_raw(self, raw_message: str):
        """Broadcast pre-formatted SSE message"""
        dead_subscribers = []
        
        async with self._lock:
            for sub_id, subscriber in list(self._subscribers.items()):
                success = await subscriber.put(raw_message)
                if not success:
                    if subscriber.is_stale(self.stale_timeout):
                        dead_subscribers.append(sub_id)
        
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
