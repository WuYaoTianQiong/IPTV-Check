from dataclasses import dataclass, field
from typing import List, Optional

_LEGACY_SOURCE_DESC_PREFIX = "从M3U源解析"


def is_legacy_channel_source(src) -> bool:
    """判断源是否为历史遗留的"M3U 被拆成频道级源"条目。

    旧版本在同步/解析 M3U 时会把每个频道拆成一个独立"源"写入库，
    description 统一标记为「从M3U源解析: <频道名>」。当前版本已改为
    把 M3U 整体作为一个列表源，因此此类条目属遗留坏数据，在迁移、
    同步、拉取时都应过滤，防止其重新入库。

    支持 dict（上游 JSON 条目）与 OnlineSource 两种输入形态。
    """
    if isinstance(src, dict):
        desc = src.get("description") or ""
    else:
        desc = getattr(src, "description", None) or ""
    return str(desc).strip().startswith(_LEGACY_SOURCE_DESC_PREFIX)


def is_channel_url(src) -> bool:
    """判断源是否为"频道级源"（URL 直接是流地址，无需下载解析）。

    组合判断：
    1) URL 以 .m3u 结尾 → 播放列表源（下载解析频道列表）；
    2) m3u_ 前缀的整体源（channel_count>1，来自 M3U 同步）→ 列表源；
    3) 其余按原 category 后缀判断（兼容 URL 无扩展名的列表 API 源）。

    检测（check）与拉取（fetch）两条路径共用此判定，避免"其他频道"等
    分类的列表源被误当成单频道源。
    支持 dict（上游 JSON 条目）与 OnlineSource 两种输入形态。
    """
    if isinstance(src, dict):
        url = src.get("url") or ""
        sid = src.get("id") or ""
        channel_count = src.get("channel_count") or 0
        category = src.get("category") or ""
    else:
        url = getattr(src, "url", "") or ""
        sid = getattr(src, "id", "") or ""
        channel_count = getattr(src, "channel_count", None) or 0
        category = getattr(src, "category", "") or ""

    path = url.strip().lower().split("?", 1)[0].rstrip("/")
    if path.endswith(".m3u"):
        return False
    if str(sid).startswith("m3u_") and channel_count > 1:
        return False
    return category.endswith("频道") or category.endswith("电台")


@dataclass
class OnlineSource:
    id: str
    name: str
    url: str
    isp: List[str] = field(default_factory=list)
    protocol: str = "ipv4"
    features: List[str] = field(default_factory=list)
    description: str = ""
    category: str = "其他"
    mirror_url: Optional[str] = None
    disabled: bool = False
    epg_url: Optional[str] = None
    logo_base_url: Optional[str] = None
    update_frequency: str = "daily"
    quality_rating: str = "A"
    channel_count: int = 0
    last_updated: Optional[str] = None
    cache_filename: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "OnlineSource":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            url=data.get("url", ""),
            isp=data.get("isp", []),
            protocol=data.get("protocol", "ipv4"),
            features=data.get("features", []),
            description=data.get("description", ""),
            category=data.get("category", "其他"),
            mirror_url=data.get("mirror_url"),
            disabled=data.get("disabled", False),
            epg_url=data.get("epg_url"),
            logo_base_url=data.get("logo_base_url"),
            update_frequency=data.get("update_frequency", "daily"),
            quality_rating=data.get("quality_rating", "A"),
            channel_count=data.get("channel_count", 0),
            last_updated=data.get("last_updated"),
            cache_filename=data.get("cache_filename"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "isp": self.isp,
            "protocol": self.protocol,
            "features": self.features,
            "description": self.description,
            "category": self.category,
            "mirror_url": self.mirror_url,
            "disabled": self.disabled,
            "epg_url": self.epg_url,
            "logo_base_url": self.logo_base_url,
            "update_frequency": self.update_frequency,
            "quality_rating": self.quality_rating,
            "channel_count": self.channel_count,
            "last_updated": self.last_updated,
            "cache_filename": self.cache_filename,
        }

    def is_isp_compatible(self, local_isp: str) -> bool:
        isps = self.isp
        if isinstance(isps, str):
            # 兼容历史脏数据：字符串"未知"/"其他/未知"等价于无标注，不参与运营商匹配
            isps = [] if isps in ("", "未知", "其他/未知") else [isps]
        else:
            isps = isps or []
        # 本地运营商未识别出具体值时不做运营商过滤（避免把整个源库一键筛空）
        if not local_isp or local_isp in ("未知", "其他/未知"):
            return True
        return local_isp in isps or "其他" in isps

    @property
    def has_epg(self) -> bool:
        return self.epg_url is not None and self.epg_url != ""

    @property
    def has_logo_support(self) -> bool:
        return self.logo_base_url is not None and self.logo_base_url != ""

