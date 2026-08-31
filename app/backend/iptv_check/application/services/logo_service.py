import logging
import asyncio
import re
from typing import Optional, Dict, List

from iptv_check.models.source import OnlineSource
from iptv_check.infra.logo_cache import LogoCacheManager
from iptv_check.infra.network import HttpClient

logger = logging.getLogger(__name__)

_CHANNEL_NAME_MAPPINGS = {
    "cctv1": "CCTV1", "cctv2": "CCTV2", "cctv3": "CCTV3", "cctv4": "CCTV4",
    "cctv5": "CCTV5", "cctv6": "CCTV6", "cctv7": "CCTV7", "cctv8": "CCTV8",
    "cctv9": "CCTV9", "cctv10": "CCTV10", "cctv11": "CCTV11", "cctv12": "CCTV12",
    "cctv13": "CCTV13", "cctv14": "CCTV14", "cctv15": "CCTV15", "cctv16": "CCTV16",
    "cctv17": "CCTV17",
}


class LogoService:
    def __init__(self, http_client: HttpClient, cache: LogoCacheManager):
        self._http_client = http_client
        self._cache = cache
        self._logo_base_urls: Dict[str, str] = {}

    def register_logo_sources(self, sources: List[OnlineSource]) -> None:
        for source in sources:
            if source.has_logo_support and not source.disabled:
                self._logo_base_urls[source.id] = source.logo_base_url

    async def get_logo(
        self,
        channel_name: str,
        tvg_logo: str = "",
        source_id: str = "",
    ) -> Optional[bytes]:
        if tvg_logo:
            logo_data = await self._fetch_logo_from_url(tvg_logo)
            if logo_data:
                self._cache.set_logo(channel_name, logo_data)
                return logo_data

        cached = self._cache.get_logo(channel_name)
        if cached:
            return cached

        logo_data = await self._search_logo_from_bases(channel_name, source_id)
        if logo_data:
            self._cache.set_logo(channel_name, logo_data)
            return logo_data

        return None

    async def _fetch_logo_from_url(self, url: str) -> Optional[bytes]:
        url_cached = self._cache.get_logo_url_cache(url)
        if url_cached:
            return url_cached

        try:
            resp = await asyncio.to_thread(self._http_client.get, url, timeout=(5, 10))
            if resp.status_code == 200 and resp.content:
                content_type = resp.headers.get("content-type", "")
                if any(t in content_type for t in ["image", "octet-stream"]) or len(resp.content) > 100:
                    self._cache.set_logo_url_cache(url, resp.content)
                    return resp.content
        except Exception as e:
            logger.debug("台标URL下载失败 %s: %s", url[:50], e)
        return None

    async def _search_logo_from_bases(self, channel_name: str, source_id: str = "") -> Optional[bytes]:
        clean_name = self._normalize_channel_name(channel_name)
        if not clean_name:
            return None

        search_urls = []

        if source_id and source_id in self._logo_base_urls:
            base = self._logo_base_urls[source_id]
            search_urls.append(f"{base}{clean_name}.png")

        for sid, base in self._logo_base_urls.items():
            if sid != source_id:
                search_urls.append(f"{base}{clean_name}.png")

        for url in search_urls:
            logo = await self._fetch_logo_from_url(url)
            if logo:
                return logo

        return None

    @staticmethod
    def _normalize_channel_name(name: str) -> str:
        if not name:
            return ""
        clean = re.sub(r"[^\w\u4e00-\u9fff]", "", name)
        lower = clean.lower()

        for key, mapped in _CHANNEL_NAME_MAPPINGS.items():
            if key in lower:
                return mapped

        if clean:
            return clean
        return name.strip()

    async def batch_download_logos(
        self,
        channels: List[dict],
        source_id: str = "",
        max_concurrent: int = 10,
    ) -> Dict[str, bool]:
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _download_one(ch_info: dict):
            async with semaphore:
                name = ch_info.get("name", "")
                tvg_logo = ch_info.get("logo_url", "")
                logo = await self.get_logo(name, tvg_logo, source_id)
                results[name] = logo is not None

        tasks = [_download_one(ch) for ch in channels]
        await asyncio.gather(*tasks, return_exceptions=True)

        success = sum(1 for v in results.values() if v)
        logger.info("批量台标下载: %d/%d 成功", success, len(results))
        return results

    def get_stats(self) -> dict:
        return self._cache.get_stats()
