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
from iptv_check.infra.persistence.event_store import EventStore
from iptv_check.infra.persistence.read_model import ReadModel
from iptv_check.infra.check_engine import ThreadPoolCheckEngine
from iptv_check.infra.exporter import ExportEngine
from iptv_check.infra.stream_proxy import StreamProxy
from iptv_check.infra.database import DatabaseManager
from iptv_check.infra.media_probe import MediaProbe
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

from iptv_check.server.routers.channels import router as channels_router
from iptv_check.server.routers.sources import router as sources_router
from iptv_check.server.routers.check import router as check_router
from iptv_check.server.routers.export import router as export_router
from iptv_check.server.routers.epg import router as epg_router
from iptv_check.server.routers.logos import router as logos_router
from iptv_check.server.routers.cache import router as cache_router

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = str(path_settings.data_dir)
STATIC_DIR = str(path_settings.static_dir)


def _compute_group_stats(results):
    groups = {}
    for r in results:
        g = r.channel.group or "未分组"
        if g not in groups:
            groups[g] = {"total": 0, "valid": 0}
        groups[g]["total"] += 1
        if r.is_valid:
            groups[g]["valid"] += 1
    return [{"name": k, **v} for k, v in sorted(groups.items(), key=lambda x: x[1]["valid"], reverse=True)]


class AppState:
    def __init__(self):
        self.http_client = ResilientHttpClient()
        self.stream_proxy = StreamProxy(
            max_connections=settings.stream_proxy_max_connections,
            timeout_connect=settings.stream_proxy_timeout_connect,
            timeout_read=settings.stream_proxy_timeout_read,
        )
        self.cache = DiskCacheManager(base_dir=DATA_DIR)
        self.settings = SettingsManager(base_dir=DATA_DIR)
        self.database = DatabaseManager(db_path=os.path.join(DATA_DIR, "iptv_check.db"))
        self.isp_detector = ISPDetector(self.http_client)
        self.export_engine = ExportEngine()

        db_path = settings.db_path or os.path.join(DATA_DIR, "events.db")
        self.event_store = EventStore(db_path=db_path)
        self.read_model = ReadModel(self.event_store)

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

        self._sse_subscribers: List[asyncio.Queue] = []
        self._sse_counter: int = 0
        self._check_service: Optional[CheckService] = None

        self._load_online_sources()

    @property
    def is_checking(self) -> bool:
        return self._check_service.is_running if self._check_service else False

    def _load_online_sources(self):
        try:
            sources_file = os.path.join(DATA_DIR, "local_sources.json")
            if os.path.exists(sources_file):
                with open(sources_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.online_sources = [OnlineSource.from_dict(s) for s in data.get("sources", [])]
                logger.info("加载了 %d 个在线直播源", len(self.online_sources))
        except Exception as e:
            logger.warning("加载在线源失败: %s", e)

    async def start(self):
        asyncio.create_task(self.detect_isp())
        await self.stream_proxy.initialize()

        connector = aiohttp.TCPConnector(
            limit=100, limit_per_host=30, ttl_dns_cache=300,
            use_dns_cache=True, enable_cleanup_closed=True, force_close=False,
        )
        self._async_session = aiohttp.ClientSession(connector=connector)
        self._ffmpeg_available = MediaProbe.is_ffmpeg_available()

        check_engine = ThreadPoolCheckEngine(self.http_client, self.cache)
        self._check_service = CheckService(
            event_store=self.event_store,
            read_model=self.read_model,
            check_engine=check_engine,
            broadcast_fn=self.broadcast,
        )
        logger.info("检测服务初始化完成，FFmpeg: %s", "可用" if self._ffmpeg_available else "不可用")

        epg_cache = EpgCacheManager(DATA_DIR)
        logo_cache = LogoCacheManager(DATA_DIR)
        self._epg_service = EpgService(self.http_client, epg_cache)
        self._logo_service = LogoService(self.http_client, logo_cache)
        self._logo_service.register_logo_sources(self.online_sources)
        logger.info("EPG和台标服务初始化完成")

        m3u_path = os.path.join(DATA_DIR, "exports", "iptv_live.m3u")
        if os.path.isfile(m3u_path):
            self._m3u_service_running = True
            self._m3u_service_file = m3u_path
            self._m3u_service_started_at = datetime.datetime.utcnow()
            logger.info("检测到上次遗留的 M3U 文件: %s", m3u_path)

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

    async def broadcast(self, event: str, data: dict):
        self._sse_counter += 1
        msg = {"event": event}
        msg.update(data)
        sse_msg = f"id: {self._sse_counter}\nevent: {event}\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
        dead = []
        for i, queue in enumerate(self._sse_subscribers):
            try:
                await queue.put(sse_msg)
            except Exception:
                dead.append(i)
        for i in sorted(dead, reverse=True):
            if i < len(self._sse_subscribers):
                self._sse_subscribers.pop(i)

    def subscribe_sse(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._sse_subscribers.append(queue)
        return queue

    def unsubscribe_sse(self, queue: asyncio.Queue):
        try:
            self._sse_subscribers.remove(queue)
        except ValueError:
            pass


app_state: Optional[AppState] = None


def create_app() -> FastAPI:
    global app_state

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global app_state
        app_state = AppState()
        await app_state.start()
        yield
        await app_state.stop()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True if settings.cors_origins != ["*"] else False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(channels_router)
    app.include_router(sources_router)
    app.include_router(check_router)
    app.include_router(export_router)
    app.include_router(epg_router)
    app.include_router(logos_router)
    app.include_router(cache_router)

    static_dir = Path(STATIC_DIR)
    lib_dir = static_dir / "lib"
    js_dir = static_dir / "js"
    fonts_dir = static_dir / "fonts"
    static_hls_dir = Path(DATA_DIR) / "static"
    assets_dir = Path(DATA_DIR) / "assets"

    path_settings.ensure_dirs()

    if (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")
        logger.info("Static assets mounted from: %s", static_dir / "assets")
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

    from iptv_check.infra.config.settings import render_player_html

    @app.get("/player")
    async def player_page(url: str = "", name: str = "", sources: str = ""):
        try:
            decoded = base64.b64decode(url).decode("utf-8") if url else ""
            stream_url = urllib.parse.unquote(decoded)
        except Exception:
            stream_url = url
        channel_name = name or "未知频道"

        source_list = None
        if sources:
            try:
                source_list = json.loads(base64.b64decode(sources).decode("utf-8"))
            except Exception:
                pass

        html = render_player_html(stream_url, channel_name, sources=source_list)
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
            raise HTTPException(502, f"代理错误: {str(e)[:100]}")

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
            raise HTTPException(502, f"代理错误: {str(e)[:100]}")

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
        queue = app_state.subscribe_sse()

        async def generate():
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
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=30)
                        yield msg
                    except asyncio.TimeoutError:
                        yield f"event: heartbeat\ndata: {{}}\n\n"
            finally:
                app_state.unsubscribe_sse(queue)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/check/progress")
    async def get_check_progress():
        if not app_state._check_service:
            return {"total": 0, "checked": 0, "valid": 0, "invalid": 0, "is_running": False, "progress_percent": 0.0}
        return app_state._check_service.get_progress()

    return app


app = create_app()
