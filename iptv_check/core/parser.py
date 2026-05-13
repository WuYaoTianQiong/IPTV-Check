import re
import os
import hashlib
import logging
from typing import List

from iptv_check.models.channel import Channel

logger = logging.getLogger(__name__)


class PlaylistParser:
    @staticmethod
    def parse_file(file_path: str) -> List[Channel]:
        channels = []
        url_seen = {}
        file_name = os.path.splitext(os.path.basename(file_path))[0]

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error("解析文件 %s 失败: %s", file_path, e)
            return []

        name = "N/A"
        group = ""
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                continue
            if line.startswith("#EXTINF:"):
                match = re.search(r",(.+)", line)
                name = match.group(1).strip() if match else "N/A"
                group_match = re.search(r'group-title="([^"]+)"', line)
                group = group_match.group(1) if group_match else ""
            elif "://" in line and not line.startswith("#"):
                url = line
                if "," in line and "://" in line.split(",", 1)[1]:
                    parts = line.split(",", 1)
                    name, url = parts[0].strip(), parts[1].strip()

                url_key = hashlib.md5(url.encode()).hexdigest()
                if url_key in url_seen:
                    existing = url_seen[url_key]
                    if file_name not in existing.sources:
                        existing.sources.append(file_name)
                else:
                    channel = Channel(
                        name=name, url=url, group=group,
                        sources=[file_name], index=len(channels) + 1,
                    )
                    url_seen[url_key] = channel
                    channels.append(channel)
                name = "N/A"
                group = ""

        return channels

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
        channels = []
        url_seen = {}
        name = "N/A"
        group = ""

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                continue
            if line.startswith("#EXTINF:"):
                match = re.search(r",(.+)", line)
                name = match.group(1).strip() if match else "N/A"
                group_match = re.search(r'group-title="([^"]+)"', line)
                group = group_match.group(1) if group_match else ""
            elif "://" in line and not line.startswith("#"):
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
                    channel = Channel(
                        name=name, url=url, group=group,
                        sources=[source_name] if source_name else [],
                        index=len(channels) + 1,
                    )
                    url_seen[url_key] = channel
                    channels.append(channel)
                name = "N/A"
                group = ""

        return channels
