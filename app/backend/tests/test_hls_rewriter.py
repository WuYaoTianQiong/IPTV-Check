"""Tests for HlsRewriter — URL rewriting in M3U8 playlists and circuit breaking."""
import base64
import sys
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from iptv_check.infra.hls_rewriter import (
    rewrite_hls_urls,
    _has_uri_attribute,
    _rewrite_tag_uri,
    _rewrite_bare_url,
    _resolve_and_encode,
)


def decode_proxy_url(proxy_url: str) -> str:
    """Helper: extract and decode the target URL from a proxy URL."""
    encoded = proxy_url.split("?url=")[1]
    return base64.b64decode(encoded).decode("utf-8")


class TestHlsRewriter:
    """Core M3U8 URL rewriting tests."""

    BASE = "http://example.com/live/playlist.m3u8"
    PROXY = "/proxy"

    # ── basic segment rewriting ──

    def test_simple_ts_segment(self):
        result = rewrite_hls_urls("segment-001.ts\n", self.BASE, self.PROXY)
        decoded = decode_proxy_url(result.strip())
        assert decoded == "http://example.com/live/segment-001.ts"

    def test_multiple_segments(self):
        content = "segment-000.ts\nsegment-001.ts\nsegment-002.ts\n"
        result = rewrite_hls_urls(content, self.BASE, self.PROXY)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        for i, line in enumerate(lines):
            decoded = decode_proxy_url(line.strip())
            assert decoded.endswith(f"segment-00{i}.ts")

    # ── absolute URLs ──

    def test_absolute_url_segment(self):
        result = rewrite_hls_urls(
            "https://cdn.other.com/segment.ts\n", self.BASE, self.PROXY
        )
        decoded = decode_proxy_url(result.strip())
        assert decoded == "https://cdn.other.com/segment.ts"

    # ── HLS tags (non-URI) passed through ──

    def test_extm3u_and_extinf_passthrough(self):
        content = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-TARGETDURATION:10\n"
            "#EXTINF:5.0,\n"
        )
        result = rewrite_hls_urls(content, self.BASE, self.PROXY)
        assert "#EXTM3U" in result
        assert "#EXT-X-VERSION:3" in result
        assert "#EXT-X-TARGETDURATION:10" in result
        assert "#EXTINF:5.0," in result

    def test_ext_x_endlist_passthrough(self):
        result = rewrite_hls_urls("#EXT-X-ENDLIST\n", self.BASE, self.PROXY)
        assert "#EXT-X-ENDLIST" in result

    # ── EXT-X-MAP (init segments) ──

    def test_ext_x_map_uri(self):
        result = rewrite_hls_urls(
            '#EXT-X-MAP:URI="init.mp4"\n', self.BASE, self.PROXY
        )
        # URI value should be rewritten
        assert 'URI="' in result
        m = __import__("re").search(r'URI="([^"]+)"', result)
        assert m is not None
        encoded = m.group(1)
        decoded = base64.b64decode(encoded).decode("utf-8")
        assert decoded == "http://example.com/live/init.mp4"

    def test_ext_x_map_with_byterange(self):
        result = rewrite_hls_urls(
            '#EXT-X-MAP:URI="init.mp4",BYTERANGE="0-999"\n', self.BASE, self.PROXY
        )
        assert 'BYTERANGE=' in result
        decoded = base64.b64decode(
            __import__("re").search(r'URI="([^"]+)"', result).group(1)
        ).decode("utf-8")
        assert decoded == "http://example.com/live/init.mp4"

    # ── EXT-X-KEY ──

    def test_ext_x_key_uri(self):
        result = rewrite_hls_urls(
            '#EXT-X-KEY:METHOD=AES-128,URI="key.bin",IV=0x1234\n',
            self.BASE, self.PROXY,
        )
        assert 'METHOD=AES-128' in result
        assert 'URI="' in result
        m = __import__("re").search(r'URI="([^"]+)"', result)
        decoded = base64.b64decode(m.group(1)).decode("utf-8")
        assert decoded == "http://example.com/live/key.bin"

    # ── relative paths ──

    def test_relative_subdirectory(self):
        """Segments in a subdirectory resolve relative to playlist directory."""
        base = "http://example.com/live/sub/playlist.m3u8"
        result = rewrite_hls_urls("../segments/video.ts\n", base, self.PROXY)
        decoded = decode_proxy_url(result.strip())
        assert decoded == "http://example.com/live/segments/video.ts"

    def test_root_relative_path(self):
        result = rewrite_hls_urls("/vod/segment.ts\n", self.BASE, self.PROXY)
        decoded = decode_proxy_url(result.strip())
        assert decoded == "http://example.com/vod/segment.ts"

    # ── query parameters ──

    def test_segment_with_query_params(self):
        result = rewrite_hls_urls(
            "segment.ts?token=abc&expires=123\n", self.BASE, self.PROXY
        )
        decoded = decode_proxy_url(result.strip())
        assert "token=abc" in decoded

    def test_playlist_url_with_query(self):
        base = "http://example.com/live/playlist.m3u8?auth=xyz"
        result = rewrite_hls_urls("segment.ts\n", base, self.PROXY)
        decoded = decode_proxy_url(result.strip())
        # Base URL with query is still stripped to directory
        assert decoded == "http://example.com/live/segment.ts"

    # ── variant playlists ──

    def test_variant_playlist_url(self):
        result = rewrite_hls_urls(
            "variant_720p.m3u8\n", self.BASE, self.PROXY
        )
        decoded = decode_proxy_url(result.strip())
        assert decoded == "http://example.com/live/variant_720p.m3u8"

    # ── empty / edge cases ──

    def test_empty_playlist(self):
        assert rewrite_hls_urls("", self.BASE, self.PROXY) == ""

    def test_comment_lines_only(self):
        content = "#EXTM3U\n# comment\n"
        result = rewrite_hls_urls(content, self.BASE, self.PROXY)
        assert result == content

    # ── real-world playlist snapshot ──

    def test_realistic_multivariant_playlist(self):
        content = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
            "low.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720\n"
            "mid.m3u8\n"
        )
        result = rewrite_hls_urls(content, self.BASE, self.PROXY)
        lines = result.strip().split("\n")
        # Tags preserved
        assert lines[0] == "#EXTM3U"
        assert "BANDWIDTH=800000" in lines[2]
        # Variant playlist URLs rewritten
        assert decode_proxy_url(lines[3].strip()) == "http://example.com/live/low.m3u8"
        assert decode_proxy_url(lines[5].strip()) == "http://example.com/live/mid.m3u8"

    def test_realistic_media_playlist(self):
        content = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:6\n"
            "#EXT-X-TARGETDURATION:6\n"
            "#EXT-X-MEDIA-SEQUENCE:0\n"
            "#EXT-X-MAP:URI=\"init.mp4\"\n"
            "#EXTINF:6.0,\n"
            "segment-000.ts\n"
            "#EXTINF:6.0,\n"
            "segment-001.ts\n"
            "#EXT-X-ENDLIST\n"
        )
        result = rewrite_hls_urls(content, self.BASE, self.PROXY)
        lines = result.strip().split("\n")
        assert len(lines) == 10  # 6 tags + 2 segments + 1 map + 1 endlist
        # init segment rewritten (URI value is base64 of the full URL)
        m = __import__("re").search(r'URI="([^"]+)"', lines[4])
        assert m is not None
        decoded_uri = base64.b64decode(m.group(1)).decode("utf-8")
        assert decoded_uri == "http://example.com/live/init.mp4"
        # TS segments rewritten (proxy URL format)
        assert decode_proxy_url(lines[6].strip()) == "http://example.com/live/segment-000.ts"
        assert decode_proxy_url(lines[8].strip()) == "http://example.com/live/segment-001.ts"


