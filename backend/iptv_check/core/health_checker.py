import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

from iptv_check.models.check_result import CheckResult

logger = logging.getLogger(__name__)

DEFAULT_HEALTH_THRESHOLD = 0.3


@dataclass
class SourceHealth:
    source_name: str
    total: int = 0
    valid: int = 0
    invalid: int = 0
    valid_rate: float = 0.0
    avg_latency: float = 0.0
    is_healthy: bool = True
    alerts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "total": self.total,
            "valid": self.valid,
            "invalid": self.invalid,
            "valid_rate": round(self.valid_rate * 100, 1),
            "avg_latency": round(self.avg_latency, 0),
            "is_healthy": self.is_healthy,
            "alerts": self.alerts,
        }


class SourceHealthChecker:
    def __init__(self, threshold: float = DEFAULT_HEALTH_THRESHOLD):
        self._threshold = threshold
        self._last_report: Dict[str, SourceHealth] = {}

    def check(self, results: List[CheckResult], local_isp: str = "") -> Dict[str, SourceHealth]:
        by_source: Dict[str, List[CheckResult]] = {}
        for r in results:
            for src in r.channel.sources:
                if src not in by_source:
                    by_source[src] = []
                by_source[src].append(r)

        report: Dict[str, SourceHealth] = {}
        for name, items in by_source.items():
            total = len(items)
            valid_items = [r for r in items if r.is_valid]
            valid = len(valid_items)
            valid_rate = valid / total if total > 0 else 0
            latencies = [r.latency for r in valid_items if r.latency > 0]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0

            alerts = []
            is_healthy = True

            if total > 0 and valid_rate < self._threshold:
                is_healthy = False
                alerts.append(f"有效率 {valid_rate*100:.1f}% 低于阈值 {self._threshold*100:.0f}%")

            if total >= 10 and valid == 0:
                is_healthy = False
                alerts.append("全部频道检测失败")

            if avg_latency > 500:
                alerts.append(f"平均延迟 {avg_latency:.0f}ms 偏高")

            health = SourceHealth(
                source_name=name, total=total, valid=valid,
                invalid=total - valid, valid_rate=valid_rate,
                avg_latency=avg_latency, is_healthy=is_healthy, alerts=alerts,
            )
            report[name] = health

            if not is_healthy:
                logger.warning("源健康告警: %s - %s", name, ", ".join(alerts))

        self._last_report = report
        return report

    def get_unhealthy_sources(self) -> List[SourceHealth]:
        return [h for h in self._last_report.values() if not h.is_healthy]

    def get_last_report(self) -> Dict[str, SourceHealth]:
        return self._last_report

    def to_dict(self) -> Dict[str, Any]:
        return {
            "threshold": self._threshold,
            "sources": {name: health.to_dict() for name, health in self._last_report.items()},
            "unhealthy_count": len(self.get_unhealthy_sources()),
        }
