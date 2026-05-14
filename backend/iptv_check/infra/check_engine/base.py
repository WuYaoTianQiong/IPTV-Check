from typing import Protocol, List, Optional, Callable, runtime_checkable

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig


@runtime_checkable
class CheckEngineProtocol(Protocol):
    def start(self, channels: List[Channel], config: CheckConfig,
              on_result: Optional[Callable[[CheckResult], None]] = None,
              on_complete: Optional[Callable[[], None]] = None) -> None: ...

    def add_channels(self, channels: List[Channel], config: CheckConfig,
                     on_result: Optional[Callable[[CheckResult], None]] = None) -> None: ...

    def stop(self) -> None: ...

    @property
    def is_running(self) -> bool: ...
