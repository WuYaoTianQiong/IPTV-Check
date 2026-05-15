"""
流式检测引擎 (Stream Check Engine)
基于 asyncio.Queue 的生产者-消费者模式
核心设计：频道加载与检测完全解耦，支持流式处理
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
from iptv_check.infra.event_bus import event_bus

logger = logging.getLogger(__name__)

_SENTINEL = None  # 队列结束标记


class StreamCheckEngine:
    """
    流式检测引擎 - 生产者消费者模式

    架构设计：
    ┌─────────────┐    asyncio.Queue    ┌─────────────┐
    │  频道生产者   │ ─────────────────→ │  检测消费者   │
    │             │                     │             │
    │ • 本地文件   │   Channel / None    │ • 异步检测   │
    │ • 在线源下载 │   (None = 结束)     │ • 限流控制   │
    │ • 去重过滤   │                     │ • 结果回调   │
    └─────────────┘                     └─────────────┘

    关键特性：
    1. 生产与消费完全解耦 - 频道边加载边检测
    2. 支持动态追加频道 - 在线源异步下载不影响检测
    3. 优雅关闭 - 等待队列清空后才触发完成
    4. 背压保护 - 队列满时生产者等待
    """

    def __init__(self, http_session: aiohttp.ClientSession, cache, m3u8_validator: M3U8Validator):
        self._http = http_session
        self._cache = cache
        self._m3u8 = m3u8_validator
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._stop_event = asyncio.Event()
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._consumer_task: Optional[asyncio.Task] = None
        self._config: Optional[CheckConfig] = None
        self._on_result: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, channels: List[Channel], config: CheckConfig,
              on_result: Optional[Callable[[CheckResult], None]] = None,
              on_complete: Optional[Callable[[], None]] = None) -> None:
        """启动检测引擎"""
        self._running = True
        self._stop_event.clear()
        self._config = config
        self._on_result = on_result
        self._on_complete = on_complete
        self._semaphore = asyncio.Semaphore(config.max_threads)
        self._worker_tasks = []

        event_bus.emit("check:started")
        logger.info("[StreamEngine] 启动检测, 初始频道=%d", len(channels))

        self._consumer_task = asyncio.create_task(self._consumer_loop())

        asyncio.create_task(self._feed_channels(channels))

    async def _feed_channels(self, channels: List[Channel]):
        """将初始频道送入队列"""
        for ch in channels:
            if self._stop_event.is_set():
                break
            url_key = ch.url_key
            if self._config.use_cache and self._cache.has(url_key):
                cached = self._cache.get(url_key)
                result = CheckResult.from_cache(ch, cached)
                if self._on_result:
                    self._on_result(result)
            else:
                await self._queue.put(ch)

    async def _consumer_loop(self):
        """消费者循环：从队列取频道，提交检测任务"""
        worker_count = 0
        active_count = 0

        while self._running and not self._stop_event.is_set():
            try:
                ch = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if ch is _SENTINEL:
                self._queue.task_done()
                break

            if self._config.use_cache and self._cache.has(ch.url_key):
                cached = self._cache.get(ch.url_key)
                result = CheckResult.from_cache(ch, cached)
                if self._on_result:
                    self._on_result(result)
                self._queue.task_done()
                continue

            task = asyncio.create_task(self._check_and_callback(ch))
            self._worker_tasks.append(task)
            active_count += 1

        logger.info("[StreamEngine] 消费者循环结束, 活跃任务=%d", active_count)

    async def _check_and_callback(self, channel: Channel):
        """检测单个频道并回调"""
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
        """检测单个频道"""
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
                            )
                        else:
                            chunk = await resp.content.read(1024)
                            if not chunk:
                                raise ValueError("无数据流")

                    result.is_valid = True
                    result.latency = latency
                    result.speed = speed
                    result.details = f"OK ({resp.status})"

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
            return "∞"
        except Exception:
            return "N/A"

    def add_channels(self, channels: List[Channel], config: CheckConfig,
                     on_result: Optional[Callable[[CheckResult], None]] = None) -> None:
        """动态添加频道到队列"""
        if not self._running:
            return
        asyncio.create_task(self._feed_channels(channels))
        logger.info("[StreamEngine] 添加 %d 个频道到队列", len(channels))

    def stop(self) -> None:
        """停止检测"""
        self._stop_event.set()
        self._running = False
        event_bus.emit("check:stopped")
        logger.info("[StreamEngine] 停止请求已发送")

    async def wait_complete(self):
        """等待所有检测完成"""
        if self._consumer_task:
            await self._consumer_task

        if self._worker_tasks:
            results = await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("[StreamEngine] 检测任务异常: %s", r)

        self._running = False
        event_bus.emit("check:completed")
        logger.info("[StreamEngine] 所有检测完成")

        if self._on_complete:
            self._on_complete()
