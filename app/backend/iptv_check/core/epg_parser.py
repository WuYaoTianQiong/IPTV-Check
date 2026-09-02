import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from datetime import datetime

from iptv_check.models.epg_program import EpgChannel, EpgProgram

logger = logging.getLogger(__name__)


class EPGParser:
    @staticmethod
    def parse_xmltv(content: str) -> Dict[str, EpgChannel]:
        channels: Dict[str, EpgChannel] = {}
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error("XMLTV解析失败: %s", e)
            return channels

        for ch_elem in root.findall("channel"):
            ch_id = ch_elem.get("id", "")
            display_name_elem = ch_elem.find("display-name")
            display_name = display_name_elem.text if display_name_elem is not None and display_name_elem.text else ch_id
            channels[ch_id] = EpgChannel(channel_id=ch_id, display_name=display_name)

        for prog_elem in root.findall("programme"):
            channel_id = prog_elem.get("channel", "")
            start = prog_elem.get("start", "")
            stop = prog_elem.get("stop", "")

            title_elem = prog_elem.find("title")
            title = title_elem.text if title_elem is not None and title_elem.text else ""

            desc_elem = prog_elem.find("desc")
            desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

            category_elem = prog_elem.find("category")
            category = category_elem.text if category_elem is not None and category_elem.text else ""

            program = EpgProgram(title=title, start=start, stop=stop, desc=desc, category=category)

            if channel_id not in channels:
                channels[channel_id] = EpgChannel(channel_id=channel_id)

            channels[channel_id].programs.append(program)

        total_programs = sum(len(ch.programs) for ch in channels.values())
        logger.info("XMLTV解析完成: %d 频道, %d 节目", len(channels), total_programs)
        return channels

    @staticmethod
    def parse_xmltv_file(file_path: str) -> Dict[str, EpgChannel]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return EPGParser.parse_xmltv(f.read())
        except Exception as e:
            logger.error("读取EPG文件失败 %s: %s", file_path, e)
            return {}

    @staticmethod
    def match_channel_to_epg(
        channel_name: str,
        tvg_id: str,
        tvg_name: str,
        epg_data: Dict[str, EpgChannel],
    ) -> Optional[EpgChannel]:
        if tvg_id and tvg_id in epg_data:
            return epg_data[tvg_id]

        if tvg_name:
            for ch_id, epg_ch in epg_data.items():
                if ch_id.lower() == tvg_name.lower():
                    return epg_ch
                if epg_ch.display_name.lower() == tvg_name.lower():
                    return epg_ch

        if channel_name:
            name_lower = channel_name.lower()
            for ch_id, epg_ch in epg_data.items():
                if ch_id.lower() == name_lower:
                    return epg_ch
                if epg_ch.display_name.lower() == name_lower:
                    return epg_ch

        if channel_name:
            name_lower = channel_name.lower()
            for ch_id, epg_ch in epg_data.items():
                clean_id = ch_id.replace("-", "").replace("_", "").replace(" ", "").lower()
                clean_name = name_lower.replace("-", "").replace("_", "").replace(" ", "")
                # 归一化后 id 太短（如 "C"）会误命中任意含该字母的频道名，
                # 要求 id 至少 3 字符再参与子串匹配，避免单/双字符 id 的灾难性误匹配。
                if clean_id and clean_name and len(clean_id) >= 3 and (clean_id in clean_name or clean_name in clean_id):
                    return epg_ch

        return None

    @staticmethod
    def get_current_programs(
        epg_data: Dict[str, EpgChannel],
    ) -> Dict[str, dict]:
        result = {}
        for ch_id, epg_ch in epg_data.items():
            current = epg_ch.get_current_program()
            if current:
                result[ch_id] = {
                    "channel_id": ch_id,
                    "display_name": epg_ch.display_name,
                    "current_program": current.to_dict(),
                }
        return result
