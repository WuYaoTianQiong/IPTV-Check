import os
import logging
import time
from typing import Optional, Dict, Any

from iptv_check.models.epg_program import EpgChannel

logger = logging.getLogger(__name__)

EPG_CACHE_TTL = 48 * 3600
LOGO_CACHE_TTL = 30 * 24 * 3600


class EpgCacheManager:
    def __init__(self, base_dir: str):
        self._base_dir = os.path.join(base_dir, "data", "cache", "epg")
        os.makedirs(self._base_dir, exist_ok=True)
        self._cache = None

    def _get_cache(self):
        if self._cache is None:
            try:
                from diskcache import Cache
                self._cache = Cache(self._base_dir)
            except ImportError:
                logger.warning("diskcache不可用，EPG缓存禁用")
                return None
        return self._cache

    def get_epg_data(self, source_id: str) -> Optional[Dict[str, EpgChannel]]:
        cache = self._get_cache()
        if not cache:
            return None
        key = f"epg:{source_id}"
        entry = cache.get(key)
        if entry and time.time() - entry.get("timestamp", 0) < EPG_CACHE_TTL:
            return entry.get("data")
        return None

    def set_epg_data(self, source_id: str, data: Dict[str, EpgChannel]) -> None:
        cache = self._get_cache()
        if not cache:
            return
        serializable = {}
        for ch_id, epg_ch in data.items():
            serializable[ch_id] = {
                "channel_id": epg_ch.channel_id,
                "display_name": epg_ch.display_name,
                "programs": [p.to_dict() for p in epg_ch.programs],
            }
        cache.set(f"epg:{source_id}", {"data": serializable, "timestamp": time.time()})

    def get_epg_source_urls(self) -> Dict[str, str]:
        cache = self._get_cache()
        if not cache:
            return {}
        return cache.get("epg:source_urls", {})

    def set_epg_source_urls(self, urls: Dict[str, str]) -> None:
        cache = self._get_cache()
        if not cache:
            return
        cache.set("epg:source_urls", urls)

    def clear(self) -> None:
        cache = self._get_cache()
        if cache:
            cache.clear()
            logger.info("EPG缓存已清理")

    def get_stats(self) -> dict:
        cache = self._get_cache()
        if not cache:
            return {"enabled": False}
        return {
            "enabled": True,
            "size": cache.volume() if hasattr(cache, "volume") else 0,
            "count": len(cache) if hasattr(cache, "__len__") else 0,
        }
