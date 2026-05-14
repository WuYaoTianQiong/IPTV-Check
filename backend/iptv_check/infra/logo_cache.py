import os
import logging
import time
import re
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

LOGO_CACHE_TTL = 30 * 24 * 3600


class LogoCacheManager:
    def __init__(self, base_dir: str):
        self._base_dir = os.path.join(base_dir, "data", "cache", "logos")
        os.makedirs(self._base_dir, exist_ok=True)
        self._cache = None

    def _get_cache(self):
        if self._cache is None:
            try:
                from diskcache import Cache
                self._cache = Cache(self._base_dir)
            except ImportError:
                logger.warning("diskcache不可用，台标缓存禁用")
                return None
        return self._cache

    def get_logo(self, channel_name: str) -> Optional[bytes]:
        cache = self._get_cache()
        if not cache:
            return None
        key = f"logo:{channel_name.lower()}"
        entry = cache.get(key)
        if entry and time.time() - entry.get("timestamp", 0) < LOGO_CACHE_TTL:
            return entry.get("data")
        return None

    def set_logo(self, channel_name: str, data: bytes) -> None:
        cache = self._get_cache()
        if not cache:
            return
        cache.set(f"logo:{channel_name.lower()}", {"data": data, "timestamp": time.time()})

    def get_logo_url_cache(self, url: str) -> Optional[bytes]:
        cache = self._get_cache()
        if not cache:
            return None
        key = f"logo_url:{url}"
        entry = cache.get(key)
        if entry and time.time() - entry.get("timestamp", 0) < LOGO_CACHE_TTL:
            return entry.get("data")
        return None

    def set_logo_url_cache(self, url: str, data: bytes) -> None:
        cache = self._get_cache()
        if not cache:
            return
        cache.set(f"logo_url:{url}", {"data": data, "timestamp": time.time()})

    def has_logo(self, channel_name: str) -> bool:
        return self.get_logo(channel_name) is not None

    def cleanup_stale(self, max_age_days: int = 30) -> int:
        cache = self._get_cache()
        if not cache:
            return 0
        cutoff = time.time() - max_age_days * 24 * 3600
        removed = 0
        for key in list(cache.iterkeys()):
            entry = cache.get(key)
            if entry and entry.get("timestamp", 0) < cutoff:
                cache.delete(key)
                removed += 1
        if removed:
            logger.info("台标缓存清理: 移除 %d 个过期条目", removed)
        return removed

    def get_stats(self) -> dict:
        cache = self._get_cache()
        if not cache:
            return {"enabled": False}
        return {
            "enabled": True,
            "size": cache.volume() if hasattr(cache, "volume") else 0,
            "count": len(cache) if hasattr(cache, "__len__") else 0,
        }
