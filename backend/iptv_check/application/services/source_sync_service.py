import asyncio
import hashlib
import json
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Literal, Optional

import aiohttp

from iptv_check.models.source import OnlineSource
from iptv_check.infra.cn_time import cn_tz

logger = logging.getLogger(__name__)

_UPDATABLE_FIELDS = [
    "url", "mirror_url", "name", "description", "category",
    "isp", "protocol", "quality_rating", "epg_url",
    "logo_base_url", "update_frequency", "features",
]

_LOCAL_ONLY_FIELDS = [
    "channel_count", "cache_filename", "last_updated", "disabled",
]

_DEFAULT_REMOTE_CONFIG_URLS = [
    "https://gitee.com/why006/TV/raw/master/source.json",
    "https://gitee.com/why006/TV/raw/master/output/result.m3u",
    "https://gitproxy.click/https://raw.githubusercontent.com/Guovin/iptv-api/gd/source.json",
    "https://gitproxy.click/https://raw.githubusercontent.com/fanmingming/live/main/tv/source.json",
    "https://gitproxy.click/https://raw.githubusercontent.com/fanmingming/live/main/radio/source.json",
    "https://iprd-org.github.io/iprd/site_data/all_stations.m3u",
]

_CATEGORY_RULES = [
    # 国内外语频道（CGTN/CCTV外语）归属国内，必须优先于"国际频道"规则匹配（REQ-DOMESTIC-002）
    ("央视频道", r"CCTV|央视|CGTN|China\s*Global\s*Television"),
    ("卫视频道", r"卫视"),
    ("地方频道", r"广东|浙江|江苏|湖南|北京|上海|深圳|山东|河南|河北|湖北|四川|重庆|天津|辽宁|陕西|福建|安徽|江西|山西|黑龙江|吉林|甘肃|贵州|云南|海南|青海|西藏|宁夏|新疆|内蒙古|内蒙|广西|香港|澳门|台湾|苏州|南京|无锡|常州|南通|徐州|扬州|镇江|泰州|盐城|淮安|连云港|宿迁|哈尔滨|南宁|蒙语"),
    ("4K超清", r"4K|超清|超高清|UHD|HDR"),
    ("教育频道", r"CETV|教育|学习|课堂|学校|课程|University|Educat"),
    ("体育频道", r"体育|CCTV-5|五星|劲爆|足球|篮球|高尔夫|网球|乒乓球|羽毛球|赛车|综合体育|ESPN|Fox\s*Sports|beIN\s*Sports|Sky\s*Sports|NBA\s*TV|NFL\s*Network|DeporTV|Racing"),
    ("电影频道", r"电影|CHC|淘剧场|天映|私人影院|星空卫视|动作|悬疑|剧情|HBO|Cinemax|AMC|IFC|Showtime|Starz|Cine\.AR"),
    ("影视点播", r"寒战|拆弹|囧途|倩女幽魂|药神|武侠|影剧|影院|影视|剧场|剧集|追剧|热播|热播剧|Canal\s*de\s*Cine|Película|Película|港剧"),
    ("少儿动画", r"少儿|动画|卡通|动漫|优漫|金鹰|卡酷|炫动|哈哈|亲子|益智|Nick|Cartoon\s*Network|Disney\s*Channel|Baby\s*TV|Pakapaka|Disney\s*Junior|Disney\s*XD|Boomerang"),
    ("纪录片", r"纪实|纪录|探索|发现|地理|自然|历史|人文|科学|动物|旅游|Discovery|National\s*Geographic|History\s*Channel|Animal\s*Planet|Encuentro|Nat\s*Geo\s*Wild|Crime\s*&\s*Investigation|History\s*\d"),
    ("音乐频道", r"音乐|CCTV-15|歌曲|MV|演唱会|流行|MTV|VH1|Music\s*TV|1Mus"),
    ("国际频道", r"凤凰|TVB|翡翠|明珠|无线|纬来|东森|中天|三立|民视|公视|NHK|KBS|MBC|SBS|Arirang|BBC\s*World|CNN\s*International|France\s*24|DW\s*TV|Al\s*Jazeera|RT\s*News|CNA|TV5\s*Monde|Euronews"),
    ("国际频道", r"Argentina|Azerbaijan|Albania|Austria|Australia|Belarus|Brazil|Canada|Colombia|Czech|Denmark|Egypt|Estonia|Finland|France|Georgia|Germany|Greece|Hungary|Iceland|India|Iran|Iraq|Ireland|Israel|Italy|Japan|Kazakhstan|Kenya|Latvia|Lebanon|Lithuania|Luxembourg|Macao|Malaysia|Mexico|Moldova|Mongolia|Morocco|Netherlands|New\s*Zealand|Nigeria|Norway|Pakistan|Peru|Philippines|Poland|Portugal|Romania|Russia|Saudi|Serbia|Singapore|Slovakia|South\s*Africa|South\s*Korea|Spain|Sri\s*Lanka|Sweden|Switzerland|Thailand|Turkey|UAE|UK|Ukraine|Uruguay|USA|Uzbekistan|Venezuela|Vietnam|China\s*TV|Arab|Asian|European|American|Latin|African"),
    ("国际频道", r"Apollon|Vizion|Tropoja|Syri|Kanali|Andorra|Todo Noticias|Televisión Pública|Barricada|Noticias|Armenia|ARB|Azad|AZTV|Baku|CBC|Dünya|İctimai|İdman|Kanal S|Mədəniyyət|Real TV|Space TV|Xəzər|Беларусь|ОНТ|СТВ|8 Kanal|R9|oe24|W24|P3TV|RTV|Servus TV|ORF|Tirol|Urbana|Comarca|El Trece|El Nueve|Telefe|A24|Aunar|Tec TV|Canal 26|Canal E|TV Universidad|ABC|TVSN|ABC Me|M4TV|9Go|9Life|9Rush|C5N"),
    ("国际频道", r"^Rai\s*[1-9]|^La\s*[1-9]\b|TVE|Arte|ZDF|RTL|Sat\.1|ProSieben|TF1|M6|C8|BFM TV|NPO\s*[1-9]|SVT[1-9]|NRK[1-9]|DR[1-9]|YLE TV|MTV3|TV\s*2\b|TV4\b|Prva TV|HRT|Nova TV|BNT|bTV|Pro TV|Antena|TVR|Pink|RTCG|MRT|Sitel|BHRT|FTV|OBN|TVCG|RTS\b|Alpo TV|Report TV|Kentron|5TV\b|Səhiyyə|TMB\b|Azərbaycan|TMB Azərbaycan"),
    ("广播电台", r"广播|Radio|FM|AM|调频|中波|频率|之声|新闻广播|交通广播|音乐广播|经济广播|综合广播|文艺广播|故事广播|环球广播|世界广播|BBC\s*Radio|NPR|WNYC|KEXP"),
    ("新闻频道", r"新闻|资讯|News|头条|报道|直播新闻|Noticias|IP Noticias|El Destape|Crónica|LN\+|ARB 24|A24|CNBC|Bloomberg|Sky\s*News"),
    ("天气频道", r"天气|气象|Weather"),
    ("游戏电竞", r"游戏|电竞|Gaming|Esport|熊猫|虎牙|斗鱼|Ginx|ESL\s*TV"),
    ("宗教频道", r"EWTN|Daystar|TBN|God\s*TV|Christian|Gospel|Faith"),
    ("购物频道", r"QVC|HSN|Shop\s*TV|Home\s*Shop|Shopping|Infomercials"),
    ("生活频道", r"生活|时尚|Fashion|Lifestyle|美食|Food|烹饪|Cooking|TLC|HGTV|Motor\s*Trend|Auto\s*Motor"),
    ("综合频道", r"综合|通用|General|Telemax|Net TV|VIP\s*HD"),
]

