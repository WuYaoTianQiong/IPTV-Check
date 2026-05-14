from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Channel:
    name: str
    url: str
    group: str = ""
    sources: List[str] = field(default_factory=list)
    index: int = 0
    tvg_name: str = ""
    tvg_id: str = ""
    logo_url: str = ""
    language: str = ""
    country: str = ""
    category: str = ""
    is_radio: bool = False
    quality_rating: str = ""

    @classmethod
    def from_m3u_extinf(cls, info_line: str, url_line: str, index: int = 0, source_name: str = "") -> "Channel":
        import re
        attrs = cls._parse_extinf_attrs(info_line)
        name = attrs.pop("name", "N/A")
        sources = [source_name] if source_name else []
        return cls(name=name, url=url_line.strip(), sources=sources, index=index, **attrs)

    @staticmethod
    def _parse_extinf_attrs(info_line: str) -> dict:
        import re
        attrs = {}
        name_match = re.search(r",(.+)", info_line)
        if name_match:
            attrs["name"] = name_match.group(1).strip()

        for key, pattern in [
            ("tvg_id", r'tvg-id="([^"]*)"'),
            ("tvg_name", r'tvg-name="([^"]*)"'),
            ("logo_url", r'tvg-logo="([^"]*)"'),
            ("group", r'group-title="([^"]*)"'),
            ("language", r'tvg-language="([^"]*)"'),
            ("country", r'tvg-country="([^"]*)"'),
        ]:
            m = re.search(pattern, info_line)
            if m:
                attrs[key] = m.group(1)

        catchup_match = re.search(r'catchup="([^"]*)"', info_line)
        if catchup_match:
            attrs["category"] = "catchup"

        radio_group = attrs.get("group", "").lower()
        if any(kw in radio_group for kw in ["广播", "电台", "radio", "fm", "am"]):
            attrs["is_radio"] = True

        return attrs

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
        if self._is_ipv6_url():
            return "IPv6"
        return "IPv4"

    def _is_ipv6_url(self) -> bool:
        url = self.url.lower()
        if "ipv6" in url or "/v6/" in url:
            return True
        import re
        if re.search(r"https?://\[?[0-9a-f]{4}:", url):
            return True
        return False

    @property
    def display_name(self) -> str:
        return self.tvg_name or self.name
