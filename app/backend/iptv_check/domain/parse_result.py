from dataclasses import dataclass, field
from typing import List, Optional

from iptv_check.models.channel import Channel


@dataclass
class ParseError:
    line: int
    raw: str
    error: str


@dataclass
class ParseResult:
    channels: List[Channel] = field(default_factory=list)
    errors: List[ParseError] = field(default_factory=list)
    source: str = ""

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def channel_count(self) -> int:
        return len(self.channels)
