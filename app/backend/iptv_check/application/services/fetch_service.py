import asyncio
import time
import logging
import json
from typing import List, Optional, Callable, Awaitable
from datetime import datetime

from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import Index, text as sa_text

from iptv_check.models.channel import Channel
from iptv_check.infra.cn_time import cn_now

logger = logging.getLogger(__name__)


class FetchedChannelModel(SQLModel, table=True):
    __tablename__ = "fetched_channels"

    id: Optional[int] = Field(default=None, primary_key=True)
    url_key: str = Field(default="", index=True)
    name: str = Field(default="")
    url: str = Field(default="")
    channel_group: str = Field(default="")
    source_name: str = Field(default="")
    source_id: str = Field(default="")
    tvg_id: str = Field(default="")
    tvg_name: str = Field(default="")
    logo_url: str = Field(default="")
    language: str = Field(default="")
    country: str = Field(default="")
    is_radio: int = Field(default=0)
    resolution: str = Field(default="")
    fetched_at: datetime = Field(default_factory=cn_now)

    __table_args__ = (
        Index("ix_fc_url_key", "url_key"),
        Index("ix_fc_source_id", "source_id"),
    )


class FetchService:
    def __init__(self, event_store, broadcast_fn: Callable, session_factory, app_state=None):
        self._event_store = event_store
        self._broadcast_fn = broadcast_fn
        self._session_factory = session_factory
        self._app_state = app_state
        self._is_fetching = False
        self._fetched_count = 0
        self._total_sources = 0
        self._done_sources = 0

    @property
    def is_fetching(self) -> bool:
        return self._is_fetching

    @property
    def fetch_progress(self) -> dict:
        return {
            "is_fetching": self._is_fetching,
            "total_sources": self._total_sources,
            "done_sources": self._done_sources,
            "fetched_channels": self._fetched_count,
        }

    def get_fetched_channels(self, source_ids: Optional[List[str]] = None, limit: Optional[int] = None) -> List[Channel]:
        from iptv_check.core.parser import _translate_channel_name, _clean_name
        with self._session_factory() as session:
            stmt = select(FetchedChannelModel)
            if source_ids:
                stmt = stmt.where(FetchedChannelModel.source_id.in_(source_ids))
            if limit:
                stmt = stmt.limit(limit)
            rows = session.exec(stmt).all()
            channels = []
            for row in rows:
                cleaned = _clean_name(row.name) if row.name else row.name
                clean_name = _translate_channel_name(cleaned, row.tvg_name or "")
                ch = Channel(
                    name=cleaned,
                    url=row.url,
                    group=row.channel_group,
                    sources=[row.source_name] if row.source_name else [],
                    tvg_id=row.tvg_id,
                    tvg_name=row.tvg_name,
                    logo_url=row.logo_url,
                    language=row.language,
                    country=row.country,
                    is_radio=bool(row.is_radio),
                    resolution=row.resolution,
                    clean_name=clean_name,
                )
                channels.append(ch)
            return channels

    def has_fetched_channels(self) -> bool:
        with self._session_factory() as session:
            count = session.exec(
                sa_text("SELECT COUNT(*) FROM fetched_channels")
            ).scalar()
            return count > 0

    def count_fetched_channels(self, source_ids: Optional[List[str]] = None) -> int:
        with self._session_factory() as session:
            if source_ids:
                placeholders = ",".join([f":sid{i}" for i in range(len(source_ids))])
                params = {f"sid{i}": sid for i, sid in enumerate(source_ids)}
                count = session.exec(
                    sa_text(f"SELECT COUNT(DISTINCT url_key) FROM fetched_channels WHERE source_id IN ({placeholders})"), params=params
                ).scalar()
            else:
                count = session.exec(sa_text("SELECT COUNT(DISTINCT url_key) FROM fetched_channels")).scalar()
            return count or 0

    def clear_fetched_channels(self, source_ids: Optional[List[str]] = None):
        with self._session_factory() as session:
            if source_ids:
                placeholders = ",".join([f":sid{i}" for i in range(len(source_ids))])
                params = {f"sid{i}": sid for i, sid in enumerate(source_ids)}
                session.exec(sa_text(f"DELETE FROM fetched_channels WHERE source_id IN ({placeholders})"), params=params)
            else:
                session.exec(sa_text("DELETE FROM fetched_channels"))
            session.commit()

    async def start_fetch(self, online_source_ids: List[str], use_cache: bool = True, min_valid_rate: float = 0):
        from iptv_check.infra.config.settings import settings
        import aiohttp

        if self._is_fetching:
            raise RuntimeError("拉取正在进行中")

        self._is_fetching = True
        self._fetched_count = 0
        self._done_sources = 0

        sources_to_fetch = [src for src in self._app_state.online_sources if src.id in online_source_ids]

        if min_valid_rate > 0:
            from iptv_check.infra.persistence.event_store import EventStore
            health_map = self._get_source_health_map()
            before = len(sources_to_fetch)
            sources_to_fetch = [s for s in sources_to_fetch if self._should_fetch_source(s, health_map, min_valid_rate)]
            after = len(sources_to_fetch)
            if before != after:
                logger.info("[拉取] 智能筛选: %d → %d 个源 (有效率阈值=%.0f%%)", before, after, min_valid_rate * 100)
                await self._broadcast_fn("stage_changed", {"stage": "fetching", "message": f"智能筛选: {before} → {after} 个源 (有效率≥{min_valid_rate*100:.0f}%)"})
        self._total_sources = len(sources_to_fetch)
        logger.info("[拉取] 开始拉取 %d 个在线源", self._total_sources)

        await self._broadcast_fn("fetch_started", {"total_sources": self._total_sources})
        await self._broadcast_fn("stage_changed", {"stage": "fetching", "message": f"正在拉取在线源 (0/{self._total_sources})..."})

        self.clear_fetched_channels(source_ids=[s.id for s in sources_to_fetch])

        channel_sources = [s for s in sources_to_fetch if s.category.endswith("频道") or s.category.endswith("电台")]
        list_sources = [s for s in sources_to_fetch if not (s.category.endswith("频道") or s.category.endswith("电台"))]

        logger.info("[拉取] %d 个频道级 + %d 个列表级", len(channel_sources), len(list_sources))

        seen: set = set()
        results: List[Channel] = []
        raw_counts: List[int] = []
        lock = asyncio.Lock()

        direct_count = 0
        for src in channel_sources:
            url = src.url
            if src.mirror_url and self._app_state.local_isp not in src.isp:
                url = src.mirror_url
            is_radio = src.category.endswith("电台") or "广播" in src.category or "radio" in src.category.lower()
            group = src.category
            if is_radio:
                from iptv_check.application.services.check_service import CheckService
                region = CheckService._infer_region(src.name, src.url)
                if region:
                    group = f"{src.category}/{region}"
            ch = Channel(
                name=src.name,
                url=url,
                group=group,
                sources=[src.name],
                country=getattr(src, 'country', ''),
                is_radio=is_radio,
            )
            if ch.url_key not in seen:
                seen.add(ch.url_key)
                results.append(ch)
                direct_count += 1

        if direct_count:
            self._persist_direct_channels(channel_sources, seen)
            raw_counts.append(direct_count)
            self._fetched_count += direct_count
            logger.info("[拉取] 频道级源直接加载 %d 个频道", direct_count)

        if not list_sources:
            self._is_fetching = False
            self._done_sources = self._total_sources
            await self._broadcast_fn("fetch_completed", {"fetched_channels": len(results), "raw_channels": direct_count, "dedup_channels": 0})
            await self._broadcast_fn("stage_changed", {"stage": "fetch_done", "message": f"拉取完成，共获取 {len(results)} 个频道"})
            return

        sem = asyncio.Semaphore(settings.download_concurrency)

        async def fetch_one(src):
            from iptv_check.core.parser import PlaylistParser

            async with sem:
                fresh: List[Channel] = []
                try:
                    url = src.url
                    if src.mirror_url and self._app_state.local_isp not in src.isp:
                        url = src.mirror_url

                    cache_key = f"source:{src.id}"
                    cache = getattr(self._app_state, 'cache', None)

                    if use_cache and cache and cache.has(cache_key):
                        cached = cache.get(cache_key)
                        if cached:
                            new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, cached, src.name, src.category or "")
                            async with lock:
                                raw_counts.append(len(new_channels))
                            for ch in new_channels:
                                if ch.url_key not in seen:
                                    seen.add(ch.url_key)
                                    fresh.append(ch)
                            if not fresh:
                                logger.warning("[拉取] 在线源 %s 缓存解析出0个频道，重新下载", src.name)
                                fresh = []
                                if cache.has(cache_key):
                                    pass
                            else:
                                logger.info("[拉取] 在线源 %s 缓存命中, %d 个频道", src.name, len(fresh))
                            if fresh:
                                async with lock:
                                    results.extend(fresh)
                                    self._fetched_count += len(fresh)
                                    self._done_sources += 1
                                    await asyncio.to_thread(self._persist_batch, fresh, src)
                                    await self._broadcast_fn("stage_changed", {"stage": "fetching", "message": f"正在拉取在线源 ({self._done_sources}/{self._total_sources})... 已获取 {self._fetched_count} 个频道"})
                                    await self._broadcast_fn("fetch_progress", self.fetch_progress)
                                return

                    timeout = aiohttp.ClientTimeout(
                        total=settings.download_timeout,
                        connect=10,
                        sock_read=settings.download_timeout,
                    )
                    async with self._app_state._async_session.get(url, timeout=timeout, ssl=False) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            new_channels = await asyncio.to_thread(PlaylistParser.parse_m3u_content, text, src.name, src.category or "")
                            if use_cache and text and cache:
                                await asyncio.to_thread(cache.set, cache_key, text, 6 * 3600)
                            async with lock:
                                raw_counts.append(len(new_channels))
                            for ch in new_channels:
                                if ch.url_key not in seen:
                                    seen.add(ch.url_key)
                                    fresh.append(ch)
                            if fresh:
                                logger.info("[拉取] 在线源 %s 下载完成, %d 个频道", src.name, len(fresh))
                            else:
                                logger.info("[拉取] 在线源 %s 下载完成, 0 个新频道", src.name)
                        else:
                            logger.warning("[拉取] 在线源 %s HTTP %d", src.name, resp.status)
                except Exception as e:
                    logger.warning("[拉取] 在线源 %s 失败: %s", src.name, e)

                if fresh:
                    async with lock:
                        results.extend(fresh)
                        self._fetched_count += len(fresh)
                        await asyncio.to_thread(self._persist_batch, fresh, src)

                async with lock:
                    self._done_sources += 1
                    await self._broadcast_fn("stage_changed", {"stage": "fetching", "message": f"正在拉取在线源 ({self._done_sources}/{self._total_sources})... 已获取 {self._fetched_count} 个频道"})
                    await self._broadcast_fn("fetch_progress", self.fetch_progress)

        await asyncio.gather(*[fetch_one(src) for src in list_sources])

        self._is_fetching = False
        total_raw = sum(raw_counts)
        total_dedup = len(results)
        if total_raw != total_dedup:
            logger.info("[拉取] 完成, 去重前 %d 个频道 → 去重后 %d 个频道 (跨源重复 %d 个)", total_raw, total_dedup, total_raw - total_dedup)
        else:
            logger.info("[拉取] 完成, 共 %d 个频道 (无跨源重复)", total_dedup)
        await self._broadcast_fn("fetch_completed", {"fetched_channels": len(results), "raw_channels": total_raw, "dedup_channels": total_raw - len(results)})
        if total_raw != total_dedup:
            await self._broadcast_fn("stage_changed", {"stage": "fetch_done", "message": f"拉取完成，共获取 {len(results)} 个唯一频道（去重前 {total_raw}，跨源重复 {total_raw - len(results)} 个）"})
        else:
            await self._broadcast_fn("stage_changed", {"stage": "fetch_done", "message": f"拉取完成，共获取 {len(results)} 个频道"})

    def _persist_direct_channels(self, channel_sources, seen: set):
        with self._session_factory() as session:
            for src in channel_sources:
                url = src.url
                if src.mirror_url:
                    url = src.mirror_url
                url_key = Channel(name=src.name, url=url).url_key
                if url_key in seen:
                    row = FetchedChannelModel(
                        url_key=url_key,
                        name=src.name,
                        url=url,
                        channel_group=src.category,
                        source_name=src.name,
                        source_id=src.id,
                        country=getattr(src, 'country', ''),
                    )
                    session.add(row)
            session.commit()

    def _persist_batch(self, channels: List[Channel], source):
        with self._session_factory() as session:
            for ch in channels:
                row = FetchedChannelModel(
                    url_key=ch.url_key,
                    name=ch.name,
                    url=ch.url,
                    channel_group=ch.group,
                    source_name=source.name,
                    source_id=source.id,
                    tvg_id=ch.tvg_id,
                    tvg_name=ch.tvg_name,
                    logo_url=ch.logo_url,
                    language=ch.language,
                    country=ch.country,
                    is_radio=1 if ch.is_radio else 0,
                    resolution=ch.resolution,
                )
                session.add(row)
            session.commit()

    def _get_source_health_map(self) -> dict:
        health = {}
        try:
            health_data = self._app_state._health_checker.to_dict()
            for src_id, info in health_data.get("sources", {}).items():
                health[src_id] = info.get("valid_rate", 0)
        except Exception:
            pass
        return health

    @staticmethod
    def _should_fetch_source(source, health_map: dict, min_valid_rate: float) -> bool:
        rate = health_map.get(source.id, -1)
        if rate < 0:
            return True
        return rate >= min_valid_rate
