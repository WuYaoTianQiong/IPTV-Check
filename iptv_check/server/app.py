import os
import json
import asyncio
import logging
import threading
import concurrent.futures
import time
import urllib.parse
from typing import List, Optional
from pathlib import Path
from contextlib import asynccontextmanager

import base64
import aiohttp

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response
from starlette.requests import Request
from pydantic import BaseModel

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.source import OnlineSource
from iptv_check.models.settings import CheckConfig, ExportConfig
from iptv_check.infra.network import HttpClient
from iptv_check.infra.cache import CacheManager
from iptv_check.infra.persistence import SettingsManager
from iptv_check.infra.state import StateStore
from iptv_check.infra.check_state_machine import CheckStateMachine
from iptv_check.infra.exporter import ExportEngine
from iptv_check.infra.stream_proxy import StreamProxy
from iptv_check.infra.database import DatabaseManager
from iptv_check.infra.media_probe import MediaProbe
from iptv_check.core.checker import CheckEngine
from iptv_check.core.async_checker import AsyncCheckEngine
from iptv_check.core.isp_detector import ISPDetector
from iptv_check.core.parser import PlaylistParser
from iptv_check.core.converter import FormatConverter
from iptv_check.core.optimizer import SmartOptimizer
from iptv_check.config import APP_TITLE, APP_VERSION

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


class CheckRequest(BaseModel):
    file_paths: List[str] = []
    online_source_ids: List[str] = []
    timeout_connect: int = 3
    timeout_read: int = 8
    max_threads: int = 80
    run_speed_test: bool = True
    use_cache: bool = True


class ExportRequest(BaseModel):
    format: str = "m3u"
    export_dir: str = ""
    base_name: str = "检测结果"
    export_mode: str = "merged"


class ConvertRequest(BaseModel):
    input_path: str = ""
    output_format: str = "m3u"


class ConvertTextRequest(BaseModel):
    content: str
    from_format: str
    to_format: str