_INVALID_NAME_KEYWORDS = [
    r"源$", r"源\s*$", r"m3u$", r"\.m3u$", r"\.m3u8$", r"ipv[46]源",
    "全球精选", "中东频道", "东亚频道", "南亚频道", "欧洲频道", "拉美频道", "俄语频道",
    "伊朗频道", "古巴频道", "朝鲜频道", "中国频道", "iptv-org",
    "支持作者", "中国交通",
    r"^Test\s", r"^Placeholder", r"^Empty$", r"^No\s+Signal$", r"^Tech\s+Storm$",
    r"^\d{4}-\d{2}-\d{2}",
    r"直播中国",
    r"范明明", r"vbskycn", r"Guovin", r"Kimentanm", r"suxuang", r"zbefine", r"YueChan",
]

_INVALID_GROUP_KEYWORDS = [
    "更新时间", "更新", "update", "date", "time", "last",
    "ALL", "all", "OTHER", "other",
    "央视高清", "4K频道", "IPTV",
    # 2026-05-17: 移除"国内电视""国际电视""国内""国际""电视"
    # 原因：过于宽泛导致合法国外频道被误杀（REQ-FILTER-004）
    # 现在合法频道应通过 _CATEGORY_RULES 分类而非被过滤丢弃
]

_IPTV_ORG_EPG_URL = "https://iptv-org.github.io/epg.xml"

