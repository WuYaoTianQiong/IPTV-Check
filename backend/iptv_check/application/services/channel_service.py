import logging
from typing import List, Optional

from iptv_check.models.source import OnlineSource
from iptv_check.infra.network import HttpClient
from iptv_check.core.isp_detector import ISPDetector
from iptv_check.application.services.base import BaseService

logger = logging.getLogger(__name__)


class ChannelService(BaseService):
    def __init__(self, http_client: HttpClient):
        super().__init__(name="ChannelService")
        self._http_client = http_client
        self._isp_detector = ISPDetector(http_client)
        self.local_isp: str = "未知"
        self.online_sources: List[OnlineSource] = []

    async def _do_initialize(self) -> None:
        await self.detect_isp()

    async def _do_shutdown(self) -> None:
        pass

    async def detect_isp(self) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        self.local_isp = await loop.run_in_executor(None, self._isp_detector.detect_local_isp)
        return self.local_isp

    def load_online_sources(self, base_dir: str) -> None:
        import json
        import os
        try:
            sources_file = os.path.join(base_dir, "local_sources.json")
            if os.path.exists(sources_file):
                with open(sources_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.online_sources = [OnlineSource.from_dict(s) for s in data.get("sources", [])]
                logger.info("加载了 %d 个在线直播源", len(self.online_sources))
        except Exception as e:
            logger.warning("加载在线源失败: %s", e)

    def get_enabled_sources(self) -> List[OnlineSource]:
        return [s for s in self.online_sources if not s.disabled and s.is_isp_compatible(self.local_isp)]

    def get_source_by_id(self, source_id: str) -> Optional[OnlineSource]:
        for s in self.online_sources:
            if s.id == source_id:
                return s
        return None
