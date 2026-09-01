import logging
import asyncio
from typing import Dict, List, Optional

from iptv_check.models.epg_program import EpgChannel, EpgProgram
from iptv_check.models.source import OnlineSource
from iptv_check.core.epg_parser import EPGParser
from iptv_check.infra.epg_cache import EpgCacheManager
from iptv_check.infra.network import HttpClient

logger = logging.getLogger(__name__)


class EpgService:
    def __init__(self, http_client: HttpClient, cache: EpgCacheManager):
        self._http_client = http_client
        self._cache = cache
        self._epg_data: Dict[str, Dict[str, EpgChannel]] = {}
        self._is_loading = False

    async def load_epg_for_sources(self, sources: List[OnlineSource]) -> None:
        epg_sources = [s for s in sources if s.has_epg and not s.disabled]
        if not epg_sources:
            logger.info("没有需要加载EPG的源")
            return

        self._is_loading = True
        seen_urls = set()

        for source in epg_sources:
            cached = self._cache.get_epg_data(source.id)
            if cached:
                self._epg_data[source.id] = self._deserialize_epg(cached)
                logger.info("EPG缓存命中: %s (%d 频道)", source.name, len(cached))
                continue

            url = source.epg_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            try:
                resp = await asyncio.to_thread(self._http_client.get, url, timeout=(15, 30))
                if resp.status_code == 200:
                    epg = EPGParser.parse_xmltv(resp.text)
                    if epg:
                        self._epg_data[source.id] = epg
                        self._cache.set_epg_data(source.id, epg)
                        logger.info("EPG加载成功: %s (%d 频道)", source.name, len(epg))
                else:
                    logger.warning("EPG下载失败 %s: HTTP %d", source.name, resp.status_code)
            except Exception as e:
                logger.warning("EPG下载异常 %s: %s", source.name, e)

        self._is_loading = False

    async def refresh_epg(self, source: OnlineSource) -> bool:
        if not source.has_epg:
            return False
        try:
            resp = await asyncio.to_thread(self._http_client.get, source.epg_url, timeout=(15, 30))
            if resp.status_code == 200:
                epg = EPGParser.parse_xmltv(resp.text)
                if epg:
                    self._epg_data[source.id] = epg
                    self._cache.set_epg_data(source.id, epg)
                    logger.info("EPG刷新成功: %s", source.name)
                    return True
        except Exception as e:
            logger.warning("EPG刷新失败 %s: %s", source.name, e)
        return False

    def get_channel_epg(
        self,
        source_id: str,
        channel_name: str,
        tvg_id: str = "",
        tvg_name: str = "",
    ) -> Optional[EpgChannel]:
        epg = self._epg_data.get(source_id)
        if not epg:
            for sid, sedata in self._epg_data.items():
                matched = EPGParser.match_channel_to_epg(channel_name, tvg_id, tvg_name, sedata)
                if matched:
                    return matched
            return None
        return EPGParser.match_channel_to_epg(channel_name, tvg_id, tvg_name, epg)

    def get_current_programs(self, source_id: str = "") -> Dict[str, dict]:
        if source_id:
            epg = self._epg_data.get(source_id, {})
            return EPGParser.get_current_programs(epg)
        all_epg = {}
        for epg in self._epg_data.values():
            all_epg.update(epg)
        return EPGParser.get_current_programs(all_epg)

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @property
    def loaded_sources(self) -> List[str]:
        return list(self._epg_data.keys())

    def get_merged_epg(self) -> Dict[str, EpgChannel]:
        """合并所有已加载源的节目单，返回扁平的 channel_id -> EpgChannel。

        供导出（瘦身节目单）复用网页已加载的 EPG 源：若用户已在网页配置了自定义/区域 EPG 源，
        导出就基于它而不是默认的全量源，保持与网页内 EPG 匹配一致。未加载任何源时返回空字典。
        """
        merged: Dict[str, EpgChannel] = {}
        for epg in self._epg_data.values():
            merged.update(epg)
        return merged

    def get_stats(self) -> dict:
        total_channels = sum(len(epg) for epg in self._epg_data.values())
        total_programs = sum(
            sum(len(ch.programs) for ch in epg.values())
            for epg in self._epg_data.values()
        )
        return {
            "loaded_sources": len(self._epg_data),
            "total_channels": total_channels,
            "total_programs": total_programs,
            "is_loading": self._is_loading,
            "cache": self._cache.get_stats(),
        }

    @staticmethod
    def _deserialize_epg(data: dict) -> Dict[str, EpgChannel]:
        result = {}
        for ch_id, ch_data in data.items():
            programs = []
            for p_data in ch_data.get("programs", []):
                programs.append(EpgProgram(
                    title=p_data.get("title", ""),
                    start=p_data.get("start", ""),
                    stop=p_data.get("stop", ""),
                    desc=p_data.get("desc", ""),
                    category=p_data.get("category", ""),
                ))
            result[ch_id] = EpgChannel(
                channel_id=ch_data.get("channel_id", ch_id),
                display_name=ch_data.get("display_name", ""),
                programs=programs,
            )
        return result
