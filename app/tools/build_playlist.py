#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 江苏移动.m3u 与 电视直播源.m3u，生成去重、带分组（默认无台标）的播放列表。

默认不写 tvg-logo：远程台标会让 Kodi 等播放器开机逐个下载、启动极慢（一直 loading），
普通用户只需要能秒开看电视。需要台标时加 --with-logo（并自行评估 Kodi 启动速度）。

用法:
    python app/tools/build_playlist.py            # 生成 电视-国内-江苏移动.m3u（江苏移动专版）
    python app/tools/build_playlist.py --with-logo   # 额外写入远程台标（默认不写）
    python app/tools/build_playlist.py --check-logo  # 联网校验台标 URL 可达性（隐含 --with-logo）
    python app/tools/build_playlist.py --prune-dead  # 联网探测并剔除外部公网死链（内网源始终保留）

设计要点:
  * 台标与 EPG 均来自 fanmingming/live 仓库，走 jsDelivr CDN（原文件使用的
    ghproxy.cc / ghfast.top 已 403，台标全部失效）。
  * 去重分两级：URL 完全相同只保留一条；同一频道的内网源与外网备源只保留一条最优源
    （优先江苏移动内网源，无内网才留外部公网源；并去除 IPv6 重复）。
  * 输出一份：电视-国内-江苏移动.m3u 以江苏移动内网源为主（每频道仅留一条、无内网才留外部备源）。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_A = os.path.join(ROOT, "app", "tools", "sources", "江苏移动.m3u")          # 第三方 OTT 聚合源（外网可播）
SRC_B = os.path.join(ROOT, "app", "tools", "sources", "电视直播源.m3u")         # 江苏移动内网源 + 少量第三方补录
OUT_MOBILE = os.path.join(ROOT, "电视-国内-江苏移动.m3u")

LOGO_BASE = "https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/"
EPG_URL = "https://cdn.jsdelivr.net/gh/fanmingming/live@main/e.xml"

# 官方内网源网段（仅对应运营商内网可达），其余按外网第三方处理
OFFICIAL_HOSTS = ("223.110.241.204", "223.110.242.217")

GROUP_CCTV = "📺央视频道"
GROUP_SATELLITE = "📡卫视频道"
GROUP_JIANGSU = "📺江苏地方频道"
GROUP_KIDS = "📺少儿"
GROUP_NEWTV = "☘️NEWTV"
GROUP_HKMO = "🌐港澳台"
GROUP_OTHER = "📦其他频道"
GROUP_ORDER = [GROUP_CCTV, GROUP_SATELLITE, GROUP_JIANGSU, GROUP_KIDS, GROUP_NEWTV, GROUP_HKMO, GROUP_OTHER]

# 原始源中命名与 URL 实际指向不符的频道，按 URL 路径证据纠正
# 依据：福建卫视 -> .../DNWS/（DongNanWeiShi，东南卫视）；篮球 -> .../G_GUOXUE/（国学频道）
RENAME = {
    "福建卫视": "东南卫视",
    "篮球": "国学",
}

# CCTV 英文台号 → 中文显示名（仅改播放器可见的显示名；tvg-name / 台标 / EPG 仍用 CCTV1 等以匹配 fanmingming/live）
# 命名格式：保留英文台号 + 中文，如 CCTV-1 综合 / CCTV-5+ 体育赛事
CCTV_DISPLAY = {
    "CCTV1": "CCTV-1 综合",
    "CCTV2": "CCTV-2 财经",
    "CCTV3": "CCTV-3 综艺",
    "CCTV4": "CCTV-4 中文国际",
    "CCTV5": "CCTV-5 体育",
    "CCTV5+": "CCTV-5+ 体育赛事",
    "CCTV6": "CCTV-6 电影",
    "CCTV7": "CCTV-7 国防军事",
    "CCTV8": "CCTV-8 电视剧",
    "CCTV9": "CCTV-9 纪录",
    "CCTV10": "CCTV-10 科教",
    "CCTV11": "CCTV-11 戏曲",
    "CCTV12": "CCTV-12 社会与法",
    "CCTV13": "CCTV-13 新闻",
    "CCTV14": "CCTV-14 少儿",
    "CCTV15": "CCTV-15 音乐",
    "CCTV16": "CCTV-16 奥林匹克",
    "CCTV17": "CCTV-17 农业农村",
    "CCTV4K": "CCTV-4K 超高清",
    "CCTV8K": "CCTV-8K 超高清",
}

