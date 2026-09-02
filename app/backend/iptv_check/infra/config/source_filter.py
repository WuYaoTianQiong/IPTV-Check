"""风险源过滤（域名黑名单）

背景
----
部分 IPTV 聚合源的频道 URL 返回的并不是流媒体，而是一个 HTML + JS 跳转页
（典型形态：整页只有一句 ``window.location.replace('http://...api.php?...')``），
用作防盗链/广告网关。这类 URL：
1) 不是流，播放器/检测器都拿不到数据；
2) 会被杀毒软件按 ``JS.Redirector`` 特征拦截，每次检测都弹告警。

机制
----
1. 静态黑名单 ``data/blocked_domains.json`` 的 ``manual`` 段，可手工维护；
2. 自动拉黑：检测时发现源返回 ``text/html`` 且不是 m3u8，自动将其域名写入 ``auto`` 段；
3. 命中黑名单的源在**发起 HTTP 请求之前**就被判定无效，因此不会反复触发告警。

匹配规则：按 URL 的 host 精确匹配，或以 ``.域名`` 结尾的子域匹配。
自动拉黑时除了完整 host，还会拉黑其根域（如 ``kkk.jjjj.jiduo.me`` -> ``jiduo.me``），
避免对方换个三级子域就绕过；根域提取已排除 ``com.cn`` 这类双后缀，不会误伤整个 cn 域。
"""

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_CACHE: Optional[dict] = None

# 已知风险域（返回 HTML + JS 跳转页）
DEFAULT_BLOCKED = ["jiduo.me"]

# 常见双后缀：这些后缀下不能把"最后两段"当作根域，否则会误伤整个国家域
_MULTI_PART_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk",
    "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
    "com.hk", "net.hk", "org.hk", "gov.hk", "edu.hk",
    "com.tw", "net.tw", "org.tw", "edu.tw",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "co.kr", "or.kr", "ne.kr",
    "com.au", "net.au", "org.au", "com.br", "com.mx", "com.ar",
    "com.tr", "com.sg", "co.nz", "co.za", "com.ua", "com.pl",
}


def _file_path() -> Path:
    from iptv_check.infra.config.settings import get_path_settings
    return Path(get_path_settings().data_dir) / "blocked_domains.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> dict:
    """加载黑名单（带内存缓存），首次加载时补齐内置默认项"""
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE

        data: Dict = {"manual": [], "auto": {}}
        path = _file_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded.get("manual"), list):
                    data["manual"] = [m for m in loaded["manual"] if isinstance(m, dict)]
                if isinstance(loaded.get("auto"), dict):
                    data["auto"] = dict(loaded["auto"])
            except Exception as e:
                logger.warning("[源过滤] 读取 %s 失败，使用空名单: %s", path, e)

        existing = {str(m.get("domain", "")).lower() for m in data["manual"]}
        added = False
        for domain in DEFAULT_BLOCKED:
            if domain not in existing:
                data["manual"].append({
                    "domain": domain,
                    "reason": "内置：返回HTML+JS跳转页，易被杀软判定为JS.Redirector",
                    "added_at": _now(),
                })
                added = True

        _CACHE = data
        if added:
            _save(data)
        return data


def _save(data: dict) -> None:
    """原子写入，避免写入中断产生损坏文件"""
    path = _file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("[源过滤] 写入 %s 失败: %s", path, e)


def _host_of(url: str) -> str:
    """从 URL 提取小写主机名，失败返回空串"""
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    return host.lower().strip(".")


_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _root_domain(host: str) -> str:
    """提取根域：kkk.jjjj.jiduo.me -> jiduo.me；a.b.com.cn -> b.com.cn；
    IP 地址（IPv4/IPv6）原样返回，不做根域提取"""
    if _IPV4_RE.match(host) or ":" in host:
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    last_two = ".".join(parts[-2:])
    if last_two in _MULTI_PART_SUFFIXES:
        return ".".join(parts[-3:]) if len(parts) >= 3 else host
    return last_two


def match(url: str) -> Optional[str]:
    """URL 是否命中黑名单。命中返回命中的域名，否则返回 None"""
    host = _host_of(url)
    if not host:
        return None
    data = _load()
    for item in data["manual"]:
        domain = str(item.get("domain", "")).lower().strip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return domain
    for domain in data["auto"]:
        domain = str(domain).lower().strip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return domain
    return None


def is_blocked(url: str) -> bool:
    return match(url) is not None


def block(url: str, reason: str) -> Optional[str]:
    """自动拉黑：把 URL 的 host（及根域）加入黑名单，返回被拉黑的 host"""
    host = _host_of(url)
    if not host:
        return None

    now = _now()
    with _LOCK:
        data = _load()
        auto = data["auto"]

        rec = auto.get(host)
        if isinstance(rec, dict):
            rec["count"] = int(rec.get("count", 0)) + 1
            rec["last_seen"] = now
        else:
            auto[host] = {"reason": reason, "first_seen": now, "last_seen": now, "count": 1}
            logger.info("[源过滤] 自动拉黑域名 %s（%s）", host, reason)

        root = _root_domain(host)
        if root != host and root not in auto:
            auto[root] = {
                "reason": f"{reason}（同根域连带）",
                "first_seen": now,
                "last_seen": now,
                "count": 0,
            }
            logger.info("[源过滤] 连带拉黑根域 %s", root)

        _save(data)
    return host


def add_manual(domain: str, reason: str = "手动添加") -> bool:
    """手动加入黑名单。返回是否新增（已存在返回 False）"""
    domain = (domain or "").strip().lower().strip(".")
    if not domain:
        return False
    with _LOCK:
        data = _load()
        for item in data["manual"]:
            if str(item.get("domain", "")).lower() == domain:
                return False
        data["manual"].append({"domain": domain, "reason": reason, "added_at": _now()})
        _save(data)
    return True


def remove(domain: str) -> bool:
    """解除拉黑（manual 与 auto 同时尝试）。返回是否有删除"""
    domain = (domain or "").strip().lower().strip(".")
    if not domain:
        return False
    removed = False
    with _LOCK:
        data = _load()
        before = len(data["manual"])
        data["manual"] = [m for m in data["manual"] if str(m.get("domain", "")).lower() != domain]
        removed = removed or len(data["manual"]) != before
        if domain in data["auto"]:
            del data["auto"][domain]
            removed = True
        if removed:
            _save(data)
    return removed


def clear_auto() -> int:
    """清空自动拉黑记录，返回清除条数"""
    with _LOCK:
        data = _load()
        n = len(data["auto"])
        if n:
            data["auto"] = {}
            _save(data)
        return n


def all_entries() -> dict:
    """返回完整黑名单，供 API 展示"""
    data = _load()
    manual: List[dict] = [dict(m) for m in data["manual"]]
    auto: List[dict] = [
        {"domain": d, **rec} for d, rec in data["auto"].items() if isinstance(rec, dict)
    ]
    auto.sort(key=lambda x: x.get("count", 0), reverse=True)
    return {"manual": manual, "auto": auto, "total": len(manual) + len(auto)}
