import sys
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="IPTV-Check Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9528, help="监听端口 (default: 9528)")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    from iptv_check.server.main import run_server
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)

if __name__ == "__main__":
    main()