# 江苏移动.m3u 未带 tvg-logo 的频道，按 fanmingming/live 仓库实际文件名补齐
EXTRA_LOGO = {
    "CCTV兵器科技": "兵器科技.png",
    "CCTV第一剧场": "第一剧场.png",
    "CCTV电视指南": "电视指南.png",
    "CCTV风云剧场": "风云剧场.png",
    "CCTV风云音乐": "风云音乐.png",
    "CCTV风云足球": "风云足球.png",
    "CCTV女性时尚": "女性时尚.png",
    "CCTV高尔夫网球": "高尔夫网球.png",
    "CCTV怀旧剧场": "怀旧剧场.png",
    "CCTV世界地理": "世界地理.png",
    "CCTV央视台球": "央视台球.png",
    "CCTV央视文化精品": "文化精品.png",
    "CCTV老故事": "老故事.png",
    "中国教育1": "中国教育1台.png",
    "中国教育2": "中国教育2台.png",
    "中国教育3": "中国教育3台.png",
    "中国教育4": "中国教育4台.png",
    "CETV1": "CETV1.png",
    "CETV3": "CETV3.png",
    "CETV4": "CETV4.png",
    "CGTN": "CGTN.png",
    "凤凰中文": "凤凰中文.png",
    "凤凰香港": "凤凰卫视香港台.png",
    "上海哈哈炫动": "哈哈炫动.png",
    "炫动卡通": "哈哈炫动.png",
    "北京卡酷少儿": "卡酷少儿.png",
    "卡酷少儿": "卡酷少儿.png",
    "湖南金鹰卡通": "金鹰卡通.png",
    "金鹰卡通": "金鹰卡通.png",
    "广东嘉佳卡通": "嘉佳卡通.png",
    "嘉佳卡通": "嘉佳卡通.png",
    "江苏优漫卡通": "优漫卡通.png",
    "优漫卡通": "优漫卡通.png",
    "江苏体育休闲": "江苏休闲体育.png",
    "江苏公共新闻": "江苏公共新闻.png",
    "江苏城市": "江苏城市.png",
    "江苏影视": "江苏影视.png",
    "江苏综艺": "江苏综艺.png",
    "江苏教育": "江苏教育电视台.png",
    "江苏好享购物": "好享购物.png",
    "4K UHD": "爱上4K.png",
    "南方卫视": "南方卫视.png",
    "农林卫视": "农林卫视.png",
    "旅游卫视": "海南卫视.png",     # 旅游卫视已于 2019 年更名海南卫视
    "国学": "国学.png",
    "NewTV中国功夫": "NEWTV中国功夫.png",
    "NewTV军事评论": "NEWTV军事评论.png",
    "NewTV军旅剧场": "NEWTV军旅剧场.png",
    "NewTV家庭剧场": "NEWTV家庭剧场.png",
    "NewTV惊悚悬疑": "NEWTV惊悚悬疑.png",
    "NewTV明星大片": "NEWTV明星大片.png",
    "NewTV海外剧场": "NEWTV海外剧场.png",
    "NewTV潮妈辣婆": "NEWTV潮妈辣婆.png",
    "NewTV炫舞未来": "NEWTV炫舞未来.png",
    "NewTV精品体育": "NEWTV精品体育.png",
    "NewTV精品大剧": "NEWTV精品大剧.png",
    "NewTV精品纪录": "NEWTV精品纪录.png",
    "NewTV精品萌宠": "NEWTV精品萌宠.png",
}

