import asyncio
import os
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from iptv_check.infra.cn_time import cn_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["export"])


class ExportRequest(BaseModel):
    format: str = "m3u"
    export_dir: str = ""
    base_name: str = "检测结果"
    export_mode: str = "merged"
    only_valid: bool = True
    channel_urls: List[str] = []
    groups: List[str] = []
    folder_id: Optional[int] = None


class ConvertRequest(BaseModel):
    input_path: str = ""
    output_format: str = "m3u"


class ConvertTextRequest(BaseModel):
    content: str
    from_format: str
    to_format: str


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


def _get_check_service():
    state = _get_state()
    if state is None:
        return None
    return getattr(state, "_check_service", None)


def _get_session_id() -> str:
    state = _get_state()
    service = _get_check_service()
    if service and service.session_id:
        return service.session_id
    if state and state.event_store:
        return state.event_store.current_session_id
    return ""


def _load_check_results(session_id: str) -> list:
    from iptv_check.models.check_result import CheckResult
    from iptv_check.models.channel import Channel
    state = _get_state()
    results_data = state.read_model.get_checked_results_raw(session_id)
    check_results = []
    for rd in results_data:
        ch = Channel(
            name=rd["channel"]["name"], url=rd["channel"]["url"],
            group=rd["channel"].get("group", ""), sources=rd["channel"].get("sources", [])
        )
        r = CheckResult(
            channel=ch, is_valid=rd["is_valid"], quality_tier=rd.get("quality_tier", ""),
            latency=rd["latency"], speed=rd["speed"], details=rd["details"]
        )
        check_results.append(r)
    return check_results


def _filter_results(results, only_valid=True, channel_urls=None, groups=None, folder_id=None):
    from sqlmodel import select
    filtered = results
    if only_valid:
        filtered = [r for r in filtered if r.is_valid]
    if channel_urls:
        url_set = set(channel_urls)
        filtered = [r for r in filtered if r.channel.url in url_set]
    if groups:
        group_set = set(groups)
        filtered = [r for r in filtered if r.channel.group in group_set]
    if folder_id is not None:
        state = _get_state()
        from iptv_check.infra.database import FavoriteModel
        with state.database.get_session() as session:
            fav_urls = set(
                f.url for f in session.exec(
                    select(FavoriteModel).where(FavoriteModel.folder_id == folder_id)
                ).all()
            )
        filtered = [r for r in filtered if r.channel.url in fav_urls]
    return filtered


@router.post("/export")
async def export_results(req: ExportRequest):
    import traceback
    session_id = _get_session_id()
    if not session_id:
        raise HTTPException(400, "没有检测结果可导出")

    try:
        check_results = await asyncio.to_thread(_load_check_results, session_id)
    except Exception as e:
        logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"读取检测结果失败: {e}")

    if not check_results:
        raise HTTPException(400, "没有检测结果可导出")

    check_results = await asyncio.to_thread(
        _filter_results,
        check_results,
        only_valid=req.only_valid,
        channel_urls=req.channel_urls or None,
        groups=req.groups or None,
        folder_id=req.folder_id,
    )

    if not check_results:
        raise HTTPException(400, "过滤后无可导出的频道")

    state = _get_state()
    from iptv_check.server.app import DATA_DIR
    export_dir = req.export_dir or os.path.join(DATA_DIR, "exports")
    os.makedirs(export_dir, exist_ok=True)
    try:
        exported = state.export_engine.export_batch(
            [req.format], check_results, export_dir, req.base_name, local_isp=state.local_isp
        )
        return {"exported": exported, "dir": export_dir, "count": len(check_results)}
    except Exception as e:
        logger.error("导出失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"导出失败: {e}")


@router.post("/convert")
async def convert_format(req: ConvertRequest):
    from iptv_check.core.converter import FormatConverter
    try:
        output = FormatConverter.convert_file(req.input_path, req.output_format)
        return {"output": output}
    except Exception as e:
        raise HTTPException(500, f"转换失败: {e}")


@router.post("/convert-text")
async def convert_text(req: ConvertTextRequest):
    from iptv_check.core.converter import FormatConverter
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


@router.post("/optimize")
async def smart_optimize():
    import traceback
    session_id = _get_session_id()
    if not session_id:
        raise HTTPException(400, "没有检测结果可优选")

    try:
        check_results = await asyncio.to_thread(_load_check_results, session_id)
    except Exception as e:
        logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"读取检测结果失败: {e}")

    if not check_results:
        raise HTTPException(400, "没有检测结果可优选")

    from iptv_check.core.optimizer import SmartOptimizer
    state = _get_state()
    original_count = len([r for r in check_results if r.is_valid])
    optimized = SmartOptimizer.optimize(check_results, local_isp=getattr(state, 'local_isp', "未知"))
    optimized_count = len([r for r in optimized if r.is_valid])
    return {"original_valid": original_count, "optimized_valid": optimized_count, "removed": original_count - optimized_count}


