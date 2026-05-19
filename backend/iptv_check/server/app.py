import os
import json
import asyncio
import logging
import datetime
import time
import urllib.parse
import base64
from typing import List, Optional
from pathlib import Path

from iptv_check.infra.cn_time import cn_now
from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response
from pydantic import BaseModel

from iptv_check.models.channel import Channel
from iptv_check.models.source import OnlineSource
from iptv_check.models.settings import CheckConfig, ExportConfig
from iptv_check.infra.network import ResilientHttpClient
from iptv_check.infra.disk_cache import DiskCacheManager
from iptv_check.infra.persistence_settings import SettingsManager
from iptv_check.infra.persistence.event_store import EventStore, SourceStore
from iptv_check.infra.persistence.read_model import ReadModel
from iptv_check.infra.persistence.materialization import MaterializationService
from iptv_check.infra.check_engine import AsyncCheckEngine
from iptv_check.core.m3u8_validator import M3U8Validator
from iptv_check.infra.exporter import ExportEngine
from iptv_check.infra.stream_proxy import StreamProxy
from iptv_check.infra.database import DatabaseManager
from iptv_check.infra.media_probe import MediaProbe
from iptv_check.infra.exceptions import CheckAlreadyRunningError, CheckNotRunningError, StreamProxyError
from iptv_check.core.isp_detector import ISPDetector
from iptv_check.core.parser import PlaylistParser
from iptv_check.core.converter import FormatConverter
from iptv_check.core.optimizer import SmartOptimizer
from iptv_check.core.health_checker import SourceHealthChecker
from iptv_check.infra.epg_cache import EpgCacheManager
from iptv_check.infra.logo_cache import LogoCacheManager
from iptv_check.application.services.check_service import CheckService
from iptv_check.application.services.epg_service import EpgService
from iptv_check.application.services.logo_service import LogoService
from iptv_check.infra.config.settings import settings, path_settings
from iptv_check.infra.config.settings import APP_TITLE, APP_VERSION
from iptv_check.infra.task_scheduler import TaskScheduler
from iptv_check.infra.event_bus import event_bus, Events
from iptv_check.application.services.source_sync_service import SourceSyncService
from iptv_check.infra.metrics import metrics
from iptv_check.infra.sse_broker import SSEBroker
from iptv_check.server.middleware import register_exception_handlers, register_middleware
from iptv_check.server.routers.channels import router as channels_router
from iptv_check.server.routers.sources import router as sources_router
from iptv_check.server.routers.check import router as check_router
from iptv_check.server.routers.export import router as export_router
from iptv_check.server.routers.epg import router as epg_router
from iptv_check.server.routers.logos import router as logos_router
from iptv_check.server.routers.cache import router as cache_router
from iptv_check.server.routers.source_sync import router as source_sync_router
from iptv_check.server.routers.fetch import router as fetch_router
from iptv_check.infra.logging_config import setup_logging

# 配置日志系统
setup_logging(level="INFO", json_format=False)

logger = logging.getLogger(__name__)

BASE_DIR = str(path_settings.base_dir)
DATA_DIR = str(path_settings.data_dir)
STATIC_DIR = str(path_settings.static_dir)


def _compute_group_stats(results):
    groups = {}
    for r in results:
        if not r or not r.channel:
            continue
        g = r.channel.group or "未分组"
        if g not in groups:
            groups[g] = {"total": 0, "valid": 0}
        groups[g]["total"] += 1
        if r.is_valid:
            groups[g]["valid"] += 1
    return [{"name": k, **v} for k, v in sorted(groups.items(), key=lambda x: x[1]["valid"], reverse=True)]


