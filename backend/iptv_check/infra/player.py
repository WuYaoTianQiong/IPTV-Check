import os
import base64
import webbrowser
import threading
import logging
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional
from io import BytesIO

from iptv_check.infra.config.settings import PLAYER_HTML_TEMPLATE

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "static")


class PlayerService:
    def __init__(self):
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port: Optional[int] = None
        self._player_html: str = ""
        self._http_client = None

    def set_http_client(self, http_client):
        self._http_client = http_client

    def play(self, url: str, name: str):
        self._player_html = PLAYER_HTML_TEMPLATE.format(url=url, name=name)
        port = self._ensure_server()
        if port is not None:
            webbrowser.open(f"http://127.0.0.1:{port}/player.html")
        else:
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp_player")
            os.makedirs(temp_dir, exist_ok=True)
            player_file = os.path.join(temp_dir, "player.html")
            with open(player_file, "w", encoding="utf-8") as f:
                f.write(self._player_html)
            webbrowser.open(f"file:///{player_file.replace(os.sep, '/')}")

        logger.info("正在播放: %s", name)

    def _ensure_server(self) -> Optional[int]:
        if self._server is not None:
            return self._port

        player_service = self

        class PlayerHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/" or self.path == "/player.html":
                    self._serve_html(player_service._player_html)
                elif self.path.startswith("/static/"):
                    self._serve_static()
                elif self.path.startswith("/proxy"):
                    self._serve_proxy(player_service._http_client)
                else:
                    self._serve_favicon()

            def _serve_html(self, content: str):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))

            def _serve_static(self):
                rel_path = self.path[len("/static/"):]
                file_path = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
                if not file_path.startswith(os.path.normpath(STATIC_DIR)):
                    self.send_error(403)
                    return
                if not os.path.isfile(file_path):
                    self.send_error(404)
                    return
                mime_type, _ = mimetypes.guess_type(file_path)
                mime_type = mime_type or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())

            def _serve_proxy(self, http_client):
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                encoded = qs.get("url", [None])[0]

                if not encoded:
                    encoded = parsed.path[len("/proxy/"):]

                if not encoded:
                    self.send_error(400, "Missing proxy URL parameter")
                    return

                try:
                    target_url = base64.b64decode(encoded).decode("utf-8")
                except Exception:
                    self.send_error(400, "Invalid proxy URL encoding")
                    return

                logger.debug("Proxy request: %s", target_url)

                range_header = self.headers.get("Range")
                try:
                    if http_client is not None:
                        resp = http_client.get(target_url, timeout=(10, 30), stream=True)
                    else:
                        import requests
                        resp = requests.get(target_url, timeout=(10, 30), stream=True, headers={"User-Agent": "Mozilla/5.0"})

                    content_type = resp.headers.get("Content-Type", "application/octet-stream")
                    content_length = resp.headers.get("Content-Length")

                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    if content_length:
                        self.send_header("Content-Length", content_length)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()

                    chunk_size = 65536
                    try:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if chunk:
                                self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        resp.close()

                except Exception as e:
                    logger.warning("Proxy error for %s: %s", target_url, e)
                    self.send_error(502, f"Proxy error: {str(e)[:50]}")

            def _serve_favicon(self):
                self.send_response(204)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        for port in range(19527, 19537):
            try:
                server = HTTPServer(("127.0.0.1", port), PlayerHandler)
                self._server = server
                self._port = port
                self._thread = threading.Thread(target=server.serve_forever, daemon=True)
                self._thread.start()
                logger.info("Player server started on port %d", port)
                return port
            except OSError:
                continue
        return None

    def stop(self):
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
            self._thread = None
            self._port = None
