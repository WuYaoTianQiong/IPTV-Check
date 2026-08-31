import asyncio
import hashlib
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
        app_state=None,
    ):
        self._event_store = event_store
        self._read_model = read_model
        self._check_engine = check_engine
        self._broadcast_fn = broadcast_fn
        self._app_state = app_state
        self._lock = threading.Lock()
        self._is_running = False
        self._check_total: int = 0
        self._session_id: str = ""
        self._collector: Optional[BatchResultCollector] = None
        self._current_stage: str = ""
        self._current_stage_message: str = ""

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def session_id(self) -> str:
        return self._session_id

    def get_progress(self) -> dict:
        if self._collector:
            result = self._collector.get_progress_dict()
        else:
            result = self._read_model.get_check_progress(self._session_id)
        result["is_running"] = self.is_running
        if self.is_running:
            result["stage"] = self._current_stage
            result["stage_message"] = self._current_stage_message
        return result

    def get_full_state(self) -> dict:
        state = self._read_model.get_full_state(self._session_id)
        state["is_running"] = self.is_running
        state["stage"] = getattr(self, "_current_stage", "")
        state["stage_message"] = getattr(self, "_current_stage_message", "")
        return state

    async def start_check(self, req) -> None:
        with self._lock:
            if self._is_running:
                raise RuntimeError("检测正在进行中")
            self._is_running = True
            self._check_total = 0
            self._current_stage = ""
            self._current_stage_message = ""

        self._session_id = self._event_store.new_session()
        await self._event_store.append(DomainEvents.CHECK_STARTED, {"session_id": self._session_id}, self._session_id)
        await self._broadcast_fn("check_started", {"total": 0, "session_id": self._session_id})
        await self._broadcast_stage("parsing", "正在解析本地文件...")

        logger.info("[CheckService] 准备创建检测任务")
        task = asyncio.create_task(self._run_check(req))
        logger.info("[CheckService] 检测任务已创建，task=%s", task)
        task.add_done_callback(self._on_check_task_done)
        logger.info("[CheckService] 已注册完成回调")

    async def start_check_from_channels(self, channels: List[Channel], config: CheckConfig) -> None:
        with self._lock:
            if self._is_running:
                raise RuntimeError("检测正在进行中")
            self._is_running = True
            self._check_total = 0
            self._current_stage = ""
            self._current_stage_message = ""

        self._session_id = self._event_store.new_session()
        await self._event_store.append(DomainEvents.CHECK_STARTED, {"session_id": self._session_id}, self._session_id)
        await self._broadcast_fn("check_started", {"total": 0, "session_id": self._session_id})

        task = asyncio.create_task(self._run_check_from_channels(channels, config))
        task.add_done_callback(self._on_check_task_done)

    def _on_check_task_done(self, task):
        """后台检测任务完成回调，用于捕获和记录异常"""
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("[CheckService] 检测任务被取消")
        except Exception as e:
            logger.error("[CheckService] 检测任务异常: %s", e, exc_info=True)
            asyncio.create_task(self._broadcast_fn("check_completed", {
                "total": self._check_total,
                "checked": self._check_total,
                "valid": 0,
                "likely_valid": 0,
                "invalid": 0,
                "is_running": False,
                "error": str(e)[:200],
            }))
        finally:
            with self._lock:
                self._is_running = False
            self._current_stage = ""
            self._current_stage_message = ""

    async def _broadcast_stage(self, stage: str, message: str):
        self._current_stage = stage
        self._current_stage_message = message
        await self._broadcast_fn("stage_changed", {"stage": stage, "message": message})

    async def stop_check(self) -> None:
        with self._lock:
            if not self._is_running:
                return
        self._check_engine.stop()
        if self._collector:
            await self._collector.stop()
        self._current_stage = ""
        self._current_stage_message = ""
        await self._event_store.append(DomainEvents.CHECK_STOPPED, {}, self._session_id)
        await self._broadcast_fn("check_stopped", {})

    async def _run_check_from_channels(self, channels: List[Channel], config: CheckConfig):
        t0 = time.time()
        logger.info("[检测] 从已拉取频道启动检测, session=%s, 频道数=%d", self._session_id, len(channels))

        self._collector = BatchResultCollector(
            event_store=self._event_store,
            broadcast_fn=self._broadcast_fn,
            batch_size=100,
            flush_interval=3.0,
            session_id=self._session_id,
        )
        await self._collector.start()

        all_channels = channels
        self._check_total = len(all_channels)
        self._collector.set_total(self._check_total)

        for ch in all_channels:
            await self._event_store.append(
                DomainEvents.CHANNEL_SUBMITTED,
                {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group, "is_radio": ch.is_radio},
                self._session_id,
            )

        logger.info("[检测] 频道加载完毕, 总计=%d", self._check_total)

        if not self._check_total:
            await self._event_store.append(DomainEvents.CHECK_FAILED, {"reason": "没有可检测的频道"}, self._session_id)
            with self._lock:
                self._is_running = False
            await self._collector.stop()
            await self._broadcast_fn("check_completed", {
                "total": 0, "checked": 0, "valid": 0, "likely_valid": 0, "invalid": 0, "is_running": False
            })
            return

        await self._broadcast_fn("channels_loaded", {"total": self._check_total})
        await self._broadcast_stage("checking", f"正在检测 {self._check_total} 个频道...")
        logger.info("[检测] 启动检测引擎, 频道数=%d", self._check_total)

        def on_result(result: CheckResult):
            self._collector.submit_result_sync(result)

        def on_cached_result(result: CheckResult):
            self._collector.submit_cached_result_sync(result)

        def on_complete():
            logger.info("[CheckService] on_complete 回调被触发")
            self._collector.submit_complete_sync()
            logger.info("[CheckService] submit_complete_sync 已调用")

        self._check_engine.start(all_channels, config, on_result=on_result, on_complete=on_complete, on_cached_result=on_cached_result)

        await self._collector.wait_for_complete()

    async def _run_check(self, req):
        from iptv_check.core.parser import PlaylistParser

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
            max_latency_ms=getattr(req, 'max_latency_ms', 10000),
            enable_recheck=getattr(req, 'enable_recheck', False),
        )

        seen: set = set()
        all_channels: List[Channel] = []

        def on_result(result: CheckResult):
            self._collector.submit_result_sync(result)

        def on_cached_result(result: CheckResult):
            self._collector.submit_cached_result_sync(result)

        def on_complete():
            logger.info("[CheckService] on_complete 回调被触发")
            self._collector.submit_complete_sync()
            logger.info("[CheckService] submit_complete_sync 已调用")

        async def _emit_channel_submitted(channels: List):
            for ch in channels:
                await self._event_store.append(
                    DomainEvents.CHANNEL_SUBMITTED,
                    {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group, "is_radio": ch.is_radio},
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
                await self._broadcast_stage("downloading", f"本地文件已加载 {len(all_channels)} 个频道")

        # Phase 2: 加载在线源频道
        if req.online_source_ids:
            fetch_svc = getattr(self._app_state, '_fetch_service', None)
            use_fetched = False
            if fetch_svc:
                use_fetched = await asyncio.to_thread(fetch_svc.has_fetched_channels)
            if use_fetched:
                estimated_total = await asyncio.to_thread(fetch_svc.count_fetched_channels, list(req.online_source_ids))
                await self._broadcast_stage("downloading", f"正在从数据库加载频道（预计 {estimated_total} 个）...")
                fetched_channels = await asyncio.to_thread(fetch_svc.get_fetched_channels, list(req.online_source_ids))
                for ch in fetched_channels:
                    if ch.url_key not in seen:
                        seen.add(ch.url_key)
                        all_channels.append(ch)
                if all_channels:
                    await _emit_channel_submitted(all_channels)
                await self._broadcast_stage("downloading", f"已从数据库加载 {len(all_channels)} 个频道")
                logger.info("[检测] 从数据库加载频道完成, 频道数=%d", len(all_channels))
            else:
                await self._broadcast_stage("downloading", f"正在下载在线源 (0/{len(req.online_source_ids)})...")
                online_channels = await self._download_sources(req, seen, self._app_state, on_channels_ready=_emit_channel_submitted)
                all_channels.extend(online_channels)

        self._check_total = len(all_channels)
        self._collector.set_total(self._check_total)

        logger.info("[检测] 频道加载完毕, 总计=%d", self._check_total)

        if not self._check_total:
            await self._event_store.append(DomainEvents.CHECK_FAILED, {"reason": "未解析到任何频道"}, self._session_id)
            with self._lock:
                self._is_running = False
            await self._collector.stop()
            await self._broadcast_fn("check_completed", {
                "total": 0, "checked": 0, "valid": 0, "likely_valid": 0, "invalid": 0, "is_running": False
            })
            logger.warning("[检测] 未解析到任何频道")
            return

        # Phase 3: 启动检测引擎
        await self._broadcast_fn("channels_loaded", {"total": self._check_total})
        await self._broadcast_stage("checking", f"正在检测 {self._check_total} 个频道...")
        logger.info("[检测] 启动检测引擎, 频道数=%d", self._check_total)

        self._check_engine.start(all_channels, config, on_result=on_result, on_complete=on_complete, on_cached_result=on_cached_result)

        # Phase 4: 等待首轮完成
        await self._collector.wait_for_complete()

        # Phase 5: 二轮复检
        invalid_channels = self._collector.get_invalid_channels()
        if config.enable_recheck and invalid_channels:
            await self._broadcast_stage("rechecking", f"正在复检 {len(invalid_channels)} 个频道...")
            logger.info("[复检] 开始复检, 无效频道数=%d", len(invalid_channels))

            recheck_config = CheckConfig(
                timeout_connect=req.timeout_connect,
                timeout_read=req.timeout_read * 2,
                max_threads=max(req.max_threads // 4, config.min_threads),
                min_threads=max(req.max_threads // 8, 3),
                run_speed_test=False,
                use_cache=False,
                max_latency_ms=config.max_latency_ms,
            )

            from iptv_check.infra.check_engine.async_engine import AsyncCheckEngine
            from iptv_check.core.m3u8_validator import M3U8Validator

            recheck_engine = AsyncCheckEngine(
                http_session=self._app_state._async_session,
                cache=self._check_engine._cache,
                m3u8_validator=M3U8Validator(self._app_state.http_client),
                proxy_base=getattr(settings, 'stream_proxy_base', ''),
            )

            recheck_collector = BatchResultCollector(
                event_store=self._event_store,
                broadcast_fn=self._broadcast_fn,
                batch_size=100,
                flush_interval=3.0,
                session_id=self._session_id,
                event_type="channel_rechecked",
            )
            await recheck_collector.start()

            def on_recheck_result(result: CheckResult):
                self._collector.update_result(result)
                recheck_collector.submit_result_sync(result)

            recheck_engine.start(invalid_channels, recheck_config,
                                 on_result=on_recheck_result,
                                 on_complete=lambda: recheck_collector.submit_complete_sync())
            if recheck_engine.adaptive_ctrl:
                recheck_engine.adaptive_ctrl._is_recheck = True

            await recheck_collector.wait_for_complete()
            await recheck_collector.stop()
            logger.info("[复检] 完成, 复检频道=%d", len(invalid_channels))
        else:
            logger.info("[复检] 无需复检, 首轮无invalid频道")

        # Phase 6: finalizing
        await self._broadcast_stage("finalizing", "正在生成报告...")

        with self._lock:
            self._is_running = False

        self._current_stage = ""
        self._current_stage_message = ""

        await self._event_store.append(
            DomainEvents.CHECK_COMPLETED,
            {
                "total": self._collector.progress.total,
                "valid": self._collector.progress.valid,
                "invalid": self._collector.progress.invalid,
            },
            self._session_id,
        )

        await self._broadcast_fn("check_completed", {
            "total": self._collector.progress.total,
            "checked": self._collector.progress.checked,
            "valid": self._collector.progress.valid,
            "likely_valid": self._collector.progress.likely_valid,
            "invalid": self._collector.progress.invalid,
            "is_running": False,
        })

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    self._save_to_history(t0),
                    self._materialize_results(),
                ),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.error("[检测] 物化/历史保存超时(60s)，下次查询将回退到事件表")
        except Exception as e:
            logger.error("[检测] 物化/历史保存失败: %s", e)

        logger.info("[检测] 全部完成, 耗时=%.1fs, 有效=%d, 疑似有效=%d, 无效=%d",
                    time.time() - t0, self._collector.progress.valid,
                    self._collector.progress.likely_valid, self._collector.progress.invalid)

    async def _materialize_results(self) -> None:
        """Materialize check results to channel_results table for fast reads"""
        try:
            if self._app_state and hasattr(self._app_state, 'materialization'):
                count = await self._app_state.materialization.materialize_session_async(self._session_id)
                if count > 0:
                    logger.info("[检测] 物化完成: %d 条结果", count)
        except Exception as e:
            logger.warning("[检测] 物化结果失败(不影响功能): %s", e)

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

    @staticmethod
    def _is_channel_url(src) -> bool:
        return src.category.endswith("频道") or src.category.endswith("电台")

    @staticmethod
    def _infer_region(name: str, url: str) -> str:
        _REGION_KEYWORDS = {
            "意大利": ["rai ", "radio italia", "mediaset", "italia", "bergamo", "campania", "marche", "santeramo", "orsc.ru"],
            "英国": ["bbc ", "bbc radio", "pluto.tv", "rakuten"],
            "德国": ["ndr ", "radio bremen", "akamaized.net/hls/live/2020435"],
            "爱尔兰": ["98fm", "fm104", "radio nova", "today fm", "audioxi.com"],
            "迪拜": ["dubai", "sama dubai", "mangomolo"],
            "芬兰": ["järviradio", "radiotaajuus"],
            "匈牙利": ["parlament", "parlament.hu"],
            "俄罗斯": ["orsk.ru", "camsh"],
            "斯洛伐克": ["joj", "cdn.joj"],
            "丹麦": ["dr ", "drlive"],
            "伊朗": ["alalam", "al-alam"],
            "墨西哥": ["américa", "américa"],
            "卢森堡": ["chamber tv", "webtvlive"],
            "西班牙": ["onda web"],
        }
        text = f"{name} {url}".lower()
        for region, keywords in _REGION_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return region
        return "其他"

    async def _download_sources(self, req, seen: set, app_state, on_channels_ready=None) -> List[Channel]:
        from iptv_check.core.parser import PlaylistParser

        sources_to_download = [src for src in app_state.online_sources if src.id in req.online_source_ids]

        channel_sources = [s for s in sources_to_download if self._is_channel_url(s)]
        list_sources = [s for s in sources_to_download if not self._is_channel_url(s)]

        logger.info("[检测] 在线源: %d 个频道级 + %d 个列表级", len(channel_sources), len(list_sources))

        results: List[List[Channel]] = []

        direct_channels = []
        for src in channel_sources:
            url = src.url
            if src.mirror_url and app_state.local_isp not in src.isp:
                url = src.mirror_url
            is_radio = src.category.endswith("电台") or "广播" in src.category or "radio" in src.category.lower()
            group = src.category
            if is_radio:
                region = self._infer_region(src.name, src.url)
                if region:
                    group = f"{src.category}/{region}"
            ch = Channel(
                name=src.name,
                url=url,
                group=group,
                sources=[src.name],
                country=getattr(src, 'country', ''),
                is_radio=is_radio,
            )
            if ch.url_key not in seen:
                seen.add(ch.url_key)
                direct_channels.append(ch)

        if direct_channels:
            results.append(direct_channels)
            await self._event_store.append_batch(
                [(DomainEvents.CHANNEL_SUBMITTED,
                  {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group, "is_radio": ch.is_radio})
                 for ch in direct_channels],
                self._session_id,
            )
            await self._event_store.append(
                DomainEvents.SOURCE_DOWNLOADED,
                {"source_name": "频道级源", "channel_count": len(direct_channels), "success": True},
                self._session_id,
            )
            if on_channels_ready:
                await on_channels_ready(direct_channels)
            logger.info("[检测] 频道级源直接加载 %d 个频道", len(direct_channels))

        if not list_sources:
            all_fresh = []
            for group in results:
                all_fresh.extend(group)
            return all_fresh

        sem = asyncio.Semaphore(settings.download_concurrency)
        download_done_count = 0
        total_sources = len(list_sources)
        download_lock = asyncio.Lock()

        async def _notify_source_done():
            nonlocal download_done_count
            async with download_lock:
                download_done_count += 1
                await self._broadcast_stage("downloading", f"正在下载在线源 ({download_done_count}/{total_sources})...")

        async def download_one(src):
            async with sem:
                try:
                    url = src.url
                    if src.mirror_url and app_state.local_isp not in src.isp:
                        url = src.mirror_url

                    cache_key = f"source:{src.id}"
                    cache = getattr(app_state, 'cache', None)
                    logger.info("[检测] cache对象: %s (type=%s)", cache, type(cache).__name__ if cache else 'None')
                    if req.use_cache and cache and cache.has(cache_key):
                        cached = cache.get(cache_key)
                        if cached:
                            new_channels = PlaylistParser.parse_m3u_content(cached, src.name, src.category or "")
                            fresh = []
                            for ch in new_channels:
                                if ch.url_key not in seen:
                                    seen.add(ch.url_key)
                                    fresh.append(ch)
                            if fresh:
                                logger.info("[检测] 在线源 %s 缓存命中, %d 个频道", src.name, len(fresh))
                                results.append(fresh)
                                await self._event_store.append(
                                    DomainEvents.SOURCE_DOWNLOADED,
                                    {"source_name": src.name, "channel_count": len(fresh), "success": True},
                                    self._session_id,
                                )
                                if on_channels_ready:
                                    await on_channels_ready(fresh)
                            else:
                                logger.warning("[检测] 在线源 %s 缓存解析出0个频道，视为无效缓存，重新下载", src.name)
                            await _notify_source_done()
                            return

                    timeout = aiohttp.ClientTimeout(
                        total=settings.download_timeout,
                        connect=10,
                        sock_read=settings.download_timeout,
                    )
                    async with app_state._async_session.get(url, timeout=timeout, ssl=False) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            content_hash = hashlib.md5(text.encode()).hexdigest()
                            cached_hash = cache.get(f"{cache_key}:hash") if cache else None
                            if cached_hash == content_hash:
                                logger.info("[检测] 在线源 %s 内容未变化(hash=%s), 跳过解析", src.name, content_hash[:8])
                                await self._event_store.append(
                                    DomainEvents.SOURCE_DOWNLOADED,
                                    {"source_name": src.name, "channel_count": 0, "success": True, "unchanged": True},
                                    self._session_id,
                                )
                                await _notify_source_done()
                                return
                            new_channels = PlaylistParser.parse_m3u_content(text, src.name, src.category or "")
                            if req.use_cache and text and cache:
                                cache.set(cache_key, text, ttl=6 * 3600)
                                cache.set(f"{cache_key}:hash", content_hash, ttl=7 * 24 * 3600)
                            fresh = []
                            for ch in new_channels:
                                if ch.url_key not in seen:
                                    seen.add(ch.url_key)
                                    fresh.append(ch)
                            if fresh:
                                logger.info("[检测] 在线源 %s 下载完成, 新增 %d 个频道", src.name, len(fresh))
                                results.append(fresh)
                                if on_channels_ready:
                                    await on_channels_ready(fresh)
                            else:
                                logger.info("[检测] 在线源 %s 下载完成, 共 %d 个频道（全部已存在）", src.name, len(new_channels))
                            await self._event_store.append(
                                DomainEvents.SOURCE_DOWNLOADED,
                                {"source_name": src.name, "channel_count": len(fresh), "success": True},
                                self._session_id,
                            )
                        else:
                            logger.warning("[检测] 在线源 %s HTTP %d", src.name, resp.status)
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

            await _notify_source_done()

        await asyncio.gather(*[download_one(src) for src in list_sources])

        all_fresh = []
        for group in results:
            all_fresh.extend(group)
        return all_fresh
