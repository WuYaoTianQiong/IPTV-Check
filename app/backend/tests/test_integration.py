"""
Integration tests for new architecture components
Tests DI Container, Exception Handling, SSE Broker, Metrics, and Repository Pattern.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.infra.di.container import DIContainer
from iptv_check.infra.exceptions import (
    AppBaseException,
    BusinessLogicError,
    ResourceNotFoundError,
    ChannelNotFoundError,
    CheckAlreadyRunningError,
)
from iptv_check.infra.sse_broker import SSEBroker, SSESubscriber
from iptv_check.infra.metrics import MetricsCollector


class TestDIContainer:
    @pytest.fixture
    def container(self):
        return DIContainer()

    def test_register_and_resolve_instance(self, container):
        instance = {"key": "value"}
        container.register_instance("test_service", instance)
        assert container.resolve("test_service") is instance

    def test_register_instance_reusable(self, container):
        instance = {"key": "value"}
        container.register_instance("singleton_service", instance)
        
        r1 = container.resolve("singleton_service")
        r2 = container.resolve("singleton_service")
        
        assert r1 is r2

    def test_register_transient(self, container):
        call_count = [0]
        
        def factory():
            call_count[0] += 1
            return {"count": call_count[0]}
        
        container.register_transient("transient_service", factory)
        
        r1 = container.resolve("transient_service")
        r2 = container.resolve("transient_service")
        
        assert r1 is not r2
        assert call_count[0] == 2

    def test_resolve_unregistered_service(self, container):
        with pytest.raises(KeyError):
            container.resolve("nonexistent")

    def test_has_method(self, container):
        container.register_instance("test", {})
        assert container.has("test") is True
        assert container.has("missing") is False


class TestExceptions:
    def test_app_base_exception(self):
        exc = AppBaseException("Test error", error_code="TEST", status_code=400)
        assert exc.message == "Test error"
        assert exc.error_code == "TEST"
        assert exc.status_code == 400

    def test_business_logic_error(self):
        exc = BusinessLogicError("Validation failed")
        assert exc.status_code == 400
        assert exc.error_code == "BUSINESS_ERROR"

    def test_resource_not_found_error(self):
        exc = ResourceNotFoundError("Item not found")
        assert exc.status_code == 404
        assert exc.error_code == "NOT_FOUND"

    def test_channel_not_found_error(self):
        exc = ChannelNotFoundError(123)
        assert exc.status_code == 404
        assert "123" in exc.message
        assert exc.details["channel_id"] == 123

    def test_check_already_running_error(self):
        exc = CheckAlreadyRunningError()
        assert exc.error_code == "CHECK_ALREADY_RUNNING"
        assert "检测" in exc.message


class TestSSEBroker:
    @pytest.fixture
    def broker(self):
        return SSEBroker(max_subscribers=10, max_queue_size=5)

    def test_subscriber_creation(self, broker):
        sub = SSESubscriber("test_sub", max_queue_size=5)
        assert sub.subscriber_id == "test_sub"
        assert sub.queue.maxsize == 5
        assert sub.messages_sent == 0
        assert sub.messages_dropped == 0

    def test_subscriber_stats(self):
        sub = SSESubscriber("test_sub")
        stats = sub.stats()
        assert stats["subscriber_id"] == "test_sub"
        assert "queue_size" in stats
        assert "messages_sent" in stats

    def test_subscriber_is_stale(self, broker):
        sub = SSESubscriber("test_sub")
        assert sub.is_stale(timeout_seconds=300) is False
        
        sub.last_activity = 0
        assert sub.is_stale(timeout_seconds=1) is True

    def test_broker_stats(self, broker):
        stats = broker.get_stats()
        assert stats["total_subscribers"] == 0
        assert stats["max_subscribers"] == 10
        assert stats["max_queue_size"] == 5
        assert stats["subscribers"] == []


class TestMetricsCollector:
    @pytest.fixture
    def metrics(self):
        return MetricsCollector()

    def test_increment_counter(self, metrics):
        metrics.increment_counter("test_counter")
        metrics.increment_counter("test_counter")
        
        assert "" in metrics._counters["test_counter"]
        assert metrics._counters["test_counter"][""] == 2

    def test_increment_counter_with_labels(self, metrics):
        metrics.increment_counter("http_requests", labels={"method": "GET", "path": "/api"})
        metrics.increment_counter("http_requests", labels={"method": "GET", "path": "/api"})
        
        key = 'method="GET",path="/api"'
        assert metrics._counters["http_requests"][key] == 2

    def test_set_gauge(self, metrics):
        metrics.set_gauge("active_users", 100)
        assert metrics._gauges["active_users"] == 100
        
        metrics.set_gauge("active_users", 50)
        assert metrics._gauges["active_users"] == 50

    def test_increment_decrement_gauge(self, metrics):
        metrics._gauges["connections"] = 0
        metrics.increment_gauge("connections")
        metrics.increment_gauge("connections")
        assert metrics._gauges["connections"] == 2
        
        metrics.decrement_gauge("connections")
        assert metrics._gauges["connections"] == 1

    def test_record_histogram(self, metrics):
        metrics.record_histogram("request_duration", 0.5)
        metrics.record_histogram("request_duration", 1.2)
        
        assert metrics._histograms["request_duration"]["count"] == 2
        assert metrics._histograms["request_duration"]["sum"] == 1.7

    def test_generate_metrics_output(self, metrics):
        metrics.increment_counter("my_counter")
        metrics.set_gauge("my_gauge", 42)
        
        output = metrics.generate_metrics()
        assert "my_counter" in output
        assert "my_gauge" in output
        assert "42" in output

    def test_get_stats(self, metrics):
        stats = metrics.get_stats()
        assert "counters" in stats
        assert "gauges" in stats
        assert "histograms" in stats
        assert "uptime_seconds" in stats
        assert isinstance(stats["uptime_seconds"], (int, float))
