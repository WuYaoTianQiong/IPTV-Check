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
        )

    def is_isp_compatible(self, local_isp: str) -> bool:
        return local_isp in self.isp or "其他" in self.isp
