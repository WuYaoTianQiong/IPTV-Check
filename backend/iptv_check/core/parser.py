import re
import os
import hashlib
import logging
from typing import List, Optional

from iptv_check.models.channel import Channel
from iptv_check.domain.parse_result import ParseResult, ParseError

logger = logging.getLogger(__name__)

_EXTINF_ATTR_PATTERNS = {
    "tvg_id": re.compile(r'tvg-id="([^"]*)"'),
    "tvg_name": re.compile(r'tvg-name="([^"]*)"'),
    "logo_url": re.compile(r'tvg-logo="([^"]*)"'),
    "group": re.compile(r'group-title="([^"]*)"'),
    "language": re.compile(r'tvg-language="([^"]*)"'),
    "country": re.compile(r'tvg-country="([^"]*)"'),
}

_RADIO_KEYWORDS = {"广播", "电台", "radio", "fm", "am", "broadcast"}
_IPV6_PATTERN = re.compile(r"https?://\[?[0-9a-f]{4}:", re.IGNORECASE)


def _parse_extinf_line(line: str) -> dict:
    attrs = {}
    name_match = re.search(r",(.+)", line)
    if name_match:
        attrs["name"] = name_match.group(1).strip()

    for key, pattern in _EXTINF_ATTR_PATTERNS.items():
        m = pattern.search(line)
        if m:
            attrs[key] = m.group(1)

    if re.search(r'catchup="[^"]*"', line):
        attrs["category"] = "catchup"

    group = attrs.get("group", "")
    if group and any(kw in group.lower() for kw in _RADIO_KEYWORDS):
        attrs["is_radio"] = True

    return attrs


def _is_ipv6(url: str) -> bool:
    lower = url.lower()
    if "ipv6" in lower or "/v6/" in lower:
        return True
    return bool(_IPV6_PATTERN.search(url))


def _create_channel(name: str, url: str, group: str, sources: List[str],
                    index: int, extinf_attrs: dict) -> Channel:
    return Channel(
        name=name,
        url=url,
        group=group,
        sources=sources,
        index=index,
        tvg_name=extinf_attrs.get("tvg_name", ""),
        tvg_id=extinf_attrs.get("tvg_id", ""),
        logo_url=extinf_attrs.get("logo_url", ""),
        language=extinf_attrs.get("language", ""),
        country=extinf_attrs.get("country", ""),
        category=extinf_attrs.get("category", ""),
        is_radio=extinf_attrs.get("is_radio", False),
    )


def _parse_line_with_url(line: str, name: str, group: str, extinf_attrs: dict,
                         source_name: str, index: int, url_seen: dict,
                         channels: List[Channel], errors: List[ParseError], line_num: int) -> tuple:
    try:
        url = line
        if "," in line and "://" in line.split(",", 1)[1]:
            parts = line.split(",", 1)
            name, url = parts[0].strip(), parts[1].strip()

        url_key = hashlib.md5(url.encode()).hexdigest()
        if url_key in url_seen:
            existing = url_seen[url_key]
            if source_name and source_name not in existing.sources:
                existing.sources.append(source_name)
        else:
            sources = [source_name] if source_name else []
            channel = _create_channel(name, url, group, sources, index, extinf_attrs)
            url_seen[url_key] = channel
            channels.append(channel)
    except Exception as e:
        errors.append(ParseError(line=line_num, raw=line[:100], error=str(e)))
    return name, group, extinf_attrs


class PlaylistParser:
    @staticmethod
    def parse_file(file_path: str) -> List[Channel]:
        result = PlaylistParser.parse_file_safe(file_path)
        return result.channels

    @staticmethod
    def parse_file_safe(file_path: str) -> ParseResult:
        channels = []
        errors = []
        url_seen = {}
        file_name = os.path.splitext(os.path.basename(file_path))[0]

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error("解析文件 %s 失败: %s", file_path, e)
            return ParseResult(channels=[], errors=[ParseError(line=0, raw=file_path, error=str(e))], source=file_name)

        name = "N/A"
        group = ""
        extinf_attrs = {}

        for line_num, line in enumerate(lines, 1):
            try:
                line = line.strip()
                if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                    continue
                if line.startswith("#EXTINF:"):
                    extinf_attrs = _parse_extinf_line(line)
                    name = extinf_attrs.get("name", "N/A")
                    group = extinf_attrs.get("group", "")
                elif "://" in line and not line.startswith("#"):
                    name, group, extinf_attrs = _parse_line_with_url(
                        line, name, group, extinf_attrs, file_name,
                        len(channels) + 1, url_seen, channels, errors, line_num
                    )
                    name = "N/A"
                    group = ""
                    extinf_attrs = {}
            except Exception as e:
                errors.append(ParseError(line=line_num, raw=line[:100], error=str(e)))
                name = "N/A"
                group = ""
                extinf_attrs = {}
                continue

        if errors:
            logger.warning("解析文件 %s: %d 行异常（已跳过）", file_path, len(errors))
        return ParseResult(channels=channels, errors=errors, source=file_name)

    @staticmethod
    def parse_files(file_paths: List[str]) -> List[Channel]:
        all_channels = []
        url_seen = {}

        for path in file_paths:
            file_channels = PlaylistParser.parse_file(path)
            for ch in file_channels:
                if ch.url_key in url_seen:
                    existing = url_seen[ch.url_key]
                    for src in ch.sources:
                        if src not in existing.sources:
                            existing.sources.append(src)
                else:
                    url_seen[ch.url_key] = ch
                    all_channels.append(ch)

        for idx, ch in enumerate(all_channels, 1):
            ch.index = idx

        return all_channels

    @staticmethod
    def parse_m3u_content(content: str, source_name: str = "") -> List[Channel]:
        result = PlaylistParser.parse_m3u_content_safe(content, source_name)
        return result.channels

    @staticmethod
    def parse_m3u_content_safe(content: str, source_name: str = "") -> ParseResult:
        channels = []
        errors = []
        url_seen = {}
        name = "N/A"
        group = ""
        extinf_attrs = {}

        for line_num, line in enumerate(content.splitlines(), 1):
            try:
                line = line.strip()
                if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                    continue
                if line.startswith("#EXTINF:"):
                    extinf_attrs = _parse_extinf_line(line)
                    name = extinf_attrs.get("name", "N/A")
                    group = extinf_attrs.get("group", "")
                elif "://" in line and not line.startswith("#"):
                    name, group, extinf_attrs = _parse_line_with_url(
                        line, name, group, extinf_attrs, source_name,
                        len(channels) + 1, url_seen, channels, errors, line_num
                    )
                    name = "N/A"
                    group = ""
                    extinf_attrs = {}
            except Exception as e:
                errors.append(ParseError(line=line_num, raw=line[:100], error=str(e)))
                name = "N/A"
                group = ""
                extinf_attrs = {}
                continue

        if errors:
            logger.warning("解析源 %s: %d 行异常（已跳过）", source_name, len(errors))
        return ParseResult(channels=channels, errors=errors, source=source_name)
