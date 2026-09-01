#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""播放级「精选」验证：复用项目自带的 MediaProbe（ffprobe 拉 5 秒码流判定可播性）。

与 build_playlist.py --prune-dead（粗筛：HTTP 200 连通性）互为补充：
  * 粗筛（coarse）—— app/tools/probe_playlist.py，构建时快速剔除连不上的死链；
  * 精选（fine） —— 本脚本，直接调用 backend 的 iptv_check.infra.media_probe.MediaProbe，
    用 ffmpeg/ffprobe 真实分析流媒体，给出 分辨率 / 编码 / 是否可播放。

不重复造轮子：MediaProbe 通过 importlib 直接加载项目源码，无需启动整套 Web 服务 / 数据库。
需本机已安装 ffmpeg 且 pip 装有 ffmpeg-python。

用法:
    python app/tools/verify_playlist.py 电视-国内-江苏移动.m3u
    python app/tools/verify_playlist.py 电视-国内-江苏移动.m3u --out 精选-江苏移动.m3u
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEDIA_PROBE_PATH = os.path.join(
    ROOT, "app", "backend", "iptv_check", "infra", "media_probe.py")


def load_media_probe():
    """直接加载项目自带的 MediaProbe，绕过整个包 __init__（避免触发 sqlmodel 等依赖）。"""
    spec = importlib.util.spec_from_file_location("media_probe_standalone", MEDIA_PROBE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MediaProbe


def parse_m3u(path):
    """返回 [(extinf_line, name, url), ...]"""
    items = []
    extinf = None
    name = ""
    with io.open(path, encoding="utf-8", errors="replace") as fp:
        for raw in fp:
            line = raw.rstrip("\n")
            if line.startswith("#EXTINF"):
                extinf = line
                name = line.split(",", 1)[1].strip() if "," in line else ""
            elif line and not line.startswith("#"):
                if extinf is not None:
                    items.append((extinf, name, line.strip()))
                extinf = None
    return items


async def verify(path, out, concurrency):
    MediaProbe = load_media_probe()
    mp = MediaProbe(timeout=10.0)
    if not mp.is_ffmpeg_available():
        print("错误：ffmpeg/ffprobe 不可用，无法做精选验证。请先安装 ffmpeg。")
        return 1

    items = parse_m3u(path)
    if not items:
        print("未解析到任何条目: %s" % path)
        return 1

    sem = asyncio.Semaphore(concurrency)

    async def one(extinf, name, url):
        async with sem:
            try:
                res = await mp.probe(url)
            except Exception as exc:  # noqa: BLE001
                return (extinf, name, url, False, "探测异常: %s" % str(exc)[:60])
            return (extinf, name, url, res.is_playable, res.summary())

    print("精选验证中（ffprobe 拉 5 秒码流，并发 %d）: %s" % (concurrency, path))
    results = await asyncio.gather(*[one(e, n, u) for e, n, u in items])

    ok = [r for r in results if r[3]]
    bad = [r for r in results if not r[3]]

    print("\n=== 结果 ===")
    print("总计 %d 条 | 可播放 %d | 不可播放 %d" % (len(results), len(ok), len(bad)))
    if bad:
        print("\n不可播放：")
        for _extinf, name, url, _play, detail in bad:
            print("  ✗ %-28s %s" % (name[:28], detail))
            print("      %s" % url)

    if out:
        with io.open(out, "w", encoding="utf-8", newline="\n") as fp:
            fp.write("#EXTM3U\n# 播放级精选（ffprobe 验证可播放）: %s\n" % os.path.basename(path))
            for extinf, _n, url, _play, _d in ok:
                fp.write(extinf + "\n")
                fp.write(url + "\n")
        print("\n已写出精选列表: %s (%d 条)" % (out, len(ok)))
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="用项目自带 MediaProbe 做播放级精选验证")
    ap.add_argument("m3u", help="待验证的 m3u 文件")
    ap.add_argument("--out", help="写出「可播放」频道组成的精选 m3u")
    ap.add_argument("--concurrency", type=int, default=20, help="并发 ffprobe 数（默认 20）")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(verify(args.m3u, args.out, args.concurrency)))


if __name__ == "__main__":
    main()
