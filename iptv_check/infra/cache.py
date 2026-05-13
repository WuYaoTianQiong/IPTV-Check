import json
import time
import logging
import os
from typing import Optional

from iptv_check.config import CACHE_FILE, CACHE_EXPIRY_HOURS

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self._cache_path = os.path.join(self._base_dir, CACHE_FILE)
        self._cache: dict = {}
        self.load()

    def load(self):
        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                now = time.time()
                expired = [k for k, v in self._cache.items() if now - v.get("timestamp", 0) > CACHE_EXPIRY_HOURS * 3600]
                for k in expired:
                    del self._cache[k]
                if expired:
                    self.save()
                logger.info("加载缓存: %d 条记录", len(self._cache))
            except Exception as e:
                logger.warning("加载缓存失败: %s", e)
                self._cache = {}

    def save(self):
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存缓存失败: %s", e)

    def get(self, url_key: str) -> Optional[dict]:
        return self._cache.get(url_key)

    def set(self, url_key: str, data: dict):
        self._cache[url_key] = data

    def has(self, url_key: str) -> bool:
        return url_key in self._cache

    def __contains__(self, url_key: str) -> bool:
        return url_key in self._cache

    def __getitem__(self, url_key: str) -> dict:
        return self._cache[url_key]
