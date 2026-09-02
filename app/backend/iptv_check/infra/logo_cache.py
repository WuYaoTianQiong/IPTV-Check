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
        return cache.get(f"logo:{channel_name.lower()}")

    def set_logo(self, channel_name: str, data: bytes) -> None:
        cache = self._get_cache()
        if not cache:
            return
        # 利用 diskcache 内建 TTL 过期，替代手写 timestamp 比较
        cache.set(f"logo:{channel_name.lower()}", data, expire=LOGO_CACHE_TTL)

    def get_logo_url_cache(self, url: str) -> Optional[bytes]:
        cache = self._get_cache()
        if not cache:
            return None
        return cache.get(f"logo_url:{url}")

    def set_logo_url_cache(self, url: str, data: bytes) -> None:
        cache = self._get_cache()
        if not cache:
            return
        cache.set(f"logo_url:{url}", data, expire=LOGO_CACHE_TTL)

    def has_logo(self, channel_name: str) -> bool:
        return self.get_logo(channel_name) is not None

    def cleanup_stale(self, max_age_days: int = 30) -> int:
        cache = self._get_cache()
        if not cache:
            return 0
        if max_age_days <= 0:
            # max_age_days<=0 语义为「清空全部」（routers/cache.py 调用 cleanup_stale(0)）
            removed = len(cache)
            cache.clear()
            if removed:
                logger.info("台标缓存已清空: %d 条", removed)
            return removed
        cutoff = time.time() - max_age_days * 24 * 3600
        removed = 0
        for key in list(cache.iterkeys()):
            _, exp = cache.get(key, expire_time=True) or (None, None)
            if exp is not None and exp < cutoff:
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
