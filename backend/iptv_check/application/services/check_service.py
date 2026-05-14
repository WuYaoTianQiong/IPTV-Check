import asyncio
import time
import logging
import threading
from typing import List, Optional, Callable

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.domain.events import DomainEvents
from iptv_check.infra.persistence.event_store import EventStore
from iptv_check.infra.persistence.read_model import ReadModel
from iptv_check.infra.check_engine.base import CheckEngineProtocol
from iptv_check.infra.config.settings import settings

logger = logging.getLogger(__name__)


class CheckService:
    def __init__(
        self,
        event_store: EventStore,
        read_model: ReadModel,
        check_engine: CheckEngineProtocol,
        broadcast_fn: Callable,
    ):
        self._event_store = event_store
        self._read_model = read_model
        self._check_engine = check_engine
        self._broadcast_fn = broadcast_fn
        self._lock = threading.Lock()
        self._is_running = False
        self._check_total: int = 0
        self._session_id: str = ""
        self._result_queue: Optional[asyncio.Queue] = None
        self._check_has_started: bool = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def session_id(self) -> str:
        return self._session_id

    def get_progress(self) -> dict:
        return self._read_model.get_check_progress(self._session_id)

    def get_full_state(self) -> dict:
        return self._read_model.get_full_state(self._session_id)

    async def start_check(self, req) -> None:
        with self._lock:
            if self._is_running:
                raise RuntimeError("检测正在进行中")
            self._is_running = True
            self._check_total = 0
            self._check_has_started = False
            self._result_queue = asyncio.Queue()

        self._session_id = self._event_store.new_session()
        await self._event_store.append(DomainEvents.CHECK_STARTED, {"session_id": self._session_id}, self._session_id)

        progress = self._read_model.get_check_progress(self._session_id)
        await self._broadcast_fn("check_started", {"total": progress["total"], "session_id": self._session_id})

        asyncio.create_task(self._run_streaming_check(req))

    async def stop_check(self) -> None:
        with self._lock:
            if not self._is_running:
                return
        self._check_engine.stop()
        await self._event_store.append(DomainEvents.CHECK_STOPPED, {}, self._session_id)
        await self._broadcast_fn("check_stopped", {})

    async def _run_streaming_check(self, req):
        from iptv_check.core.parser import PlaylistParser
        from iptv_check.server.app import app_state

        t0 = time.time()
        logger.info("[检测] 流式检测任务启动, session=%s", self._session_id)

        config = CheckConfig(
            timeout_connect=req.timeout_connect,
            timeout_read=req.timeout_read,
            max_threads=req.max_threads,
            run_speed_test=req.run_speed_test,
            use_cache=req.use_cache,
        )

        seen: set = set()
        pending_channels: List = []

        def on_result(result: CheckResult):
            if self._result_queue:
                self._result_queue.put_nowait(("result", result))

        def on_complete():
            if self._result_queue:
                self._result_queue.put_nowait(("complete", None))

        async def _emit_channel_submitted(channels: List):
            for ch in channels:
                await self._event_store.append(
                    DomainEvents.CHANNEL_SUBMITTED,
                    {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group},
                    self._session_id,
                )

        def _start_engine():
            if not pending_channels or self._check_has_started:
                return
            self._check_engine.start(pending_channels, config, on_result=on_result, on_complete=on_complete)
            self._check_total = len(pending_channels)
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._broadcast_channels_loaded()))
            self._check_has_started = True
            logger.info("[检测] 检测引擎启动, 频道数=%d", self._check_total)

        async def _add_channels(channels: List):
            if not channels:
                return
            await _emit_channel_submitted(channels)
            if not self._check_has_started:
                pending_channels.extend(channels)
                _start_engine()
            else:
                self._check_engine.add_channels(channels, config, on_result)
                self._check_total += len(channels)
                await self._broadcast_channels_loaded()

        if req.file_paths:
            channels = await asyncio.to_thread(PlaylistParser.parse_files, req.file_paths)
            logger.info("[检测] 本地文件解析完成, 频道数=%d", len(channels))
            for ch in channels:
                if ch.url_key not in seen:
                    seen.add(ch.url_key)
                    pending_channels.append(ch)
            await _emit_channel_submitted(pending_channels)
            _start_engine()

        if req.online_source_ids:
            await self._download_sources(req, seen, _add_channels, app_state)

        if not self._check_has_started:
            await self._event_store.append(DomainEvents.CHECK_FAILED, {"reason": "未解析到任何频道"}, self._session_id)
            with self._lock:
                self._is_running = False
            await self._broadcast_fn("check_completed", {"total": 0, "valid": 0, "invalid": 0})
            logger.warning("[检测] 未解析到任何频道")
            return

        await self._wait_check_queue()
        with self._lock:
            self._is_running = False
        logger.info("[检测] 全部完成, 耗时=%.1fs", time.time() - t0)

    async def _download_sources(self, req, seen: set, add_channels_fn, app_state):
        from iptv_check.core.parser import PlaylistParser

        sources_to_download = [src for src in app_state.online_sources if src.id in req.online_source_ids]
        logger.info("[检测] 后台开始下载 %d 个在线源", len(sources_to_download))

        sem = asyncio.Semaphore(settings.download_concurrency)

        async def download_and_feed(src):
            async with sem:
                try:
                    url = src.url
                    if src.mirror_url and app_state.local_isp not in src.isp:
                        url = src.mirror_url
                    resp = await asyncio.to_thread(
                        app_state.http_client.get_with_retry,
                        url,
                        timeout=settings.download_timeout,
                        verify=False,
                    )
                    if resp.status_code == 200:
                        new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, resp.text, src.name)
                        fresh = []
                        for ch in new_channels:
                            if ch.url_key not in seen:
                                fresh.append(ch)
                                seen.add(ch.url_key)
                        if fresh:
                            logger.info("[检测] 在线源 %s 下载完成, 新增 %d 个频道", src.name, len(fresh))
                            await add_channels_fn(fresh)
                        else:
                            logger.info("[检测] 在线源 %s 下载完成, 共 %d 个频道（全部已存在）", src.name, len(new_channels))

                        await self._event_store.append(
                            DomainEvents.SOURCE_DOWNLOADED,
                            {"source_name": src.name, "channel_count": len(fresh), "success": True},
                            self._session_id,
                        )
                    else:
                        logger.warning("[检测] 在线源 %s HTTP %d", src.name, resp.status_code)
                        await self._event_store.append(
                            DomainEvents.SOURCE_DOWNLOADED,
                            {"source_name": src.name, "channel_count": 0, "success": False},
                            self._session_id,
                        )
                except Exception as e:
                    logger.warning("[检测] 在线源 %s 下载失败: %s", src.name, e)
                    await self._event_store.append(
                        DomainEvents.SOURCE_DOWNLOAD_FAILED,
                        {"source_name": src.name, "error": str(e)},
                        self._session_id,
                    )

        await asyncio.gather(*[download_and_feed(src) for src in sources_to_download])
        logger.info("[检测] 所有在线源下载完毕, 总频道数=%d", self._check_total)

    async def _broadcast_channels_loaded(self):
        progress = self._read_model.get_check_progress(self._session_id)
        await self._broadcast_fn("channels_loaded", {"total": progress["total"]})

    async def _wait_check_queue(self):
        if not self._result_queue:
            return
        while True:
            msg_type, data = await self._result_queue.get()
            if msg_type == "result":
                result = data
                country = result.channel.country
                is_radio = result.channel.is_radio
                ch_name = result.channel.name
                group = result.channel.group
                url = result.channel.url

                content_type = "其他"
                if is_radio:
                    content_type = "广播"
                elif any(kw in ch_name for kw in ["CCTV", "cctv"]) or "央视" in ch_name:
                    content_type = "央视"
                elif "卫视" in ch_name or "卫视" in group:
                    content_type = "卫视"
                elif any(kw in ch_name for kw in ["4K", "4k", "UHD", "uhd", "超清"]) or any(kw in group for kw in ["4K", "4k", "UHD", "uhd", "超清"]):
                    content_type = "4K"
                elif any(kw in url for kw in ["ipv6", "IPv6", "/v6/"]) or "IPv6" in group:
                    content_type = "IPv6"
                elif country and country.upper().split(";")[0] in {"CN", "CHN", "HK", "HKG", "MO", "MAC", "TW", "TWN"}:
                    content_type = "地方"
                elif country:
                    content_type = "国际"

                await self._event_store.append(
                    DomainEvents.CHANNEL_CHECKED,
                    {
                        "url_key": result.channel.url_key,
                        "name": result.channel.name,
                        "url": result.channel.url,
                        "is_valid": result.is_valid,
                        "latency": result.latency_display,
                        "speed": result.speed,
                        "details": result.details,
                        "group": result.channel.group,
                        "sources": ", ".join(result.channel.sources),
                        "country": country,
                        "is_radio": is_radio,
                        "language": result.channel.language,
                        "content_type": content_type,
                    },
                    self._session_id,
                )
                await self._broadcast_fn("channel_checked", {
                    "index": result.channel.index,
                    "name": result.channel.name,
                    "url": result.channel.url,
                    "is_valid": result.is_valid,
                    "latency": result.latency_display,
                    "speed": result.speed,
                    "details": result.details,
                    "status": result.status_text,
                    "sources": ", ".join(result.channel.sources),
                    "group": result.channel.group,
                    "tag": result.tag,
                })
            elif msg_type == "complete":
                progress = self._read_model.get_check_progress(self._session_id)
                await self._event_store.append(
                    DomainEvents.CHECK_COMPLETED,
                    {"total": progress["total"], "valid": progress["valid"], "invalid": progress["invalid"]},
                    self._session_id,
                )
                await self._broadcast_fn("check_completed", {
                    "total": progress["total"],
                    "valid": progress["valid"],
                    "invalid": progress["invalid"],
                })
                logger.info("[检测] 检测完成, 有效=%d, 无效=%d", progress["valid"], progress["invalid"])
                break
