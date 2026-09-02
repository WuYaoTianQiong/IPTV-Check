"""
异步检测引擎 (Async Check Engine)
使用 asyncio + aiohttp 替代 ThreadPoolExecutor
核心设计：基于 asyncio.Queue 的生产者-消费者模式
"""
import asyncio
import logging
import re
import time
from typing import List, Optional, Callable

import aiohttp

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig, CheckMode
from iptv_check.infra.check_engine.base import CheckEngineProtocol
from iptv_check.infra.check_engine.adaptive_controller import AdaptiveConcurrencyController
from iptv_check.core.m3u8_validator import M3U8Validator
from iptv_check.infra.config.settings import settings
from iptv_check.infra.proxy_url import encode_proxy_url
from iptv_check.infra.speed_measure import measure_speed_async
from iptv_check.infra.config import source_filter
from iptv_check.infra.event_bus import event_bus, Events

logger = logging.getLogger(__name__)

_SENTINEL = object()
_UNSUPPORTED_PROTOCOLS = ("rtp://", "rtmp://")
# 检测结果缓存有效期：直播源可用性变化快，缓存过长会把一次污染结果(如被源站限流
# 误判的 invalid)长期复用，导致重测结果永远不变。6h 内重复检测加速，超时后重新探测。
_CHECK_RESULT_CACHE_TTL = 6 * 3600
# 检测结果缓存版本号：电视/电台判定逻辑（media_type 推断/CODECS 解析/TS PMT 解析等）
# 变化时必须递增，使旧版本 key 失配自动作废——否则"改了代码重测却命中旧缓存"，
# 新逻辑永远不生效。当前从"无版本号(纯启发式)"升级为 v1(media_type 事实判定)。
_CHECK_RESULT_CACHE_VERSION = 1


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
        # 流式批次支持：_pending_feeds 记录尚未入队完成的批次，_feed_open 标记是否还可继续添加批次
        self._pending_feeds = 0
        self._feed_open = True

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def adaptive_ctrl(self) -> Optional[AdaptiveConcurrencyController]:
        return self._adaptive_ctrl

    def start(self, channels: List[Channel], config: CheckConfig,
              on_result: Optional[Callable[[CheckResult], None]] = None,
              on_complete: Optional[Callable[[], None]] = None,
              on_cached_result: Optional[Callable[[CheckResult], None]] = None,
              streaming: bool = False) -> None:
        """
        启动检测引擎。

        streaming=False（默认）：单批次喂入，本批次入队完成后自动发送结束标记（兼容旧行为）。
        streaming=True：支持后续通过 add_channels 流式添加批次，需显式调用 complete() 结束。
        """
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
        self._pending_feeds = 0
        self._feed_open = streaming

        event_bus.emit(Events.CHECK_STARTED)
        logger.info("[AsyncEngine] 启动检测, 初始频道=%d, streaming=%s", len(channels), streaming)

        self._consumer_task = asyncio.create_task(self._consumer_loop())
        self._add_feed_batch(channels)

    def _add_feed_batch(self, channels: List[Channel]):
        """登记一个待入队的频道批次并异步入队"""
        self._pending_feeds += 1
        asyncio.create_task(self._feed_channels(channels))

    async def _feed_channels(self, channels: List[Channel]):
        """将频道送入检测队列"""
        try:
            queued = 0
            cached = 0
            blocked_count = 0
            for ch in channels:
                if self._stop_event.is_set():
                    break
                # 黑名单预检：在缓存/入队之前拦截，不发起任何 HTTP 请求
                blocked = source_filter.match(ch.url)
                if blocked:
                    result = CheckResult(channel=ch, timestamp=time.time())
                    result.is_valid = False
                    result.quality_tier = "invalid"
                    result.details = f"已拦截（风险源: {blocked}）"
                    if self._on_result:
                        self._on_result(result)
                    blocked_count += 1
                    continue
                url_key = ch.url_key
                # 缓存 key 区分检测方案：QUICK/STANDARD/DEEP 深度不同，结果不能互相复用
                # （否则 DEEP 细筛会命中 QUICK 粗筛缓存，跳过拉流验证与测速）。
                # 前置版本号：判定逻辑升级后旧缓存自动失配作废。
                cache_key = f"{_CHECK_RESULT_CACHE_VERSION}:{self._config.effective_mode.value}:{url_key}"
                if self._config.use_cache and self._cache.has(cache_key):
                    cached_result = self._cache.get(cache_key)
                    result = CheckResult.from_cache(ch, cached_result)
                    if self._on_cached_result:
                        self._on_cached_result(result)
                    elif self._on_result:
                        self._on_result(result)
                    cached += 1
                else:
                    await self._queue.put(ch)
                    queued += 1

            logger.info(
                "[AsyncEngine] 频道入队完成, 缓存命中=%d, 入队=%d, 黑名单拦截=%d",
                cached, queued, blocked_count,
            )
        finally:
            self._pending_feeds -= 1
            self._maybe_sentinel()

    def _maybe_sentinel(self):
        """所有批次入队完成且不再接受新批次时，发送结束标记"""
        if not self._feed_open and self._pending_feeds <= 0:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._queue.put(_SENTINEL))
            else:
                logger.warning("[AsyncEngine] 无运行中的事件循环，无法发送完成标记")

    def complete(self):
        """流式模式：停止接受新批次，待已入队频道全部检测完后触发 on_complete"""
        self._feed_open = False
        self._maybe_sentinel()
        logger.info("[AsyncEngine] 完成信号已提交")

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
        event_bus.emit(Events.CHECK_COMPLETED)
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
            # 限流/拥塞信号：除了超时，源站返回 429、服务器主动断开连接、
            # 连接被拒/重置/失败都说明当前并发对源站过于激进，应触发降并发。
            # 2026-09-01 实测：2.8 万频道仅靠 120 并发打崩源站，4859 个 429 + 9576 个断连
            # 导致大量误判无效，故将这些信号纳入自适应降速统计。
            is_failure = (
                result.details == "超时"
                or "429" in (result.details or "")
                or result.details in (
                    "服务器断开连接",
                    "连接被拒绝",
                    "连接被重置",
                    "连接失败",
                )
            )
            new_threads = self._adaptive_ctrl.report_result(is_failure)
            if new_threads is not None:
                self._semaphore = asyncio.Semaphore(new_threads)
                logger.info("[AsyncEngine] 信号量更新为 %d", new_threads)

        cache_key = f"{_CHECK_RESULT_CACHE_VERSION}:{self._config.effective_mode.value}:{channel.url_key}"
        self._cache.set(cache_key, result.to_cache_dict(), ttl=_CHECK_RESULT_CACHE_TTL)
        event_bus.emit(Events.CHANNEL_CHECKED, result=result)
        if self._on_result:
            self._on_result(result)

    def _maybe_proxy_url(self, url: str) -> str:
        """If proxy_base is set, encode the URL for the proxy endpoint."""
        if self._proxy_base:
            return encode_proxy_url(url, self._proxy_base)
        return url

    @staticmethod
    def _detect_media_type(data: bytes) -> str:
        """从流首包字节判断媒体类型，仅返回高置信结论：'video' / 'audio' / ''。

        2026-09-02: 容器格式(TS/fMP4/WebM)无法从首包区分纯音频与视频
        （纯音频电台 HLS 也封装在 TS/fMP4 中），故一律返回 '' 不参与判定，
        避免把纯音频电台误判为电视；此类流改由 HLS CODECS 声明或启发式兜底。
        """
        if not data or len(data) < 4:
            return ""
        if data[0] == 0x47:  # MPEG-TS：解析 PAT/PMT 判断是否含视频轨（纯音频电台也用TS封装）
            return AsyncCheckEngine._detect_ts_media_type(data)
        # 明确视频封装
        if data[:3] == b"FLV":  # FLV 基本必含视频轨
            return "video"
        if data[:4] == b"OggS":  # Ogg：Theora=视频，否则(Vorbis/Opus)=音频
            return "video" if b"theora" in data[:128] else "audio"
        # 明确音频格式（裸流）
        if data[:3] == b"ID3":  # MP3 (ID3 tag)
            return "audio"
        if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:  # MP3 / AAC(ADTS) 帧头
            return "audio"
        if data[:4] == b"fLaC":  # FLAC
            return "audio"
        if data[:8] == b"OpusHead":  # Opus (裸流)
            return "audio"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":  # WAV
            return "audio"
        return ""

    @staticmethod
    def _validate_stream_header(data: bytes) -> bool:
        """Validate that data starts with a known stream format signature.

        2026-09-01: 增加音频流与 M3U8 文本识别。此前只认视频封装头
        (TS/FLV/MP4/WebM/OggS)，导致大量广播电台音频流(MP3/AAC/FLAC/Opus 等)
        被误判为"非有效流数据"——实测一轮检测 11399 个误判全部是音频流。
        """
        if not data or len(data) < 4:
            return False
        # 视频封装
        if data[0] == 0x47:  # MPEG-TS
            return True
        if data[:3] == b"FLV":
            return True
        if len(data) >= 8 and data[4:8] in (b"ftyp", b"styp"):  # MP4 / fMP4(分片)
            return True
        if data[:4] == b"\x1a\x45\xdf\xa3":  # WebM/Matroska
            return True
        if data[:4] == b"OggS":  # Ogg (含 Opus/Vorbis 容器)
            return True
        # 音频格式
        if data[:3] == b"ID3":  # MP3 (ID3 tag)
            return True
        if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:  # MP3 / AAC(ADTS) 帧头
            return True
        if data[:4] == b"fLaC":  # FLAC
            return True
        if data[:8] == b"OpusHead":  # Opus (裸流)
            return True
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":  # WAV
            return True
        # M3U8/HLS 播放列表文本（部分源 content-type 非 mpegurl 且 URL 无 .m3u8 后缀）
        if data[:7] == b"#EXTM3U":
            return True
        return False

    @staticmethod
    def _detect_ts_media_type(data: bytes) -> str:
        """解析 MPEG-TS 的 PAT/PMT 判断媒体类型：'video' / 'audio' / ''（无法解析）。

        TS 容器既可用于视频电视也可用于纯音频电台（如央广 wxhainjtgb 这类
        音频流也封装在 video/mp2t 中），必须解析 PSI 表看节目里是否声明视频流。
        视频 stream_type: MPEG1/2, H.264(0x1B), HEVC(0x24), AV1(0x27), AVS(0x42), VC-1(0xEA)
        音频 stream_type: MPEG1/2 Audio, AAC(0x0F/0x11), AC-3(0x81), E-AC-3(0x87), DTS(0x83)
        """
        if not data or data[0] != 0x47:
            return ""
        video_types = {0x01, 0x02, 0x10, 0x1B, 0x24, 0x27, 0x42, 0xEA}
        audio_types = {0x03, 0x04, 0x0F, 0x11, 0x81, 0x83, 0x87}
        n = len(data)

        def _pid(pkt: int) -> int:
            return ((data[pkt + 1] & 0x1F) << 8) | data[pkt + 2]

        def _payload(pkt: int) -> int:
            """返回负载起点；无负载返回 -1"""
            afc = (data[pkt + 3] >> 4) & 0x03
            if afc in (0x00, 0x02):  # 00=保留(按仅适配处理), 02=仅适配字段
                return -1
            off = pkt + 4
            if afc == 0x03:
                off += 1 + data[off]
            return off

        def _section_start(pkt: int) -> int:
            """定位 PSI section 数据起点（处理 pointer_field）"""
            pld = _payload(pkt)
            if pld < 0 or pld + 1 > n:
                return -1
            if data[pkt + 1] & 0x40:  # payload_unit_start_indicator
                pointer = data[pld]
                return pld + 1 + pointer
            return pld

        # 第一遍：PAT (PID=0) 收集 PMT PID
        pmt_pids = set()
        for pkt in range(0, n - 187, 188):
            if data[pkt] != 0x47 or _pid(pkt) != 0:
                continue
            s = _section_start(pkt)
            if s < 0 or s + 5 > n or data[s] != 0x00:
                continue
            sec_len = ((data[s + 1] & 0x0F) << 8) | data[s + 2]
            end = min(s + 3 + sec_len - 4, n)
            e = s + 8  # 跳过 table_id/section_length/ts_id/version/section/last_section
            while e + 4 <= end:
                prog = (data[e] << 8) | data[e + 1]
                pmt_pid = ((data[e + 2] & 0x1F) << 8) | data[e + 3]
                if prog != 0:
                    pmt_pids.add(pmt_pid)
                e += 4

        if not pmt_pids:
            return ""

        # 第二遍：解析 PMT 的 ES stream_type
        has_video = False
        has_audio = False
        for pkt in range(0, n - 187, 188):
            if data[pkt] != 0x47 or _pid(pkt) not in pmt_pids:
                continue
            s = _section_start(pkt)
            if s < 0 or s + 12 > n or data[s] != 0x02:
                continue
            sec_len = ((data[s + 1] & 0x0F) << 8) | data[s + 2]
            prog_info_len = ((data[s + 10] & 0x0F) << 8) | data[s + 11]
            e = s + 12 + prog_info_len
            end = min(s + 3 + sec_len - 4, n)
            while e + 5 <= end:
                stype = data[e]
                if stype in video_types:
                    has_video = True
                elif stype in audio_types:
                    has_audio = True
                es_info_len = ((data[e + 3] & 0x0F) << 8) | data[e + 4]
                e += 5 + es_info_len
            if has_video:
                return "video"

        if has_video:
            return "video"
        if has_audio:
            return "audio"
        return ""

    @staticmethod
    def _m3u8_codecs_media_type(playlist: str) -> str:
        """解析 HLS 播放列表的 CODECS 声明：纯音频→'audio'，含视频编码→'video'，无声明→''。

        服务端在 #EXT-X-STREAM-INF 中明确声明的编码，比容器/首包猜测更权威，
        是 HLS 电台（如 CODECS=\"mp4a.40.2\"）最可靠的媒体事实信号。
        """
        if not playlist or "CODECS" not in playlist.upper():
            return ""
        video_codecs = ("avc1", "avc3", "hev1", "hvc1", "vp09", "av01", "mp4v", "dvhe", "dvh1")
        audio_codecs = ("mp4a", "ac-3", "ec-3", "aac", "opus", "vorbis")
        has_video = False
        has_audio = False
        for m in re.finditer(r'CODECS="([^"]*)"', playlist, re.IGNORECASE):
            for codec in (c.strip().lower() for c in m.group(1).split(",") if c.strip()):
                base = codec.split(".")[0]
                if base in video_codecs:
                    has_video = True
                elif base in audio_codecs:
                    has_audio = True
        if has_video:
            return "video"
        if has_audio:
            return "audio"
        return ""

    @staticmethod
    def _is_valid_m3u8_content(content: str) -> bool:
        """Check if content is valid M3U8, tolerating BOM, blank lines, and leading comments."""
        text = content.strip()
        if text.startswith('\ufeff'):
            text = text[1:]
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#') and not line.startswith('#EXTM3U'):
                continue
            return line.startswith('#EXTM3U')
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
        elif isinstance(exc, aiohttp.ServerDisconnectedError):
            result.details = "服务器断开连接"
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
        mode = self._config.effective_mode
        # 检测事实：媒体类型（"video"/"audio"/""），最终由流首包签名定论，Content-Type 仅作初判
        media_type = ""

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
            if content_type.startswith("audio/"):
                media_type = "audio"
            elif content_type.startswith("video/"):
                media_type = "video"

            # 返回网页而非流媒体：常见于防盗链/广告的 JS 跳转页。
            # 自动加入拦截名单，之后的检测不再对该域名发起请求（避免反复触发杀软告警）
            if "text/html" in content_type and not is_m3u8:
                domain = source_filter.block(channel.url, "返回HTML页面(疑似JS跳转)")
                raise ValueError(
                    f"非流媒体响应(HTML页面，已拦截 {domain})" if domain else "非流媒体响应(HTML页面)"
                )

            if mode == CheckMode.QUICK:
                # 方案1（快速）：只确认 HTTP 可达且响应体非空，不做任何拉流验证
                chunk = await resp.content.read(1024)
                if not chunk:
                    raise ValueError("无响应数据")
                chunk_media = self._detect_media_type(chunk)
                if chunk_media:
                    media_type = chunk_media
            elif mode == CheckMode.DEEP:
                # 方案1+2+测速（深度）：可达性 + 拉流验证 + 真实下载测速
                if is_m3u8:
                    playlist_content = await resp.text()
                    if not self._is_valid_m3u8_content(playlist_content):
                        raise ValueError("非标准M3U8内容")
                    playlist_media = self._m3u8_codecs_media_type(playlist_content)
                    if playlist_media:
                        media_type = playlist_media
                    # 2026-09-02: DEEP 测速 128KB/4s；粗筛已偏慢的源（prior_latency>=2500ms）
                    # 再给更短上限（2.5s），避免无谓等待。测速超时只影响速度精度，不影响判定。
                    speed_measure_seconds = 2.5 if (getattr(channel, 'prior_latency', None) or 0) >= 2500 else 4.0
                    speed = await self._m3u8.get_speed_async(
                        channel.url, playlist_content, self._headers,
                        self._config.timeout_connect, self._config.timeout_read,
                        http_session=self._http,
                        proxy_base=self._proxy_base,
                        max_bytes=128 * 1024,
                        max_seconds=speed_measure_seconds,
                    )
                else:
                    speed_measure_seconds = 2.5 if (getattr(channel, 'prior_latency', None) or 0) >= 2500 else 4.0
                    speed = await measure_speed_async(
                        resp.content.iter_any(), self._config.timeout_read, empty_result="",
                        max_bytes=128 * 1024, max_seconds=speed_measure_seconds,
                    )
            else:
                # 方案1+2（标准·推荐）：可达性 + 首包流验证，读到有效流头即通过
                if is_m3u8:
                    playlist_content = await resp.text()
                    if not self._is_valid_m3u8_content(playlist_content):
                        raise ValueError("非标准M3U8内容")
                    playlist_media = self._m3u8_codecs_media_type(playlist_content)
                    if playlist_media:
                        media_type = playlist_media
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
                    chunk_media = self._detect_media_type(chunk)
                    if chunk_media:
                        media_type = chunk_media

            result.latency = latency
            result.speed = speed
            # 分片类型（HLS 时）优先于 Content-Type 推断；无分片信号时保留首包/Content-Type 判定
            result.media_type = result.media_type or media_type

            # 2026-09-01: 移除"疑似有效"三态概念。流验证通过一律视为有效，
            # 延迟偏高/测速超时只记入 details 供排序参考，不再降为独立档位。
            result.is_valid = True
            result.quality_tier = "valid"
            if mode == CheckMode.DEEP and speed in ("-", "N/A"):
                result.details = "速度测试超时（流可拉通）" if not is_m3u8 else "分片速度测试超时（流可拉通）"
            elif latency > self._config.max_latency_ms * 2:
                result.details = f"延迟偏高 ({latency}ms > {self._config.max_latency_ms * 2}ms)"
            elif latency > self._config.max_latency_ms:
                result.details = f"延迟偏高 ({latency}ms > {self._config.max_latency_ms}ms)"
            else:
                result.details = f"OK ({resp.status})"

            if is_m3u8 and result.is_valid and mode != CheckMode.QUICK:
                try:
                    segments = self._m3u8.find_all_segment_urls(playlist_content, channel.url, limit=4)
                    if len(segments) >= 2:

                        async def _check_segment(seg_url: str) -> bool:
                            try:
                                fetch_seg_url = self._maybe_proxy_url(seg_url)
                                async with self._http.get(
                                    fetch_seg_url, headers=self._headers,
                                    timeout=aiohttp.ClientTimeout(
                                        # 2026-09-02: 分段读 1KB 校验超时从 8s 收紧到 5s（正常分段 1s 内返回）
                                        total=self._config.timeout_connect + min(self._config.timeout_read, 5),
                                        connect=self._config.timeout_connect,
                                        sock_read=min(self._config.timeout_read, 5),
                                    ),
                                    ssl=False, allow_redirects=True,
                                ) as seg_resp:
                                    seg_resp.raise_for_status()
                                    # 4096 字节足够容纳 TS PAT/PMT（纯音频 TS 需解析 PSI 判定）
                                    chunk = await seg_resp.content.read(4096)
                                    seg_media = self._detect_media_type(chunk)
                                    if seg_media:
                                        result.media_type = seg_media
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

        blocked = source_filter.match(channel.url)
        if blocked:
            result.is_valid = False
            result.quality_tier = "invalid"
            result.details = f"已拦截（风险源: {blocked}）"
            logger.debug("[黑名单跳过] 频道=%s, 域名=%s", channel.name, blocked)
            return result

        async with self._semaphore:
            if self._stop_event.is_set():
                result.is_valid = False
                result.quality_tier = "stopped"
                result.details = "已停止"
                return result

            try:
                result = await self._execute_check(channel)
            except asyncio.TimeoutError:
                logger.debug("[重试] 频道=%s 首次超时，重试1次", channel.name)
                try:
                    if self._stop_event.is_set():
                        result.is_valid = False
                        result.quality_tier = "stopped"
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

    def add_channels(self, channels: List[Channel], config: CheckConfig,
                     on_result: Optional[Callable[[CheckResult], None]] = None) -> None:
        """流式添加频道批次（需 start(streaming=True) 后使用，完成后调用 complete()）"""
        if not self._running:
            logger.warning("[AsyncEngine] 引擎未运行，忽略 %d 个频道", len(channels))
            return
        if not self._feed_open:
            logger.warning("[AsyncEngine] 已调用 complete()，忽略 %d 个频道", len(channels))
            return
        if on_result:
            self._on_result = on_result
        self._add_feed_batch(channels)
        logger.info("[AsyncEngine] 流式添加 %d 个频道到队列", len(channels))

    def stop(self) -> None:
        """停止检测"""
        self._stop_event.set()
        self._running = False
        self._feed_open = False
        self._maybe_sentinel()
        event_bus.emit(Events.CHECK_STOPPED)
        logger.info("[AsyncEngine] 停止请求已发送")

    async def wait_complete(self):
        """等待所有检测完成"""
        if self._consumer_task:
            await self._consumer_task
