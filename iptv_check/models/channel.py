from dataclasses import dataclass, field
from typing import List


@dataclass
class Channel:
    name: str
    url: str
    group: str = ""
    sources: List[str] = field(default_factory=list)
    index: int = 0

    @classmethod
    def from_m3u_extinf(cls, info_line: str, url_line: str, index: int = 0, source_name: str = "") -> "Channel":
        import re
        name = "N/A"
        group = ""
        match = re.search(r",(.+)", info_line)
        if match:
            name = match.group(1).strip()
        group_match = re.search(r'group-title="([^"]+)"', info_line)
        if group_match:
            group = group_match.group(1)
        sources = [source_name] if source_name else []
        return cls(name=name, url=url_line.strip(), group=group, sources=sources, index=index)

    @classmethod
    def from_txt_line(cls, line: str, index: int = 0, source_name: str = "") -> "Channel":
        parts = line.strip().split(",", 1)
        if len(parts) == 2:
            name, url = parts[0].strip(), parts[1].strip()
        else:
            name, url = "N/A", parts[0].strip()
        sources = [source_name] if source_name else []
        return cls(name=name, url=url, index=index, sources=sources)

    @property
    def url_key(self) -> str:
        import hashlib
        return hashlib.md5(self.url.encode()).hexdigest()

    @property
    def protocol_type(self) -> str:
        if "ipv6" in self.url.lower() or "/v6/" in self.url.lower():
            return "IPv6"
        return "IPv4"
