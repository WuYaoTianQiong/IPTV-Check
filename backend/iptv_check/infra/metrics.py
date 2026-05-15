"""
Prometheus metrics collection for IPTV-Check
Provides application-level metrics for monitoring and alerting.
"""
import time
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Simple metrics collector with Prometheus-compatible format
    
    Collects:
    - HTTP request metrics (count, latency)
    - Check operation metrics
    - System resource metrics
    - Custom business metrics
    """
    
    def __init__(self):
        self._counters = {}
        self._gauges = {}
        self._histograms = {}
        self._start_time = time.time()
        
        self._initialize_default_metrics()
    
    def _initialize_default_metrics(self):
        """Initialize default metrics"""
        self._counters["http_requests_total"] = {}
        self._gauges["http_active_requests"] = 0
        self._gauges["check_channels_total"] = 0
        self._gauges["check_channels_valid"] = 0
        self._gauges["check_channels_invalid"] = 0
        self._gauges["sse_subscribers"] = 0
        self._gauges["stream_proxy_connections"] = 0
    
    def increment_counter(self, name: str, value: int = 1, labels: Optional[dict] = None):
        """Increment a counter metric"""
        if name not in self._counters:
            self._counters[name] = {}
        
        key = self._labels_key(labels)
        self._counters[name][key] = self._counters[name].get(key, 0) + value
    
    def set_gauge(self, name: str, value: float, labels: Optional[dict] = None):
        """Set a gauge metric"""
        if labels:
            key = self._labels_key(labels)
            if name not in self._gauges:
                self._gauges[name] = {}
            self._gauges[name][key] = value
        else:
            self._gauges[name] = value
    
    def increment_gauge(self, name: str, value: float = 1):
        """Increment a gauge metric"""
        if name not in self._gauges:
            self._gauges[name] = 0
        self._gauges[name] += value
    
    def decrement_gauge(self, name: str, value: float = 1):
        """Decrement a gauge metric"""
        if name in self._gauges:
            self._gauges[name] -= value
    
    def record_histogram(self, name: str, value: float, labels: Optional[dict] = None):
        """Record a histogram metric"""
        if name not in self._histograms:
            self._histograms[name] = {"sum": 0, "count": 0, "buckets": {}}
        
        key = self._labels_key(labels)
        self._histograms[name]["sum"] += value
        self._histograms[name]["count"] += 1
        
        bucket = self._get_bucket(value)
        if bucket not in self._histograms[name]["buckets"]:
            self._histograms[name]["buckets"][bucket] = 0
        self._histograms[name]["buckets"][bucket] += 1
    
    @contextmanager
    def timer(self, name: str, labels: Optional[dict] = None):
        """Context manager for timing operations"""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.record_histogram(f"{name}_duration_seconds", duration, labels)
            self.increment_counter(f"{name}_total", labels=labels)
    
    def record_http_request(self, method: str, path: str, status_code: int, duration: float):
        """Record HTTP request metrics"""
        labels = {"method": method, "path": path, "status": str(status_code)}
        self.increment_counter("http_requests_total", labels=labels)
        self.record_histogram("http_request_duration_seconds", duration, labels)
    
    def record_check_result(self, is_valid: bool):
        """Record channel check result"""
        if is_valid:
            self.increment_gauge("check_channels_valid")
        else:
            self.increment_gauge("check_channels_invalid")
    
    def reset_check_metrics(self, total: int = 0):
        """Reset check metrics for a new run"""
        self._gauges["check_channels_total"] = total
        self._gauges["check_channels_valid"] = 0
        self._gauges["check_channels_invalid"] = 0
    
    def generate_metrics(self) -> str:
        """Generate Prometheus-compatible metrics text"""
        lines = []
        
        lines.append("# HELP app_uptime_seconds Application uptime in seconds")
        lines.append("# TYPE app_uptime_seconds gauge")
        lines.append(f"app_uptime_seconds {time.time() - self._start_time:.1f}")
        
        for name, values in self._counters.items():
            lines.append(f"# HELP {name} Total count")
            lines.append(f"# TYPE {name} counter")
            if isinstance(values, dict):
                for labels, value in values.items():
                    lines.append(f"{name}{{{labels}}} {value}")
            else:
                lines.append(f"{name} {values}")
        
        for name, value in self._gauges.items():
            lines.append(f"# HELP {name} Current value")
            lines.append(f"# TYPE {name} gauge")
            if isinstance(value, dict):
                for labels, v in value.items():
                    lines.append(f"{name}{{{labels}}} {v}")
            else:
                lines.append(f"{name} {value}")
        
        for name, hist in self._histograms.items():
            lines.append(f"# HELP {name} Histogram")
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_sum {hist['sum']:.4f}")
            lines.append(f"{name}_count {hist['count']}")
            for bucket, count in sorted(hist["buckets"].items()):
                lines.append(f'{name}_bucket{{le="{bucket}"}} {count}')
            lines.append(f'{name}_bucket{{le="+Inf"}} {hist["count"]}')
        
        return "\n".join(lines)
    
    def get_stats(self) -> dict:
        """Get metrics as dictionary"""
        return {
            "counters": self._counters,
            "gauges": self._gauges,
            "histograms": {k: {"sum": v["sum"], "count": v["count"]} for k, v in self._histograms.items()},
            "uptime_seconds": round(time.time() - self._start_time, 1),
        }
    
    @staticmethod
    def _labels_key(labels: Optional[dict]) -> str:
        """Convert labels dict to string key"""
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    
    @staticmethod
    def _get_bucket(value: float) -> str:
        """Get histogram bucket for value"""
        buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        for bucket in buckets:
            if value <= bucket:
                return str(bucket)
        return "+Inf"


metrics = MetricsCollector()
