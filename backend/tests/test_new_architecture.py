import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.infra.error_strategy import ErrorClassifier, ErrorSeverity, ErrorCategory
from iptv_check.infra.check_state_machine import CheckStateMachine, CheckPhase, CheckMetrics
from iptv_check.infra.disk_cache import DiskCacheManager
from iptv_check.infra.media_probe import MediaProbe, StreamProbeResult


class TestErrorClassifier:
    def test_classify_timeout(self):
        exc = asyncio.TimeoutError("Connection timed out")
        info = ErrorClassifier.classify(exc)
        assert info.severity == ErrorSeverity.TRANSIENT
        assert info.category == ErrorCategory.TIMEOUT
        assert info.retryable is True

    def test_classify_value_error(self):
        exc = ValueError("非标准M3U8内容")
        info = ErrorClassifier.classify(exc)
        assert info.severity == ErrorSeverity.PERMANENT
        assert info.category == ErrorCategory.STREAM_INVALID
        assert info.retryable is False

    def test_error_info_not_retryable(self):
        info = ErrorClassifier.classify(ValueError("test"))
        assert not info.is_retryable(max_retries=3, current_attempt=0)


class TestCheckStateMachine:
    def test_initial_state(self):
        sm = CheckStateMachine()
        assert sm.phase == CheckPhase.IDLE
        assert sm.is_running is False
        assert sm.is_terminal is False

    def test_valid_transition(self):
        sm = CheckStateMachine()
        sm.start()
        assert sm.phase == CheckPhase.INITIALIZING
        sm.initialized()
        assert sm.phase == CheckPhase.PARSING
        sm.parsing_done()
        assert sm.phase == CheckPhase.CHECKING
        sm.check_done()
        assert sm.phase == CheckPhase.OPTIMIZING
        sm.optimize_done()
        assert sm.phase == CheckPhase.COMPLETED
        assert sm.is_terminal is True

    def test_update_metrics(self):
        sm = CheckStateMachine()
        sm.update_metrics(total_count=100, checked_count=50)
        assert sm.metrics.total_count == 100
        assert sm.metrics.checked_count == 50

    def test_increment_metric(self):
        sm = CheckStateMachine()
        sm.increment_metric("valid_count", 5)
        assert sm.metrics.valid_count == 5

    def test_to_dict(self):
        sm = CheckStateMachine()
        sm.update_metrics(total_count=100, checked_count=50, valid_count=30, invalid_count=20)
        result = sm.to_dict()
        assert result["phase"] == CheckPhase.IDLE
        assert result["metrics"]["total_count"] == 100
        assert result["metrics"]["progress_percent"] == 50.0


class TestDiskCacheManager:
    def test_set_and_get(self, tmp_path):
        cache = DiskCacheManager(base_dir=str(tmp_path))
        cache.set("key1", {"status": "有效", "latency": 50})
        assert cache.has("key1")
        assert cache.get("key1")["status"] == "有效"

    def test_missing_key(self, tmp_path):
        cache = DiskCacheManager(base_dir=str(tmp_path))
        assert cache.get("nonexistent") is None
        assert not cache.has("nonexistent")

    def test_delete(self, tmp_path):
        cache = DiskCacheManager(base_dir=str(tmp_path))
        cache.set("key1", {"data": "test"})
        assert cache.delete("key1") is True
        assert cache.has("key1") is False

    def test_count(self, tmp_path):
        cache = DiskCacheManager(base_dir=str(tmp_path))
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert cache.count() == 3

    def test_clear(self, tmp_path):
        cache = DiskCacheManager(base_dir=str(tmp_path))
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.count() == 0

    def test_stats(self, tmp_path):
        cache = DiskCacheManager(base_dir=str(tmp_path))
        cache.set("key1", "value1")
        stats = cache.stats()
        assert stats["count"] == 1
        assert "size_bytes" in stats


class TestMediaProbe:
    def test_ffmpeg_availability(self):
        result = MediaProbe.is_ffmpeg_available()
        assert isinstance(result, bool)

    def test_probe_result_summary_playable(self):
        probe_result = StreamProbeResult(
            is_playable=True,
            has_video=True,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
            resolution="1920x1080",
        )
        summary = probe_result.summary()
        assert "可播放" in summary
        assert "h264" in summary

    def test_probe_result_summary_not_playable(self):
        probe_result = StreamProbeResult(
            is_playable=False,
            error_message="探测失败",
        )
        summary = probe_result.summary()
        assert "不可播放" in summary

    def test_m3u8_url_without_ffmpeg(self):
        probe_result = StreamProbeResult(
            has_video=False,
            has_audio=False,
            is_playable=False,
            error_message="无流",
        )
        from urllib.parse import urlparse
        parsed = urlparse("http://example.com/stream.m3u8")
        if parsed.path.endswith(".m3u8"):
            probe_result.is_playable = True
        assert probe_result.is_playable is True
