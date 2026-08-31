import socket
import threading
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import List, Optional

from iptv_check.models.check_result import CheckResult

logger = logging.getLogger(__name__)


class M3UServer:
    def __init__(self, port: int = 9527):
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._valid_items: List[tuple] = []

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
        return f"http://{ip}:{self._port}/playlist.m3u"

    def start(self, valid_results: List[CheckResult]):
        self._valid_items = [(r.channel.name, r.channel.url) for r in valid_results if r.is_valid]
        if not self._valid_items:
            return False

        items = self._valid_items

        class M3UHandler(SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/playlist.m3u":
                    self.send_response(200)
                    self.send_header("Content-type", "audio/x-mpegurl")
                    self.send_header("Content-Disposition", "attachment; filename=playlist.m3u")
                    self.end_headers()
                    content = "#EXTM3U\n"
                    for name, url in items:
                        content += f"#EXTINF:-1,{name}\n{url}\n"
                    self.wfile.write(content.encode("utf-8"))
                elif self.path == "/playlist.txt":
                    self.send_response(200)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    content = ""
                    for name, url in items:
                        content += f"{name},{url}\n"
                    self.wfile.write(content.encode("utf-8"))
                else:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    html = f"""<html><head><title>IPTV-Check 在线服务</title></head>
                    <body><h2>IPTV-Check 在线M3U服务</h2>
                    <p>有效频道: {len(items)} 个</p>
                    <ul><li><a href="/playlist.m3u">下载 M3U 播放列表</a></li>
                    <li><a href="/playlist.txt">下载 TXT 列表</a></li></ul>
                    <p>在手机/电视播放器中输入URL即可使用</p></body></html>"""
                    self.wfile.write(html.encode("utf-8"))

            def log_message(self, format, *args):
                pass

        try:
            self._server = HTTPServer(("0.0.0.0", self._port), M3UHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info("M3U服务已启动: %s", self.url)
            return True
        except Exception as e:
            logger.error("启动M3U服务失败: %s", e)
            self._server = None
            return False

    def stop(self):
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
            self._thread = None
            logger.info("M3U服务已停止")
