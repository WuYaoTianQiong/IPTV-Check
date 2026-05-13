import logging
import time
from typing import List, Optional, Dict
from dataclasses import dataclass
from transitions import Machine

logger = logging.getLogger(__name__)


class CheckPhase:
    IDLE = "idle"
    INITIALIZING = "initializing"
    PARSING = "parsing"
    DOWNLOADING = "downloading"
    CHECKING = "checking"
    OPTIMIZING = "optimizing"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class CheckMetrics:
    total_count: int = 0
    checked_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    current_workers: int = 30
    consecutive_success: int = 0
    consecutive_fail: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        if self.start_time:
            return time.time() - self.start_time
        return 0.0

    @property
    def progress_percent(self) -> float:
        if self.total_count == 0:
            return 0.0
        return (self.checked_count / self.total_count) * 100


class CheckStateMachine:
    states = [
        {"name": CheckPhase.IDLE, "on_enter": "_on_enter_idle"},
        {"name": CheckPhase.INITIALIZING, "on_enter": "_on_enter_initializing"},
        {"name": CheckPhase.PARSING, "on_enter": "_on_enter_parsing"},
        {"name": CheckPhase.DOWNLOADING, "on_enter": "_on_enter_downloading"},
        {"name": CheckPhase.CHECKING, "on_enter": "_on_enter_checking"},
        {"name": CheckPhase.OPTIMIZING, "on_enter": "_on_enter_optimizing"},
        {"name": CheckPhase.COMPLETED, "on_enter": "_on_enter_completed"},
        {"name": CheckPhase.STOPPED, "on_enter": "_on_enter_stopped"},
        {"name": CheckPhase.FAILED, "on_enter": "_on_enter_failed"},
    ]

    transitions = [
        {"trigger": "start", "source": CheckPhase.IDLE, "dest": CheckPhase.INITIALIZING},
        {"trigger": "initialized", "source": CheckPhase.INITIALIZING, "dest": CheckPhase.PARSING},
        {"trigger": "parsing_done", "source": CheckPhase.PARSING, "dest": CheckPhase.CHECKING},
        {"trigger": "download_done", "source": CheckPhase.DOWNLOADING, "dest": CheckPhase.CHECKING},
        {"trigger": "check_done", "source": CheckPhase.CHECKING, "dest": CheckPhase.OPTIMIZING},
        {"trigger": "optimize_done", "source": CheckPhase.OPTIMIZING, "dest": CheckPhase.COMPLETED},
        {"trigger": "stop", "source": "*", "dest": CheckPhase.STOPPED, "unless": "is_terminal"},
        {"trigger": "fail", "source": "*", "dest": CheckPhase.FAILED, "unless": "is_terminal"},
        {"trigger": "reset", "source": "*", "dest": CheckPhase.IDLE},
    ]

    def __init__(self):
        self.metrics = CheckMetrics()
        self._listeners: List = []

        self.machine = Machine(
            model=self,
            states=CheckStateMachine.states,
            transitions=CheckStateMachine.transitions,
            initial=CheckPhase.IDLE,
            send_event=True,
        )

    @property
    def phase(self) -> str:
        return self.state

    @property
    def is_running(self) -> bool:
        return self.phase not in (CheckPhase.IDLE, CheckPhase.COMPLETED, CheckPhase.STOPPED, CheckPhase.FAILED)

    @property
    def is_terminal(self) -> bool:
        return self.phase in (CheckPhase.COMPLETED, CheckPhase.STOPPED, CheckPhase.FAILED)

    def on_enter(self, callback):
        self._listeners.append(callback)

    def _notify_listeners(self, event):
        for callback in self._listeners:
            try:
                callback(self.phase, self.metrics)
            except Exception as e:
                logger.warning("状态监听器回调失败: %s", e)

    def _on_enter_idle(self, event):
        self.metrics = CheckMetrics()
        self._notify_listeners(event)

    def _on_enter_initializing(self, event):
        self.metrics.start_time = time.time()
        self._notify_listeners(event)

    def _on_enter_parsing(self, event):
        self._notify_listeners(event)

    def _on_enter_downloading(self, event):
        self._notify_listeners(event)

    def _on_enter_checking(self, event):
        self._notify_listeners(event)

    def _on_enter_optimizing(self, event):
        self._notify_listeners(event)

    def _on_enter_completed(self, event):
        self.metrics.end_time = time.time()
        self._notify_listeners(event)

    def _on_enter_stopped(self, event):
        self.metrics.end_time = time.time()
        self._notify_listeners(event)

    def _on_enter_failed(self, event):
        self.metrics.end_time = time.time()
        self._notify_listeners(event)

    def update_metrics(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.metrics, key):
                setattr(self.metrics, key, value)

    def increment_metric(self, field_name: str, delta: int = 1):
        current = getattr(self.metrics, field_name)
        setattr(self.metrics, field_name, current + delta)

    def to_dict(self) -> Dict:
        return {
            "phase": self.phase,
            "is_running": self.is_running,
            "is_terminal": self.is_terminal,
            "metrics": {
                "total_count": self.metrics.total_count,
                "checked_count": self.metrics.checked_count,
                "valid_count": self.metrics.valid_count,
                "invalid_count": self.metrics.invalid_count,
                "current_workers": self.metrics.current_workers,
                "progress_percent": round(self.metrics.progress_percent, 1),
                "elapsed_seconds": round(self.metrics.elapsed_seconds, 1),
            },
        }
