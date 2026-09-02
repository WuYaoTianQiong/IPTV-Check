import logging
import asyncio
import time
from typing import Dict, List, Optional

from iptv_check.models.epg_program import EpgChannel, EpgProgram
from iptv_check.models.source import OnlineSource
from iptv_check.core.epg_parser import EPGParser
from iptv_check.infra.epg_cache import EpgCacheManager
from iptv_check.infra.network import HttpClient
from iptv_check.infra.exporter import _FANMINGMING_EPG_URL

logger = logging.getLogger(__name__)

# 内置默认全量 EPG（未配 epg_url 的源也能自动匹配到节目单）。
# 与 exporter 的瘦身 EPG 导出共用同一数据源，保证播放器/导出匹配一致。
_DEFAULT_EPG_URLS = [_FANMINGMING_EPG_URL]
# 默认 EPG 拉取失败后的冷却时间：1 小时内不重复拉取大文件
_DEFAULT_EPG_RETRY_AFTER = 3600


class EpgService:
    def __init__(self, http_client: HttpClient, cache: EpgCacheManager):
        self._http_client = http_client
        self._cache = cache
        self._epg_data: Dict[str, Dict[str, EpgChannel]] = {}
        self._is_loading = False
        # 内置默认全量 EPG 兜底（按需懒加载，未配 epg_url 的源也能匹配到节目单）
        self._default_epg: Optional[Dict[str, EpgChannel]] = None
        self._default_lock = asyncio.Lock()
        self._default_loading_task: Optional[asyncio.Task] = None
        self._default_failed_at: float = 0.0

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

    def ensure_default_epg(self) -> bool:
        """按需触发内置默认全量 EPG 加载（不阻塞调用方）。

        - 已就绪（内存/磁盘缓存命中）返回 True，调用方可立即匹配；
        - 未就绪则启动后台加载任务并返回 False，调用方返回 loading 状态，
          前端稍后自动重查即可命中（首次下载约几秒，之后走缓存毫秒级）。
        拉取失败带 1 小时冷却，避免每次查询都重复下载几十 MB 大文件。
        """
        if self._default_epg is not None:
            return True
        if self._default_failed_at and time.time() - self._default_failed_at < _DEFAULT_EPG_RETRY_AFTER:
            return False
        if self._default_loading_task is None or self._default_loading_task.done():
            self._default_loading_task = asyncio.create_task(self._load_default_epg())
        return False

    async def _load_default_epg(self) -> bool:
        if self._default_epg is not None:
            return True
        async with self._default_lock:
            if self._default_epg is not None:
                return True
            cached = self._cache.get_epg_data("__default__")
            if cached:
                self._default_epg = self._deserialize_epg(cached)
                logger.info("默认全量EPG缓存命中: %d 频道", len(self._default_epg))
                return True
            for url in _DEFAULT_EPG_URLS:
                try:
                    resp = await asyncio.to_thread(self._http_client.get, url, timeout=(30, 180))
                    if resp.status_code == 200:
                        epg = EPGParser.parse_xmltv(resp.text)
                        if epg:
                            self._default_epg = epg
                            self._cache.set_epg_data("__default__", epg)
                            logger.info("默认全量EPG加载成功: %s (%d 频道)", url, len(epg))
                            return True
                        logger.warning("默认全量EPG解析为空: %s", url)
                    else:
                        logger.warning("默认全量EPG下载失败 %s: HTTP %d", url, resp.status_code)
                except Exception as e:
                    logger.warning("默认全量EPG加载异常 %s: %s", url, e)
            self._default_failed_at = time.time()
            return False

    def get_channel_epg(
        self,
        source_id: str,
        channel_name: str,
        tvg_id: str = "",
        tvg_name: str = "",
        include_default: bool = False,
    ) -> Optional[EpgChannel]:
        if source_id:
            epg = self._epg_data.get(source_id)
            matched = EPGParser.match_channel_to_epg(channel_name, tvg_id, tvg_name, epg) if epg else None
            if matched:
                return matched
        else:
            for sid, sedata in self._epg_data.items():
                matched = EPGParser.match_channel_to_epg(channel_name, tvg_id, tvg_name, sedata)
                if matched:
                    return matched
        if include_default and self._default_epg:
            matched = EPGParser.match_channel_to_epg(channel_name, tvg_id, tvg_name, self._default_epg)
            if matched:
                return matched
        return None

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
            "default_epg_channels": len(self._default_epg) if self._default_epg else 0,
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
