import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.infra.network import HttpClient
from iptv_check.infra.cache import CacheManager
from iptv_check.infra.persistence import SettingsManager
from iptv_check.infra.exporter import ExportEngine
from iptv_check.infra.event_bus import Events
from iptv_check.infra.state import StateStore, AppState
from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult


class TestHttpClient:
    def test_init(self):
        client = HttpClient(timeout_connect=3, timeout_read=8)
        assert client._timeout == (3, 8)
        client.close()

    def test_update_timeout(self):
        client = HttpClient()
        client.update_timeout(5, 10)
        assert client._timeout == (5, 10)
        client.close()


class TestCacheManager:
    def test_set_and_get(self, tmp_path):
        cache = CacheManager(base_dir=str(tmp_path))
        cache.set("key1", {"status": "有效", "latency": 50})
        assert cache.has("key1")
        assert cache.get("key1")["status"] == "有效"

    def test_missing_key(self, tmp_path):
        cache = CacheManager(base_dir=str(tmp_path))
        assert cache.get("nonexistent") is None
        assert not cache.has("nonexistent")


class TestSettingsManager:
    def test_set_and_get(self, tmp_path):
        settings = SettingsManager(base_dir=str(tmp_path))
        settings.set("skip_wizard", True)
        assert settings.get("skip_wizard") is True

    def test_default_value(self, tmp_path):
        settings = SettingsManager(base_dir=str(tmp_path))
        assert settings.get("nonexistent", "default") == "default"


class TestExportEngine:
    def test_m3u_export(self, tmp_path):
        ch = Channel(name="CCTV-1", url="http://example.com/live.m3u8", sources=["src"], index=1)
        results = [CheckResult(channel=ch, is_valid=True, latency=50, speed="100", details="OK")]
        engine = ExportEngine()
        path = str(tmp_path / "test.m3u")
        result = engine.export("m3u", results, path, local_isp="移动")
        assert os.path.exists(result)
        with open(result, "r", encoding="utf-8") as f:
            content = f.read()
        assert "#EXTM3U" in content
        assert "CCTV-1" in content

    def test_csv_export(self, tmp_path):
        ch = Channel(name="CCTV-1", url="http://example.com/live.m3u8", sources=["src"], index=1)
        results = [CheckResult(channel=ch, is_valid=True, latency=50, speed="100", details="OK")]
        engine = ExportEngine()
        path = str(tmp_path / "test.csv")
        result = engine.export("csv", results, path)
        assert os.path.exists(result)

    def test_unsupported_format(self):
        engine = ExportEngine()
        with pytest.raises(ValueError):
            engine.export("pdf", [], "test.pdf")


class TestStateStore:
    def test_update(self):
        store = StateStore()
        store.update(is_running=True, current_stage="checking")
        assert store.state.is_running is True
        assert store.state.current_stage == "checking"

    def test_increment(self):
        store = StateStore()
        store.increment("checked_count", 5)
        assert store.state.checked_count == 5

    def test_reset_counts(self):
        store = StateStore()
        store.update(checked_count=100, valid_count=50)
        store.reset_counts()
        assert store.state.checked_count == 0
        assert store.state.valid_count == 0


class TestEvents:
    def test_signal_exists(self):
        assert Events.check_started is not None
        assert Events.channel_checked is not None
        assert Events.isp_detected is not None

    def test_signal_connect(self):
        received = []
        Events.check_started.connect(lambda sender, **kw: received.append(True))
        Events.check_started.send()
        assert len(received) == 1
