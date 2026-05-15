import asyncio
import time
import logging
import threading
from typing import List, Optional, Callable

import aiohttp

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.domain.events import DomainEvents
from iptv_check.infra.persistence.event_store import EventStore
from iptv_check.infra.persistence.read_model import ReadModel
from iptv_check.infra.check_engine.base import CheckEngineProtocol
from iptv_check.infra.config.settings import settings
from iptv_check.infra.batch_result_collector import BatchResultCollector

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
        self._collector: Optional[BatchResultCollector] = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def session_id(self) -> str:
        return self._session_id

    def get_progress(self) -> dict:
        if self._collector:
            return self._collector.get_progress_dict()
        return self._read_model.get_check_progress(self._session_id)

    def get_full_state(self) -> dict:
        return self._read_model.get_full_state(self._session_id)

    async def start_check(self, req) -> None:
        with self._lock:
            if self._is_running:
                raise RuntimeError("检测正在进行中")
            self._is_running = True
            self._check_total = 0

        self._session_id = self._event_store.new_session()
        await self._event_store.append(DomainEvents.CHECK_STARTED, {"session_id": self._session_id}, self._session_id)
        await self._broadcast_fn("check_started", {"total": 0, "session_id": self._session_id})

        logger.info("[CheckService] 准备创建检测任务")
        task = asyncio.create_task(self._run_check(req))
        logger.info("[CheckService] 检测任务已创建，task=%s", task)
        task.add_done_callback(self._on_check_task_done)
        logger.info("[CheckService] 已注册完成回调")

    def _on_check_task_done(self, task):
        """后台检测任务完成回调，用于捕获和记录异常"""
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("[CheckService] 检测任务被取消")
        except Exception as e:
            logger.error("[CheckService] 检测任务异常: %s", e, exc_info=True)

    async def stop_check(self) -> None:
        with self._lock:
            if not self._is_running:
                return
        self._check_engine.stop()
        if self._collector:
            await self._collector.stop()
        await self._event_store.append(DomainEvents.CHECK_STOPPED, {}, self._session_id)
        await self._broadcast_fn("check_stopped", {})

    async def _run_check(self, req):
        from iptv_check.core.parser import PlaylistParser
        from iptv_check.server.app import app_state

        t0 = time.time()
        logger.info("[检测] 检测任务启动, session=%s", self._session_id)

        self._collector = BatchResultCollector(
            event_store=self._event_store,
            broadcast_fn=self._broadcast_fn,
            batch_size=100,
            flush_interval=3.0,
            session_id=self._session_id,
        )
        await self._collector.start()

        config = CheckConfig(
            timeout_connect=req.timeout_connect,
            timeout_read=req.timeout_read,
            max_threads=req.max_threads,
            run_speed_test=req.run_speed_test,
            use_cache=req.use_cache,
        )

        seen: set = set()
        all_channels: List[Channel] = []

        def on_result(result: CheckResult):
            self._collector.submit_result_sync(result)

        def on_complete():
            logger.info("[CheckService] on_complete 回调被触发")
            self._collector.submit_complete_sync()
            logger.info("[CheckService] submit_complete_sync 已调用")

        async def _emit_channel_submitted(channels: List):
            for ch in channels:
                await self._event_store.append(
                    DomainEvents.CHANNEL_SUBMITTED,
                    {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group},
                    self._session_id,
                )

        # Phase 1: 加载本地文件
        if req.file_paths:
            channels = await asyncio.to_thread(PlaylistParser.parse_files, req.file_paths)
            logger.info("[检测] 本地文件解析完成, 频道数=%d", len(channels))
            for ch in channels:
                if ch.url_key not in seen:
                    all_channels.append(ch)
                    seen.add(ch.url_key)
            if all_channels:
                await _emit_channel_submitted(all_channels)

        # Phase 2: 下载在线源
        if req.online_source_ids:
            online_channels = await self._download_sources(req, seen, app_state)
            all_channels.extend(online_channels)
            if online_channels:
                await _emit_channel_submitted(online_channels)

        self._check_total = len(all_channels)
        self._collector.set_total(self._check_total)

        logger.info("[检测] 频道加载完毕, 总计=%d", self._check_total)

        if not self._check_total:
            await self._event_store.append(DomainEvents.CHECK_FAILED, {"reason": "未解析到任何频道"}, self._session_id)
            with self._lock:
                self._is_running = False
            await self._collector.stop()
            await self._broadcast_fn("check_completed", {"total": 0, "valid": 0, "invalid": 0})
            logger.warning("[检测] 未解析到任何频道")
            return

        # Phase 3: 启动检测引擎
        await self._broadcast_fn("channels_loaded", {"total": self._check_total})
        logger.info("[检测] 启动检测引擎, 频道数=%d", self._check_total)

        self._check_engine.start(all_channels, config, on_result=on_result, on_complete=on_complete)

        # Phase 4: 等待完成
        await self._collector.wait_for_complete()

        with self._lock:
            self._is_running = False

        # Save session to history
        await self._save_to_history(t0)

        logger.info("[检测] 全部完成, 耗时=%.1fs, 有效=%d, 无效=%d",
                    time.time() - t0, self._collector.progress.valid, self._collector.progress.invalid)

    async def _save_to_history(self, start_time: float) -> None:
        """Save completed session to history table"""
        try:
            elapsed = round(time.time() - start_time, 1)
            self._event_store.save_history(
                session_id=self._session_id,
                total=self._check_total,
                valid=self._collector.progress.valid,
                invalid=self._collector.progress.invalid,
                elapsed=elapsed,
            )
            logger.info("[检测] 已保存历史记录: %s", self._session_id)
        except Exception as e:
            logger.warning("[检测] 保存历史记录失败: %s", e)

    async def _download_sources(self, req, seen: set, app_state) -> List[Channel]:
        from iptv_check.core.parser import PlaylistParser

        sources_to_download = [src for src in app_state.online_sources if src.id in req.online_source_ids]
        logger.info("[检测] 开始下载 %d 个在线源", len(sources_to_download))

        sem = asyncio.Semaphore(settings.download_concurrency)
        results: List[List[Channel]] = []

        async def download_one(src):
            async with sem:
                try:
                    url = src.url
                    if src.mirror_url and app_state.local_isp not in src.isp:
                        url = src.mirror_url

                    timeout = aiohttp.ClientTimeout(
                        total=settings.download_timeout,
                        connect=10,
                        sock_read=settings.download_timeout,
                    )
                    async with app_state._async_session.get(url, timeout=timeout, ssl=False) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            new_channels = PlaylistParser.parse_m3u_content(text, src.name)
                            fresh = []
                            for ch in new_channels:
                                if ch.url_key not in seen:
                                    seen.add(ch.url_key)
                                    fresh.append(ch)
                            if fresh:
                                logger.info("[检测] 在线源 %s 下载完成, 新增 %d 个频道", src.name, len(fresh))
                                results.append(fresh)
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

        await asyncio.gather(*[download_one(src) for src in sources_to_download])

        all_fresh = []
        for group in results:
            all_fresh.extend(group)
        return all_fresh
