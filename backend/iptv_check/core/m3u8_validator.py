import logging
from urllib.parse import urljoin
from typing import Optional, Tuple

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
