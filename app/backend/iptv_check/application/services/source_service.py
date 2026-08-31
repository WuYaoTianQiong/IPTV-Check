"""
Source Service
Manages online source lifecycle, downloading, and ISP matching.
Extracted from AppState to follow Single Responsibility Principle.
"""

import asyncio
import logging
from typing import List, Optional

from iptv_check.application.services.base import BaseService
from iptv_check.infra.repository.source_repo import SourceRepository
from iptv_check.infra.cache.multi_tenant import MultiTenantCacheManager
from iptv_check.infra.network import HttpClient
from iptv_check.infra.event_bus import event_bus, Events
from iptv_check.models.source import OnlineSource
from iptv_check.core.parser import PlaylistParser

logger = logging.getLogger(__name__)


class SourceService(BaseService):
    """
    Service for managing online IPTV sources.
    Handles source loading, downloading, parsing, and ISP matching.
    """

    def __init__(
        self,
        source_repo: SourceRepository,
        cache_manager: MultiTenantCacheManager,
        http_client: HttpClient,
    ):
        super().__init__("SourceService")
        self._source_repo = source_repo
        self._cache_manager = cache_manager
        self._http_client = http_client
        self._local_isp: str = "未知"

    async def _do_initialize(self) -> None:
        """Initialize source service."""
        self._logger.info("SourceService initialized with %d sources", self._source_repo.count())

    async def _do_shutdown(self) -> None:
        """Shutdown source service."""
        self._logger.info("SourceService shutdown complete")

    def get_all_sources(self, enabled_only: bool = True) -> List[OnlineSource]:
        """Get all online sources."""
        return self._source_repo.get_all(enabled_only)

    def get_source_by_id(self, source_id: str) -> Optional[OnlineSource]:
        """Get source by ID."""
        return self._source_repo.get_by_id(source_id)

    def get_sources_by_category(self, category: str) -> List[OnlineSource]:
        """Get sources by category."""
        return self._source_repo.get_by_category(category)

    def get_categories(self) -> List[str]:
        """Get all source categories."""
        return self._source_repo.get_categories()

    def set_local_isp(self, isp: str) -> None:
        """Set local ISP for source matching."""
        self._local_isp = isp
        self._logger.info("Local ISP set to: %s", isp)

    def get_isp_compatible_sources(self) -> List[OnlineSource]:
        """Get sources compatible with local ISP."""
        return [
            s for s in self.get_all_sources()
            if s.is_isp_compatible(self._local_isp)
        ]

    async def download_source(self, source: OnlineSource, force_refresh: bool = False) -> str:
        """
        Download M3U content from source.
        Uses cache unless force_refresh is True.
        Returns M3U content string.
        """
        cache_key = f"source:{source.id}"

        if not force_refresh and self._cache_manager.has("detection", cache_key):
            cached = self._cache_manager.get("detection", cache_key)
            if cached:
                self._logger.info("Cache hit for source: %s", source.name)
                return cached

        try:
            url = source.url
            if source.mirror_url and not source.is_isp_compatible(self._local_isp):
                url = source.mirror_url
                self._logger.info("Using mirror URL for: %s", source.name)

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self._http_client.get(url, timeout=(15, 15))
            )

            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")

            content = resp.text
            self._cache_manager.set("detection", cache_key, content, ttl=24 * 3600)
            self._logger.info("Downloaded source: %s (%d bytes)", source.name, len(content))

            event_bus.emit(Events.SOURCE_DOWNLOADED, source_id=source.id, source_name=source.name)
            return content

        except Exception as e:
            self._logger.error("Failed to download source %s: %s", source.name, e)
            event_bus.emit(Events.SOURCE_DOWNLOAD_ERROR, source_id=source.id, error=str(e))
            raise

    async def download_multiple_sources(
        self,
        source_ids: List[str],
        force_refresh: bool = False,
    ) -> dict[str, str]:
        """
        Download multiple sources concurrently.
        Returns dict of {source_id: m3u_content}.
        """
        sources = [
            s for s in self.get_all_sources()
            if s.id in source_ids
        ]

        async def download_one(source: OnlineSource) -> tuple[str, str]:
            try:
                content = await self.download_source(source, force_refresh)
                return (source.id, content)
            except Exception as e:
                self._logger.warning("Download failed for %s: %s", source.name, e)
                return (source.id, "")

        tasks = [download_one(s) for s in sources]
        results = await asyncio.gather(*tasks)

        return {sid: content for sid, content in results if content}

    def parse_source_content(self, content: str, source_name: str) -> list:
        """Parse M3U content and return list of Channel objects."""
        return PlaylistParser.parse_m3u_content(content, source_name)

    async def download_and_parse(
        self,
        source_id: str,
        force_refresh: bool = False,
    ) -> list:
        """Download and parse a single source."""
        source = self.get_source_by_id(source_id)
        if not source:
            raise ValueError(f"Source not found: {source_id}")

        content = await self.download_source(source, force_refresh)
        return self.parse_source_content(content, source.name)

    def update_source(self, source_id: str, update_data: dict) -> Optional[OnlineSource]:
        """Update source configuration."""
        return self._source_repo.update_source(source_id, update_data)

    def add_source(self, source: OnlineSource) -> None:
        """Add a new source."""
        self._source_repo.add_source(source)

    def delete_source(self, source_id: str) -> bool:
        """Delete a source."""
        return self._source_repo.delete_source(source_id)