# 省级卫视排列顺序（未列出的排在末尾，按名称排序）
PROVINCE_ORDER = [
    "北京卫视", "天津卫视", "河北卫视", "山西卫视", "内蒙古卫视",
    "辽宁卫视", "吉林卫视", "黑龙江卫视", "东方卫视", "江苏卫视",
    "浙江卫视", "安徽卫视", "东南卫视", "福建卫视", "江西卫视",
    "山东卫视", "河南卫视", "湖北卫视", "湖南卫视", "广东卫视",
    "广西卫视", "海南卫视", "重庆卫视", "四川卫视", "贵州卫视",
    "云南卫视", "西藏卫视", "陕西卫视", "甘肃卫视", "青海卫视",
    "宁夏卫视", "新疆卫视", "深圳卫视", "厦门卫视", "延边卫视",
    "南方卫视", "农林卫视", "旅游卫视", "4K UHD",
]

QUALITY_RANK = {"超清": 0, "高清": 1, "标清": 2, "备用": 3, "": 4}


def parse_m3u(path):
    """解析 m3u，返回 [{'name','url','tvg','logo','group'}]"""
    items = []
    cur = None
    with io.open(path, encoding="utf-8", errors="replace") as fp:
        for raw in fp:
            line = raw.strip()
            if not line or line.startswith("#EXTM3U"):
                continue
            if line.startswith("#EXTINF"):
                name = line.split(",", 1)[1].strip() if "," in line else ""
                tvg = re.search(r'tvg-name="([^"]*)"', line)
                logo = re.search(r'tvg-logo="([^"]*)"', line)
                grp = re.search(r'group-title="([^"]*)"', line)
                cur = {
                    "name": name,
                    "tvg": tvg.group(1) if tvg else "",
                    "logo": logo.group(1) if logo else "",
                    "group": grp.group(1) if grp else "",
                }
            elif line.startswith("#"):
                continue
            else:
                if cur is None:
                    cur = {"name": "", "tvg": "", "logo": "", "group": ""}
                cur["url"] = line
                items.append(cur)
                cur = None
    return items


def is_official(url):
    return any(h in url for h in OFFICIAL_HOSTS)


def long_pull_ok(url, duration=15, timeout=35, retries=1):
    """ffmpeg 真实解码拉流 duration 秒，能解出帧即视为可播放；用于复核 HTTP 短探针失败的源。

    与 probe_playlist.probe（仅 HTTP 连通性）互补：某些源首连会瞬时断流 / 握手抖动，短探针误判为
    死链，但 ffmpeg 持续拉流可正常解码。返回 (ok, frames, detail)：
      ok=True   → 解码出帧，可播放（复活，保留）
      ok=False  → 解码失败 / 0 帧 / 超时挂死，确属死链（剔除）
      ok=None   → ffmpeg 不可用，无法复核（保留 HTTP 短探针原判，即剔除）
    """
    if shutil.which("ffmpeg") is None:
        return (None, 0, "ffmpeg 未找到，跳过长拉流复核")
    for _attempt in range(1, retries + 1):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "info",
               "-i", url, "-t", str(duration), "-f", "null", "-"]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired:
            return (False, 0, "拉流超时挂死（%ds）" % timeout)
        text = proc.stderr.decode("utf-8", "replace")
        frames = 0
        for line in text.splitlines():
            if line.strip().startswith("frame="):
                try:
                    frames = int(line.strip().split("=")[1].split()[0])
                except (IndexError, ValueError):
                    pass
        if proc.returncode == 0 and frames > 0:
            return (True, frames, "解码帧数=%d" % frames)
    return (False, frames, "解码失败/0帧 (rc=%s)" % proc.returncode)


def normalize(name):
    """归一化频道名：去来源前缀、去清晰度后缀、去连字符与空格。"""
    s = name.replace("[第三方]", "").strip()
    s = re.sub(r"(超高清|超清|高清|标清)\s*$", "", s).strip()
    s = s.replace(" ", "").replace("CCTV-", "CCTV")
    return s


def clean_name(name):
    """去掉 [第三方] 前缀与清晰度后缀，得到基础显示名。"""
    s = name.replace("[第三方]", "").strip()
    s = re.sub(r"(超高清|超清|高清|标清)\s*$", "", s).strip()
    return s


