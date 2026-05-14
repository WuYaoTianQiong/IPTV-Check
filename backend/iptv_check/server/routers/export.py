import os
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["export"])


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


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


@router.post("/export")
async def export_results(req: ExportRequest):
    state = _get_state()
    if not state.check_results:
        raise HTTPException(400, "没有检测结果可导出")
    from iptv_check.server.app import DATA_DIR
    export_dir = req.export_dir or os.path.join(DATA_DIR, "exports")
    os.makedirs(export_dir, exist_ok=True)
    try:
        exported = state.export_engine.export_batch(
            [req.format], state.check_results, export_dir, req.base_name, local_isp=state.local_isp
        )
        return {"exported": exported, "dir": export_dir}
    except Exception as e:
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
    state = _get_state()
    if not state.check_results:
        raise HTTPException(400, "没有检测结果可优选")
    from iptv_check.core.optimizer import SmartOptimizer
    original_count = len([r for r in state.check_results if r.is_valid])
    state.check_results = SmartOptimizer.optimize(state.check_results)
    optimized_count = len([r for r in state.check_results if r.is_valid])
    return {"original_valid": original_count, "optimized_valid": optimized_count, "removed": original_count - optimized_count}


@router.post("/export/aggregated")
async def export_aggregated_m3u(max_alternatives: int = 3):
    import re
    from datetime import datetime
    from fastapi.responses import Response
    state = _get_state()
    if not state.check_results:
        raise HTTPException(400, "没有检测结果可导出")
    valid_results = [r for r in state.check_results if r.is_valid]
    channel_groups: dict = {}
    for r in valid_results:
        name_key = re.sub(r'[\s\-_|]', '', r.channel.name).lower()
        if name_key not in channel_groups:
            channel_groups[name_key] = []
        channel_groups[name_key].append(r)
    lines = ["#EXTM3U\n", f"# 聚合导出: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
    lines.append(f"# 每频道最多 {max_alternatives} 个备选源\n\n")
    for name_key, group_results in channel_groups.items():
        sorted_results = sorted(group_results, key=lambda r: r.latency if r.latency >= 0 else float('inf'))
        primary = sorted_results[0]
        alternatives = sorted_results[1:max_alternatives]
        group_info = f" group-title=\"{primary.channel.group}\"" if primary.channel.group else ""
        lines.append(f"#EXTINF:-1{group_info},{primary.channel.name}\n{primary.channel.url}\n")
        for alt in alternatives:
            lines.append(f"#EXTINF:-1{group_info},{primary.channel.name} (备选 延迟{int(alt.latency)}ms)\n{alt.channel.url}\n")
    content = "".join(lines)
    return Response(
        content=content, media_type="audio/x-mpegurl",
        headers={"Content-Disposition": "attachment; filename=aggregated.m3u"},
    )


@router.post("/m3u/start")
async def start_m3u_server():
    import datetime
    state = _get_state()
    from iptv_check.server.app import DATA_DIR
    try:
        if not state.check_results:
            raise HTTPException(400, "没有检测结果可服务")
        valid_results = [r for r in state.check_results if r.is_valid]
        m3u_content = state.export_engine.export_m3u(valid_results, local_isp=state.local_isp)
        m3u_path = os.path.join(DATA_DIR, "exports", "iptv_live.m3u")
        os.makedirs(os.path.dirname(m3u_path), exist_ok=True)
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write(m3u_content)
        state._m3u_service_running = True
        state._m3u_service_file = m3u_path
        state._m3u_service_started_at = datetime.datetime.utcnow()
        return {"status": "started", "url": "http://127.0.0.1:8080/iptv_live.m3u"}
    except Exception as e:
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
    return {
        "running": state._m3u_service_running and file_exists,
        "url": "http://127.0.0.1:8080/iptv_live.m3u" if file_exists else "",
        "file_exists": file_exists,
        "valid_channels": len([r for r in state.check_results if r.is_valid]) if state.check_results else 0,
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
