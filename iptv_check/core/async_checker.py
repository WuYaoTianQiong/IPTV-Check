import asyncio
import logging
import time
from typing import List, Optional, Callable, Awaitable
from urllib.parse import urlparse

import aiohttp

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.error_strategy import ErrorClassifier, ErrorCategory
from iptv_check.infra.media_probe import MediaProbe, StreamProbeResult

logger = logging.getLogger(__name__)


class AsyncCheckEngine:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        cache,
        use_media_probe: bool = False,
        media_probe_timeout: float = 10.0,
    ):
        self._session = session
        self._cache = cache
        self._use_media_probe = use_media_probe and MediaProbe.is_ffmpeg_available()
        self._media_probe = MediaProbe(timeout=media_probe_timeout) if self._use_media_probe else None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._running = False

    async def check_channel(self, channel: Channel, config: CheckConfig) -> CheckResult:
        result = CheckResult(channel=channel, timestamp=time.time())
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        }
        start_time = time.time()

        async with self._semaphore:
            try:
                timeout = aiohttp.ClientTimeout(
                    connect=config.timeout_connect,
                    sock_read=config.timeout_read,
                    total=config.timeout_connect + config.timeout_read,
                )

                async with self._session.get(
                    channel.url,
                    headers=headers,
                    timeout=timeout,
                    ssl=False,
                    allow_redirects=True,
                ) as response:
                    response.raise_for_status()
                    latency = int((time.time() - start_time) * 1000)
                    content_type = response.headers.get("Content-Type", "").lower()
                    is_m3u8 = "mpegurl" in content_type or channel.url.lower().endswith(".m3u8")

                    if config.run_speed_test:
                        speed = await self._test_speed_streaming(response, is_m3u8, channel.url, headers, config)
                    else:
                        if is_m3u8:
                            playlist_content = await response.text()
                            if not playlist_content.strip().startswith("#EXTM3U"):
                                raise ValueError("非标准M3U8内容")
                            await self._validate_m3u8_recursive(channel.url, playlist_content, headers, config)
                        else:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                raise ValueError("无数据流")

                    if self._use_media_probe and is_m3u8:
                        probe_result = await self._media_probe.probe(channel.url)
                        if not probe_result.is_playable:
                            result.is_valid = False
                            result.details = f"流不可播放: {probe_result.error_message}"
                            logger.debug("媒体探针失败 %s: %s", channel.name, probe_result.error_message)
                            result.timestamp = time.time()
                            return result

                    result.is_valid = True
                    result.latency = latency
                    result.speed = speed if config.run_speed_test else "-"
                    result.details = f"OK ({response.status})"
                    if self._use_media_probe and is_m3u8:
                        result.details += f" - {probe_result.summary()}"

            except Exception as e:
                error_info = ErrorClassifier.classify(e)
                result.is_valid = False
                result.details = error_info.message
                logger.debug("检测失败 %s: %s", channel.name, error_info.message)

            result.timestamp = time.time()
            return result

    async def _validate_m3u8_recursive(
        self,
        base_url: str,
        playlist_content: str,
        headers: dict,
        config: CheckConfig,
        depth: int = 0,
        max_depth: int = 5,
    ) -> None:
        if depth >= max_depth:
            return

        segment_url = self._find_segment_url(base_url, playlist_content)
        if not segment_url:
            raise ValueError("M3U8无有效分片")

        timeout = aiohttp.ClientTimeout(
            connect=config.timeout_connect,
            sock_read=config.timeout_read,
        )

        async with self._session.get(
            segment_url,
            headers=headers,
            timeout=timeout,
            ssl=False,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "mpegurl" in content_type or segment_url.lower().endswith(".m3u8"):
                nested_content = await response.text()
                if nested_content.strip().startswith("#EXTM3U"):
                    await self._validate_m3u8_recursive(
                        segment_url, nested_content, headers, config, depth + 1, max_depth
                    )
            else:
                chunk = await response.content.read(1024)
                if not chunk:
                    raise ValueError("分片无数据")

    async def _test_speed_streaming(
        self,
        response,
        is_m3u8: bool,
        base_url: str,
        headers: dict,
        config: CheckConfig,
    ) -> str:
        if is_m3u8:
            playlist_content = await response.text()
            segment_url = self._find_segment_url(base_url, playlist_content)
            if not segment_url:
                return "-"

            timeout = aiohttp.ClientTimeout(
                connect=config.timeout_connect,
                sock_read=config.timeout_read,
            )

            try:
                async with self._session.get(
                    segment_url,
                    headers=headers,
                    timeout=timeout,
                    ssl=False,
                ) as seg_response:
                    seg_response.raise_for_status()
                    seg_content_type = seg_response.headers.get("Content-Type", "").lower()

                    if "mpegurl" in seg_content_type or segment_url.lower().endswith(".m3u8"):
                        nested_content = await seg_response.text()
                        if nested_content.strip().startswith("#EXTM3U"):
                            nested_url = self._find_segment_url(segment_url, nested_content)
                            if nested_url:
                                return await self._measure_download_speed(nested_url, headers, config)

                    return await self._measure_download_speed_from_response(seg_response)
            except Exception:
                return "-"
        else:
            return await self._measure_download_speed_from_response(response)

    async def _measure_download_speed(self, url: str, headers: dict, config: CheckConfig) -> str:
        timeout = aiohttp.ClientTimeout(
            connect=config.timeout_connect,
            sock_read=config.timeout_read,
        )

        async with self._session.get(url, headers=headers, timeout=timeout, ssl=False) as response:
            response.raise_for_status()
            return await self._measure_download_speed_from_response(response)

    async def _measure_download_speed_from_response(self, response) -> str:
        start_time = time.time()
        downloaded_size = 0

        try:
            async for chunk in response.content.iter_chunked(8192):
                downloaded_size += len(chunk)
                if downloaded_size >= 256 * 1024:
                    break
                if time.time() - start_time > response.timeout.sock_read / 2:
                    return "N/A"
        except Exception:
            return "N/A"

        elapsed = time.time() - start_time
        if elapsed > 0:
            speed_kbps = (downloaded_size / 1024) / elapsed
            return f"{speed_kbps:.2f}"
        return "∞"

    @staticmethod
    def _find_segment_url(base_url: str, playlist_content: str) -> Optional[str]:
        from urllib.parse import urljoin

        for line in playlist_content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return urljoin(base_url, line)
        return None

    async def start(
        self,
        channels: List[Channel],
        config: CheckConfig,
        on_result: Optional[Callable[[CheckResult], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        if self._running:
            logger.warning("检测引擎正在运行")
            return

        self._running = True
        self._semaphore = asyncio.Semaphore(config.max_threads)

        try:
            tasks = []
            for channel in channels:
                url_key = channel.url_key
                if config.use_cache and self._cache.has(url_key):
                    cached = self._cache.get(url_key)
                    result = CheckResult.from_cache(channel, cached)
                    if on_result:
                        on_result(result)
                else:
                    task = asyncio.create_task(
                        self._check_with_callback(channel, config, on_result)
                    )
                    tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    logger.error("检测任务异常: %s", r)

            if on_complete:
                on_complete()

        finally:
            self._running = False

    async def _check_with_callback(
        self,
        channel: Channel,
        config: CheckConfig,
        on_result: Optional[Callable[[CheckResult], None]] = None,
    ) -> None:
        result = await self.check_channel(channel, config)
        url_key = channel.url_key
        self._cache.set(url_key, result.to_cache_dict())
        if on_result:
            on_result(result)

    async def stop(self) -> None:
        self._running = False
