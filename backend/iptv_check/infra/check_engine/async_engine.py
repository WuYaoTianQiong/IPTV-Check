"""
异步检测引擎 (Async Check Engine)
使用 asyncio + aiohttp 替代 ThreadPoolExecutor
核心设计：基于 asyncio.Queue 的生产者-消费者模式
"""
import asyncio
import base64
import logging
import time
from typing import List, Optional, Callable

import aiohttp

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.check_engine.base import CheckEngineProtocol
from iptv_check.infra.check_engine.adaptive_controller import AdaptiveConcurrencyController
from iptv_check.core.m3u8_validator import M3U8Validator
from iptv_check.infra.config.settings import settings
from iptv_check.infra.event_bus import event_bus

logger = logging.getLogger(__name__)

_SENTINEL = object()
_UNSUPPORTED_PROTOCOLS = ("rtp://", "rtmp://")


class AsyncCheckEngine:
    """
    异步检测引擎 - 基于队列的生产者-消费者模式

    关键设计：
    1. _feed_channels 在所有频道入队后发送 _SENTINEL 结束标记
    2. 消费者循环收到 _SENTINEL 后等待所有 worker 任务完成，然后触发 on_complete
    3. 工作协程受 Semaphore 限流，防止连接过载
    4. 自适应并发控制根据超时率动态调整并发度
    """

    def __init__(self, http_session: aiohttp.ClientSession, cache, m3u8_validator: M3U8Validator,
                 proxy_base: str = ""):
        self._http = http_session
        self._cache = cache
        self._m3u8 = m3u8_validator
        self._proxy_base = proxy_base.rstrip("/")
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._stop_event = asyncio.Event()
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None
        self._worker_tasks: List[asyncio.Task] = []
        self._config: Optional[CheckConfig] = None
        self._on_result: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._on_cached_result: Optional[Callable] = None
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        self._last_progress_emit = 0.0
        self._adaptive_ctrl: Optional[AdaptiveConcurrencyController] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def adaptive_ctrl(self) -> Optional[AdaptiveConcurrencyController]:
        return self._adaptive_ctrl

    def start(self, channels: List[Channel], config: CheckConfig,
              on_result: Optional[Callable[[CheckResult], None]] = None,
              on_complete: Optional[Callable[[], None]] = None,
              on_cached_result: Optional[Callable[[CheckResult], None]] = None) -> None:
        self._running = True
        self._stop_event.clear()
        self._config = config
        self._on_result = on_result
        self._on_complete = on_complete
        self._on_cached_result = on_cached_result
        self._semaphore = asyncio.Semaphore(config.max_threads)
        self._worker_tasks = []
        self._adaptive_ctrl = AdaptiveConcurrencyController(
            max_threads=config.max_threads,
            min_threads=config.min_threads,
        )

        event_bus.emit("check:started")
        logger.info("[AsyncEngine] 启动检测, 初始频道=%d", len(channels))

        self._consumer_task = asyncio.create_task(self._consumer_loop())
        asyncio.create_task(self._feed_channels(channels))

    async def _feed_channels(self, channels: List[Channel]):
        """将频道送入检测队列，完成后发送结束标记"""
        try:
            queued = 0
            cached = 0
            for ch in channels:
                if self._stop_event.is_set():
                    break
                url_key = ch.url_key
                if self._config.use_cache and self._cache.has(url_key):
                    cached_result = self._cache.get(url_key)
                    result = CheckResult.from_cache(ch, cached_result)
                    if self._on_cached_result:
                        self._on_cached_result(result)
                    elif self._on_result:
                        self._on_result(result)
                    cached += 1
                else:
                    await self._queue.put(ch)
                    queued += 1

            logger.info("[AsyncEngine] 频道入队完成, 缓存命中=%d, 入队=%d", cached, queued)
        finally:
            await self._queue.put(_SENTINEL)

    async def _consumer_loop(self):
        """消费者循环：从队列取频道，提交检测任务"""
        logger.info("[AsyncEngine] _consumer_loop 启动")
        while not self._stop_event.is_set():
            ch = await self._queue.get()

            if ch is _SENTINEL:
                logger.info("[AsyncEngine] 收到_SENTINEL，消费者循环退出")
                self._queue.task_done()
                break

            task = asyncio.create_task(self._check_and_callback(ch))
            self._worker_tasks.append(task)
            self._queue.task_done()

        # 收到结束标记后，等待所有正在运行的检测任务完成
        logger.info("[AsyncEngine] 等待 %d 个 worker 任务完成", len(self._worker_tasks))
        if self._worker_tasks:
            results = await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("[AsyncEngine] 检测任务异常: %s", r)

        self._running = False
        event_bus.emit("check:completed")
        logger.info("[AsyncEngine] 所有检测完成, 共处理 %d 个任务", len(self._worker_tasks))
        if self._on_complete:
            logger.info("[AsyncEngine] 调用 on_complete 回调")
            self._on_complete()
            logger.info("[AsyncEngine] on_complete 回调完成")

    async def _check_and_callback(self, channel: Channel):
        """检测单个频道"""
        try:
            result = await self._check_single(channel)
        except Exception as e:
            result = CheckResult(channel=channel, timestamp=time.time())
            result.is_valid = False
            result.quality_tier = "invalid"
            result.details = f"检测异常: {str(e)[:30]}"

        if self._adaptive_ctrl:
            is_timeout = (result.details == "超时")
            new_threads = self._adaptive_ctrl.report_result(is_timeout)
            if new_threads is not None:
                self._semaphore = asyncio.Semaphore(new_threads)
                logger.info("[AsyncEngine] 信号量更新为 %d", new_threads)

        self._cache.set(channel.url_key, result.to_cache_dict())
        event_bus.emit("channel:checked", result=result)
        if self._on_result:
            self._on_result(result)

    def _maybe_proxy_url(self, url: str) -> str:
        """If proxy_base is set, encode the URL for the proxy endpoint."""
        if self._proxy_base:
            enc = base64.b64encode(url.encode("utf-8")).decode("utf-8")
            return f"{self._proxy_base}?url={enc}"
        return url

    @staticmethod
    def _validate_stream_header(data: bytes) -> bool:
        """Validate that data starts with a known stream format signature."""
        if not data or len(data) < 4:
            return False
        if data[0] == 0x47:
            return True
        if data[:3] == b"FLV":
            return True
        if len(data) >= 8 and data[4:8] == b"ftyp":
            return True
        if data[:4] == b"\x1a\x45\xdf\xa3":
            return True
        if data[:4] == b"OggS":
            return True
        return False

    @staticmethod
    def _handle_check_exception(exc: Exception, result: CheckResult) -> CheckResult:
        """将检测异常映射为CheckResult字段"""
        result.is_valid = False
        result.quality_tier = "invalid"
        if isinstance(exc, asyncio.TimeoutError):
            result.details = "超时"
        elif isinstance(exc, aiohttp.ClientSSLError):
            result.details = f"SSL证书错误: {str(exc)[:30]}"
        elif isinstance(exc, aiohttp.ClientConnectorError):
            err_str = str(exc).lower()
            if "dns" in err_str or "name resolution" in err_str:
                result.details = "DNS解析失败"
            elif "refused" in err_str:
                result.details = "连接被拒绝"
            elif "reset" in err_str:
                result.details = "连接被重置"
            else:
                result.details = "连接失败"
        elif isinstance(exc, aiohttp.ClientResponseError):
            if exc.status == 403:
                result.details = "访问被拒绝(403)"
            elif exc.status == 404:
                result.details = "资源不存在(404)"
            elif exc.status >= 500:
                result.details = f"服务器错误({exc.status})"
            else:
                result.details = f"HTTP错误({exc.status})"
        elif isinstance(exc, ValueError):
            result.details = str(exc)
        else:
            result.details = f"未知错误: {str(exc)[:30]}"
        return result

    async def _execute_check(self, channel: Channel) -> CheckResult:
        """执行单次检测核心逻辑（不含信号量和重试），返回设置好结果的CheckResult"""
        result = CheckResult(channel=channel, timestamp=time.time())
        start_time = time.time()

        timeout = aiohttp.ClientTimeout(
            total=self._config.timeout_connect + self._config.timeout_read,
            connect=self._config.timeout_connect,
            sock_read=self._config.timeout_read,
        )

        likely_m3u8 = channel.url.lower().endswith(".m3u8")
        fetch_url = self._maybe_proxy_url(channel.url) if likely_m3u8 else channel.url

        async with self._http.get(
            fetch_url,
            headers=self._headers,
            timeout=timeout,
            allow_redirects=True,
            ssl=False,
        ) as resp:
            resp.raise_for_status()
            latency = int((time.time() - start_time) * 1000)
            speed = "-"
            content_type = resp.headers.get("Content-Type", "").lower()
            is_m3u8 = "mpegurl" in content_type or likely_m3u8

            if self._config.run_speed_test:
                if is_m3u8:
                    playlist_content = await resp.text()
                    if not playlist_content.strip().startswith("#EXTM3U"):
                        raise ValueError("非标准M3U8内容")
                    speed = await self._m3u8.get_speed_async(
                        channel.url, playlist_content, self._headers,
                        self._config.timeout_connect, self._config.timeout_read,
                        http_session=self._http,
                        proxy_base=self._proxy_base,
                    )
                else:
                    speed = await self._test_speed_async(resp.content.iter_any(), self._config.timeout_read)
            else:
                if is_m3u8:
                    playlist_content = await resp.text()
                    if not playlist_content.strip().startswith("#EXTM3U"):
                        raise ValueError("非标准M3U8内容")
                    await self._m3u8.validate_recursive_async(
                        channel.url, playlist_content, self._headers,
                        self._config.timeout_connect, self._config.timeout_read,
                        http_session=self._http,
                        proxy_base=self._proxy_base,
                    )
                else:
                    chunk = await resp.content.read(65536)
                    if not chunk:
                        raise ValueError("无数据流")
                    if not self._validate_stream_header(chunk):
                        raise ValueError("非有效流数据")

            result.latency = latency
            result.speed = speed

            if self._config.run_speed_test and speed in ("-", "N/A"):
                result.is_valid = False
                result.quality_tier = "invalid"
                result.details = "流不可达" if not is_m3u8 else "分片不可达"
            elif latency > self._config.max_latency_ms * 2:
                result.is_valid = False
                result.quality_tier = "invalid"
                result.details = f"延迟过高 ({latency}ms > {self._config.max_latency_ms * 2}ms)"
            elif latency > self._config.max_latency_ms:
                result.is_valid = True
                result.quality_tier = "likely_valid"
                result.details = f"延迟偏高 ({latency}ms > {self._config.max_latency_ms}ms)"
            else:
                result.is_valid = True
                result.quality_tier = "valid"
                result.details = f"OK ({resp.status})"

            if is_m3u8 and result.is_valid:
                try:
                    segments = self._m3u8.find_all_segment_urls(playlist_content, channel.url, limit=4)
                    if len(segments) >= 2:

                        async def _check_segment(seg_url: str) -> bool:
                            try:
                                fetch_seg_url = self._maybe_proxy_url(seg_url)
                                async with self._http.get(
                                    fetch_seg_url, headers=self._headers,
                                    timeout=aiohttp.ClientTimeout(
                                        total=self._config.timeout_connect + min(self._config.timeout_read, 8),
                                        connect=self._config.timeout_connect,
                                        sock_read=min(self._config.timeout_read, 8),
                                    ),
                                    ssl=False, allow_redirects=True,
                                ) as seg_resp:
                                    seg_resp.raise_for_status()
                                    chunk = await seg_resp.content.read(1024)
                                    return bool(chunk)
                            except Exception:
                                return False

                        seg_results = await asyncio.gather(*[_check_segment(u) for u in segments[:3]])
                        ok_count = sum(1 for r in seg_results if r)
                        tested = min(len(segments), 3)
                        min_required = max(1, (tested + 2) // 3)
                        if ok_count < min_required:
                            result.is_valid = False
                            result.quality_tier = "invalid"
                            result.details = f"分段不可达 ({ok_count}/{tested})"
                except Exception:
                    pass

            if not is_m3u8 and result.is_valid:
                try:
                    sustained_ok = await self._sustained_stream_check(
                        channel.url, duration_secs=2,
                    )
                    if not sustained_ok:
                        result.is_valid = False
                        result.quality_tier = "invalid"
                        result.details = "流中断"
                except Exception:
                    pass

        return result

    async def _check_single(self, channel: Channel) -> CheckResult:
        """检测单个频道（含协议跳过、信号量限流、超时重试）"""
        result = CheckResult(channel=channel, timestamp=time.time())

        url_lower = channel.url.lower()
        if any(url_lower.startswith(proto) for proto in _UNSUPPORTED_PROTOCOLS):
            result.is_valid = False
            result.quality_tier = "invalid"
            result.details = "不支持该协议"
            logger.debug("[协议跳过] 频道=%s, 协议=%s", channel.name, channel.url.split("://")[0])
            return result

        async with self._semaphore:
            if self._stop_event.is_set():
                result.is_valid = False
                result.quality_tier = "invalid"
                result.details = "已停止"
                return result

            try:
                result = await self._execute_check(channel)
            except asyncio.TimeoutError:
                logger.debug("[重试] 频道=%s 首次超时，重试1次", channel.name)
                try:
                    if self._stop_event.is_set():
                        result.is_valid = False
                        result.quality_tier = "invalid"
                        result.details = "已停止"
                        return result
                    result = await self._execute_check(channel)
                except asyncio.TimeoutError:
                    result.is_valid = False
                    result.quality_tier = "invalid"
                    result.details = "超时"
                except Exception as retry_exc:
                    result = self._handle_check_exception(retry_exc, result)
            except Exception as e:
                result = self._handle_check_exception(e, result)

        return result

    async def _test_speed_async(self, content_iterator, timeout: int) -> str:
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
            return ""
        except Exception:
            return "N/A"

    async def _sustained_stream_check(self, url: str, duration_secs: int = 5) -> bool:
        """Verify a non-M3U8 stream continues to deliver data over time."""
        timeout = aiohttp.ClientTimeout(
            total=self._config.timeout_connect + duration_secs + 2,
            connect=self._config.timeout_connect,
            sock_read=duration_secs + 2,
        )
        try:
            fetch_url = self._maybe_proxy_url(url)
            async with self._http.get(
                fetch_url, headers=self._headers,
                timeout=timeout, allow_redirects=True, ssl=False,
            ) as resp:
                resp.raise_for_status()
                chunk_count = 0
                deadline = time.time() + duration_secs
                async for chunk in resp.content.iter_any():
                    if chunk:
                        chunk_count += 1
                    if chunk_count >= 2 or time.time() >= deadline:
                        break
                return chunk_count >= 2
        except Exception:
            return False

    def add_channels(self, channels: List[Channel], config: CheckConfig,
                     on_result: Optional[Callable[[CheckResult], None]] = None) -> None:
        """动态添加频道（不支持流式添加，仅兼容接口）"""
        if not self._running:
            logger.warning("[AsyncEngine] 引擎未运行，忽略 %d 个频道", len(channels))
            return
        if on_result:
            self._on_result = on_result
        asyncio.create_task(self._feed_channels(channels))
        logger.info("[AsyncEngine] 添加 %d 个频道到队列", len(channels))

    def stop(self) -> None:
        """停止检测"""
        self._stop_event.set()
        self._running = False
        event_bus.emit("check:stopped")
        logger.info("[AsyncEngine] 停止请求已发送")

    async def wait_complete(self):
        """等待所有检测完成"""
        if self._consumer_task:
            await self._consumer_task