class AppState:
    def __init__(self):
        self.http_client = HttpClient()
        self.stream_proxy = StreamProxy(max_connections=100, timeout_connect=10, timeout_read=30)
        self.cache = CacheManager(base_dir=BASE_DIR)
        self.settings = SettingsManager(base_dir=BASE_DIR)
        self.state_store = StateStore()
        self.check_engine = CheckEngine(self.http_client, self.cache, self.state_store)
        self.isp_detector = ISPDetector(self.http_client)
        self.export_engine = ExportEngine()
        self.database = DatabaseManager(db_path=os.path.join(BASE_DIR, "data", "iptv_check.db"))
        self.online_sources: List[OnlineSource] = []
        self.local_isp: str = "未知"
        self.is_checking: bool = False
        self.check_results: List[CheckResult] = []
        self._ws_clients: List[WebSocket] = []
        self._ws_lock = threading.Lock()
        self._event_queue: Optional[asyncio.Queue] = None
        self._broadcast_task: Optional[asyncio.Task] = None
        self._check_total: int = 0

        self._async_session: Optional[aiohttp.ClientSession] = None
        self._async_check_engine: Optional[AsyncCheckEngine] = None
        self._check_state_machine: Optional[CheckStateMachine] = None
        self._use_media_probe = False
        self._ffmpeg_available = False

        # M3U 服务状态追踪
        self._m3u_service_running = False
        self._m3u_service_file = ""
        self._m3u_service_started_at = None

        self._load_latest_results()
        self._load_online_sources()

    def _load_online_sources(self):
        try:
            sources_file = os.path.join(BASE_DIR, "local_sources.json")
            if os.path.exists(sources_file):
                with open(sources_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.online_sources = [OnlineSource.from_dict(s) for s in data.get("sources", [])]
                logger.info("加载了 %d 个在线直播源", len(self.online_sources))
        except Exception as e:
            logger.warning("加载在线源失败: %s", e)

    def _load_latest_results(self):
        try:
            latest = self.database.load_latest_results()
            if latest:
                logger.info("从数据库加载上次检测结果: %d 条", len(latest))
                self.check_results = [CheckResult(**r) for r in latest]
        except Exception as e:
            logger.warning("加载上次检测结果失败: %s", e)

    async def start(self):
        """服务启动时调用"""
        self._event_queue = asyncio.Queue()
        self._broadcast_task = asyncio.create_task(self._broadcast_worker())
        asyncio.create_task(self.detect_isp())
        await self.stream_proxy.initialize()

        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True,
            force_close=False,
        )
        self._async_session = aiohttp.ClientSession(connector=connector)
        self._ffmpeg_available = MediaProbe.is_ffmpeg_available()
        self._async_check_engine = AsyncCheckEngine(
            session=self._async_session,
            cache=self.cache,
            use_media_probe=self._use_media_probe,
        )
        self._check_state_machine = CheckStateMachine()
        logger.info("异步检测引擎初始化完成，FFmpeg: %s", "可用" if self._ffmpeg_available else "不可用")

        # 恢复 M3U 服务状态
        m3u_path = os.path.join(BASE_DIR, "exports", "iptv_live.m3u")
        if os.path.isfile(m3u_path):
            self._m3u_service_running = True
            self._m3u_service_file = m3u_path
            self._m3u_service_started_at = datetime.datetime.utcnow()
            logger.info("检测到上次遗留的 M3U 文件: %s", m3u_path)

    async def stop(self):
        """服务关闭时调用"""
        if self._broadcast_task:
            await self._event_queue.put(None)
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
        await self.stream_proxy.close()
        if self._async_session:
            await self._async_session.close()
            self._async_session = None
        if self._async_check_engine:
            await self._async_check_engine.stop()
        logger.info("服务已关闭")

    async def detect_isp(self):
        loop = asyncio.get_event_loop()
        self.local_isp = await loop.run_in_executor(None, self.isp_detector.detect_local_isp)
        return self.local_isp

    async def broadcast(self, event: str, data: dict):
        """将事件放入队列，由 broadcast_worker 统一推送"""
        if self._event_queue:
            await self._event_queue.put({"event": event, **data})

    async def _broadcast_worker(self):
        """单一异步任务，从队列取消息并广播给所有 WebSocket 客户端"""
        while True:
            msg = await self._event_queue.get()
            if msg is None:
                break
            dead = []
            with self._ws_lock:
                clients = list(self._ws_clients)
            for ws in clients:
                try:
                    await ws.send_json(msg)
                except Exception:
                    dead.append(ws)
            if dead:
                with self._ws_lock:
                    for ws in dead:
                        if ws in self._ws_clients:
                            self._ws_clients.remove(ws)

    def register_ws(self, ws: WebSocket):
        with self._ws_lock:
            self._ws_clients.append(ws)

    def unregister_ws(self, ws: WebSocket):
        with self._ws_lock:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)