def apply_rename(items):
    """按 RENAME 纠正命名与 URL 不符的频道，保留原有清晰度后缀。"""
    for it in items:
        base = clean_name(it["name"])
        if base not in RENAME:
            continue
        m = re.search(r"(超高清|超清|高清|标清)\s*$", it["name"])
        it["name"] = RENAME[base] + (m.group(1) if m else "")
    return items


def detect_quality(name):
    if "超清" in name:
        return "超清"
    if "高清" in name:
        return "高清"
    return "标清"


def detect_group(name, fallback=""):
    if fallback:
        return fallback
    if name.startswith(("CCTV", "CGTN", "CETV")) or name.startswith("中国教育") or "央视" in name or "老故事" in name:
        return GROUP_CCTV
    if "凤凰" in name:
        return GROUP_HKMO
    if name.startswith("NewTV"):
        return GROUP_NEWTV
    if any(k in name for k in ("卡通", "少儿", "卡酷", "金鹰", "炫动", "优漫", "嘉佳")):
        return GROUP_KIDS
    if name.startswith("江苏") or name.startswith("盐城"):
        return GROUP_JIANGSU
    if name in RENAME.values():
        return GROUP_OTHER
    return GROUP_SATELLITE


def cctv_num(name):
    m = re.match(r"^CCTV-?(\d+)", name)
    return int(m.group(1)) if m else 999


