import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.source import OnlineSource
from iptv_check.models.settings import CheckConfig
from iptv_check.core.converter import FormatConverter
from iptv_check.core.parser import PlaylistParser
from iptv_check.core.optimizer import SmartOptimizer


class TestChannel:
    def test_from_m3u_extinf(self):
        ch = Channel.from_m3u_extinf('#EXTINF:-1 group-title="央视",CCTV-1', "http://example.com/live.m3u8", index=1, source_name="test")
        assert ch.name == "CCTV-1"
        assert ch.group == "央视"
        assert ch.url == "http://example.com/live.m3u8"
        assert ch.sources == ["test"]

    def test_url_key(self):
        ch = Channel(name="test", url="http://example.com/stream.m3u8")
        assert len(ch.url_key) == 32

    def test_protocol_type(self):
        ch1 = Channel(name="v4", url="http://example.com/stream.m3u8")
        assert ch1.protocol_type == "IPv4"
        ch2 = Channel(name="v6", url="http://ipv6.example.com/stream.m3u8")
        assert ch2.protocol_type == "IPv6"


class TestCheckResult:
    def test_status_text(self):
        ch = Channel(name="test", url="http://example.com")
        r_valid = CheckResult(channel=ch, is_valid=True, latency=50)
        assert r_valid.status_text == "有效"
        r_invalid = CheckResult(channel=ch, is_valid=False, details="超时")
        assert r_invalid.status_text == "无效"

    def test_to_cache_roundtrip(self):
        ch = Channel(name="CCTV-1", url="http://example.com/live.m3u8")
        original = CheckResult(channel=ch, is_valid=True, latency=100, speed="125.50", details="OK (200)", timestamp=1000.0)
        cache_dict = original.to_cache_dict()
        restored = CheckResult.from_cache(ch, cache_dict)
        assert restored.is_valid == original.is_valid
        assert restored.speed == original.speed
        assert restored.details == original.details

    def test_to_tree_values(self):
        ch = Channel(name="CCTV-1", url="http://example.com", sources=["src1", "src2"], index=1)
        r = CheckResult(channel=ch, is_valid=True, latency=50, speed="100.00", details="OK")
        values = r.to_tree_values()
        assert values[0] == 1
        assert values[2] == "CCTV-1"
        assert values[4] == "有效"


class TestOnlineSource:
    def test_from_dict(self):
        data = {"id": "test", "name": "Test Source", "url": "http://example.com", "isp": ["移动", "电信"], "protocol": "ipv4", "disabled": False}
        src = OnlineSource.from_dict(data)
        assert src.id == "test"
        assert src.is_isp_compatible("移动") is True
        assert src.is_isp_compatible("联通") is False

    def test_isp_other_fallback(self):
        data = {"id": "global", "name": "Global", "url": "http://example.com", "isp": ["其他"]}
        src = OnlineSource.from_dict(data)
        assert src.is_isp_compatible("移动") is True


class TestFormatConverter:
    def test_m3u_to_txt(self):
        m3u = "#EXTM3U\n#EXTINF:-1,CCTV-1\nhttp://example.com/cctv1.m3u8\n#EXTINF:-1,CCTV-2\nhttp://example.com/cctv2.m3u8\n"
        txt = FormatConverter.m3u_to_txt(m3u)
        assert "CCTV-1,http://example.com/cctv1.m3u8" in txt
        assert "CCTV-2,http://example.com/cctv2.m3u8" in txt

    def test_txt_to_m3u(self):
        txt = "CCTV-1,http://example.com/cctv1.m3u8\nCCTV-2,http://example.com/cctv2.m3u8\n"
        m3u = FormatConverter.txt_to_m3u(txt)
        assert "#EXTM3U" in m3u
        assert "#EXTINF:-1,CCTV-1" in m3u
        assert "http://example.com/cctv1.m3u8" in m3u


class TestSmartOptimizer:
    def test_optimize_keeps_best_latency(self):
        ch = Channel(name="CCTV-1", url="http://example.com")
        results = [
            CheckResult(channel=ch, is_valid=True, latency=100),
            CheckResult(channel=Channel(name="CCTV-1", url="http://example2.com"), is_valid=True, latency=50),
            CheckResult(channel=Channel(name="CCTV-2", url="http://example3.com"), is_valid=True, latency=80),
            CheckResult(channel=Channel(name="CCTV-3", url="http://example4.com"), is_valid=False, details="超时"),
        ]
        optimized = SmartOptimizer.optimize(results, max_per_group=1)
        valid = [r for r in optimized if r.is_valid]
        assert len(valid) == 2
        cctv1_results = [r for r in valid if "CCTV-1" in r.channel.name]
        assert len(cctv1_results) == 1
        assert cctv1_results[0].latency == 50
