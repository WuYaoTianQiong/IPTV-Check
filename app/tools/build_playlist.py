#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 江苏移动.m3u 与 电视直播源.m3u，生成去重、带分组和台标的播放列表。

用法:
    python app/tools/build_playlist.py            # 生成 live.m3u（外网通用）+ jiangsu-mobile.m3u（江苏移动专版）
    python app/tools/build_playlist.py --check-logo   # 额外联网校验每个台标 URL 可达性

设计要点:
  * 台标与 EPG 均来自 fanmingming/live 仓库，走 jsDelivr CDN（原文件使用的
    ghproxy.cc / ghfast.top 已 403，台标全部失效）。
  * 去重分两级：URL 完全相同只保留一条；同一频道的内网源与外网备源都保留，
    用名称后缀区分（超清/高清/标清 = 江苏移动内网，备用 = 外网第三方）。
  * 输出两份：live.m3u 仅含公网可播的外网源；jiangsu-mobile.m3u 含内网源+备源
    （适配江苏移动网络，本项目主推版本）。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import ssl
import sys
from collections import OrderedDict
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_A = os.path.join(ROOT, "app", "tools", "sources", "江苏移动.m3u")          # 第三方 OTT 聚合源（外网可播）
SRC_B = os.path.join(ROOT, "app", "tools", "sources", "电视直播源.m3u")         # 江苏移动内网源 + 少量第三方补录
OUT_LIVE = os.path.join(ROOT, "live.m3u")
OUT_MOBILE = os.path.join(ROOT, "jiangsu-mobile.m3u")

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


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-logo", action="store_true", help="联网校验台标 URL 可达性")
    args = ap.parse_args(argv)

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

    # 4) 生成显示名（IPv6 源单独标注，因多数家庭宽带无 IPv6，必然播不了）
    for e in entries:
        name = ("%s %s" % (e["base"], e["quality"])).strip() if e["quality"] else e["base"]
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
            if e["logo"]:
                # 中文文件名一律百分号编码，避免部分播放器不自动编码导致台标 404
                attrs.append('tvg-logo="%s%s"' % (LOGO_BASE, quote(e["logo"])))
            attrs.append('group-title="%s"' % e["group"])
            lines.append("#EXTINF:-1 %s,%s" % (" ".join(attrs), e["name"]))
            lines.append(e["url"])
        lines.append("")
        return lines

    live_entries = [e for e in entries if not e["official"]]
    mobile_entries = entries

    header_live = [
        "#",
        "# 外网通用版 | 仅含公网可播的外网第三方源（不含运营商内网源）",
        "# 由 tools/build_playlist.py 自动生成，请勿手工编辑",
        "# 来源：江苏移动.m3u + 电视直播源.m3u 中的外网源",
        "# 适用：任意公网播放器 / 非江苏移动网络",
        "# 台标 / EPG：fanmingming/live，经 jsDelivr CDN 加速",
    ]
    header_mobile = [
        "#",
        "# 江苏移动电视直播源（内网+备用）",
        "# 由 tools/build_playlist.py 自动生成，请勿手工编辑",
        "# 来源：江苏移动.m3u（第三方 OTT 外网源） + 电视直播源.m3u（江苏移动内网源 + 补录）",
        "# 命名规则：超清/高清/标清 = 江苏移动内网源；备用 = 外网第三方源；无后缀 = 仅此一路源",
        "# 命名纠正：%s" % "；".join("%s 实为 %s" % (k, v) for k, v in RENAME.items()),
        "# 台标 / EPG：fanmingming/live，经 jsDelivr CDN 加速",
    ]

    with io.open(OUT_LIVE, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(["#EXTM3U x-tvg-url=\"%s\"" % EPG_URL] + header_live + render(live_entries)))
    with io.open(OUT_MOBILE, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(["#EXTM3U x-tvg-url=\"%s\"" % EPG_URL] + header_mobile + render(mobile_entries)))

    stat = OrderedDict([
        ("live.m3u（外网通用）", len(live_entries)),
        ("jiangsu-mobile.m3u（江苏移动专版）", len(mobile_entries)),
        ("其中内网源", sum(1 for e in entries if e["official"])),
        ("其中外网第三方源", sum(1 for e in entries if not e["official"])),
        ("仅IPv6可达", sum(1 for e in entries if e["ipv6"])),
        ("已有台标", sum(1 for e in entries if e["logo"])),
        ("缺台标", [e["name"] for e in entries if not e["logo"]]),
        ("分组明细", OrderedDict((g, sum(1 for e in entries if e["group"] == g)) for g in GROUP_ORDER)),
    ])
    print(json.dumps(stat, ensure_ascii=False, indent=2))
    print("输出: %s" % OUT_LIVE)
    print("输出: %s" % OUT_MOBILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
