import os
import sys
import webbrowser
import threading
import argparse
import logging

from iptv_check.infra.config.settings import path_settings

logger = logging.getLogger(__name__)


def validate_startup():
    """Validate required directories and files before starting server"""
    # Directories are automatically created by PathSettings model_validator
    
    static_dir = path_settings.static_dir
    index_html = static_dir / "index.html"
    
    if not index_html.is_file():
        logger.warning("Frontend not built: %s not found", index_html)
        logger.warning("Run 'cd frontend && npm run build' to build frontend")
        logger.warning("Server will start in API-only mode")
    else:
        logger.info("Static files found at: %s", static_dir)


def run_server(host: str = "127.0.0.1", port: int = 9528, open_browser: bool = False):
    import uvicorn
    from iptv_check.server.app import create_app

    validate_startup()

    app = create_app()

    if open_browser:
        def open_after_startup():
            import time
            import urllib.request
            url = f"http://{host}:{port}"
            for i in range(15):
                time.sleep(1)
                try:
                    urllib.request.urlopen(f"{url}/healthz", timeout=2)
                    logger.info("Opening browser: %s", url)
                    webbrowser.open(url)
                    return
                except Exception:
                    pass
            logger.warning("Could not verify server is ready, opening browser anyway")
            webbrowser.open(url)

        threading.Thread(target=open_after_startup, daemon=True).start()

    logger.info("Starting IPTV-Check Web Server: http://%s:%d", host, port)
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
