import json
import time
import logging
import os
from typing import Optional, Any
from diskcache import Cache

from iptv_check.config import CACHE_FILE, CACHE_EXPIRY_HOURS

logger = logging.getLogger(__name__)


class DiskCacheManager:
    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self._cache_dir = os.path.join(self._base_dir, "cache_store")
        self._ttl = CACHE_EXPIRY_HOURS * 3600
        self._cache: Optional[Cache] = None

    def _ensure_cache(self) -> Cache:
        if self._cache is None:
            os.makedirs(self._cache_dir, exist_ok=True)
            self._cache = Cache(
                self._cache_dir,
                timeout=10,
                size_limit=500 * 1024 * 1024,
                eviction_policy="least-recently-used",
            )
            logger.info("DiskCache 初始化: %s", self._cache_dir)
        return self._cache

    def get(self, key: str) -> Optional[Any]:
        cache = self._ensure_cache()
        value = cache.get(key, default=None)
        if value is not None:
            logger.debug("缓存命中: %s", key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        cache = self._ensure_cache()
        expire = ttl if ttl is not None else self._ttl
        cache.set(key, value, expire=expire)
        logger.debug("缓存设置: %s, TTL=%ds", key, expire)

    def has(self, key: str) -> bool:
        cache = self._ensure_cache()
        return key in cache

    def delete(self, key: str) -> bool:
        cache = self._ensure_cache()
        return cache.delete(key)

    def clear(self) -> None:
        cache = self._ensure_cache()
        cache.clear()
        logger.info("缓存已清空")

    def count(self) -> int:
        cache = self._ensure_cache()
        return len(cache)

    def cleanup_expired(self) -> int:
        cache = self._ensure_cache()
        count_before = len(cache)
        cache.expire()
        count_after = len(cache)
        expired = count_before - count_after
        if expired > 0:
            logger.info("清理过期缓存: %d 条", expired)
        return expired

    def stats(self) -> dict:
        cache = self._ensure_cache()
        return {
            "count": len(cache),
            "size_bytes": cache.volume(),
            "ttl_seconds": self._ttl,
            "directory": self._cache_dir,
        }

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()
            self._cache = None
            logger.info("DiskCache 已关闭")