class TestHlsRewriterHelpers:
    """Unit tests for helper functions."""

    def test_has_uri_attribute_map(self):
        assert _has_uri_attribute('#EXT-X-MAP:URI="init.mp4"')

    def test_has_uri_attribute_key(self):
        assert _has_uri_attribute('#EXT-X-KEY:METHOD=AES-128,URI="key.bin"')

    def test_has_uri_attribute_false(self):
        assert not _has_uri_attribute("#EXTINF:5.0,")
        assert not _has_uri_attribute("segment.ts")

    def test_rewrite_tag_uri_map(self):
        result = _rewrite_tag_uri(
            '#EXT-X-MAP:URI="init.mp4"',
            "http://example.com/live/",
            "/proxy",
        )
        assert result is not None
        assert result.startswith("#EXT-X-MAP:URI=")
        encoded = result.split('URI="')[1].rstrip('"')
        decoded = base64.b64decode(encoded).decode()
        assert decoded == "http://example.com/live/init.mp4"

    def test_rewrite_tag_uri_no_match(self):
        assert _rewrite_tag_uri("#EXTINF:5.0,", "", "/proxy") is None

    def test_rewrite_bare_url_relative(self):
        result = _rewrite_bare_url("segment.ts", "http://x.com/live/", "/proxy")
        decoded = base64.b64decode(result.split("?url=")[1]).decode()
        assert decoded == "http://x.com/live/segment.ts"

    def test_rewrite_bare_url_absolute(self):
        result = _rewrite_bare_url("https://cdn.com/video.ts", "", "/proxy")
        decoded = base64.b64decode(result.split("?url=")[1]).decode()
        assert decoded == "https://cdn.com/video.ts"


class TestStreamProxyBreaker:
    """Circuit breaker behavior on StreamProxy."""

    @pytest.fixture
    def proxy(self):
        from iptv_check.infra.stream_proxy import StreamProxy
        p = StreamProxy()
        p._circuit_threshold = 2
        p._circuit_cooldown_secs = 30
        return p

    def test_initial_state(self, proxy):
        assert proxy._is_source_circuit_open("example.com") is False
        assert len(proxy._source_circuit_open) == 0

    def test_circuit_opens_after_threshold(self, proxy):
        proxy._record_source_error("example.com")
        proxy._record_source_error("example.com")
        assert proxy._is_source_circuit_open("example.com") is True

    def test_circuit_not_open_below_threshold(self, proxy):
        proxy._record_source_error("example.com")
        assert proxy._is_source_circuit_open("example.com") is False

    def test_success_resets_consecutive(self, proxy):
        proxy._record_source_error("example.com")
        proxy._record_source_ok("example.com")
        proxy._record_source_error("example.com")
        # Consecutive was reset, so only 1 consecutive error
        assert proxy._is_source_circuit_open("example.com") is False

    def test_circuit_cooldown(self, proxy):
        proxy._record_source_error("example.com")
        proxy._record_source_error("example.com")
        assert proxy._is_source_circuit_open("example.com") is True

        # Fast-forward past cooldown
        proxy._source_circuit_open["example.com"] = time.time() - 31
        assert proxy._is_source_circuit_open("example.com") is False

    def test_extract_domain_https(self, proxy):
        assert proxy._extract_domain("https://cdn.example.com/path/stream.m3u8") == "cdn.example.com"

    def test_extract_domain_http(self, proxy):
        assert proxy._extract_domain("http://hls.nntv.cn/nnlive/stream.m3u8") == "hls.nntv.cn"

    def test_extract_domain_with_port(self, proxy):
        assert proxy._extract_domain("http://localhost:8080/path") == "localhost"
