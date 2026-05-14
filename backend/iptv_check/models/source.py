from dataclasses import dataclass, field
from typing import List, Optional


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
        return local_isp in self.isp or "其他" in self.isp

    @property
    def has_epg(self) -> bool:
        return self.epg_url is not None and self.epg_url != ""

    @property
    def has_logo_support(self) -> bool:
        return self.logo_base_url is not None and self.logo_base_url != ""

