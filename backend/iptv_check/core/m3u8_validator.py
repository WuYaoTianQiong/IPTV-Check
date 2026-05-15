import asyncio
import base64
import logging
import time
from urllib.parse import urljoin
from typing import Optional, Tuple

import aiohttp

from iptv_check.infra.network import HttpClient

logger = logging.getLogger(__name__)


class M3U8Validator:
    def __init__(self, http_client: HttpClient):
        self._http = http_client

    def validate_recursive(self, base_url: str, playlist_content: str,
                           headers: dict, timeout: Tuple[int, int], depth: int = 0, max_depth: int = 5):
        if depth >= max_depth:
            return
        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            raise ValueError("M3U8无有效分片")

        with self._http.get(segment_url, headers=headers, timeout=timeout, stream=True) as r:
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "").lower()
            if "mpegurl" in content_type or segment_url.lower().endswith(".m3u8"):
                nested_playlist = r.text
                if nested_playlist.strip().startswith("#EXTM3U"):
                    self.validate_recursive(segment_url, nested_playlist, headers, timeout, depth + 1, max_depth)
            elif not next(r.iter_content(chunk_size=1024), None):
                raise ValueError("分片无数据")

    def get_speed(self, base_url: str, playlist_content: str,
                  headers: dict, timeout: Tuple[int, int]) -> str:
        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            return "-"

        try:
            with self._http.get(segment_url, headers=headers, timeout=timeout, stream=True) as seg_r:
                seg_r.raise_for_status()
                seg_content_type = seg_r.headers.get("Content-Type", "").lower()
                if "mpegurl" in seg_content_type or segment_url.lower().endswith(".m3u8"):
                    nested_playlist = seg_r.text
                    if nested_playlist.strip().startswith("#EXTM3U"):
                        nested_segment = self._find_segment_url(segment_url, nested_playlist)
                        if nested_segment:
                            with self._http.get(nested_segment, headers=headers, timeout=timeout, stream=True) as nested_r:
                                nested_r.raise_for_status()
                                return self._test_speed(nested_r.iter_content(chunk_size=8192), timeout[1])
                return self._test_speed(seg_r.iter_content(chunk_size=8192), timeout[1])
        except Exception:
            return "-"

    @staticmethod
    def _find_segment_url(base_url: str, playlist_content: str) -> Optional[str]:
        for line in playlist_content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return urljoin(base_url, line)
        return None

    @staticmethod
    def _test_speed(response_iterator, timeout: int) -> str:
        import time
        try:
            start_time = time.time()
            downloaded_size = 0
            for chunk in response_iterator:
                downloaded_size += len(chunk)
                if downloaded_size >= 256 * 1024:
                    break
                if time.time() - start_time > timeout / 2:
                    return "N/A"
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                return f"{(downloaded_size / 1024) / elapsed_time:.2f}"
            return "∞"
        except Exception:
            return "N/A"

    async def validate_recursive_async(self, base_url: str, playlist_content: str,
                                       headers: dict, timeout_connect: int, timeout_read: int,
                                       depth: int = 0, max_depth: int = 5, http_session: aiohttp.ClientSession = None,
                                       proxy_base: str = ""):
        if depth >= max_depth:
            return
        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            raise ValueError("M3U8无有效分片")

        if http_session is None:
            raise ValueError("http_session is required for async validation")

        segment_url = self._maybe_proxy_url(segment_url, proxy_base)

        timeout = aiohttp.ClientTimeout(
            total=timeout_connect + timeout_read,
            connect=timeout_connect,
            sock_read=timeout_read,
        )
        async with http_session.get(segment_url, headers=headers, timeout=timeout, ssl=False) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").lower()
            if "mpegurl" in content_type or segment_url.lower().endswith(".m3u8"):
                nested_playlist = await resp.text()
                if nested_playlist.strip().startswith("#EXTM3U"):
                    await self.validate_recursive_async(segment_url, nested_playlist, headers, timeout_connect, timeout_read, depth + 1, max_depth, http_session)
            else:
                chunk = await resp.content.read(1024)
                if not chunk:
                    raise ValueError("分片无数据")

    def _maybe_proxy_url(self, url: str, proxy_base: str) -> str:
        """If proxy_base is set, encode the URL for the proxy endpoint."""
        if proxy_base:
            enc = base64.b64encode(url.encode("utf-8")).decode("utf-8")
            return f"{proxy_base}?url={enc}"
        return url

    async def get_speed_async(self, base_url: str, playlist_content: str,
                              headers: dict, timeout_connect: int, timeout_read: int,
                              http_session: aiohttp.ClientSession = None,
                              proxy_base: str = "") -> str:
        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            return "-"

        if http_session is None:
            raise ValueError("http_session is required for async speed test")

        segment_url = self._maybe_proxy_url(segment_url, proxy_base)

        timeout = aiohttp.ClientTimeout(
            total=timeout_connect + timeout_read,
            connect=timeout_connect,
            sock_read=timeout_read,
        )
        try:
            async with http_session.get(segment_url, headers=headers, timeout=timeout, ssl=False) as seg_resp:
                seg_resp.raise_for_status()
                seg_content_type = seg_resp.headers.get("Content-Type", "").lower()
                if "mpegurl" in seg_content_type or segment_url.lower().endswith(".m3u8"):
                    nested_playlist = await seg_resp.text()
                    if nested_playlist.strip().startswith("#EXTM3U"):
                        nested_segment = self._find_segment_url(segment_url, nested_playlist)
                        if nested_segment:
                            async with http_session.get(nested_segment, headers=headers, timeout=timeout, ssl=False) as nested_resp:
                                nested_resp.raise_for_status()
                                return await self._test_speed_async(nested_resp.content.iter_any(), timeout_read)
                return await self._test_speed_async(seg_resp.content.iter_any(), timeout_read)
        except Exception:
            return "-"

    @staticmethod
    async def validate_segment_through_proxy(
        segment_url: str,
        proxy_base: str,
        http_session: aiohttp.ClientSession,
        timeout_connect: int,
        timeout_read: int,
    ) -> int:
        """
        Validate that a single segment is reachable through the proxy path.
        This mimics the actual playback path, ensuring "pass = playable."

        Returns the HTTP status code, or raises on failure.
        """
        import base64 as _b64
        proxy_url = f"{proxy_base}?url={_b64.b64encode(segment_url.encode('utf-8')).decode('utf-8')}"
        timeout = aiohttp.ClientTimeout(
            total=timeout_connect + timeout_read,
            connect=timeout_connect,
            sock_read=min(timeout_read, 10),  # cap per-segment read at 10s
        )
        async with http_session.get(proxy_url, timeout=timeout, ssl=False, allow_redirects=True) as resp:
            resp.raise_for_status()
            # Consume at least 1KB to verify data flow
            chunk = await resp.content.read(1024)
            if not chunk:
                raise ValueError("分片无数据")
            return resp.status

    @staticmethod
    def find_all_segment_urls(playlist_content: str, base_url: str, limit: int = 5) -> list[str]:
        """Extract up to `limit` segment URLs from an M3U8 playlist."""
        segments = []
        from urllib.parse import urljoin as _urljoin
        for line in playlist_content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                segments.append(_urljoin(base_url, line))
                if len(segments) >= limit:
                    break
        return segments

    @staticmethod
    async def _test_speed_async(content_iterator, timeout: int) -> str:
        try:
            start_time = time.time()
            downloaded_size = 0
            async for chunk in content_iterator:
                downloaded_size += len(chunk)
                if downloaded_size >= 256 * 1024:
                    break
                if time.time() - start_time > timeout / 2:
                    return "N/A"
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                return f"{(downloaded_size / 1024) / elapsed_time:.2f}"
            return "∞"
        except Exception:
            return "N/A"
