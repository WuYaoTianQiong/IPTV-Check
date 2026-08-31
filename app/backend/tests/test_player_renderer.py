"""Unit tests for PlayerRenderer — unified player HTML generator."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from iptv_check.infra.player_renderer import PlayerRenderer, player_renderer


class TestPlayerRenderer:
    """Core rendering tests."""

    def setup_method(self):
        self.renderer = PlayerRenderer()

    # ── basic rendering ──

    def test_minimal_render(self):
        html = self.renderer.render("http://example.com/stream.m3u8", "Test Channel")
        assert "Test Channel" in html
        assert "proxy_url" not in html  # no literal placeholder string
        assert "{{" not in html
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_empty_url_and_name(self):
        html = self.renderer.render("", "")
        assert "未知频道" in html or "IPTV Player" in html
        assert "{{" not in html

    def test_special_chars_in_name(self):
        html = self.renderer.render("http://x.com/a.m3u8", "测试 <>&\"' 频道")
        assert "测试 <>&\"' 频道" in html

    # ── proxy URL encoding round-trip ──

    def test_proxy_url_roundtrip(self):
        """Verify the proxy URL can be decoded correctly."""
        stream_url = "http://hls.example.com/live/stream.m3u8?token=abc+123"
        html = self.renderer.render(stream_url, "Test")

        # Extract the proxy URL from the template
        m = re.search(r"var proxyUrl = '([^']+)'", html)
        assert m, "proxyUrl not found in rendered HTML"
        proxy_url = m.group(1)

        # Decode the embedded base64
        import base64
        import urllib.parse
        qs = proxy_url.split("?url=")[1]
        # Reverse the URL quoting
        decoded_b64 = urllib.parse.unquote(qs)
        decoded = base64.b64decode(decoded_b64).decode("utf-8")
        assert decoded == stream_url, f"Round-trip failed: {decoded} != {stream_url}"

    # ── sources support ──

    def test_no_sources(self):
        html = self.renderer.render("http://x.com/a.m3u8", "Ch")
        assert "var sources = null" in html

    def test_single_source(self):
        sources = [{"url": "http://x.com/a.m3u8", "latency": 26, "recommended": True}]
        html = self.renderer.render("http://x.com/a.m3u8", "Ch", sources=sources)
        assert "var sources = [" in html

    def test_multiple_sources_selector_class(self):
        sources = [
            {"url": "http://a.com/1.m3u8", "latency": 10, "recommended": False},
            {"url": "http://b.com/2.m3u8", "latency": 20, "recommended": True},
        ]
        html = self.renderer.render("http://a.com/1.m3u8", "Ch", sources=sources)
        # Both URLs should appear in sources JSON
        assert "a.com" in html
        assert "b.com" in html
        # Recommended index should be 1 (second source)
        assert "var currentSourceIdx = 1" in html

    def test_recommended_idx_default(self):
        sources = [
            {"url": "http://a.com/1.m3u8", "latency": 10},
            {"url": "http://b.com/2.m3u8", "latency": 20},
        ]
        html = self.renderer.render("http://a.com/1.m3u8", "Ch", sources=sources)
        assert "var currentSourceIdx = 0" in html

    # ── error overlay & fault tolerance ──

    def test_error_overlay_present(self):
        html = self.renderer.render("http://x.com/a.m3u8", "Ch")
        assert "error-overlay" in html
        assert "播放失败" in html

    def test_fallback_div_present(self):
        html = self.renderer.render("http://x.com/a.m3u8", "Ch")
        assert "hls-fallback" in html
        assert "location.reload" in html

    def test_script_onerror(self):
        html = self.renderer.render("http://x.com/a.m3u8", "Ch")
        assert "onerror=" in html
        assert "__hlsLoadFailed" in html

    # ── template caching ──

    def test_template_caching(self):
        r = PlayerRenderer()
        html1 = r.render("http://a.com/1.m3u8", "C1")
        html2 = r.render("http://b.com/2.m3u8", "C2")
        assert r._cached_template is not None
        # Different renderings, same cached template
        assert "C1" in html1
        assert "C2" in html2
        assert "C1" not in html2

    # ── find_recommended_idx ──

    def test_find_recommended_idx_found(self):
        sources = [
            {"url": "a", "recommended": False},
            {"url": "b", "recommended": True},
            {"url": "c", "recommended": False},
        ]
        assert PlayerRenderer._find_recommended_idx(sources) == 1

    def test_find_recommended_idx_none(self):
        sources = [{"url": "a"}, {"url": "b"}]
        assert PlayerRenderer._find_recommended_idx(sources) == 0

    def test_find_recommended_idx_empty(self):
        assert PlayerRenderer._find_recommended_idx([]) == 0


class TestPlayerRendererMissingTemplate:
    """Edge case: template file not found."""

    def test_missing_template_raises(self):
        r = PlayerRenderer(template_dir=Path("/nonexistent/dir"))
        with pytest.raises(FileNotFoundError):
            r.render("http://x.com/a.m3u8", "Test")
