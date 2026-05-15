"""
HLS Playlist URL Rewriter — standalone, testable module.

Rewrites segment and playlist URLs in M3U8 manifests so all requests
route through the proxy, avoiding cross-origin and referer issues.
"""
import base64
import re
import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# HLS tags whose values contain URIs that need rewriting
_URI_TAG_PATTERNS = [
    # #EXT-X-MAP:URI="init.mp4"
    (re.compile(r'^(#EXT-X-MAP:URI=")([^"]+)(".*)$', re.IGNORECASE), 2),
    # #EXT-X-KEY:URI="key.bin"
    (re.compile(r'^(#EXT-X-KEY:.*URI=")([^"]+)(".*)$', re.IGNORECASE), 2),
    # #EXT-X-I-FRAME-STREAM-INF:URI="..."
    (re.compile(r'^(#EXT-X-I-FRAME-STREAM-INF:.*URI=")([^"]+)(".*)$', re.IGNORECASE), 2),
    # #EXT-X-MEDIA:URI="..."
    (re.compile(r'^(#EXT-X-MEDIA:.*URI=")([^"]+)(".*)$', re.IGNORECASE), 2),
]

# Known segment extension patterns (used only for bare-segment detection)
_SEGMENT_EXTENSIONS = (".m3u8", ".ts", ".aac", ".mp4", ".mp3", ".m4s", ".m4a", ".m4v", ".vtt", ".webvtt")


def _encode_proxy_url(url: str, proxy_base: str) -> str:
    """Encode a target URL into a proxy URL."""
    encoded = base64.b64encode(url.encode("utf-8")).decode("utf-8")
    return f"{proxy_base}?url={encoded}"


def rewrite_hls_urls(
    playlist_content: str,
    original_url: str,
    proxy_base: str = "/proxy",
) -> str:
    """
    Rewrite all URLs in an M3U8 playlist to pass through the proxy.

    Handles:
      - Bare segment/playlist lines (e.g., ``segment-000.ts``)
      - Absolute HTTP(S) URLs
      - URI attributes in HLS tags (EXT-X-MAP, EXT-X-KEY, etc.)
      - Query parameters on segment URLs

    Args:
        playlist_content: Raw M3U8 manifest text.
        original_url: The URL from which this playlist was fetched (for resolving relative URLs).
        proxy_base: Base path of the proxy endpoint (default ``/proxy``).

    Returns:
        Rewritten M3U8 content with all segment/playlist URLs pointing through the proxy.
    """
    # Compute the base directory for resolving relative URLs
    base_url = original_url.rsplit("?", 1)[0].rsplit("/", 1)[0] + "/"

    rewritten_lines = []
    for line in playlist_content.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")

        # ── 1. Skip non-URL content ──
        if not stripped or stripped.startswith("#") and not _has_uri_attribute(stripped):
            rewritten_lines.append(line)
            continue

        # ── 2. HLS tag with URI attribute ──
        uri_rewritten = _rewrite_tag_uri(stripped, base_url, proxy_base)
        if uri_rewritten is not None:
            rewritten_lines.append(uri_rewritten + line[len(stripped):])
            continue

        # ── 3. Bare URL line (segment or variant playlist) ──
        rewritten_lines.append(_rewrite_bare_url(stripped, base_url, proxy_base) + line[len(stripped):])

    return "".join(rewritten_lines)


def _has_uri_attribute(line: str) -> bool:
    """Check if a tag line contains a URI attribute."""
    for pattern, _ in _URI_TAG_PATTERNS:
        if pattern.search(line):
            return True
    return False


def _rewrite_tag_uri(line: str, base_url: str, proxy_base: str) -> str | None:
    """Rewrite URI attribute values inside HLS tags. Returns None if no match."""
    for pattern, group_idx in _URI_TAG_PATTERNS:
        m = pattern.match(line)
        if m:
            uri = m.group(group_idx)
            new_uri = _resolve_and_encode(uri, base_url, proxy_base)
            return m.group(1) + new_uri + m.group(3)
    return None


def _rewrite_bare_url(line: str, base_url: str, proxy_base: str) -> str:
    """Rewrite a bare URL line (segment file, variant playlist, etc.)."""
    # Strip any leading/trailing whitespace
    url = line.strip()

    # Already an absolute HTTP URL
    if url.startswith(("http://", "https://")):
        return _encode_proxy_url(url, proxy_base)

    # Relative URL — resolve against the playlist base
    full_url = urljoin(base_url, url)
    return _encode_proxy_url(full_url, proxy_base)


def _resolve_and_encode(url: str, base_url: str, proxy_base: str) -> str:
    """Resolve a URL (possibly relative) and encode it for proxy."""
    if url.startswith(("http://", "https://")):
        full_url = url
    else:
        full_url = urljoin(base_url, url)
    encoded = base64.b64encode(full_url.encode("utf-8")).decode("utf-8")
    return encoded