def _classify_channel(name: str, group: Optional[str] = None) -> Optional[str]:
    """根据频道名称和M3U group进行分类，返回标准化分类名"""
    import re
    
    for pattern in _INVALID_NAME_KEYWORDS:
        if re.search(pattern, name, re.IGNORECASE):
            return None
    
    combined = f"{name} {group or ''}"
    
    for category, pattern in _CATEGORY_RULES:
        if re.search(pattern, combined, re.IGNORECASE):
            return category
    
    if group:
        cleaned = group.strip()
        if cleaned and not any(kw.lower() in cleaned.lower() for kw in _INVALID_GROUP_KEYWORDS):
            return cleaned
    
    return "其他频道"

UrlSource = Literal["api_param", "env_var", "config_file", "default"]

_PLACEHOLDER_PATTERNS = ("your-username", "example.com")

_SENSITIVE_PARAM_KEYS = ("token", "key", "secret", "password", "apikey", "access_key")


@dataclass
class ResolvedUrls:
    urls: List[str]
    source: Optional[str]
    effective_urls: List[str]


class SourceSyncResult:
    def __init__(self):
        self.success: bool = False
        self.upstream_count: int = 0
        self.local_count: int = 0
        self.added: int = 0
        self.updated: int = 0
        self.removed: int = 0
        self.unchanged: int = 0
        self.errors: List[str] = []
        self.synced_at: Optional[str] = None
        self.remote_fetched: bool = False
        self.remote_url_used: Optional[str] = None
        self.url_source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "upstream_count": self.upstream_count,
            "local_count": self.local_count,
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "synced_at": self.synced_at,
            "remote_fetched": self.remote_fetched,
            "remote_url_used": self.remote_url_used,
            "url_source": self.url_source,
        }


class SourceSyncProgress:
    def __init__(self):
        self.is_syncing: bool = False
        self.stage: str = ""
        self.current_url_index: int = 0
        self.total_urls: int = 0
        self.current_url_label: str = ""
        self.fetched_channel_count: int = 0
        self.added: int = 0
        self.updated: int = 0
        self.unchanged: int = 0
        self.started_at: Optional[float] = None
        self.elapsed_seconds: float = 0.0
        self.eta_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "is_syncing": self.is_syncing,
            "stage": self.stage,
            "current_url_index": self.current_url_index,
            "total_urls": self.total_urls,
            "current_url_label": self.current_url_label,
            "fetched_channel_count": self.fetched_channel_count,
            "added": self.added,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else None,
        }


