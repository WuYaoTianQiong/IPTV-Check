#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速探活 m3u 里每个播放地址的连通性（烟雾测试，不做完整播放验证）。

用法:
    python app/tools/probe_playlist.py 电视-国内-江苏移动.m3u
    python app/tools/probe_playlist.py 电视-国内-江苏移动.m3u --timeout 6 --out alive.m3u

说明:
  * 对每条 URL 发一次短超时 GET（带浏览器 UA），仅判定“能否连通”，不测播放质量/清晰度。
  * 运营商内网源（223.110.x.x 等）只在对应运营商网络内可达；从其他网络探测会报“不可达”，
    属正常现象，不代表源本身坏了——请在江苏移动网络下的设备（电视/盒子）上实测。
  * 免费公网源可能因限流或防盗链（缺 Referer/UA）返回非 200，结果仅供参考。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import os
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

# 运营商内网主机（仅对应运营商网络内可达，本机探测会误报，跳过）
INTERNAL_PREFIXES = ("223.110.241.204", "223.110.242.217")


def parse_m3u(path):
    """返回 [(extinf_line, url), ...]"""
    items = []
    extinf = None
    with io.open(path, encoding="utf-8", errors="replace") as fp:
        for raw in fp:
            line = raw.rstrip("\n")
            if line.startswith("#EXTINF"):
                extinf = line
            elif line and not line.startswith("#"):
                if extinf is not None:
                    items.append((extinf, line.strip()))
                extinf = None
    return items


def is_internal(url):
    host = urlparse(url).hostname or ""
    if host.startswith("["):  # IPv6
        return True
    return any(host == p or host.startswith(p) for p in INTERNAL_PREFIXES)


def probe(item, timeout, include_internal=False):
    extinf, url = item
    if is_internal(url) and not include_internal:
        return (url, "internal", "需对应运营商网络才能探测")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(1024)
            return (url, "ok", "HTTP %s" % r.status)
    except urllib.error.HTTPError as e:
        return (url, "http%d" % e.code, "HTTP %s" % e.code)
    except (socket.timeout, urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        return (url, "fail", str(reason)[:80])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("m3u", help="待探活的 m3u 文件")
    ap.add_argument("--timeout", type=float, default=6.0, help="单条超时（秒）")
    ap.add_argument("--out", help="写出“可达 + 内网”组成的精简 m3u")
    ap.add_argument("--include-internal", action="store_true",
                    help="同时探测运营商内网源（需在本机处于对应运营商网络下时才有意义）")
    args = ap.parse_args()

    items = parse_m3u(args.m3u)
    if not items:
        print("未解析到任何条目: %s" % args.m3u)
        return 1

    status = {}
    with cf.ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(probe, it, args.timeout, args.include_internal): it for it in items}
        for f in cf.as_completed(futs):
            url, st, msg = f.result()
            status[url] = (st, msg)

    ok, internal, dead = [], [], []
    for extinf, url in items:
        st, msg = status[url]
        if st == "ok":
            ok.append((extinf, url))
        elif st == "internal":
            internal.append((extinf, url))
        else:
            dead.append((extinf, url, st, msg))

    print("文件: %s" % args.m3u)
    print("总计 %d 条" % len(items))
    print("  可达(外部公网): %d" % len(ok))
    print("  内网(本环境跳过, 需在江苏移动网络实测): %d" % len(internal))
    print("  不可达(外部公网): %d" % len(dead))

    if dead:
        print("\n不可达的外部源列表:")
        for extinf, url, st, msg in dead:
            name = extinf.split(",", 1)[1].strip() if "," in extinf else url
            print("  [%-6s] %s  %s" % (st, name, url))
            print("           -> %s" % msg)

    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fp:
            fp.write("#EXTM3U\n")
            # 保留内网（无法在此验证，原样保留）+ 已探活可达的外部源
            for extinf, url in internal + ok:
                fp.write(extinf + "\n")
                fp.write(url + "\n")
        print("\n已写出精简列表: %s (%d 条)" % (args.out, len(internal) + len(ok)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
