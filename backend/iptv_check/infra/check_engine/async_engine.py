"""
异步检测引擎 (Async Check Engine)
使用 asyncio + aiohttp 替代 ThreadPoolExecutor
核心设计：基于 asyncio.Queue 的生产者-消费者模式
"""
import asyncio
import logging
import time
from typing import List, Optional, Callable

import aiohttp

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.check_engine.base import CheckEngineProtocol
from iptv_check.core.m3u8_validator import M3U8Validator
from iptv_check.infra.config.settings import settings
from iptv_check.infra.event_bus import event_bus

logger = logging.getLogger(__name__)

_SENTINEL = object()


class AsyncCheckEngine:
    """
    异步检测引擎 - 基于队列的生产者-消费者模式

    关键设计：
    1. _feed_channels 在所有频道入队后发送 _SENTINEL 结束标记
    2. 消费者循环收到 _SENTINEL 后等待所有 worker 任务完成，然后触发 on_complete
    3. 工作协程受 Semaphore 限流，防止连接过载
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
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        self._last_progress_emit = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, channels: List[Channel], config: CheckConfig,
              on_result: Optional[Callable[[CheckResult], None]] = None,
              on_complete: Optional[Callable[[], None]] = None) -> None:
        self._running = True
        self._stop_event.clear()
        self._config = config
        self._on_result = on_result
        self._on_complete = on_complete
        self._semaphore = asyncio.Semaphore(config.max_threads)
        self._worker_tasks = []

        event_bus.emit("check:started")
        logger.info("[AsyncEngine] 启动检测, 初始频道=%d", len(channels))

        self._consumer_task = asyncio.create_task(self._consumer_loop())
        asyncio.create_task(self._feed_channels(channels))

    async def _feed_channels(self, channels: List[Channel]):
        """将频道送入检测队列，完成后发送结束标记"""
        queued = 0
        cached = 0
        for ch in channels:
            if self._stop_event.is_set():
                break
            url_key = ch.url_key
            if self._config.use_cache and self._cache.has(url_key):
                cached_result = self._cache.get(url_key)
                result = CheckResult.from_cache(ch, cached_result)
                if self._on_result:
                    self._on_result(result)
                cached += 1
            else:
                await self._queue.put(ch)
                queued += 1

        logger.info("[AsyncEngine] 频道入队完成, 缓存命中=%d, 入队=%d", cached, queued)
        # 关键：发送结束标记，让消费者循环知道没有更多频道了
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
            result.details = f"检测异常: {str(e)[:30]}"

        self._cache.set(channel.url_key, result.to_cache_dict())
        event_bus.emit("channel:checked", result=result)
        if self._on_result:
            self._on_result(result)

    async def _check_single(self, channel: Channel) -> CheckResult:
        """检测单个频道（核心逻辑）"""
        result = CheckResult(channel=channel, timestamp=time.time())
        start_time = time.time()

        async with self._semaphore:
            if self._stop_event.is_set():
                result.is_valid = False
                result.details = "已停止"
                return result

            try:
                timeout = aiohttp.ClientTimeout(
                    total=self._config.timeout_connect + self._config.timeout_read,
                    connect=self._config.timeout_connect,
                    sock_read=self._config.timeout_read,
                )

                async with self._http.get(
                    channel.url,
                    headers=self._headers,
                    timeout=timeout,
                    allow_redirects=True,
                    ssl=False,
                ) as resp:
                    resp.raise_for_status()
                    latency = int((time.time() - start_time) * 1000)
                    speed = "-"
                    content_type = resp.headers.get("Content-Type", "").lower()
                    is_m3u8 = "mpegurl" in content_type or channel.url.lower().endswith(".m3u8")

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
                            chunk = await resp.content.read(1024)
                            if not chunk:
                                raise ValueError("无数据流")

                    result.latency = latency
                    result.speed = speed

                    # Speed test returning "-" means segment download failed through proxy
                    # This indicates the stream is not playable even if the M3U8 is reachable
                    if self._config.run_speed_test and is_m3u8 and speed in ("-", "N/A"):
                        result.is_valid = False
                        result.details = "分片不可达"
                    elif latency > self._config.max_latency_ms:
                        result.is_valid = False
                        result.details = f"延迟过高 ({latency}ms > {self._config.max_latency_ms}ms)"
                    else:
                        result.is_valid = True
                        result.details = f"OK ({resp.status})"

                    # Proxy-aware multi-segment validation.
                    # Downloads multiple segments (not just the first) to catch
                    # CDN rate-limiting, geo-blocking, or intermittent failures
                    # that wouldn't show in a 1KB single-segment check.
                    if is_m3u8:
                        try:
                            segments = self._m3u8.find_all_segment_urls(playlist_content, channel.url, limit=4)
                            if len(segments) >= 1:
                                ok_count = 0
                                for seg_url in segments[:3]:
                                    try:
                                        import base64 as _b64
                                        fetch_seg_url = f"{self._proxy_base}?url={_b64.b64encode(seg_url.encode('utf-8')).decode('utf-8')}" if self._proxy_base else seg_url
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
                                            if chunk:
                                                ok_count += 1
                                    except Exception:
                                        pass
                                # If fewer than half of the tested segments work, mark as invalid
                                tested = min(len(segments), 3)
                                if ok_count < max(1, tested // 2):
                                    result.is_valid = False
                                    result.details = f"分段不可达 ({ok_count}/{tested})"
                        except Exception:
                            pass

            except asyncio.TimeoutError:
                result.details = "超时"
                result.is_valid = False
            except aiohttp.ClientSSLError as e:
                result.details = f"SSL证书错误: {str(e)[:30]}"
                result.is_valid = False
            except aiohttp.ClientConnectorError as e:
                err_str = str(e).lower()
                if "dns" in err_str or "name resolution" in err_str:
                    result.details = "DNS解析失败"
                elif "refused" in err_str:
                    result.details = "连接被拒绝"
                elif "reset" in err_str:
                    result.details = "连接被重置"
                else:
                    result.details = "连接失败"
                result.is_valid = False
            except aiohttp.ClientResponseError as e:
                if e.status == 403:
                    result.details = "访问被拒绝(403)"
                elif e.status == 404:
                    result.details = "资源不存在(404)"
                elif e.status >= 500:
                    result.details = f"服务器错误({e.status})"
                else:
                    result.details = f"HTTP错误({e.status})"
                result.is_valid = False
            except ValueError as e:
                result.details = str(e)
                result.is_valid = False
            except Exception as e:
                result.details = f"未知错误: {str(e)[:30]}"
                result.is_valid = False

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

    def add_channels(self, channels: List[Channel], config: CheckConfig,
                     on_result: Optional[Callable[[CheckResult], None]] = None) -> None:
        """动态添加频道（不支持流式添加，仅兼容接口）"""
        if not self._running:
            logger.warning("[AsyncEngine] 引擎未运行，忽略 %d 个频道", len(channels))
            return
        if on_result:
            self._on_result = on_result
        # 注意：add_channels 不会发送 sentinel，只用于兼容旧接口
        # 实际检测由 start() 一次性启动
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
