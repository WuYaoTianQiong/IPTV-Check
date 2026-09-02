from dataclasses import dataclass, field
from typing import List, Optional
import re


_RESOLUTION_PATTERN = re.compile(
    r'(?:^|(?<=[\s_\-\|])|(?<=\u4e00)|(?<=\u9fff))'
    r'('
    r'8K|UHD\s*8K|4K|UHD|2160p|'
    r'2K|1440p|'
    r'FHD|全高清|1080p|1080i|'
    r'HD720p|720p|'
    r'HD|高清|'
    r'SD576p|576p|480p|'
    r'SD|标清|流畅'
    r')'
    r'(?=[\s_\-\|\u4e00-\u9fff]|$)',
    re.IGNORECASE,
)


def _extract_resolution(name: str) -> str:
    if not name:
        return ""
    match = _RESOLUTION_PATTERN.search(name)
    if not match:
        return ""
    raw = match.group(1).strip()
    lower = raw.lower()
    if lower in ("4k", "uhd", "uhd8k", "8k", "2160p"):
        return "4K"
    if lower in ("hd", "高清", "hd720p", "720p", "fhd", "全高清", "1080p", "1080i"):
        return "HD"
    if lower in ("sd", "标清", "sd576p", "576p", "480p", "流畅"):
        return "SD"
    return raw


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
    frequency: str = ""
    quality_rating: str = ""
    clean_name: str = ""
    resolution: str = ""
    # 先验延迟（ms）：细筛从粗筛会话加载频道时带上，用于对慢源给更短的测速上限
    prior_latency: Optional[float] = None
    # 归属地标签（导出标注用，运行时推断，不落库）：国外=国家中文名；国内=省份/央视/卫视/港澳台
    region: str = ""

    def __post_init__(self):
        if not self.resolution and self.name:
            self.resolution = _extract_resolution(self.name)

    @classmethod
    def from_m3u_extinf(cls, info_line: str, url_line: str, index: int = 0, source_name: str = "") -> "Channel":
        import re
        attrs = cls._parse_extinf_attrs(info_line)
        name = attrs.pop("name", "N/A")
        url = url_line.strip()
        sources = [source_name] if source_name else []
        channel = cls(name=name, url=url, sources=sources, index=index, **attrs)

        radio_kw = ["广播", "电台", "radio", "fm", "am"]
        text_lower = f"{channel.name} {channel.group} {channel.frequency}".lower()
        url_lower = url.lower()
        if (any(kw in text_lower for kw in radio_kw) or
            any(kw in url_lower for kw in ["qingting.fm", "xmcdn.com", "ximalaya", "lrc.la"])):
            channel.is_radio = True

        return channel

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

        name = attrs.get("name", "")
        group = attrs.get("group", "")
        frequency = Channel._extract_frequency(name, group)
        if frequency:
            attrs["frequency"] = frequency

        return attrs

    @staticmethod
    def _extract_frequency(name: str, group: str) -> str:
        import re
        text_to_search = f"{name} {group}"
        
        match = re.search(r'(?:^|[^a-zA-Z0-9])(?:FM\s*)?(\d{2,3}\.\d)\s*(?:MHz|FM|fm)?', text_to_search, re.IGNORECASE)
        if match:
            freq = match.group(1)
            try:
                freq_val = float(freq)
                if 70.0 <= freq_val <= 108.0:
                    return f"FM {freq}"
            except ValueError:
                pass

        match = re.search(r'(?:^|[^a-zA-Z0-9])FM\s*(\d{2,3})(?:\s*(?:MHz|FM|fm))?(?:$|[^a-zA-Z0-9.])', text_to_search, re.IGNORECASE)
        if match:
            freq = match.group(1)
            try:
                freq_val = int(freq)
                if 87 <= freq_val <= 108:
                    return f"FM {freq}"
            except ValueError:
                pass

        match = re.search(r'(?:^|[^a-zA-Z0-9.])(\d{2,3})\s*FM(?:\s*(?:MHz))?(?:$|[^a-zA-Z0-9.])', text_to_search, re.IGNORECASE)
        if match:
            freq = match.group(1)
            try:
                freq_val = int(freq)
                if 87 <= freq_val <= 108:
                    return f"FM {freq}"
            except ValueError:
                pass

        match = re.search(r'(?:^|[^a-zA-Z0-9])(?:AM\s*)?(\d{3,4})\s*(?:kHz|AM|am|KHz)', text_to_search, re.IGNORECASE)
        if match:
            freq = match.group(1)
            try:
                freq_val = float(freq)
                if 500 <= freq_val <= 1700:
                    return f"AM {freq}"
            except ValueError:
                pass

        _radio_kw = ['广播', '电台', 'radio', 'fm', 'am', 'broadcast']
        text_lower = text_to_search.lower()
        if any(kw in text_lower for kw in _radio_kw):
            match = re.search(r'(?:^|[^a-zA-Z0-9.])(\d{2,3}\.\d)(?:$|[^a-zA-Z0-9.])', text_to_search)
            if match:
                try:
                    freq_val = float(match.group(1))
                    if 70.0 <= freq_val <= 108.0:
                        return f"FM {match.group(1)}"
                except ValueError:
                    pass

        return ""

    @classmethod
    def from_txt_line(cls, line: str, index: int = 0, source_name: str = "") -> "Channel":
        parts = line.strip().split(",", 1)
        if len(parts) == 2:
            name, url = parts[0].strip(), parts[1].strip()
        else:
            name, url = "N/A", parts[0].strip()
        sources = [source_name] if source_name else []
        channel = cls(name=name, url=url, index=index, sources=sources)

        radio_kw = ["广播", "电台", "radio", "fm", "am"]
        text_lower = f"{channel.name} {channel.frequency}".lower()
        url_lower = url.lower()
        if (any(kw in text_lower for kw in radio_kw) or
            any(kw in url_lower for kw in ["qingting.fm", "xmcdn.com", "ximalaya", "lrc.la"])):
            channel.is_radio = True

        return channel

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