@router.post("/export/aggregated")
async def export_aggregated_m3u(
    max_alternatives: int = 3,
    only_valid: bool = True,
    channel_urls: List[str] = [],
    groups: List[str] = [],
):
    import traceback
    from datetime import datetime
    from fastapi.responses import Response

    session_id = _get_session_id()
    if not session_id:
        raise HTTPException(400, "没有检测结果可导出")

    try:
        check_results = await asyncio.to_thread(_load_check_results, session_id)
    except Exception as e:
        logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"读取检测结果失败: {e}")

    if not check_results:
        raise HTTPException(400, "没有检测结果可导出")

    check_results = await asyncio.to_thread(
        _filter_results,
        check_results,
        only_valid=only_valid,
        channel_urls=channel_urls or None,
        groups=groups or None,
    )
    channel_groups: dict = {}
    for r in check_results:
        name = r.channel.name
        resolution = getattr(r.channel, "resolution", "") or ""
        group_key = f"{name}@{resolution}" if resolution else name
        if group_key not in channel_groups:
            channel_groups[group_key] = []
        channel_groups[group_key].append(r)
    lines = ["#EXTM3U\n", f"# 聚合导出: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
    lines.append(f"# 每频道最多 {max_alternatives} 个备选源\n\n")
    for group_key, group_results in channel_groups.items():
        name = group_key.split("@")[0] if "@" in group_key else group_key
        resolution = group_key.split("@")[1] if "@" in group_key else ""
        sorted_results = sorted(group_results, key=lambda r: r.latency if r.latency >= 0 else float('inf'))
        primary = sorted_results[0]
        alternatives = sorted_results[1:max_alternatives]
        group_info = f" group-title=\"{primary.channel.group}\"" if primary.channel.group else ""
        display_name = f"{name} [{resolution}]" if resolution else name
        lines.append(f"#EXTINF:-1{group_info},{display_name}\n{primary.channel.url}\n")
        for alt in alternatives:
            alt_display = f"{name} [{resolution}] (备选 延迟{int(alt.latency)}ms)" if resolution else f"{name} (备选 延迟{int(alt.latency)}ms)"
            lines.append(f"#EXTINF:-1{group_info},{alt_display}\n{alt.channel.url}\n")
    content = "".join(lines)
    return Response(
        content=content, media_type="audio/x-mpegurl",
        headers={"Content-Disposition": "attachment; filename=aggregated.m3u"},
    )


@router.post("/m3u/start")
async def start_m3u_server():
    import datetime
    import traceback
    from iptv_check.models.check_result import CheckResult
    from iptv_check.models.channel import Channel
    state = _get_state()
    service = _get_check_service()
    from iptv_check.server.app import DATA_DIR

    session_id = ""
    if service and service.session_id:
        session_id = service.session_id
    elif state and state.event_store:
        session_id = state.event_store.current_session_id

    if not session_id:
        raise HTTPException(400, "没有检测结果可服务")

    try:
        check_results = await asyncio.to_thread(_load_check_results, session_id)
    except Exception as e:
        logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"读取检测结果失败: {e}")

    if not check_results:
        raise HTTPException(400, "没有检测结果可服务")

    try:
        valid_results = [r for r in check_results if r.is_valid]
        m3u_content = state.export_engine.export_m3u(valid_results, local_isp=state.local_isp)
        m3u_path = os.path.join(DATA_DIR, "exports", "iptv_live.m3u")
        os.makedirs(os.path.dirname(m3u_path), exist_ok=True)
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write(m3u_content)

        state._m3u_service_running = True
        state._m3u_service_file = m3u_path
        state._m3u_service_started_at = cn_now()

        if not getattr(state, '_m3u_http_server', None):
            import threading
            from http.server import HTTPServer, SimpleHTTPRequestHandler

            export_dir = os.path.join(DATA_DIR, "exports")

            class M3UHandler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=export_dir, **kwargs)
                def log_message(self, format, *args):
                    pass

            for port in [8080, 8081, 8082]:
                try:
                    server = HTTPServer(("0.0.0.0", port), M3UHandler)
                    state._m3u_http_port = port
                    break
                except OSError:
                    continue
            else:
                raise RuntimeError("无可用端口启动 M3U 服务")

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            state._m3u_http_server = server

        port = getattr(state, '_m3u_http_port', 8080)
        return {"status": "started", "url": f"http://127.0.0.1:{port}/iptv_live.m3u", "port": port}
    except Exception as e:
        logger.error("M3U 服务启动失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"M3U 服务启动失败: {e}")


@router.post("/m3u/stop")
async def stop_m3u_server():
    state = _get_state()
    from iptv_check.server.app import DATA_DIR
    m3u_path = os.path.join(DATA_DIR, "exports", "iptv_live.m3u")
    if os.path.isfile(m3u_path):
        try:
            os.remove(m3u_path)
        except OSError:
            pass
    server = getattr(state, '_m3u_http_server', None)
    if server:
        try:
            server.shutdown()
        except Exception:
            pass
        state._m3u_http_server = None
    state._m3u_service_running = False
    state._m3u_service_file = ""
    state._m3u_service_started_at = None
    return {"status": "stopped"}


@router.get("/m3u/state")
async def m3u_server_state():
    state = _get_state()
    from iptv_check.server.app import DATA_DIR
    m3u_path = os.path.join(DATA_DIR, "exports", "iptv_live.m3u")
    file_exists = os.path.isfile(m3u_path)
    if file_exists and not state._m3u_service_running:
        state._m3u_service_running = True
        state._m3u_service_file = m3u_path
    elif not file_exists and state._m3u_service_running:
        state._m3u_service_running = False
        state._m3u_service_file = ""
    port = getattr(state, '_m3u_http_port', 8080)
    valid_count = 0
    if state._m3u_service_running and m3u_path:
        try:
            with open(m3u_path, "r", encoding="utf-8") as f:
                content = f.read()
            valid_count = content.count("#EXTINF")
        except Exception:
            pass

    return {
        "running": state._m3u_service_running and file_exists,
        "url": f"http://127.0.0.1:{port}/iptv_live.m3u" if file_exists else "",
        "port": port,
        "file_exists": file_exists,
        "valid_channels": valid_count,
    }


@router.get("/available-ports")
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
