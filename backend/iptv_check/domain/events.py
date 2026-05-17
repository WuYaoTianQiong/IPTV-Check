from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from iptv_check.infra.cn_time import cn_now


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: cn_now().timestamp())
    session_id: str = ""


class DomainEvents:
    CHECK_STARTED = "check_started"
    CHECK_COMPLETED = "check_completed"
    CHECK_STOPPED = "check_stopped"
    CHECK_FAILED = "check_failed"

    CHANNEL_SUBMITTED = "channel_submitted"
    CHANNEL_CHECKED = "channel_checked"
    CHANNEL_RECHECKED = "channel_rechecked"

    SOURCE_DOWNLOADED = "source_downloaded"
    SOURCE_DOWNLOAD_FAILED = "source_download_failed"

    CHANNELS_LOADED = "channels_loaded"

    @staticmethod
    def check_started(session_id: str, **kwargs) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHECK_STARTED,
            payload={"session_id": session_id, **kwargs},
            session_id=session_id,
        )

    @staticmethod
    def check_completed(session_id: str, total: int, valid: int, invalid: int) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHECK_COMPLETED,
            payload={"total": total, "valid": valid, "invalid": invalid},
            session_id=session_id,
        )

    @staticmethod
    def check_stopped(session_id: str) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHECK_STOPPED,
            payload={},
            session_id=session_id,
        )

    @staticmethod
    def check_failed(session_id: str, reason: str) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHECK_FAILED,
            payload={"reason": reason},
            session_id=session_id,
        )

    @staticmethod
    def channel_submitted(session_id: str, url_key: str, name: str, url: str, group: str = "") -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHANNEL_SUBMITTED,
            payload={"url_key": url_key, "name": name, "url": url, "group": group},
            session_id=session_id,
        )

    @staticmethod
    def channel_checked(
        session_id: str,
        url_key: str,
        name: str,
        url: str,
        is_valid: bool,
        latency: Any = -1,
        speed: str = "-",
        details: str = "",
        group: str = "",
        sources: str = "",
    ) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHANNEL_CHECKED,
            payload={
                "url_key": url_key,
                "name": name,
                "url": url,
                "is_valid": is_valid,
                "latency": latency,
                "speed": speed,
                "details": details,
                "group": group,
                "sources": sources,
            },
            session_id=session_id,
        )

    @staticmethod
    def source_downloaded(session_id: str, source_name: str, channel_count: int, success: bool = True) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.SOURCE_DOWNLOADED,
            payload={"source_name": source_name, "channel_count": channel_count, "success": success},
            session_id=session_id,
        )

    @staticmethod
    def source_download_failed(session_id: str, source_name: str, error: str) -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.SOURCE_DOWNLOAD_FAILED,
            payload={"source_name": source_name, "error": error},
            session_id=session_id,
        )

    @staticmethod
    def channels_loaded(session_id: str, total: int, source_name: str = "") -> DomainEvent:
        return DomainEvent(
            event_type=DomainEvents.CHANNELS_LOADED,
            payload={"total": total, "source_name": source_name},
            session_id=session_id,
        )
