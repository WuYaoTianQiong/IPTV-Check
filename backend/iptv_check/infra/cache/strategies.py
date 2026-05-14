"""
Cache Strategy Patterns
Defines different caching strategies for various data types.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class CacheStrategy(ABC):
    """Abstract base class for cache strategies."""

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Get diskcache configuration parameters."""
        pass

    @abstractmethod
    def get_ttl(self) -> int:
        """Get time-to-live in seconds."""
        pass


class TTLStrategy(CacheStrategy):
    """
    Time-To-Live based cache strategy.
    Suitable for data with predictable expiration (EPG, detection results).
    """

    def __init__(self, ttl_seconds: int = 86400):
        self._ttl = ttl_seconds

    def get_config(self) -> Dict[str, Any]:
        return {
            "timeout": 10,
            "size_limit": 200 * 1024 * 1024,
            "eviction_policy": "least-recently-used",
        }

    def get_ttl(self) -> int:
        return self._ttl


class LRUStrategy(CacheStrategy):
    """
    Least Recently Used cache strategy.
    Suitable for data with size constraints (logos, thumbnails).
    """

    def __init__(self, max_size_mb: int = 500):
        self._max_size = max_size_mb * 1024 * 1024

    def get_config(self) -> Dict[str, Any]:
        return {
            "timeout": 10,
            "size_limit": self._max_size,
            "eviction_policy": "least-recently-used",
        }

    def get_ttl(self) -> int:
        return 0  # LRU doesn't use TTL, evicts based on size


class PersistentStrategy(CacheStrategy):
    """
    Persistent cache strategy with no expiration.
    Suitable for configuration and metadata that should persist.
    """

    def __init__(self, max_size_mb: int = 50):
        self._max_size = max_size_mb * 1024 * 1024

    def get_config(self) -> Dict[str, Any]:
        return {
            "timeout": 10,
            "size_limit": self._max_size,
            "eviction_policy": "none",
        }

    def get_ttl(self) -> int:
        return 0  # No expiration


# Predefined strategy instances for common use cases
DETECTION_CACHE_STRATEGY = TTLStrategy(ttl_seconds=24 * 3600)  # 24 hours
EPG_CACHE_STRATEGY = TTLStrategy(ttl_seconds=48 * 3600)  # 48 hours
LOGO_CACHE_STRATEGY = LRUStrategy(max_size_mb=500)  # 500MB limit
CONFIG_CACHE_STRATEGY = PersistentStrategy(max_size_mb=10)  # 10MB, no expiry
