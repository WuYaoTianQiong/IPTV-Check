"""
Enhanced Event Bus Implementation
Provides pub/sub pattern for decoupled communication between modules.
"""

import logging
from typing import Callable, Optional
from blinker import Namespace

logger = logging.getLogger(__name__)

# ============================================================
# 职责说明：EventBus 是进程内 blinker 发布/订阅总线，用于模块间解耦与实时推送
# （如 ISP 检测结果推送、源下载状态通知）。事件名使用冒号风格（如 "check:started"），
# 请统一使用下方 Events 常量，不要手写字符串。
# 注意：domain/events.py 的 DomainEvents/DomainEvent 是事件溯源持久化模型
# （写入 EventStore 事件表），与 EventBus 职责不同、事件名格式不同（下划线风格），请勿混用。
# ============================================================

_events = Namespace()


class EventBus:
    """
    Central event bus for managing application events.
    Provides type-safe event publishing and subscribing.
    """

    def __init__(self):
        self._events = _events

    def on(self, event_name: str) -> Callable:
        """
        Decorator to subscribe to an event.
        Usage:
            @event_bus.on('check:started')
            def handle_check_started(data):
                pass
        """
        signal = self._events.signal(event_name)
        return signal.connect

    def emit(self, event_name: str, **kwargs) -> None:
        """
        Publish an event with data.
        Usage:
            event_bus.emit('check:started', total=100)
        """
        signal = self._events.signal(event_name)
        logger.debug("Event emitted: %s", event_name)
        signal.send(self, **kwargs)

    def connect(self, event_name: str, handler: Callable) -> None:
        """
        Subscribe to an event with a handler function.
        Usage:
            event_bus.connect('check:started', handle_check_started)
        """
        signal = self._events.signal(event_name)
        signal.connect(handler)
        logger.debug("Handler connected to: %s", event_name)

    def disconnect(self, event_name: str, handler: Callable) -> None:
        """Unsubscribe a handler from an event."""
        signal = self._events.signal(event_name)
        signal.disconnect(handler)
        logger.debug("Handler disconnected from: %s", event_name)


# Predefined event names for type safety
class Events:
    """
    Constants for all application events.
    Prevents typos and provides autocomplete.
    """
    # Check events
    CHECK_STARTED = "check:started"
    CHECK_PROGRESS = "check:progress"
    CHECK_COMPLETED = "check:completed"
    CHECK_STOPPED = "check:stopped"
    CHECK_ERROR = "check:error"
    CHANNEL_CHECKED = "channel:checked"
    CHANNEL_LOADED = "channel:loaded"

    # Source events
    SOURCE_DOWNLOADED = "source:downloaded"
    SOURCE_DOWNLOAD_ERROR = "source:download_error"
    SOURCE_UPDATED = "source:updated"
    SOURCE_SYNC_COMPLETED = "source:sync_completed"
    SOURCE_SYNC_ERROR = "source:sync_error"

    # EPG events
    EPG_UPDATED = "epg:updated"
    EPG_ERROR = "epg:error"

    # Logo events
    LOGO_DOWNLOADED = "logo:downloaded"
    LOGO_ERROR = "logo:error"

    # ISP events
    ISP_DETECTED = "isp:detected"
    ISP_MISMATCH = "isp:mismatch"

    # Export events
    EXPORT_COMPLETED = "export:completed"
    EXPORT_ERROR = "export:error"

    # M3U service events
    M3U_SERVER_STARTED = "m3u:server_started"
    M3U_SERVER_STOPPED = "m3u:server_stopped"

    # UI events
    THEME_CHANGED = "theme:changed"
    STATUS_MESSAGE = "status:message"


# Global event bus instance
event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    return event_bus
