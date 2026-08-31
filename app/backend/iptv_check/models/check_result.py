from dataclasses import dataclass, field
from typing import Optional
from iptv_check.models.channel import Channel


@dataclass
class CheckResult:
    channel: Channel
    is_valid: bool = False
    quality_tier: str = ""
    latency: float = -1
    speed: str = "-"
    details: str = ""
    timestamp: float = 0.0

    @property
    def status_text(self) -> str:
        tier = self.quality_tier
        if not tier:
            tier = "valid" if self.is_valid else "invalid"
        if tier == "valid":
            return "有效"
        elif tier == "likely_valid":
            return "疑似有效"
        return "无效"

    @property
    def latency_display(self) -> str:
        if self.latency < 0:
            return "-"
        return str(int(self.latency))

    @property
    def tag(self) -> str:
        if self.quality_tier:
            return self.quality_tier
        return "valid" if self.is_valid else "invalid"

    def to_tree_values(self) -> tuple:
        return (
            self.channel.index,
            ", ".join(self.channel.sources),
            self.channel.name,
            self.channel.url,
            self.status_text,
            self.latency_display,
            self.speed,
            self.details,
        )

    def to_cache_dict(self) -> dict:
        return {
            "url": self.channel.url,
            "name": self.channel.name,
            "status": self.status_text,
            "latency": self.latency_display,
            "speed": self.speed,
            "details": self.details,
            "timestamp": self.timestamp,
            "quality_tier": self.quality_tier,
            "is_valid": self.is_valid,
        }

    @classmethod
    def from_cache(cls, channel: Channel, cache_data: dict) -> "CheckResult":
        quality_tier = cache_data.get("quality_tier", "")
        if not quality_tier:
            status = cache_data.get("status", "")
            if status == "有效":
                quality_tier = "valid"
            elif status == "疑似有效":
                quality_tier = "likely_valid"
            else:
                quality_tier = "invalid"
        is_valid = quality_tier in ("valid", "likely_valid")
        return cls(
            channel=channel,
            is_valid=is_valid,
            quality_tier=quality_tier,
            latency=float(cache_data.get("latency", -1)) if cache_data.get("latency", "-") != "-" else -1,
            speed=cache_data.get("speed", "-"),
            details=cache_data.get("details", "缓存结果"),
            timestamp=cache_data.get("timestamp", 0),
        )