class SourceSyncService:

    def __init__(
        self,
        data_dir: str,
        http_session: Optional[aiohttp.ClientSession] = None,
        env_remote_config_urls: Optional[List[str]] = None,
        source_store: Optional["SourceStore"] = None,
        broadcast_fn: Optional[Callable] = None,
    ):
        self._data_dir = data_dir
        self._local_sources_path = os.path.join(data_dir, "local_sources.json")
        self._http_session = http_session
        self._env_remote_config_urls = env_remote_config_urls or []
        self._last_result: Optional[SourceSyncResult] = None
        self._is_syncing: bool = False
        self._last_resolved_urls: Optional[ResolvedUrls] = None
        self._source_store = source_store
        self._broadcast_fn = broadcast_fn
        self._progress = SourceSyncProgress()
        self._sync_task: Optional[asyncio.Task] = None

    def _load_local_sources_raw(self) -> dict:
        if self._source_store:
            sources = self._source_store.load_all()
            return {"sources": [s.to_dict() for s in sources]}
        if not os.path.exists(self._local_sources_path):
            return {"sources": []}
        try:
            with open(self._local_sources_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "sources" in data:
                return data
            return {"sources": data if isinstance(data, list) else []}
        except Exception as e:
            logger.error("加载本地源失败: %s", e)
            return {"sources": []}

    def _load_local_sources(self) -> List[OnlineSource]:
        if self._source_store:
            return self._source_store.load_all()
        data = self._load_local_sources_raw()
        return [OnlineSource.from_dict(s) for s in data.get("sources", [])]

    def _save_local_sources(self, sources: List[OnlineSource], extra_meta: Optional[dict] = None) -> None:
        if self._source_store:
            self._source_store.save_all(sources)
            return
        existing_meta = self._load_local_sources_raw()
        data = {
            "sources": [s.to_dict() for s in sources],
            "last_synced": datetime.now(cn_tz()).isoformat(),
        }
        for key in ("remote_config_url", "version"):
            if key in existing_meta:
                data[key] = existing_meta[key]
        if extra_meta:
            data.update(extra_meta)
        os.makedirs(os.path.dirname(self._local_sources_path), exist_ok=True)
        with open(self._local_sources_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("保存 %d 个源到 %s", len(sources), self._local_sources_path)

    def _get_remote_config_url(self) -> Optional[str]:
        meta = self._load_local_sources_raw()
        url = meta.get("remote_config_url")
        if url and self._validate_url(url):
            return url
        elif url:
            logger.debug("local_sources.json 中 remote_config_url 无效，已跳过")
        custom_path = os.path.join(self._data_dir, "upstream_sources.json")
        if os.path.exists(custom_path):
            try:
                with open(custom_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                url = data.get("remote_config_url")
                if url and self._validate_url(url):
                    return url
                elif url:
                    logger.debug("upstream_sources.json 中 remote_config_url 无效，已跳过")
            except Exception as e:
                logger.debug("加载 upstream_sources.json 失败: %s", e)
        return None

    @staticmethod
    def _validate_url(url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        if not (url.startswith("http://") or url.startswith("https://")):
            return False
        for placeholder in _PLACEHOLDER_PATTERNS:
            if placeholder in url:
                return False
        return True

    @staticmethod
    def _redact_url_for_log(url: str) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
            if not parsed.query:
                return url
            params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            redacted = []
            for k, v in params:
                if k.lower() in _SENSITIVE_PARAM_KEYS:
                    redacted.append((k, "***"))
                else:
                    redacted.append((k, v))
            new_query = urllib.parse.urlencode(redacted, safe="*")
            return urllib.parse.urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url

    def _resolve_remote_config_urls(
        self,
        api_remote_url: Optional[str] = None,
    ) -> ResolvedUrls:
        urls: List[str] = []
        source: Optional[str] = None
        effective_urls: List[str] = []

        if api_remote_url and self._validate_url(api_remote_url):
            urls.append(api_remote_url)
            source = "api_param"
        elif api_remote_url:
            logger.debug("优先级链: API参数URL无效，已跳过: %s", api_remote_url)

        env_urls = [u for u in self._env_remote_config_urls if self._validate_url(u)]
        if env_urls:
            urls.extend(env_urls)
            if source is None:
                source = "env_var"

        config_url = self._get_remote_config_url()
        if config_url and self._validate_url(config_url):
            if config_url not in urls:
                urls.append(config_url)
                if source is None:
                    source = "config_file"
        elif config_url:
            logger.debug("优先级链: 配置文件URL无效，已跳过: %s", config_url)

        default_urls = [u for u in _DEFAULT_REMOTE_CONFIG_URLS if self._validate_url(u)]
        for u in default_urls:
            if u not in urls:
                urls.append(u)
        if source is None and default_urls:
            source = "default"

        effective_urls = list(urls)
        logger.info("源同步优先级链: 共%d个URL, 来源=%s", len(urls), source)

        return ResolvedUrls(urls=urls, source=source, effective_urls=effective_urls)

    def _get_builtin_upstream(self) -> List[dict]:
        custom_path = os.path.join(self._data_dir, "upstream_sources.json")
        if os.path.exists(custom_path):
            try:
                with open(custom_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sources = data.get("sources", data) if isinstance(data, dict) else data
                if isinstance(sources, list) and len(sources) > 0:
                    logger.info("使用自定义上游源配置: %s (%d个源)", custom_path, len(sources))
                    return sources
            except Exception as e:
                logger.warning("加载自定义上游源配置失败: %s", e)

        local = self._load_local_sources_raw()
        sources = local.get("sources", [])
        if sources:
            storage = "数据库" if self._source_store else "local_sources.json"
            logger.info("使用现有 %s 作为上游基线 (%d个源)", storage, len(sources))
            return sources
        return []

    async def _fetch_remote_sources(self, url: str) -> Optional[List[dict]]:
        if not self._http_session:
            logger.warning("HTTP 会话未初始化，无法远程拉取")
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with self._http_session.get(url, timeout=timeout, ssl=False) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    
                    if text.startswith("#EXTM3U"):
                        return self._parse_m3u_to_sources(text, url)
                    
                    data = json.loads(text)
                    sources = data.get("sources", data) if isinstance(data, dict) else data
                    if isinstance(sources, list):
                        logger.info("从远程获取到 %d 个源: %s", len(sources), url)
                        return sources
                    logger.warning("远程数据格式不正确: %s", url)
        except Exception as e:
            logger.warning("从远程获取源列表失败 %s: %s", url, e)
        return None

    @staticmethod
    def _parse_m3u_to_sources(m3u_content: str, source_url: str) -> List[dict]:
        from iptv_check.core.parser import PlaylistParser
        
        parse_result = PlaylistParser.parse_m3u_content_safe(m3u_content, source_url)
        if not parse_result.channels:
            logger.warning("M3U解析无频道: %s", source_url)
            return []
        
        seen_urls = set()
        sources = []
        for channel in parse_result.channels:
            category = _classify_channel(channel.name, channel.group)
            if category is None:
                continue
            
            if channel.url in seen_urls:
                continue
            seen_urls.add(channel.url)
            
            isp_list = ["移动", "联通", "电信", "其他"]
            
            protocol = "unknown"
            url_lower = channel.url.lower()
            if ".m3u8" in url_lower:
                protocol = "hls"
            elif ".ts" in url_lower:
                protocol = "ts"
            elif "rtmp" in url_lower:
                protocol = "rtmp"
            elif "rtsp" in url_lower:
                protocol = "rtsp"
            elif "http" in url_lower:
                protocol = "http"
            
            sources.append({
                "id": f"m3u_{hashlib.md5(channel.url.encode()).hexdigest()[:8]}",
                "name": channel.name,
                "url": channel.url,
                "category": category,
                "isp": isp_list,
                "protocol": protocol,
                "description": f"从M3U源解析: {channel.name}",
                "epg_url": _IPTV_ORG_EPG_URL if channel.tvg_id or channel.tvg_name else None,
                "tvg_id": channel.tvg_id or None,
                "tvg_name": channel.tvg_name or None,
                "channel_count": 1,
            })
        
        logger.info("从M3U解析到 %d 个频道 (去重后): %s", len(sources), source_url)
        return sources

    def _merge_sources(
        self,
        local_sources: List[OnlineSource],
        upstream_sources: List[dict],
        upstream_ids: set,
    ) -> tuple[List[OnlineSource], int, int, int]:
        local_map = {s.id: s for s in local_sources}
        user_added_ids = {s.id for s in local_sources if s.id not in upstream_ids}

        added = 0
        updated = 0
        unchanged = 0
        merged = []
        processed_ids = set()

        for upstream_dict in upstream_sources:
            source_id = upstream_dict.get("id", "")
            if not source_id or source_id in processed_ids:
                continue
            processed_ids.add(source_id)

            upstream_source = OnlineSource.from_dict(upstream_dict)
            upstream_source.last_updated = datetime.now(cn_tz()).isoformat()

            if source_id in local_map:
                existing = local_map[source_id]
                changed = False
                for field in _UPDATABLE_FIELDS:
                    new_val = getattr(upstream_source, field)
                    old_val = getattr(existing, field)
                    if new_val != old_val and new_val:
                        setattr(existing, field, new_val)
                        changed = True
                if "channel_count" in upstream_dict and upstream_dict["channel_count"] > 0 and existing.channel_count == 0:
                    existing.channel_count = upstream_dict["channel_count"]
                    changed = True
                if changed:
                    existing.last_updated = upstream_source.last_updated
                    updated += 1
                else:
                    unchanged += 1
                merged.append(existing)
            else:
                for field in _LOCAL_ONLY_FIELDS:
                    if field in upstream_dict and field not in ("disabled",):
                        setattr(upstream_source, field, upstream_dict[field])
                merged.append(upstream_source)
                added += 1

        for s in local_sources:
            if s.id in user_added_ids and s.id not in processed_ids:
                merged.append(s)
                unchanged += 1

        return merged, added, updated, unchanged

    async def sync(self, remote_url: Optional[str] = None) -> SourceSyncResult:
        if self._is_syncing:
            result = SourceSyncResult()
            result.errors.append("同步正在进行中")
            return result

        self._progress = SourceSyncProgress()
        self._progress.is_syncing = True
        self._progress.started_at = time.time()
        self._is_syncing = True
        result = SourceSyncResult()

        try:
            resolved = self._resolve_remote_config_urls(api_remote_url=remote_url)
            self._last_resolved_urls = resolved
            urls_to_try = resolved.urls

            upstream_dicts = self._get_builtin_upstream()
            upstream_ids = {u.get("id") for u in upstream_dicts}

            self._progress.total_urls = len(urls_to_try)
            self._progress.stage = "fetching"
            await self._broadcast_progress()

            remote_fetched = False
            remote_url_used = None
            failed_urls = []
            fetch_lock = asyncio.Lock()

            async def _try_one(url: str, index: int):
                redacted = self._redact_url_for_log(url)
                async with fetch_lock:
                    self._progress.current_url_index += 1
                    self._progress.current_url_label = redacted
                    self._progress.elapsed_seconds = time.time() - self._progress.started_at
                    self._update_eta()
                    await self._broadcast_progress()

                logger.info("尝试远程源: %s", redacted)
                try:
                    remote_sources = await self._fetch_remote_sources(url)
                except Exception:
                    remote_sources = None

                async with fetch_lock:
                    if remote_sources:
                        deduped = []
                        seen_urls_in_source = set()
                        for rs in remote_sources:
                            rurl = rs.get("url", "")
                            if rurl and rurl not in seen_urls_in_source:
                                seen_urls_in_source.add(rurl)
                                deduped.append(rs)

                        for rs in deduped:
                            rid = rs.get("id", "")
                            if rid and rid not in upstream_ids:
                                upstream_dicts.append(rs)
                                upstream_ids.add(rid)

                        nonlocal remote_fetched, remote_url_used
                        remote_fetched = True
                        remote_url_used = url
                        self._progress.fetched_channel_count += len(deduped)
                        logger.info("远程源同步成功: %s (获取%d个源, 去重后%d个)", redacted, len(remote_sources), len(deduped))
                    else:
                        failed_urls.append(redacted)

                    self._progress.elapsed_seconds = time.time() - self._progress.started_at
                    self._update_eta()
                    await self._broadcast_progress()

                return url, redacted, remote_sources

            tasks = [_try_one(url, i) for i, url in enumerate(urls_to_try)]
            await asyncio.gather(*tasks, return_exceptions=True)

            if failed_urls and not remote_fetched:
                logger.info("所有远程源不可达(%d个)，使用本地基线", len(failed_urls))

            result.remote_fetched = remote_fetched
            result.remote_url_used = remote_url_used
            result.url_source = resolved.source if remote_fetched else None

            if not remote_fetched and not upstream_dicts:
                result.errors.append("所有远程配置URL均不可达，且无本地上游源数据")
                return result

            self._progress.stage = "merging"
            self._progress.elapsed_seconds = time.time() - self._progress.started_at
            await self._broadcast_progress()

            local_sources = self._load_local_sources()
            result.upstream_count = len(upstream_dicts)
            result.local_count = len(local_sources)

            merged, added, updated, unchanged = self._merge_sources(
                local_sources, upstream_dicts, upstream_ids
            )

            for s in merged:
                new_cat = _classify_channel(s.name, getattr(s, 'group', None))
                if new_cat and new_cat != s.category:
                    s.category = new_cat

            result.added = added
            result.updated = updated
            result.unchanged = unchanged
            self._progress.added = added
            self._progress.updated = updated
            self._progress.unchanged = unchanged

            for s in merged:
                if s.channel_count == 0 and s.id.startswith("m3u_"):
                    s.channel_count = 1

            self._save_local_sources(merged)
            result.success = True
            result.synced_at = datetime.now(cn_tz()).isoformat()
            result.local_count = len(merged)

            if remote_fetched:
                logger.info("源同步完成: 远程新增=%d, 更新=%d, 总计=%d", added, updated, len(merged))
            else:
                logger.info("源同步完成: 使用本地基线, 总计=%d个源", len(merged))
        except Exception as e:
            result.errors.append(str(e))
            logger.error("源同步失败: %s", e)
        finally:
            self._is_syncing = False
            self._progress.is_syncing = False
            self._progress.stage = "completed" if result.success else "failed"
            self._progress.elapsed_seconds = time.time() - self._progress.started_at if self._progress.started_at else 0
            self._progress.eta_seconds = None
            self._last_result = result
            await self._broadcast_progress()

        return result

    def start_sync_async(self, remote_url: Optional[str] = None, on_complete: Optional[Callable] = None) -> bool:
        if self._is_syncing:
            return False

        async def _run_and_callback():
            result = await self.sync(remote_url=remote_url)
            if on_complete:
                try:
                    on_complete(result)
                except Exception as e:
                    logger.warning("同步完成回调失败: %s", e)

        self._sync_task = asyncio.create_task(_run_and_callback())
        return True

    def get_progress(self) -> Dict:
        return self._progress.to_dict()

    async def _broadcast_progress(self):
        if self._broadcast_fn:
            try:
                await self._broadcast_fn("sync_progress", self._progress.to_dict())
            except Exception as e:
                logger.warning("广播同步进度失败: %s", e)

    def _update_eta(self):
        p = self._progress
        if p.current_url_index > 0 and p.total_urls > 0 and p.elapsed_seconds > 0:
            avg_per_url = p.elapsed_seconds / p.current_url_index
            remaining = p.total_urls - p.current_url_index
            p.eta_seconds = avg_per_url * remaining

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    @property
    def last_result(self) -> Optional[SourceSyncResult]:
        return self._last_result

    def get_status(self) -> dict:
        last = self._last_result
        local_count = 0
        remote_url = None
        if os.path.exists(self._local_sources_path):
            try:
                with open(self._local_sources_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                local_count = len(data.get("sources", []))
                remote_url = data.get("remote_config_url")
            except Exception:
                pass

        effective_remote_urls = []
        url_source = None
        if self._last_resolved_urls:
            effective_remote_urls = self._last_resolved_urls.effective_urls
            url_source = self._last_resolved_urls.source

        return {
            "is_syncing": self._is_syncing,
            "local_sources_count": local_count,
            "remote_config_url": remote_url,
            "last_sync": last.to_dict() if last else None,
            "effective_remote_urls": effective_remote_urls,
            "url_source": url_source,
            "sync_progress": self._progress.to_dict(),
        }
