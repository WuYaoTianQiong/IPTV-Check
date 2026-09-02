import asyncio
import hashlib
import time
import logging
import threading
from typing import List, Optional, Callable

import aiohttp

from iptv_check.models.channel import Channel
from iptv_check.models.source import is_channel_url
from iptv_check.core.parser import infer_is_radio
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig, CheckMode
from iptv_check.domain.events import DomainEvents
from iptv_check.infra.async_download import NonRetryableHttpError, fetch_text_with_retry
from iptv_check.infra.persistence.event_store import EventStore
from iptv_check.infra.persistence.read_model import ReadModel
from iptv_check.infra.check_engine.base import CheckEngineProtocol
from iptv_check.infra.config.settings import settings
from iptv_check.infra.batch_result_collector import BatchResultCollector

logger = logging.getLogger(__name__)


def _parse_check_mode(value) -> CheckMode:
    try:
        return CheckMode(value)
    except (ValueError, TypeError):
        return CheckMode.STANDARD


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
        # 下载在线源阶段的进度（供前端 downloading 阶段按真实完成度显示，替代固定 15%）
        self._download_done: int = 0
        self._download_total: int = 0
        # 检测完成后的后台任务集合（物化等），持有引用防止 GC 提前回收
        self._background_tasks: set = set()

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
        state["session_id"] = self._session_id
        state["is_running"] = self.is_running
        state["stage"] = getattr(self, "_current_stage", "")
        state["stage_message"] = getattr(self, "_current_stage_message", "")
        state["download_done"] = self._download_done
        state["download_total"] = self._download_total
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
        # 记录本会话的检测方案与来源会话（细筛场景），供历史保存与细筛加载判断
        self._check_mode = getattr(req, 'check_mode', 'standard') or 'standard'
        self._source_session_id = getattr(req, 'source_session_id', '') or ''
        await self._event_store.append(DomainEvents.CHECK_STARTED, {"session_id": self._session_id}, self._session_id)
        await self._broadcast_fn("check_started", {"total": 0, "session_id": self._session_id})
        await self._broadcast_stage("parsing", "正在解析本地文件...")

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
            check_mode=_parse_check_mode(getattr(req, 'check_mode', 'standard')),
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
            if not channels:
                return
            # 批量写入事件表，避免逐条 commit（1 万+ 频道时逐条写耗时可达数秒~数十秒）
            events = [
                (DomainEvents.CHANNEL_SUBMITTED,
                 {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group,
                  "sources": ch.sources, "is_radio": ch.is_radio})
                for ch in channels
            ]
            await self._event_store.append_batch(events, self._session_id)

        engine_started = False

        async def _feed_batch(fresh: List, label: str = ""):
            """边加载边测：每加载一批立即喂入引擎，不等待全部源加载完"""
            nonlocal engine_started
            if not fresh:
                return
            # 启动/追加判断必须放在首个 await 之前：_feed_batch 可能被
            # _download_sources 的 asyncio.gather 并发调用，协程执行到首个
            # await 前是同步的，可保证 start() 只触发一次
            if not engine_started:
                engine_started = True
                self._check_engine.start(
                    fresh, config,
                    on_result=on_result, on_complete=on_complete,
                    on_cached_result=on_cached_result,
                    streaming=True,
                )
                logger.info("[检测] 引擎已启动(边加载边测), 首批=%d", len(fresh))
            else:
                self._check_engine.add_channels(fresh, config)
            await _emit_channel_submitted(fresh)
            self._check_total += len(fresh)
            self._collector.set_total(self._check_total)
            if label:
                await self._broadcast_stage("downloading", f"{label}（已入队 {self._check_total} 个频道，边加载边检测中）")

        # Phase 0.5: 从历史会话加载有效频道（细筛入口，不重新下载任何在线源）
        source_session_id = getattr(req, 'source_session_id', '') or ''
        if source_session_id:
            await self._broadcast_stage("loading", f"正在从历史会话 {source_session_id[:8]} 加载有效频道...")
            detail_channels = await self._load_valid_channels_from_session(source_session_id)
            fresh = []
            for ch in detail_channels:
                if ch.url_key not in seen:
                    seen.add(ch.url_key)
                    fresh.append(ch)
                    all_channels.append(ch)
            if fresh:
                await _feed_batch(fresh, "历史有效频道已加载")
            logger.info("[检测] 从历史会话 %s 加载有效频道 %d 个", source_session_id, len(fresh))

        # Phase 1: 加载本地文件
        if req.file_paths:
            channels = await asyncio.to_thread(PlaylistParser.parse_files, req.file_paths)
            logger.info("[检测] 本地文件解析完成, 频道数=%d", len(channels))
            fresh = []
            for ch in channels:
                if ch.url_key not in seen:
                    seen.add(ch.url_key)
                    fresh.append(ch)
                    all_channels.append(ch)
            if fresh:
                await _feed_batch(fresh, "本地文件已加载")

        # Phase 1.5: 下载用户自定义源 URL
        custom_urls = list(getattr(req, 'custom_source_urls', None) or [])
        if custom_urls:
            await self._download_custom_sources(custom_urls, seen, all_channels, _feed_batch)

        # Phase 2: 加载在线源频道
        if req.online_source_ids:
            fetch_svc = getattr(self._app_state, '_fetch_service', None)
            use_fetched = False
            estimated_total = 0
            if fetch_svc:
                # 2026-09-01: 仅当"所选源"在 fetched_channels 中确有频道时才走 DB 加载。
                # 此前用 has_fetched_channels()（整表非空即 True）判断，导致用户选了
                # 从未拉取过的新源时误走 DB 加载、取到 0 频道 → 检测 failed("未解析到任何频道")。
                estimated_total = await asyncio.to_thread(
                    fetch_svc.count_fetched_channels, list(req.online_source_ids)
                )
                use_fetched = estimated_total > 0
            if use_fetched:
                await self._broadcast_stage("downloading", f"正在从数据库加载频道（预计 {estimated_total} 个）...")
                fetched_channels = await asyncio.to_thread(fetch_svc.get_fetched_channels, list(req.online_source_ids))
                fresh = []
                for ch in fetched_channels:
                    if ch.url_key not in seen:
                        seen.add(ch.url_key)
                        fresh.append(ch)
                        all_channels.append(ch)
                if fresh:
                    await _feed_batch(fresh, "数据库频道已加载")
                logger.info("[检测] 从数据库加载频道完成, 频道数=%d", len(all_channels))
            else:
                await self._broadcast_stage("downloading", f"正在下载在线源 (0/{len(req.online_source_ids)})...")
                online_channels = await self._download_sources(req, seen, self._app_state, on_channels_ready=_feed_batch)
                all_channels.extend(online_channels)

        # 全部源加载完毕，关闭流式接收，广播最终进度
        if engine_started:
            self._check_engine.complete()

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

        # Phase 3: 通知前端全部频道已就绪
        await self._broadcast_fn("channels_loaded", {"total": self._check_total})
        await self._broadcast_stage("checking", f"正在检测 {self._check_total} 个频道...")
        logger.info("[检测] 全部频道已入队, 等待检测完成, 总数=%d", self._check_total)

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

        # 历史记录保存（轻量，串行等待）；与物化解耦，避免慢物化拖累历史落库
        try:
            await asyncio.wait_for(self._save_to_history(t0), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("[检测] 历史保存超时(30s)")
        except Exception as e:
            logger.error("[检测] 历史保存失败: %s", e)

        # 物化放后台任务：不阻塞完成流程，耗时超过 60s 也不取消（数据不丢失）。
        # 查询层另有按需物化兜底（ReadModel._ensure_materialized），双保险。
        bg = asyncio.create_task(self._materialize_results())
        self._background_tasks.add(bg)
        bg.add_done_callback(self._background_tasks.discard)

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
                check_mode=getattr(self, '_check_mode', '') or '',
                parent_session_id=getattr(self, '_source_session_id', '') or '',
            )
            logger.info("[检测] 已保存历史记录: %s", self._session_id)
        except Exception as e:
            logger.warning("[检测] 保存历史记录失败: %s", e)

    async def _load_valid_channels_from_session(self, source_session_id: str) -> List[Channel]:
        """从历史会话的物化结果中读取有效（is_valid）频道，供细筛检测复用。

        不重新下载任何在线源，直接基于该会话上次检测已确认可达的 URL 集合
        构建输入，从而避免"每次检测都全局跑一遍"。
        """
        from iptv_check.models.channel import Channel

        results = await asyncio.to_thread(self._read_model.get_checked_results_raw, source_session_id)
        channels: List[Channel] = []
        for rd in results:
            if not rd.get("is_valid"):
                continue
            chd = rd.get("channel") or {}
            url = chd.get("url", "")
            if not url:
                continue
            # 带上粗筛 latency 作为先验：慢源在 DEEP 测速时给更短上限，避免无谓等待
            prior_lat = rd.get("latency")
            prior_latency = float(prior_lat) if isinstance(prior_lat, (int, float)) and prior_lat >= 0 else None
            channels.append(Channel(
                name=chd.get("name") or "",
                url=url,
                group=chd.get("group", ""),
                sources=chd.get("sources") or [],
                is_radio=bool(chd.get("is_radio", False)),
                tvg_name=chd.get("tvg_name", ""),
                country=chd.get("country", ""),
                resolution=chd.get("resolution", ""),
                prior_latency=prior_latency,
            ))
        return channels

    @staticmethod
    def _is_channel_url(src) -> bool:
        """判断源是否为"频道级源"（URL 直接是流地址，无需下载解析）。

        统一复用 models.source.is_channel_url，与拉取（fetch）路径保持一致，
        避免"其他频道"等分类的列表源被误当成单频道源。
        """
        return is_channel_url(src)

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

    async def _download_custom_sources(self, custom_urls: List[str], seen: set, all_channels: List[Channel], on_channels_ready=None) -> None:
        """下载用户自定义的 M3U 源 URL 并解析为频道（复用在线源的下载超时配置）"""
        from iptv_check.core.parser import PlaylistParser

        total = len(custom_urls)
        for idx, url in enumerate(custom_urls, 1):
            src_name = f"自定义源{idx}"
            try:
                await self._broadcast_stage("downloading", f"正在下载自定义源 ({idx}/{total})...")
                timeout = aiohttp.ClientTimeout(
                    total=settings.download_timeout,
                    connect=10,
                    sock_read=settings.download_timeout,
                )
                async with self._app_state._async_session.get(url, timeout=timeout, ssl=False) as resp:
                    resp.raise_for_status()
                    content = await resp.text()
                # 解析大 m3u 是同步 CPU 密集操作（2.8 万频道可达数百 ms），移入线程池避免阻塞事件循环
                new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, content, src_name, "自定义")
                fresh = []
                for ch in new_channels:
                    if ch.url_key not in seen:
                        seen.add(ch.url_key)
                        fresh.append(ch)
                all_channels.extend(fresh)
                await self._event_store.append(
                    DomainEvents.SOURCE_DOWNLOADED,
                    {"source_name": src_name, "channel_count": len(fresh), "success": True},
                    self._session_id,
                )
                if fresh and on_channels_ready:
                    await on_channels_ready(fresh)
                logger.info("[检测] 自定义源 %s 解析 %d 个频道", url, len(fresh))
            except Exception as e:
                logger.error("[检测] 自定义源 %s 下载失败: %s", url, e)
                await self._event_store.append(
                    DomainEvents.SOURCE_DOWNLOADED,
                    {"source_name": src_name, "channel_count": 0, "success": False},
                    self._session_id,
                )
        if all_channels:
            await self._broadcast_stage("downloading", f"自定义源已加载 {len(all_channels)} 个频道")

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
            frequency = Channel._extract_frequency(src.name or "", src.category or "")
            is_radio = infer_is_radio(name=src.name, group=src.category, url=url, frequency=frequency)
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
                frequency=frequency,
            )
            if ch.url_key not in seen:
                seen.add(ch.url_key)
                direct_channels.append(ch)

        if direct_channels:
            results.append(direct_channels)
            await self._event_store.append(
                DomainEvents.SOURCE_DOWNLOADED,
                {"source_name": "频道级源", "channel_count": len(direct_channels), "success": True},
                self._session_id,
            )
            if on_channels_ready:
                # CHANNEL_SUBMITTED 事件由回调（_feed_batch）统一写入，避免重复计数 total
                await on_channels_ready(direct_channels)
            else:
                await self._event_store.append_batch(
                    [(DomainEvents.CHANNEL_SUBMITTED,
                      {"url_key": ch.url_key, "name": ch.name, "url": ch.url, "group": ch.group,
                       "sources": ch.sources, "is_radio": ch.is_radio})
                     for ch in direct_channels],
                    self._session_id,
                )
            logger.info("[检测] 频道级源直接加载 %d 个频道", len(direct_channels))

        if not list_sources:
            all_fresh = []
            for group in results:
                all_fresh.extend(group)
            return all_fresh

        sem = asyncio.Semaphore(settings.download_concurrency)
        download_done_count = 0
        total_sources = len(list_sources)
        self._download_total = total_sources
        self._download_done = 0
        download_lock = asyncio.Lock()

        async def _notify_source_done():
            nonlocal download_done_count
            async with download_lock:
                download_done_count += 1
                self._download_done = download_done_count
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
                            new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, cached, src.name, src.category or "")
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
                    try:
                        text = await fetch_text_with_retry(app_state._async_session, url, timeout)
                    except NonRetryableHttpError as e:
                        # 4xx 等不可重试状态：记录下载失败，不触发重试
                        logger.warning("[检测] 在线源 %s %s", src.name, e)
                        await self._event_store.append(
                            DomainEvents.SOURCE_DOWNLOADED,
                            {"source_name": src.name, "channel_count": 0, "success": False},
                            self._session_id,
                        )
                        await _notify_source_done()
                        return
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
                    new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, text, src.name, src.category or "")
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