def download_epg(url, timeout=180):
    """下载 fanmingming 全量 EPG（XMLTV），返回字节内容。"""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    print("正在下载 EPG 全量文件: %s" % url)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def filter_epg(stream, wanted, out_path, epg_days=3):
    """从全量 XMLTV 中筛出 wanted（tvg-name 集合）对应的频道与节目，写出瘦身 EPG。

    Kodi 的 m3u 仅带 tvg-name（无 tvg-id），而 fanmingming 的 <channel id> 与 tvg-name
    基本一致（如 CCTV1、北京卫视），故按 id / display-name 命中即保留该频道及其节目。
    命中频道与节目保留子树（不清空），未命中者立即 clear() 释放内存。

    仅保留时间窗口内的节目：从「昨天」到「未来 epg_days 天」。
    弱 CPU 盒子上 Kodi 每次启动都要解析整个 EPG 建库，8 天 1.6 万条会卡住 PVR 启动；
    保留最近 3 天（当前节目 + 接下来两天）足够日常使用，解析量降到约 1/3。
    """
    def _start_ts(s):
        m = re.match(r"(\d{14})", s or "")
        if not m:
            return None
        dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone(timedelta(hours=8)))  # XMLTV 时间均为 +0800
        return dt.timestamp()

    now = time.time()
    win_start = now - 86400          # 昨天起
    win_end = now + epg_days * 86400  # 未来 epg_days 天

    wanted_l = {w.lower() for w in wanted if w}
    keep_ids = set()
    out_channels = []
    out_programs = []
    context = ET.iterparse(stream, events=("end",))
    for _event, elem in context:
        if elem.tag == "channel":
            cid = elem.get("id", "")
            disp = elem.findtext("display-name", default="") or ""
            if cid.lower() in wanted_l or disp.lower() in wanted_l:
                keep_ids.add(cid)
                out_channels.append(elem)
            else:
                elem.clear()
        elif elem.tag == "programme":
            ts = _start_ts(elem.get("start", ""))
            if elem.get("channel", "") in keep_ids and ts is not None and win_start <= ts <= win_end:
                out_programs.append(elem)
            else:
                elem.clear()
    tv = ET.Element("tv")
    tv.set("generator-info-name", "IPTV-Check slim-epg")
    tv.extend(out_channels)
    tv.extend(out_programs)
    ET.ElementTree(tv).write(out_path, encoding="utf-8", xml_declaration=True)
    print("已生成瘦身 EPG: %s（%d 频道 / %d 节目，%d 天窗口）" % (
        out_path, len(out_channels), len(out_programs), epg_days))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-logo", action="store_true",
                    help="写入远程台标（默认不写：远程台标会让 Kodi 等播放器开机逐个下载、启动极慢；仅需要台标时才开启）")
    ap.add_argument("--check-logo", action="store_true",
                    help="联网校验台标 URL 可达性（隐含 --with-logo）")
    ap.add_argument("--prune-dead", action="store_true",
                    help="联网探测并剔除外部公网死链（内网源始终保留，需于对应运营商网络下用 probe_playlist.py 单独验证）")
    ap.add_argument("--epg", action="store_true",
                    help="联网拉取 fanmingming 全量 EPG，筛出仅本列表频道的瘦身 .epg.xml（解决盒子开机全量拉取卡死）；"
                         "生成的 m3u 的 x-tvg-url 会指向本地瘦身文件，仅供本地使用，请勿提交到仓库")
    ap.add_argument("--epg-days", type=int, default=3,
                    help="瘦身 EPG 保留的天数窗口，默认 3 天（当前节目 + 未来两天）。"
                         "弱 CPU 盒子解析 EPG 是开机卡慢主因之一，天数越小解析越快（仅与 --epg 配合）")
    args = ap.parse_args(argv)
    if args.check_logo:
        args.with_logo = True

    items_a = apply_rename(parse_m3u(SRC_A))
    items_b = apply_rename(parse_m3u(SRC_B))

    # 1) 以 江苏移动.m3u 为基准建立频道元数据（基础名 / tvg-name / 台标 / 分组）
    meta = OrderedDict()
    for it in items_a:
        key = normalize(it["name"])
        logo_file = os.path.basename(it["logo"]) if it["logo"] else ""
        meta[key] = {
            "base": it["name"],
            "tvg": it["tvg"] or it["name"],
            "logo": logo_file or EXTRA_LOGO.get(it["name"], ""),
            "group": it["group"] or detect_group(it["name"]),
        }

    # 2) 电视直播源.m3u 中新增的频道补进元数据
    for it in items_b:
        key = normalize(it["name"])
        if key in meta:
            continue
        base = clean_name(it["name"])
        meta[key] = {
            "base": base,
            "tvg": base,
            "logo": EXTRA_LOGO.get(base, ""),
            "group": detect_group(base),
        }

    # 3) 合并条目并按 URL 去重（A 优先，因其自带分组/台标）
    entries = []
    seen_url = set()
    for source, items in (("A", items_a), ("B", items_b)):
        for it in items:
            if it["url"] in seen_url:
                continue
            seen_url.add(it["url"])
            m = meta[normalize(it["name"])]
            official = is_official(it["url"])
            quality = detect_quality(it["name"]) if official else ""
            entries.append({
                "base": m["base"],
                "tvg": m["tvg"],
                "logo": m["logo"],
                "group": m["group"],
                "url": it["url"],
                "official": official,
                "quality": quality,
                "ipv6": it["url"].startswith("http://["),
            })

    # 同一频道若同时存在内网源与外网源，外网源标记为「备用」
    official_bases = {e["base"] for e in entries if e["official"]}
    for e in entries:
        if not e["official"] and e["base"] in official_bases:
            e["quality"] = "备用"

    # 3.5) 可选：剔除死链。联网探测每条外部源，丢弃不可达者（仅外部公网源参与探测，
    #      运营商内网源始终保留——它只在对应网络可达，在本机构建时误杀会丢掉有效源）。
    #      短探针失败的源再用 ffmpeg 长拉流二次复核，避免把「瞬时断流/握手抖动」的可播源误删。
    pruned = 0
    revived = 0
    candidates_count = 0
    if args.prune_dead:
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from probe_playlist import probe
        except Exception:  # noqa: BLE001
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "probe_playlist", os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_playlist.py"))
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            probe = _mod.probe
        print("正在联网剔除死链（探测外部源，请稍候）...")
        candidates = set()  # 短探针失败、待长拉流复核的外部源
        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = {ex.submit(probe, (e["base"], e["url"]), 6, False): e for e in entries}
            for fut in as_completed(futs):
                url, status, _note = fut.result()
                if status not in ("ok", "internal"):
                    candidates.add(url)
        candidates_count = len(candidates)
        # 二次长拉流复核：短探针失败者用 ffmpeg 真实解码确认，可解码即复活
        dead = set(candidates)
        if candidates:
            print("短探针失败 %d 条，启动 ffmpeg 长拉流复核（拉 %ds，并发 4）..." % (candidates_count, 15))
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(long_pull_ok, url): url for url in candidates}
                for fut in as_completed(futs):
                    url = futs[fut]
                    ok, frames, detail = fut.result()
                    if ok is True:
                        dead.discard(url)
                        revived += 1
                        print("  ✓ 复核通过(可播放) 帧=%d | %s" % (frames, url))
                    else:
                        print("  ✗ 确属死链 [%s] | %s" % (detail, url))
        before = len(entries)
        entries = [e for e in entries if e["url"] not in dead]
        pruned = before - len(entries)
        if candidates_count:
            print("短探针失败 %d 条 → ffmpeg 长拉流复核复活 %d 条可播源，最终剔除 %d 条真死链"
                  % (candidates_count, revived, pruned))
        else:
            print("未检测到外部死链")

    # 4) 生成显示名（CCTV 套用中文显示名；IPv6 源单独标注，因多数家庭宽带无 IPv6，必然播不了）
    for e in entries:
        disp = CCTV_DISPLAY.get(normalize(e["base"]), e["base"])
        name = ("%s %s" % (disp, e["quality"])).strip() if e["quality"] else disp
        if e["ipv6"]:
            name += " [IPv6]"
        e["name"] = name

    # 5) 分组内排序
    def sort_key(e):
        g = GROUP_ORDER.index(e["group"]) if e["group"] in GROUP_ORDER else len(GROUP_ORDER)
        if e["group"] == GROUP_CCTV:
            n = cctv_num(e["base"])
            order = (0, n, e["base"])
        elif e["group"] == GROUP_SATELLITE:
            idx = PROVINCE_ORDER.index(e["base"]) if e["base"] in PROVINCE_ORDER else 999
            order = (1, idx, e["base"])
        else:
            order = (2, 0, e["base"])
        return (g, order[0], order[1], order[2], QUALITY_RANK.get(e["quality"], 4), e["name"])

    entries.sort(key=sort_key)

    # 6) 可选：校验台标可达性（中文路径需百分号编码后才能发起请求）
    if args.check_logo:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        broken = []
        for e in entries:
            if not e["logo"]:
                continue
            url = LOGO_BASE + quote(e["logo"])
            try:
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
                with urlopen(req, timeout=20, context=ctx) as r:
                    if r.status != 200:
                        broken.append((e["name"], e["logo"], r.status))
            except Exception as exc:  # noqa: BLE001
                broken.append((e["name"], e["logo"], str(exc)))
        if broken:
            print("台标不可达（已丢弃对应 tvg-logo）:")
            for name, logo, err in broken:
                print("  %-24s %-24s %s" % (name, logo, err))
            bad = {b[1] for b in broken}
            for e in entries:
                if e["logo"] in bad:
                    e["logo"] = ""

    # 7) 输出两份列表
    os.makedirs(ROOT, exist_ok=True)

    def render(entries):
        lines = []
        cur_group = None
        for e in entries:
            if e["group"] != cur_group:
                cur_group = e["group"]
                lines.append("#")
                lines.append("# ===== %s =====" % cur_group)
            attrs = ['tvg-name="%s"' % e["tvg"]]
            if e["logo"] and args.with_logo:
                # 默认不写台标：远程台标会让 Kodi 开机逐个下载、启动极慢；仅 --with-logo 时写入。
                # 中文文件名一律百分号编码，避免部分播放器不自动编码导致台标 404
                attrs.append('tvg-logo="%s%s"' % (LOGO_BASE, quote(e["logo"])))
            attrs.append('group-title="%s"' % e["group"])
            lines.append("#EXTINF:-1 %s,%s" % (" ".join(attrs), e["name"]))
            lines.append(e["url"])
        lines.append("")
        return lines

    def pick_best(items):
        """每频道仅留一条最优源：有内网源则留内网（优先 IPv4、清晰度优先），否则留一条外部源（优先 IPv4）。"""
        groups = OrderedDict()
        for e in items:
            groups.setdefault(e["base"], []).append(e)
        chosen = []
        for es in groups.values():
            official = [e for e in es if e["official"]]
            if official:
                chosen.append(sorted(official, key=lambda e: (e["ipv6"], QUALITY_RANK.get(e["quality"], 4)))[0])
            else:
                chosen.append(sorted(es, key=lambda e: e["ipv6"])[0])
        return chosen

    mobile_entries = sorted(pick_best(entries), key=sort_key)

    header_mobile = [
        "#",
        "# 电视-国内-江苏移动（江苏移动内网为主，国内频道）",
        "# 由 tools/build_playlist.py 自动生成，请勿手工编辑",
        "# 来源：江苏移动.m3u（第三方 OTT 外网源） + 电视直播源.m3u（江苏移动内网源 + 补录）",
        "# 去重规则：每频道仅留一条最优源——有内网源（超清/高清/标清）则留内网，否则留外部公网源；已去除 IPv6 重复",
        "# 命名纠正：%s" % "；".join("%s 实为 %s" % (k, v) for k, v in RENAME.items()),
        "# %s：fanmingming/live，经 jsDelivr CDN 加速"
        % ("台标 / EPG" if args.with_logo else "EPG（默认无台标，避免 Kodi 开机下载台标卡死）"),
    ]

    if args.prune_dead:
        note = ("# 已联网剔除死链：短探针失败 %d 条，经 ffmpeg 长拉流复核复活 %d 条可播源，"
                "最终移除 %d 条外部真死链（内网源未探测，需于江苏移动网络单独验证）"
                % (candidates_count, revived, pruned))
        header_mobile.append(note)

    # 7.5) 可选：生成瘦身节目单（仅含本列表频道，避免 Kodi 开机全量拉取卡死）
    epg_bytes = None
    if args.epg:
        try:
            epg_bytes = download_epg(EPG_URL)
        except Exception as exc:  # noqa: BLE001
            print("EPG 全量下载失败，将回退为远程全量 EPG: %s" % exc)
            epg_bytes = None

    def write_playlist(path, header, entries):
        xurl = EPG_URL
        if epg_bytes is not None:
            epg_name = os.path.splitext(os.path.basename(path))[0] + ".epg.xml"
            try:
                filter_epg(io.BytesIO(epg_bytes), {e["tvg"] for e in entries if e["tvg"]},
                           os.path.join(ROOT, epg_name), epg_days=args.epg_days)
                xurl = epg_name
            except Exception as exc:  # noqa: BLE001
                print("瘦身 EPG 生成失败，回退远程全量: %s" % exc)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write("\n".join(["#EXTM3U x-tvg-url=\"%s\"" % xurl] + header + render(entries)))

    write_playlist(OUT_MOBILE, header_mobile, mobile_entries)

    stat = OrderedDict([
        ("电视-国内-江苏移动.m3u（江苏移动专版）", len(mobile_entries)),
        ("本次剔除死链", pruned),
        ("其中长拉流复核复活", revived),
        ("短探针失败待复核", candidates_count),
        ("其中内网源（江苏移动）", sum(1 for e in mobile_entries if e["official"])),
        ("其中外部源", sum(1 for e in mobile_entries if not e["official"])),
        ("仅IPv6可达", sum(1 for e in mobile_entries if e["ipv6"])),
        ("已有台标", sum(1 for e in mobile_entries if e["logo"])),
        ("缺台标", [e["name"] for e in mobile_entries if not e["logo"]]),
        ("分组明细", OrderedDict((g, sum(1 for e in mobile_entries if e["group"] == g)) for g in GROUP_ORDER)),
    ])
    print(json.dumps(stat, ensure_ascii=False, indent=2))
    print("输出: %s" % OUT_MOBILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
