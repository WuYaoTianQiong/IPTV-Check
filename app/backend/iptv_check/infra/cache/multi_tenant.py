"""
Multi-Tenant Cache Manager
Provides namespace-isolated cache management with strategy pattern.
"""

import os
import logging
from typing import Optional, Any
from diskcache import Cache

from iptv_check.infra.cache.strategies import (
    CacheStrategy,
    DETECTION_CACHE_STRATEGY,
    EPG_CACHE_STRATEGY,
    LOGO_CACHE_STRATEGY,
    CONFIG_CACHE_STRATEGY,
)

logger = logging.getLogger(__name__)


class MultiTenantCacheManager:
    """
    Cache manager with namespace isolation.
    Each namespace has its own diskcache instance with specific strategy.
    """

    def __init__(self, base_dir: str):
        self._base_dir = base_dir
        self._cache_dir = os.path.join(base_dir, "cache_store")
        self._namespaces: dict[str, Cache] = {}
        self._strategies: dict[str, CacheStrategy] = {}

    def get_cache(self, namespace: str, strategy: CacheStrategy) -> Cache:
        """Get or create a cache instance for the given namespace."""
        if namespace not in self._namespaces:
            cache_dir = os.path.join(self._cache_dir, namespace)
            os.makedirs(cache_dir, exist_ok=True)
            config = strategy.get_config()
            self._namespaces[namespace] = Cache(cache_dir, **config)
            self._strategies[namespace] = strategy
            logger.info("Cache namespace initialized: %s", namespace)
        return self._namespaces[namespace]

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get value from cache namespace."""
        strategy = self._strategies.get(namespace)
        if not strategy:
            return default
        cache = self.get_cache(namespace, strategy)
        value = cache.get(key, default=default)
        if value is not default:
            logger.debug("Cache hit: %s:%s", namespace, key)
        return value

    def set(self, namespace: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache namespace."""
        strategy = self._strategies.get(namespace)
        if not strategy:
            raise ValueError(f"Cache namespace {namespace} not configured")
        cache = self.get_cache(namespace, strategy)
        expire = ttl if ttl is not None else strategy.get_ttl()
        cache.set(key, value, expire=expire)
        logger.debug("Cache set: %s:%s, TTL=%ds", namespace, key, expire)

    def has(self, namespace: str, key: str) -> bool:
        """Check if key exists in cache namespace."""
        strategy = self._strategies.get(namespace)
        if not strategy:
            return False
        cache = self.get_cache(namespace, strategy)
        return key in cache

    def delete(self, namespace: str, key: str) -> bool:
        """Delete key from cache namespace."""
        strategy = self._strategies.get(namespace)
        if not strategy:
            return False
        cache = self.get_cache(namespace, strategy)
        return cache.delete(key)

    def clear_namespace(self, namespace: str) -> None:
        """Clear all entries in a namespace."""
        if namespace in self._namespaces:
            self._namespaces[namespace].clear()
            logger.info("Cache namespace cleared: %s", namespace)

    def clear_all(self) -> None:
        """Clear all cache namespaces."""
        for namespace in list(self._namespaces.keys()):
            self.clear_namespace(namespace)

    def get_stats(self) -> dict:
        """Get statistics for all cache namespaces."""
        stats = {}
        for namespace, cache in self._namespaces.items():
            stats[namespace] = {
                "count": len(cache),
                "size_bytes": cache.volume(),
                "size_mb": round(cache.volume() / 1024 / 1024, 2),
                "directory": cache.directory,
            }
        return stats

    def cleanup_expired(self) -> int:
        """Clean up expired entries across all namespaces."""
        total_cleaned = 0
        for namespace, cache in self._namespaces.items():
            count_before = len(cache)
            cache.expire()
            cleaned = count_before - len(cache)
            total_cleaned += cleaned
            if cleaned > 0:
                logger.info("Cleaned %d expired entries from %s", cleaned, namespace)
        return total_cleaned

    def close_all(self) -> None:
        """Close all cache instances."""
        for namespace, cache in self._namespaces.items():
            cache.close()
            logger.info("Cache namespace closed: %s", namespace)
        self._namespaces.clear()
        self._strategies.clear()

    @property
    def detection_cache(self) -> Cache:
        """Get detection results cache (24h TTL)."""
        return self.get_cache("detection", DETECTION_CACHE_STRATEGY)

    @property
    def epg_cache(self) -> Cache:
        """Get EPG data cache (48h TTL)."""
        return self.get_cache("epg", EPG_CACHE_STRATEGY)

    @property
    def logo_cache(self) -> Cache:
        """Get logo images cache (500MB LRU)."""
        return self.get_cache("logos", LOGO_CACHE_STRATEGY)

    @property
    def config_cache(self) -> Cache:
        """Get configuration cache (persistent)."""
        return self.get_cache("config", CONFIG_CACHE_STRATEGY)
