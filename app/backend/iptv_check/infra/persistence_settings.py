import json
import os
import logging
from typing import Any, Optional

from iptv_check.infra.config.settings import SETTINGS_FILE

logger = logging.getLogger(__name__)


class SettingsManager:
    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self._path = os.path.join(self._base_dir, SETTINGS_FILE)
        self._settings: dict = {}
        self.load()

    def load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
                logger.info("加载用户设置: %d 条", len(self._settings))
            except Exception as e:
                logger.warning("加载用户设置失败: %s", e)
                self._settings = {}

    def save(self):
        try:
            # 原子写：先写临时文件再 os.replace，避免崩溃导致设置文件损坏
            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception as e:
            logger.warning("保存用户设置失败: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        self._settings[key] = value
        self.save()

    @property
    def all(self) -> dict:
        return self._settings.copy()