class AppState:
    _instance: Optional['AppState'] = None
    
    @classmethod
    def get_instance(cls) -> 'AppState':
        """单例模式：确保全局唯一实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置实例（仅用于测试）"""
        cls._instance = None
    
    def __init__(self):
        # 防止重复初始化
        if AppState._instance is not None:
            # 已经初始化过了，直接返回
            return
        AppState._instance = self
        
        self.http_client = ResilientHttpClient()
        self.stream_proxy = StreamProxy(
            max_connections=settings.stream_proxy_max_connections,
            timeout_connect=settings.stream_proxy_timeout_connect,
            timeout_read=settings.stream_proxy_timeout_read,
        )
        self.cache = DiskCacheManager(base_dir=DATA_DIR)
        self.settings = SettingsManager(base_dir=DATA_DIR)
        self.isp_detector = ISPDetector(self.http_client)
        self.export_engine = ExportEngine()

        db_path = settings.db_path or os.path.join(DATA_DIR, "events.db")
        self.database = DatabaseManager(db_path=db_path)
        self.event_store = EventStore(db_path=db_path)
        self.source_store = SourceStore(self.event_store)
        self.read_model = ReadModel(self.event_store)
        self.materialization = MaterializationService(self.event_store)

        self.online_sources: List[OnlineSource] = []
        self.local_isp: str = "未知"

        self._task_scheduler = TaskScheduler()
        self._scheduled_check_config: Optional[dict] = None
        self._health_checker = SourceHealthChecker()

        self._async_session: Optional[aiohttp.ClientSession] = None
        self._use_media_probe = False
        self._ffmpeg_available = False

        self._m3u_service_running = False
        self._m3u_service_file = ""
        self._m3u_service_started_at = None

        self._epg_service: Optional[EpgService] = None
        self._logo_service: Optional[LogoService] = None

        self._sse_broker = SSEBroker(max_subscribers=50, max_queue_size=100)
        self._check_service: Optional[CheckService] = None
        self._source_sync_service: Optional[SourceSyncService] = None
        self._fetch_service = None

        self._load_online_sources()

    @property
    def is_checking(self) -> bool:
        return self._check_service.is_running if self._check_service else False

    def _load_online_sources(self):
        try:
            if self.source_store:
                migrated = self.source_store.migrate_from_json(os.path.join(DATA_DIR, "local_sources.json"))
                if migrated > 0:
                    logger.info("数据库已有 %d 个源，跳过 JSON 迁移", migrated)
            self.online_sources = self.source_store.load_all() if self.source_store else self._load_online_sources_from_json()
            logger.info("加载了 %d 个在线直播源", len(self.online_sources))
        except Exception as e:
            logger.warning("加载在线源失败: %s", e)
            self.online_sources = []

    async def _load_online_sources_async(self):
        try:
            if self.source_store:
                migrated = await asyncio.to_thread(self.source_store.migrate_from_json, os.path.join(DATA_DIR, "local_sources.json"))
                if migrated > 0:
                    logger.info("数据库已有 %d 个源，跳过 JSON 迁移", migrated)
            if self.source_store:
                self.online_sources = await asyncio.to_thread(self.source_store.load_all)
            else:
                self.online_sources = self._load_online_sources_from_json()
            logger.info("加载了 %d 个在线直播源", len(self.online_sources))
        except Exception as e:
            logger.warning("加载在线源失败: %s", e)
            self.online_sources = []

    def _load_online_sources_from_json(self) -> List[OnlineSource]:
        sources_file = os.path.join(DATA_DIR, "local_sources.json")
        if os.path.exists(sources_file):
            with open(sources_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [OnlineSource.from_dict(s) for s in data.get("sources", [])]
        return []

    async def start(self):
        # 订阅 ISP 检测完成事件，实现实时推送
        # 注意：需要在 detect_isp 中直接调用 broadcast，而非通过事件总线
        # 因为 blinker 不支持 async 处理器
        event_bus.connect(Events.ISP_DETECTED, lambda sender, **kwargs: asyncio.create_task(self._on_isp_detected(sender, **kwargs)))
        
        asyncio.create_task(self.detect_isp())
        await self.stream_proxy.initialize()

        connector = aiohttp.TCPConnector(
            limit=settings.check_max_threads or 80, limit_per_host=30, ttl_dns_cache=300,
            use_dns_cache=True, enable_cleanup_closed=True, force_close=False,
            keepalive_timeout=30,
        )
        self._async_session = aiohttp.ClientSession(connector=connector)
        self._ffmpeg_available = MediaProbe.is_ffmpeg_available()

        check_engine = AsyncCheckEngine(
            http_session=self._async_session,
            cache=self.cache,
            m3u8_validator=M3U8Validator(self.http_client),
            proxy_base=settings.stream_proxy_base,
        )
        self._check_service = CheckService(
            event_store=self.event_store,
            read_model=self.read_model,
            check_engine=check_engine,
            broadcast_fn=self.broadcast,
        )

        from iptv_check.application.services.fetch_service import FetchService
        self._fetch_service = FetchService(
            event_store=self.event_store,
            broadcast_fn=self.broadcast,
            session_factory=lambda: self.event_store.get_session(),
        )

        logger.info("检测服务初始化完成，FFmpeg: %s", "可用" if self._ffmpeg_available else "不可用")

        repaired = await asyncio.to_thread(self.materialization.repair_is_radio)
        if repaired > 0:
            logger.info("启动时自动修复 is_radio: %d 条记录", repaired)

        epg_cache = EpgCacheManager(DATA_DIR)
        logo_cache = LogoCacheManager(DATA_DIR)
        self._epg_service = EpgService(self.http_client, epg_cache)
        self._logo_service = LogoService(self.http_client, logo_cache)
        self._logo_service.register_logo_sources(self.online_sources)
        logger.info("EPG和台标服务初始化完成")

        self._source_sync_service = SourceSyncService(
            DATA_DIR,
            http_session=self._async_session,
            env_remote_config_urls=settings.remote_config_urls,
            source_store=self.source_store,
            broadcast_fn=self.broadcast,
        )
        # Only sync from remote on first startup (empty DB); subsequent syncs use /source page
        if self.source_store and self.source_store.count() == 0:
            try:
                logger.info("数据库无源数据，执行首次远程同步...")
                sync_result = await self._source_sync_service.sync()
                if sync_result.success and (sync_result.added > 0 or sync_result.updated > 0):
                    await self._load_online_sources_async()
            except Exception as e:
                logger.warning("首次源同步失败: %s", e)
        else:
            logger.info("数据库已有 %d 个源，跳过启动同步（使用 /source 页面手动同步）",
                        self.source_store.count() if self.source_store else 0)

        try:
            if self._fetch_service and not self._fetch_service.is_fetching and not self._fetch_service.has_fetched_channels():
                all_source_ids = [s.id for s in self.online_sources]
                if all_source_ids:
                    asyncio.create_task(self._bg_startup_fetch(all_source_ids))
        except Exception as e:
            logger.warning("启动时自动拉取频道失败: %s", e)

        m3u_path = os.path.join(DATA_DIR, "exports", "iptv_live.m3u")
        if os.path.isfile(m3u_path):
            self._m3u_service_running = True
            self._m3u_service_file = m3u_path
            self._m3u_service_started_at = cn_now()
            logger.info("检测到上次遗留的 M3U 文件: %s", m3u_path)

        logger.info("服务启动完成: 在线源=%d, 本地ISP=%s, FFmpeg=%s",
                     len(self.online_sources), self.local_isp, "可用" if self._ffmpeg_available else "不可用")

    async def _bg_startup_fetch(self, source_ids):
        try:
            await self._fetch_service.start_fetch(source_ids, use_cache=True)
            logger.info("启动时自动拉取频道完成")
        except Exception as e:
            logger.warning("启动时自动拉取频道失败: %s", e)

    async def stop(self):
        await self._task_scheduler.shutdown()
        await self.stream_proxy.close()
        if self._async_session:
            await self._async_session.close()
            self._async_session = None
        self.cache.close()
        logger.info("服务已关闭")

    async def detect_isp(self):
        self.local_isp = await self.isp_detector.detect_local_isp_async()
        return self.local_isp

    async def _on_isp_detected(self, sender, **kwargs):
        """ISP 检测完成事件处理器，主动广播状态更新"""
        isp = kwargs.get("isp", "未知")
        logger.info("ISP 检测完成：%s", isp)
        await self.broadcast("isp_updated", {"local_isp": isp})

    async def broadcast(self, event: str, data: dict):
        logger.info("[SSE-BROKER] 广播事件: %s, 数据: %s", event, data)
        await self._sse_broker.broadcast(event, data)

    async def subscribe_sse(self):
        subscriber = await self._sse_broker.subscribe()
        logger.info("[SSE-BROKER] 新订阅者已创建: %s", subscriber.subscriber_id)
        return subscriber

    async def unsubscribe_sse(self, subscriber):
        logger.info("[SSE-BROKER] 订阅者取消订阅: %s", subscriber.subscriber_id)
        await self._sse_broker.unsubscribe(subscriber)


app_state: Optional[AppState] = None


def get_app_state() -> AppState:
    """获取全局 app_state 实例"""
    global app_state
    if app_state is None:
        app_state = AppState.get_instance()
    return app_state


def create_app() -> FastAPI:
    global app_state
    
    # 使用单例模式获取或创建 AppState 实例
    app_state = AppState.get_instance()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await app_state.start()
        yield
        await app_state.stop()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

    # Rate limiting
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware

        limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
        logger.info("API限流已启用: 60次/分钟/IP")
    except ImportError:
        logger.warning("slowapi未安装，API限流未启用")

    # Register middleware (correlation ID, request logging)
    register_middleware(app)

    # Register CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True if settings.cors_origins != ["*"] else False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    app.include_router(channels_router)
    app.include_router(sources_router)
    app.include_router(check_router)
    app.include_router(export_router)
    app.include_router(epg_router)
    app.include_router(logos_router)
    app.include_router(cache_router)
    app.include_router(source_sync_router)
    app.include_router(fetch_router)

    static_dir = path_settings.static_dir
    lib_dir = static_dir / "lib"
    js_dir = static_dir / "js"
    fonts_dir = static_dir / "fonts"
    static_hls_dir = path_settings.data_dir / "static"
    assets_dir = path_settings.data_dir / "assets"

    # Directories are automatically created by PathSettings model_validator

    if (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets"), html=True), name="assets")
        logger.info("Static assets mounted from: %s", static_dir / "assets")
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static-root")
        logger.info("Static files mounted from: %s", static_dir)
    if lib_dir.is_dir():
        app.mount("/lib", StaticFiles(directory=str(lib_dir)), name="lib")
    if js_dir.is_dir():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    if fonts_dir.is_dir():
        app.mount("/fonts", StaticFiles(directory=str(fonts_dir)), name="fonts")
    if static_hls_dir.is_dir():
        app.mount("/hls-static", StaticFiles(directory=str(static_hls_dir)), name="hls-static")

    @app.get("/")
    async def index():
        index_file = static_dir / "index.html"
        if index_file.is_file():
            return FileResponse(str(index_file))
        return HTMLResponse("<h1>IPTV-Check API Server</h1><p>前端未构建，请访问 <a href='/docs'>/docs</a> 查看 API</p>")

    @app.get("/healthz")
    async def healthz():
        """Liveness probe - checks if the server process is running"""
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/readyz")
    async def readyz():
        """Readiness probe - checks if the server is ready to serve requests"""
        checks = {
            "static_files": (static_dir / "index.html").is_file(),
            "database": True,
            "services": app_state is not None,
        }
        if all(checks.values()):
            return {"status": "ready", "checks": checks}
        return Response(
            status_code=503,
            content=json.dumps({"status": "not_ready", "checks": checks}, ensure_ascii=False),
            media_type="application/json",
        )

    @app.get("/api/favicon")
    async def favicon():
        icon_path = assets_dir / "icon.ico"
        if icon_path.is_file():
            return FileResponse(str(icon_path), media_type="image/x-icon")
        return Response(status_code=204)

    from iptv_check.infra.player_renderer import player_renderer
    from iptv_check.infra.config.settings import render_player_html  # keep compat

    @app.get("/player")
    async def player_page(url: str = "", name: str = "", sources: str = "", radio: str = "", region: str = "", freq: str = ""):
        try:
            decoded = base64.b64decode(url).decode("utf-8") if url else ""
            stream_url = urllib.parse.unquote(decoded)
        except Exception:
            stream_url = url
        channel_name = name or "未知频道"
        is_radio = radio == "1"

        source_list = None
        if sources:
            try:
                source_list = json.loads(base64.b64decode(sources).decode("utf-8"))
            except Exception:
                pass

        html = player_renderer.render(stream_url, channel_name, sources=source_list, is_radio=is_radio, channel_group=region, frequency=freq)
        return HTMLResponse(html)

    @app.get("/proxy")
    async def proxy_unified(request: Request, url: str = "", referer: str = "", origin: str = "", cookie: str = ""):
        if not url:
            raise HTTPException(400, "缺少代理 URL 参数")
        try:
            target_url = app_state.stream_proxy.decode_proxy_url(url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        custom_headers = {}
        if referer: custom_headers["referer"] = referer
        if origin: custom_headers["origin"] = origin
        if cookie: custom_headers["cookie"] = cookie
        try:
            return await app_state.stream_proxy.proxy_unified(target_url, request, custom_headers)
        except Exception as e:
            logger.warning("代理请求失败 %s: %s", target_url, e)
            raise StreamProxyError(str(e)[:100])

    @app.get("/proxy/hls")
    async def proxy_hls_playlist_new(request: Request, url: str = ""):
        if not url:
            raise HTTPException(400, "缺少代理 URL 参数")
        try:
            target_url = app_state.stream_proxy.decode_proxy_url(url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        try:
            return await app_state.stream_proxy.proxy_hls_playlist(target_url, request)
        except Exception as e:
            logger.warning("HLS 播放列表代理失败 %s: %s", target_url, e)
            raise StreamProxyError(str(e)[:100])

    @app.get("/proxy/stats")
    async def proxy_stats():
        return app_state.stream_proxy.get_stats()

    @app.get("/favicon.ico")
    async def favicon_ico():
        icon_path = assets_dir / "icon.ico"
        if icon_path.is_file():
            return FileResponse(str(icon_path), media_type="image/x-icon")
        return Response(status_code=204)

    @app.get("/api/events/stream")
    async def sse_stream(request: Request):
        subscriber = await app_state.subscribe_sse()

        async def generate():
            if app_state._check_service:
                progress = app_state._check_service.get_progress()
            else:
                progress = app_state.read_model.get_check_progress()
            init_data = json.dumps({
                "event": "init",
                "local_isp": app_state.local_isp,
                "is_checking": app_state.is_checking,
                **progress,
            }, ensure_ascii=False)
            yield f"event: init\ndata: {init_data}\n\n"

            try:
                while True:
                    if await request.is_disconnected():
                        break
                    msg = await subscriber.get(timeout=30)
                    if msg:
                        yield msg
                    else:
                        yield f"event: heartbeat\ndata: {{}}\n\n"
            finally:
                await app_state.unsubscribe_sse(subscriber)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/check/progress")
    async def get_check_progress():
        if not app_state or not app_state._check_service:
            return {"total": 0, "checked": 0, "valid": 0, "invalid": 0, "is_running": False, "progress_percent": 0.0}
        return app_state._check_service.get_progress()

    @app.get("/api/debug/state")
    async def debug_state():
        """调试路由：返回 app_state 的完整状态"""
        import traceback
        try:
            if app_state is None:
                return {"error": "app_state is None"}
            return {
                "app_state": "OK",
                "is_checking": app_state.is_checking,
                "event_store": app_state.event_store is not None,
                "source_store": app_state.source_store is not None,
                "_check_service": app_state._check_service is not None,
                "session_id": app_state._check_service.session_id if app_state._check_service else None,
                "read_model": app_state.read_model is not None,
            }
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    @app.get("/api/metrics")
    async def get_metrics():
        """Prometheus-compatible metrics endpoint"""
        return Response(content=metrics.generate_metrics(), media_type="text/plain")

    @app.get("/api/sse/stats")
    async def get_sse_stats():
        """SSE broker statistics"""
        return app_state._sse_broker.get_stats()

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA fallback - serve index.html for all non-API frontend routes (MUST be last)"""
        index_file = static_dir / "index.html"
        if index_file.is_file():
            return FileResponse(str(index_file))
        raise HTTPException(404, "Frontend not built")

    return app
