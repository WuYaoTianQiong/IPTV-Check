import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from iptv_check.infra.event_bus import Events


@dataclass
class AppState:
    is_running: bool = False
    stop_requested: bool = False
    current_stage: str = "idle"

    local_isp: str = "未知"
    source_isp: set = field(default_factory=set)

    channels: list = field(default_factory=list)
    results: Dict[str, list] = field(default_factory=lambda: {"all": [], "valid": [], "invalid": []})

    total_count: int = 0
    checked_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0

    current_workers: int = 30
    consecutive_success: int = 0
    consecutive_fail: int = 0

    file_paths: List[str] = field(default_factory=list)
    file_display: str = "未选择文件"
    export_dir: str = ""
    source_basename: str = ""
    last_export_path: Optional[str] = None


class StateStore:
    def __init__(self):
        self._state = AppState()
        self._lock = threading.RLock()
        self._listeners = []

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._state, k):
                    setattr(self._state, k, v)
        Events.state_changed.send(self._state)

    def increment(self, field_name: str, delta: int = 1):
        with self._lock:
            current = getattr(self._state, field_name)
            setattr(self._state, field_name, current + delta)
        Events.state_changed.send(self._state)

    def reset_counts(self):
        with self._lock:
            self._state.checked_count = 0
            self._state.valid_count = 0
            self._state.invalid_count = 0
            self._state.consecutive_success = 0
            self._state.consecutive_fail = 0
        Events.state_changed.send(self._state)

    def reset_results(self):
        with self._lock:
            self._state.results = {"all": [], "valid": [], "invalid": []}
        self.reset_counts()