def create_app() -> FastAPI:
    app_state: Optional[AppState] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal app_state
        app_state = AppState()
        await app_state.start()
        yield
        await app_state.stop()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    frontend_dir = os.path.join(BASE_DIR, "iptv_check", "frontend", "dist")
    lib_dir = os.path.join(frontend_dir, "lib")
    js_dir = os.path.join(frontend_dir, "js")
    fonts_dir = os.path.join(frontend_dir, "fonts")
    static_hls_dir = os.path.join(BASE_DIR, "iptv_check", "app", "static")
    assets_dir = os.path.join(BASE_DIR, "assets")

    if os.path.isdir(frontend_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")
    if os.path.isdir(lib_dir):
        app.mount("/lib", StaticFiles(directory=lib_dir), name="lib")
    if os.path.isdir(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if os.path.isdir(fonts_dir):
        app.mount("/fonts", StaticFiles(directory=fonts_dir), name="fonts")
    if os.path.isdir(static_hls_dir):
        app.mount("/hls-static", StaticFiles(directory=static_hls_dir), name="hls-static")

    @app.get("/")
    async def index():
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return HTMLResponse("<h1>IPTV-Check API Server</h1><p>前端未构建，请访问 <a href='/docs'>/docs</a> 查看 API</p>")

    @app.get("/api/favicon")
    async def favicon():
        icon_path = os.path.join(assets_dir, "icon.ico")
        if os.path.isfile(icon_path):
            return FileResponse(icon_path, media_type="image/x-icon")
        return Response(status_code=204)

    from iptv_check.config import PLAYER_HTML_TEMPLATE

    @app.get("/player")
    async def player_page(url: str = "", name: str = ""):
        try:
            decoded = base64.b64decode(url).decode("utf-8") if url else ""
            stream_url = urllib.parse.unquote(decoded)
        except Exception:
            stream_url = url
        channel_name = name or "未知频道"
        html = PLAYER_HTML_TEMPLATE.format(url=stream_url, name=channel_name)
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
        if referer:
            custom_headers["referer"] = referer
        if origin:
            custom_headers["origin"] = origin
        if cookie:
            custom_headers["cookie"] = cookie

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
        icon_path = os.path.join(assets_dir, "icon.ico")
        if os.path.isfile(icon_path):
            return FileResponse(icon_path, media_type="image/x-icon")
        return Response(status_code=204)

    @app.get("/api/info")
    async def get_info():
        return {
            "version": APP_VERSION,
            "title": APP_TITLE,
            "local_isp": app_state.local_isp,
            "is_checking": app_state.is_checking,
            "online_sources_count": len(app_state.online_sources),
        }

    @app.get("/api/isp")
    async def get_isp():
        if app_state.local_isp == "未知":
            await app_state.detect_isp()
        return {"local_isp": app_state.local_isp}

    @app.post("/api/isp/refresh")
    async def refresh_isp():
        await app_state.detect_isp()
        return {"local_isp": app_state.local_isp}

    @app.get("/api/online-sources")
    async def get_online_sources():
        return {
            "sources": [
                {
                    "id": s.id, "name": s.name, "url": s.url,
                    "isp": s.isp, "protocol": s.protocol,
                    "features": s.features, "description": s.description,
                    "category": s.category, "disabled": s.disabled,
                    "isp_compatible": s.is_isp_compatible(app_state.local_isp),
                }
                for s in app_state.online_sources if not s.disabled
            ],
            "local_isp": app_state.local_isp,
        }

    @app.post("/api/check/start")
    async def start_check(req: CheckRequest):
        if app_state.is_checking:
            raise HTTPException(400, "检测正在进行中")

        app_state.is_checking = True
        app_state.check_results = []
        app_state._check_total = 0
        app_state._check_has_started = False
        app_state._download_active = False
        app_state._check_result_queue = asyncio.Queue()
        app_state.state_store.update(is_running=True, total_count=0)

        await app_state.broadcast("check_started", {"total": 0})

        asyncio.create_task(_run_streaming_check(req, app_state))

        return {"status": "started"}

    async def _run_streaming_check(req: CheckRequest, state: AppState):
        """流式检测：先解析本地文件立即开始检测，后台并行下载在线源并追加"""
        t0 = time.time()
        logger.info("[检测] 流式检测任务启动")

        config = CheckConfig(
            timeout_connect=req.timeout_connect,
            timeout_read=req.timeout_read,
            max_threads=req.max_threads,
            run_speed_test=req.run_speed_test,
            use_cache=req.use_cache,
        )
        state.http_client.update_timeout(config.timeout_connect, config.timeout_read)

        seen: set[str] = set()
        pending_channels: List[Channel] = []

        def on_result(result: CheckResult):
            state.check_results.append(result)
            state._check_result_queue.put_nowait(("result", result))

        def on_complete():
            state.is_checking = False
            state.state_store.update(is_running=False)
            state.cache.save()
            state._check_result_queue.put_nowait(("complete", None))

        def _start_engine():
            """启动检测引擎，处理所有已收集的频道"""
            if not pending_channels or state._check_has_started:
                return
            state.check_engine.start(pending_channels, config, on_result=on_result, on_complete=on_complete)
            state._check_total = len(pending_channels)
            state.state_store.update(total_count=state._check_total)
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(state.broadcast("channels_loaded", {"total": state._check_total}))
            )
            state._check_has_started = True
            logger.info("[检测] 检测引擎启动, 频道数=%d", state._check_total)

        def _add_channels(channels: List[Channel]):
            """追加频道到检测引擎"""
            if not channels:
                return
            if not state._check_has_started:
                pending_channels.extend(channels)
                _start_engine()
            else:
                state.check_engine.add_channels(channels, config, on_result)
                state._check_total += len(channels)
                state.state_store.update(total_count=state._check_total)
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(state.broadcast("channels_loaded", {"total": state._check_total}))
                )

        # 1. 本地文件立即开始检测
        if req.file_paths:
            channels = await asyncio.to_thread(PlaylistParser.parse_files, req.file_paths)
            logger.info("[检测] 本地文件解析完成, 频道数=%d", len(channels))
            for ch in channels:
                if ch.url_key not in seen:
                    seen.add(ch.url_key)
                    pending_channels.append(ch)
            _start_engine()

        # 2. 后台并行下载在线源
        if req.online_source_ids:
            sources_to_download = [src for src in state.online_sources if src.id in req.online_source_ids]
            logger.info("[检测] 后台开始下载 %d 个在线源", len(sources_to_download))
            state._download_active = True

            async def download_and_feed(src: OnlineSource):
                try:
                    url = src.url
                    if src.mirror_url and state.local_isp not in src.isp:
                        url = src.mirror_url
                    resp = await asyncio.to_thread(state.http_client.get, url, timeout=(15, 15))
                    if resp.status_code == 200:
                        new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, resp.text, src.name)
                        fresh = []
                        for ch in new_channels:
                            if ch.url_key not in seen:
                                fresh.append(ch)
                                seen.add(ch.url_key)
                        if fresh:
                            logger.info("[检测] 在线源 %s 下载完成, 新增 %d 个频道", src.name, len(fresh))
                            _add_channels(fresh)
                        else:
                            logger.info("[检测] 在线源 %s 下载完成, 共 %d 个频道（全部已存在）", src.name, len(new_channels))
                    else:
                        logger.warning("[检测] 在线源 %s HTTP %d", src.name, resp.status_code)
                except Exception as e:
                    logger.warning("[检测] 在线源 %s 下载失败: %s", src.name, e)

            await asyncio.gather(*[download_and_feed(src) for src in sources_to_download])
            state._download_active = False
            logger.info("[检测] 所有在线源下载完毕, 总频道数=%d", state._check_total)

        # 3. 如果没有启动任何检测
        if not state._check_has_started:
            state.is_checking = False
            state.state_store.update(is_running=False)
            await state.broadcast("check_completed", {"total": 0, "valid": 0, "invalid": 0})
            logger.warning("[检测] 未解析到任何频道")
            return

        # 4. 等待检测完成
        await _wait_check_queue(state)
        logger.info("[检测] 全部完成, 耗时=%.1fs", time.time() - t0)

    async def _wait_check_queue(state: AppState):
        """等待检测引擎完成，通过 Queue 桥接同步回调"""
        while True:
            msg_type, data = await state._check_result_queue.get()
            if msg_type == "result":
                result: CheckResult = data
                await state.broadcast("channel_checked", {
                    "index": result.channel.index,
                    "name": result.channel.name,
                    "url": result.channel.url,
                    "is_valid": result.is_valid,
                    "latency": result.latency_display,
                    "speed": result.speed,
                    "details": result.details,
                    "status": result.status_text,
                    "sources": ", ".join(result.channel.sources),
                    "tag": result.tag,
                })
            elif msg_type == "complete":
                await state.broadcast("check_completed", {
                    "total": state.state_store.state.total_count,
                    "valid": state.state_store.state.valid_count,
                    "invalid": state.state_store.state.invalid_count,
                })
                logger.info("[检测] 检测完成, 有效=%d, 无效=%d",
                           state.state_store.state.valid_count,
                           state.state_store.state.invalid_count)
                break

    @app.post("/api/check/stop")
    async def stop_check():
        if not app_state.is_checking:
            raise HTTPException(400, "没有正在进行的检测")
        if app_state._async_check_engine:
            await app_state._async_check_engine.stop()
        app_state.is_checking = False
        app_state._check_state_machine.stop()
        await app_state.broadcast("check_stopped", {})
        return {"status": "stopped"}

    @app.get("/api/check/state")
    async def get_check_state():
        if app_state._check_state_machine:
            return app_state._check_state_machine.to_dict()
        return {"phase": "idle", "metrics": {}}

    @app.post("/api/settings/media-probe")
    async def set_media_probe(enabled: bool):
        app_state._use_media_probe = enabled
        if app_state._async_check_engine:
            app_state._async_check_engine._use_media_probe = enabled and MediaProbe.is_ffmpeg_available()
        return {"enabled": app_state._async_check_engine._use_media_probe if app_state._async_check_engine else False}

    @app.get("/api/settings/media-probe")
    async def get_media_probe_status():
        return {
            "enabled": app_state._use_media_probe,
            "ffmpeg_available": MediaProbe.is_ffmpeg_available(),
        }

    @app.get("/api/results")
    async def get_results(tab: str = "all", page: int = 1, per_page: int = 50, search: str = ""):
        results = app_state.check_results
        if tab == "valid":
            results = [r for r in results if r.is_valid]
        elif tab == "invalid":
            results = [r for r in results if not r.is_valid]
        if search:
            search_lower = search.lower()
            results = [r for r in results if search_lower in r.channel.name.lower() or search_lower in r.channel.url.lower()]

        total = len(results)
        start = (page - 1) * per_page
        end = start + per_page
        page_results = results[start:end]

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "items": [
                {
                    "index": r.channel.index,
                    "name": r.channel.name,
                    "url": r.channel.url,
                    "group": r.channel.group,
                    "sources": ", ".join(r.channel.sources),
                    "is_valid": r.is_valid,
                    "status": r.status_text,
                    "latency": r.latency_display,
                    "speed": r.speed,
                    "details": r.details,
                }
                for r in page_results
            ],
        }

    @app.get("/api/results/stats")
    async def get_results_stats():
        state = app_state.state_store.state
        db_stats = app_state.database.get_stats()
        return {
            "total": state.total_count,
            "checked": state.checked_count,
            "valid": state.valid_count,
            "invalid": state.invalid_count,
            "is_running": app_state.is_checking,
            "db_stats": db_stats,
        }

    @app.get("/api/results/history")
    async def get_check_history(limit: int = 20):
        return {"history": app_state.database.get_check_history(limit)}

    @app.post("/api/results/save")
    async def save_results_to_db():
        if not app_state.check_results:
            raise HTTPException(400, "没有检测结果可保存")
        results_data = [
            {
                "channel": {
                    "name": r.channel.name,
                    "url": r.channel.url,
                    "group": r.channel.group,
                    "sources": r.channel.sources,
                    "url_key": r.channel.url_key,
                },
                "is_valid": r.is_valid,
                "latency": r.latency,
                "speed": r.speed,
                "details": r.details,
                "tag": r.tag,
            }
            for r in app_state.check_results
        ]
        history_id = app_state.database.save_check_result(results_data)
        return {"history_id": history_id, "saved": len(results_data)}

    @app.get("/api/favorites")
    async def get_favorites():
        from iptv_check.infra.database import FavoriteModel
        with app_state.database.get_session() as session:
            items = session.exec(
                select(FavoriteModel).order_by(FavoriteModel.created_at.desc())
            ).all()
            return {
                "favorites": [
                    {"id": f.id, "channel_id": f.channel_id, "name": f.name, "url": f.url, "created_at": f.created_at.isoformat()}
                    for f in items
                ]
            }

    @app.post("/api/favorites")
    async def add_favorite(req: dict):
        from iptv_check.infra.database import FavoriteModel, ChannelModel
        with app_state.database.get_session() as session:
            channel = session.exec(
                select(ChannelModel).where(ChannelModel.url == req.get("url", ""))
            ).first()
            if not channel:
                raise HTTPException(404, "频道不存在")
            existing = session.exec(
                select(FavoriteModel).where(FavoriteModel.channel_id == channel.id)
            ).first()
            if existing:
                return {"message": "已在收藏夹中"}
            fav = FavoriteModel(channel_id=channel.id, name=channel.name, url=channel.url)
            session.add(fav)
            session.commit()
            return {"id": fav.id}

    @app.delete("/api/favorites/{fav_id}")
    async def remove_favorite(fav_id: int):
        from iptv_check.infra.database import FavoriteModel
        with app_state.database.get_session() as session:
            fav = session.get(FavoriteModel, fav_id)
            if fav:
                session.delete(fav)
                session.commit()
                return {"deleted": True}
            raise HTTPException(404, "收藏不存在")

    @app.get("/api/report")
    async def get_quality_report():
        results = app_state.check_results
        if not results:
            return {"error": "没有检测结果"}

        valid = [r for r in results if r.is_valid]
        invalid = [r for r in results if not r.is_valid]
        latencies = [r.latency for r in valid if r.latency > 0]

        latency_ranges = {"<50ms": 0, "50-100ms": 0, "100-200ms": 0, "200-500ms": 0, "500ms+": 0}
        for l in latencies:
            if l < 50: latency_ranges["<50ms"] += 1
            elif l < 100: latency_ranges["50-100ms"] += 1
            elif l < 200: latency_ranges["100-200ms"] += 1
            elif l < 500: latency_ranges["200-500ms"] += 1
            else: latency_ranges["500ms+"] += 1

        source_stats = {}
        for r in results:
            for src in r.channel.sources:
                if src not in source_stats:
                    source_stats[src] = {"total": 0, "valid": 0, "latencies": []}
                source_stats[src]["total"] += 1
                if r.is_valid:
                    source_stats[src]["valid"] += 1
                    if r.latency > 0:
                        source_stats[src]["latencies"].append(r.latency)

        source_ranking = []
        for name, stats in source_stats.items():
            avg_lat = sum(stats["latencies"]) / len(stats["latencies"]) if stats["latencies"] else 0
            source_ranking.append({
                "name": name,
                "total": stats["total"],
                "valid": stats["valid"],
                "invalid": stats["total"] - stats["valid"],
                "rate": round(stats["valid"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0,
                "avg_latency": round(avg_lat, 0),
            })
        source_ranking.sort(key=lambda x: x["rate"], reverse=True)

        return {
            "total": len(results),
            "valid": len(valid),
            "invalid": len(invalid),
            "valid_rate": round(len(valid) / len(results) * 100, 1) if results else 0,
            "avg_latency": round(sum(latencies) / len(latencies), 0) if latencies else 0,
            "min_latency": min(latencies) if latencies else 0,
            "max_latency": max(latencies) if latencies else 0,
            "latency_distribution": latency_ranges,
            "source_ranking": source_ranking,
            "group_stats": _compute_group_stats(results),
        }

    @app.post("/api/export")
    async def export_results(req: ExportRequest):
        if not app_state.check_results:
            raise HTTPException(400, "没有检测结果可导出")
        export_dir = req.export_dir or os.path.join(BASE_DIR, "exports")
        os.makedirs(export_dir, exist_ok=True)
        try:
            exported = app_state.export_engine.export_batch(
                [req.format], app_state.check_results, export_dir, req.base_name, local_isp=app_state.local_isp
            )
            return {"exported": exported, "dir": export_dir}
        except Exception as e:
            raise HTTPException(500, f"导出失败: {e}")

    @app.post("/api/convert")
    async def convert_format(req: ConvertRequest):
        try:
            output = FormatConverter.convert_file(req.input_path, req.output_format)
            return {"output": output}
        except Exception as e:
            raise HTTPException(500, f"转换失败: {e}")

    @app.post("/api/convert-text")
    async def convert_text(req: ConvertTextRequest):
        """纯文本格式转换，不需要文件"""
        try:
            if req.from_format == "m3u" and req.to_format == "txt":
                result = FormatConverter.m3u_to_txt(req.content)
            elif req.from_format == "txt" and req.to_format == "m3u":
                result = FormatConverter.txt_to_m3u(req.content)
            else:
                raise HTTPException(400, f"不支持的转换: {req.from_format} -> {req.to_format}")
            return {"content": result}
        except Exception as e:
            raise HTTPException(500, f"转换失败: {e}")

    @app.post("/api/optimize")
    async def smart_optimize():
        if not app_state.check_results:
            raise HTTPException(400, "没有检测结果可优选")
        original_count = len([r for r in app_state.check_results if r.is_valid])
        app_state.check_results = SmartOptimizer.optimize(app_state.check_results)
        optimized_count = len([r for r in app_state.check_results if r.is_valid])
        return {
            "original_valid": original_count,
            "optimized_valid": optimized_count,
            "removed": original_count - optimized_count,
        }

    @app.post("/api/m3u/start")
    async def start_m3u_server():
        try:
            if not app_state.check_results:
                raise HTTPException(400, "没有检测结果可服务")
            valid_results = [r for r in app_state.check_results if r.is_valid]
            m3u_content = app_state.export_engine.export_m3u(valid_results, local_isp=app_state.local_isp)
            m3u_path = os.path.join(BASE_DIR, "exports", "iptv_live.m3u")
            os.makedirs(os.path.dirname(m3u_path), exist_ok=True)
            with open(m3u_path, "w", encoding="utf-8") as f:
                f.write(m3u_content)
            app_state._m3u_service_running = True
            app_state._m3u_service_file = m3u_path
            app_state._m3u_service_started_at = datetime.datetime.utcnow()
            return {"status": "started", "url": "http://127.0.0.1:8080/iptv_live.m3u"}
        except Exception as e:
            raise HTTPException(500, f"M3U 服务启动失败: {e}")

    @app.post("/api/m3u/stop")
    async def stop_m3u_server():
        m3u_path = os.path.join(BASE_DIR, "exports", "iptv_live.m3u")
        if os.path.isfile(m3u_path):
            try:
                os.remove(m3u_path)
                logger.info("M3U 文件已删除")
            except OSError as e:
                logger.warning("删除 M3U 文件失败: %s", e)
        app_state._m3u_service_running = False
        app_state._m3u_service_file = ""
        app_state._m3u_service_started_at = None
        return {"status": "stopped"}

    @app.get("/api/m3u/state")
    async def m3u_server_state():
        m3u_path = os.path.join(BASE_DIR, "exports", "iptv_live.m3u")
        file_exists = os.path.isfile(m3u_path)
        if file_exists and not app_state._m3u_service_running:
            app_state._m3u_service_running = True
            app_state._m3u_service_file = m3u_path
        elif not file_exists and app_state._m3u_service_running:
            app_state._m3u_service_running = False
            app_state._m3u_service_file = ""
        return {
            "running": app_state._m3u_service_running and file_exists,
            "url": "http://127.0.0.1:8080/iptv_live.m3u" if file_exists else "",
            "file_exists": file_exists,
            "valid_channels": len([r for r in app_state.check_results if r.is_valid]) if app_state.check_results else 0,
        }

    @app.get("/api/available-ports")
    async def get_available_ports():
        import socket
        ports = []
        for port in [8080, 8081, 8082, 9528, 9529, 9530]:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    ports.append({"port": port, "available": True})
            except OSError:
                ports.append({"port": port, "available": False})
        return {"ports": ports}

    # 频道趋势分析 API
    @app.get("/api/trends/channel/{channel_id}")
    async def get_channel_trend(channel_id: int, days: int = 7):
        trend = app_state.database.get_channel_trend(channel_id, days)
        stability = app_state.database.get_channel_stability_stats(channel_id, days)
        return {
            "trend": trend,
            "stability": stability,
            "days": days,
        }

    @app.get("/api/trends/stable-channels")
    async def get_top_stable_channels(days: int = 7, limit: int = 50):
        return {"channels": app_state.database.get_top_stable_channels(days, limit)}

    @app.get("/api/trends/history-compare")
    async def compare_history(h1: int, h2: int):
        return app_state.database.get_history_comparison(h1, h2)

    @app.get("/api/settings/media-probe/status")
    async def get_media_probe_full_status():
        return {
            "enabled": app_state._use_media_probe,
            "ffmpeg_available": app_state._ffmpeg_available,
            "usable": app_state._use_media_probe and app_state._ffmpeg_available,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        app_state.register_ws(ws)
        try:
            await ws.send_json({"event": "connected", "local_isp": app_state.local_isp, "is_checking": app_state.is_checking})
            while True:
                data = await ws.receive_json()
                event = data.get("event")
                if event == "ping":
                    await ws.send_json({"event": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            app_state.unregister_ws(ws)

    class UploadRequest(BaseModel):
        filename: str = "upload.m3u"
        content_base64: str = ""

    @app.post("/api/upload")
    async def upload_file(req: UploadRequest):
        upload_dir = os.path.join(BASE_DIR, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, req.filename)
        content = base64.b64decode(req.content_base64)
        with open(file_path, "wb") as f:
            f.write(content)
        channels = PlaylistParser.parse_file(file_path)
        return {"filename": req.filename, "path": file_path, "channel_count": len(channels)}

    return app


app = create_app()
