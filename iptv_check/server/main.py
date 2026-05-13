import os
import sys
import webbrowser
import threading
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_server(host: str = "127.0.0.1", port: int = 9528, open_browser: bool = True):
    import uvicorn
    from iptv_check.server.app import create_app

    app = create_app()

    if open_browser:
        def open_after_startup():
            import time
            time.sleep(1.5)
            url = f"http://{host}:{port}"
            logger.info("正在打开浏览器: %s", url)
            webbrowser.open(url)

        threading.Thread(target=open_after_startup, daemon=True).start()

    logger.info("启动 IPTV-Check Web 服务器: http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    parser = argparse.ArgumentParser(description="IPTV-Check Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9528, help="监听端口 (default: 9528)")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
