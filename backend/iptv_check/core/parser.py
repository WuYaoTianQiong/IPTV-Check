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
_RADIO_CATEGORY_KEYWORDS = {"广播电台", "广播", "radio"}
_IPV6_PATTERN = re.compile(r"https?://\[?[0-9a-f]{4}:", re.IGNORECASE)
_FM_FREQUENCY_PATTERN = re.compile(r'(?:^|[^a-zA-Z0-9])(?:FM\s*)?(\d{2,3}\.\d)\s*(?:MHz|FM|fm)?', re.IGNORECASE)
_AM_FREQUENCY_PATTERN = re.compile(r'(?:^|[^a-zA-Z0-9])(?:AM\s*)?(\d{3,4})\s*(?:kHz|AM|am|KHz)', re.IGNORECASE)
_CLEAN_NAME_PATTERN = re.compile(r'^["\',;]+|["\',;]+$')
_CLEAN_GROUP_PATTERN = re.compile(r'^["\',;]+|["\',;]+$')
_CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')

_GROUP_NAME_MAP = {
    "news": "新闻", "sport": "体育", "sports": "体育", "music": "音乐",
    "rock": "摇滚", "pop": "流行", "jazz": "爵士", "classical": "古典",
    "country": "乡村", "electronic": "电子", "dance": "舞曲", "hip hop": "嘻哈",
    "r&b": "节奏蓝调", "metal": "金属", "punk": "朋克", "reggae": "雷鬼",
    "blues": "蓝调", "folk": "民谣", "oldies": "怀旧金曲", "hits": "热门",
    "top 40": "排行榜", "adult contemporary": "成人抒情", "lounge": "休闲",
    "chill": "放松", "ambient": "氛围", "trance": "迷幻", "house": "浩室",
    "techno": "科技舞曲", "drum and bass": "鼓打贝斯", "dubstep": "回响贝斯",
    "edm": "电子舞曲", "uplifting": "振奋", "progressive": "渐进",
    "indie": "独立", "alternative": "另类", "easy listening": "轻音乐",
    "instrumental": "纯音乐", "vocal": "人声", "acoustic": "原声",
    "world music": "世界音乐", "latin": "拉丁", "bollywood": "宝莱坞",
    "anime": "动漫", "cartoon": "卡通", "kids": "少儿", "children": "少儿",
    "family": "家庭", "entertainment": "娱乐", "comedy": "喜剧",
    "talk": "谈话", "talk radio": "谈话电台", "podcast": "播客",
    "documentary": "纪录", "science": "科学", "nature": "自然",
    "history": "历史", "culture": "文化", "education": "教育",
    "knowledge": "知识", "discovery": "探索", "adventure": "冒险",
    "travel": "旅游", "food": "美食", "cooking": "烹饪",
    "lifestyle": "生活方式", "fashion": "时尚", "beauty": "美容",
    "health": "健康", "fitness": "健身", "wellness": "养生",
    "business": "商业", "finance": "财经", "economy": "经济",
    "politics": "政治", "government": "政府", "public affairs": "公共事务",
    "religion": "宗教", "spiritual": "灵性", "christian": "基督教",
    "islam": "伊斯兰", "buddhist": "佛教", "gospel": "福音",
    "weather": "天气", "traffic": "交通", "local": "本地",
    "regional": "地区", "national": "全国", "international": "国际",
    "world": "世界", "global": "全球", "europe": "欧洲",
    "asia": "亚洲", "africa": "非洲", "america": "美洲",
    "north america": "北美", "south america": "南美", "oceania": "大洋洲",
    "middle east": "中东", "balkans": "巴尔干", "scandinavia": "斯堪的纳维亚",
    "nordic": "北欧", "caribbean": "加勒比", "pacific": "太平洋",
    "just good music": "好音乐", "good music": "好音乐", "best music": "最佳音乐",
    "great music": "优秀音乐", "classic hits": "经典热门", "golden oldies": "经典怀旧",
    "retro": "复古", "80s": "80年代", "90s": "90年代", "70s": "70年代",
    "60s": "60年代", "2000s": "2000年代", "2010s": "2010年代",
    "throwback": "怀旧", "nostalgia": "怀旧", "timeless": "永恒",
    "variety": "综合", "mixed": "混合", "general": "综合",
    "community": "社区", "campus": "校园", "college": "大学",
    "university": "大学", "school": "学校", "student": "学生",
    "youth": "青年", "teen": "青少年", "senior": "老年",
    "adult": "成人", "urban": "城市", "rural": "乡村",
    "coastal": "沿海", "mountain": "山地", "island": "岛屿",
    "beach": "海滩", "city": "城市", "town": "城镇",
    "country music": "乡村音乐", "christmas": "圣诞", "holiday": "节日",
    "love": "爱情", "romance": "浪漫", "party": "派对",
    "workout": "健身", "running": "跑步", "relax": "放松",
    "sleep": "睡眠", "meditation": "冥想", "yoga": "瑜伽",
    "spa": "水疗", "cafe": "咖啡", "bar": "酒吧",
    "restaurant": "餐厅", "hotel": "酒店", "resort": "度假",
    "swedish": "瑞典语", "german": "德语", "french": "法语",
    "spanish": "西班牙语", "italian": "意大利语", "portuguese": "葡萄牙语",
    "dutch": "荷兰语", "danish": "丹麦语", "norwegian": "挪威语",
    "finnish": "芬兰语", "polish": "波兰语", "czech": "捷克语",
    "hungarian": "匈牙利语", "romanian": "罗马尼亚语", "greek": "希腊语",
    "turkish": "土耳其语", "arabic": "阿拉伯语", "hebrew": "希伯来语",
    "hindi": "印地语", "tamil": "泰米尔语", "telugu": "泰卢固语",
    "bengali": "孟加拉语", "urdu": "乌尔都语", "persian": "波斯语",
    "thai": "泰语", "vietnamese": "越南语", "indonesian": "印尼语",
    "malay": "马来语", "tagalog": "他加禄语", "korean": "韩语",
    "japanese": "日语", "chinese": "中文", "mandarin": "普通话",
    "cantonese": "粤语", "russian": "俄语", "ukrainian": "乌克兰语",
    "serbian": "塞尔维亚语", "croatian": "克罗地亚语", "bulgarian": "保加利亚语",
    "slovenian": "斯洛文尼亚语", "slovak": "斯洛伐克语", "lithuanian": "立陶宛语",
    "latvian": "拉脱维亚语", "estonian": "爱沙尼亚语", "icelandic": "冰岛语",
    "albanian": "阿尔巴尼亚语", "macedonian": "马其顿语", "bosnian": "波斯尼亚语",
    "montenegrin": "黑山语", "english": "英语",
    "radio": "电台", "tv": "电视", "stream": "流媒体",
    "live": "直播", "24/7": "24小时", "nonstop": "不间断",
    "hitz": "热门", "fm": "调频", "am": "调幅", "online": "在线",
    "internet": "网络", "web": "网络", "digital": "数字",
    "hd": "高清", "uhd": "超高清", "4k": "4K", "8k": "8K",
    "stereo": "立体声", "mono": "单声道", "surround": "环绕声",
    "high quality": "高质量", "hq": "高质量", "low quality": "低质量",
    "lq": "低质量", "bitrate": "比特率", "kbps": "千比特每秒",
    "mbps": "兆比特每秒", "fast": "快速", "slow": "慢速",
    "clear": "清晰", "crystal": "水晶", "pure": "纯净",
    "clean": "干净", "fresh": "新鲜", "new": "新", "old": "旧",
    "classic": "经典", "modern": "现代", "contemporary": "当代",
    "vintage": "复古", "retro": "复古", "nostalgic": "怀旧",
}


def _clean_name(name: str) -> str:
    if not name:
        return ""
    cleaned = _CLEAN_NAME_PATTERN.sub("", name).strip()
    if not cleaned:
        return name.strip()
    return cleaned


def _clean_group(group: str) -> str:
    if not group:
        return ""
    cleaned = _CLEAN_GROUP_PATTERN.sub("", group).strip()
    if not cleaned:
        return ""
    return cleaned


def _map_group_name(group: str) -> str:
    if not group:
        return ""
    lower = group.strip().lower()
    if lower in _GROUP_NAME_MAP:
        return _GROUP_NAME_MAP[lower]
    for key, cn in _GROUP_NAME_MAP.items():
        if key in lower:
            return cn
    return group


def _has_chinese(text: str) -> bool:
    return bool(_CHINESE_PATTERN.search(text))


def _translate_channel_name(name: str, tvg_name: str = "") -> str:
    if _has_chinese(name):
        return ""
    if tvg_name and _has_chinese(tvg_name):
        return tvg_name
    clean = name.strip().lower()
    name_mapping = {
        "cctv-1": "CCTV-1 综合", "cctv-2": "CCTV-2 财经", "cctv-3": "CCTV-3 综艺",
        "cctv-4": "CCTV-4 中文国际", "cctv-5": "CCTV-5 体育", "cctv-5+": "CCTV-5+ 体育赛事",
        "cctv-6": "CCTV-6 电影", "cctv-7": "CCTV-7 国防军事", "cctv-8": "CCTV-8 电视剧",
        "cctv-9": "CCTV-9 纪录", "cctv-10": "CCTV-10 科教", "cctv-11": "CCTV-11 戏曲",
        "cctv-12": "CCTV-12 社会与法", "cctv-13": "CCTV-13 新闻", "cctv-14": "CCTV-14 少儿",
        "cctv-15": "CCTV-15 音乐", "cctv-16": "CCTV-16 奥林匹克", "cctv-17": "CCTV-17 农业农村",
        "cctv1": "CCTV-1 综合", "cctv2": "CCTV-2 财经", "cctv3": "CCTV-3 综艺",
        "cctv4": "CCTV-4 中文国际", "cctv5": "CCTV-5 体育", "cctv5+": "CCTV-5+ 体育赛事",
        "cctv6": "CCTV-6 电影", "cctv7": "CCTV-7 国防军事", "cctv8": "CCTV-8 电视剧",
        "cctv9": "CCTV-9 纪录", "cctv10": "CCTV-10 科教", "cctv11": "CCTV-11 戏曲",
        "cctv12": "CCTV-12 社会与法", "cctv13": "CCTV-13 新闻", "cctv14": "CCTV-14 少儿",
        "cctv15": "CCTV-15 音乐", "cctv16": "CCTV-16 奥林匹克", "cctv17": "CCTV-17 农业农村",
        "cgtn": "中国国际电视台", "cgtn documentary": "CGTN 纪录", "cgtn russian": "CGTN 俄语",
        "cgtn french": "CGTN 法语", "cgtn spanish": "CGTN 西班牙语", "cgtn arabic": "CGTN 阿拉伯语",
        "hunan tv": "湖南卫视", "zhejiang tv": "浙江卫视", "jiangsu tv": "江苏卫视",
        "beijing tv": "北京卫视", "dragon tv": "东方卫视", "shenzhen tv": "深圳卫视",
        "anhui tv": "安徽卫视", "shandong tv": "山东卫视", "guangdong tv": "广东卫视",
        "liaoning tv": "辽宁卫视", "hubei tv": "湖北卫视", "sichuan tv": "四川卫视",
        "henan tv": "河南卫视", "hebei tv": "河北卫视", "shanxi tv": "山西卫视",
        "shaanxi tv": "陕西卫视", "gansu tv": "甘肃卫视", "qinghai tv": "青海卫视",
        "ningxia tv": "宁夏卫视", "xinjiang tv": "新疆卫视", "inner mongolia tv": "内蒙古卫视",
        "guangxi tv": "广西卫视", "tibet tv": "西藏卫视", "guizhou tv": "贵州卫视",
        "yunnan tv": "云南卫视", "hainan tv": "海南卫视", "jilin tv": "吉林卫视",
        "heilongjiang tv": "黑龙江卫视", "fujian tv": "福建卫视", "jiangxi tv": "江西卫视",
        "chongqing tv": "重庆卫视", "tianjin tv": "天津卫视", "shanghai tv": "上海东方卫视",
        "discovery channel": "探索频道", "discovery": "探索频道", "national geographic": "国家地理",
        "nat geo": "国家地理", "bbc": "英国广播公司", "bbc world": "BBC 世界",
        "cnn": "美国有线电视新闻网", "fox": "福克斯", "abc": "美国广播公司",
        "nbc": "全国广播公司", "cbs": "哥伦比亚广播公司", "hbo": "家庭票房",
        "espn": "娱乐与体育节目网", "mtv": "音乐电视", "vh1": "VH1 音乐",
        "nhk": "日本放送协会", "kbs": "韩国放送公社", "sbs": "首尔广播", "mbc": "文化广播",
        "al jazeera": "半岛电视台", "dw": "德国之声", "rt": "今日俄罗斯",
        "france 24": "法国 24", "euronews": "欧洲新闻", "sky news": "天空新闻",
        "fox news": "福克斯新闻", "bloomberg": "彭博社", "cnbc": "消费者新闻与商业频道",
    }
    for key, cn in name_mapping.items():
        if key in clean:
            return cn
    return ""


def _extract_frequency(name: str, group: str) -> str:
    text_to_search = f"{name} {group}"
    
    match = _FM_FREQUENCY_PATTERN.search(text_to_search)
    if match:
        freq = match.group(1)
        try:
            freq_val = float(freq)
            if 70.0 <= freq_val <= 108.0:
                return f"FM {freq}"
        except ValueError:
            pass
    
    match = _AM_FREQUENCY_PATTERN.search(text_to_search)
    if match:
        freq = match.group(1)
        try:
            freq_val = float(freq)
            if 500 <= freq_val <= 1700:
                return f"AM {freq}"
        except ValueError:
            pass
    
    return ""


def _parse_extinf_line(line: str, source_category: str = "") -> dict:
    attrs = {}
    name_match = re.search(r",(.+)", line)
    if name_match:
        attrs["name"] = _clean_name(name_match.group(1))

    for key, pattern in _EXTINF_ATTR_PATTERNS.items():
        m = pattern.search(line)
        if m:
            attrs[key] = m.group(1)

    attrs["group"] = _clean_group(attrs.get("group", ""))

    if re.search(r'catchup="[^"]*"', line):
        attrs["category"] = "catchup"

    group = attrs.get("group", "")
    if group and any(kw in group.lower() for kw in _RADIO_KEYWORDS):
        attrs["is_radio"] = True
    elif not attrs.get("is_radio") and source_category and any(kw in source_category.lower() for kw in _RADIO_CATEGORY_KEYWORDS):
        attrs["is_radio"] = True

    name = attrs.get("name", "")
    tvg_name = attrs.get("tvg_name", "")
    attrs["clean_name"] = _translate_channel_name(name, tvg_name)

    frequency = _extract_frequency(name, group)
    if frequency:
        attrs["frequency"] = frequency

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
        frequency=extinf_attrs.get("frequency", ""),
        clean_name=extinf_attrs.get("clean_name", ""),
    )


def _parse_line_with_url(line: str, name: str, group: str, extinf_attrs: dict,
                         source_name: str, index: int, url_seen: dict,
                         channels: List[Channel], errors: List[ParseError], line_num: int,
                         source_category: str = "") -> tuple:
    try:
        url = line
        if "," in line and "://" in line.split(",", 1)[1]:
            parts = line.split(",", 1)
            name, url = parts[0].strip(), parts[1].strip()
            if name and (name.startswith('<') or name.startswith(';') or name.startswith('var ')
                         or name.startswith('var\t') or name.startswith('}') or name.startswith('function ')
                         or name == 'N/A'):
                name = "N/A"

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
            logger.warning("解析文件 %s: %d 行异常（已跳过）", file_name, len(errors))
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
    def parse_m3u_content(content: str, source_name: str = "", source_category: str = "") -> List[Channel]:
        result = PlaylistParser.parse_m3u_content_safe(content, source_name, source_category)
        return result.channels

    @staticmethod
    def parse_m3u_content_safe(content: str, source_name: str = "", source_category: str = "") -> ParseResult:
        channels = []
        errors = []
        url_seen = {}
        name = "N/A"
        group = ""
        extinf_attrs = {}

        if content and not content.lstrip().startswith("#EXTM3U"):
            first_line = content.lstrip().split("\n", 1)[0] if content.lstrip() else ""
            if not first_line.startswith("#EXTINF") and "://" not in first_line:
                logger.warning("源 %s 内容非 M3U 格式，跳过解析（首行: %s）", source_name, first_line[:80])
                return ParseResult(channels=[], errors=[], source=source_name)

        for line_num, line in enumerate(content.splitlines(), 1):
            try:
                line = line.strip()
                if not line or line.startswith("#EXTM3U") or line.startswith("# "):
                    continue
                if line.startswith("#EXTINF:"):
                    extinf_attrs = _parse_extinf_line(line, source_category)
                    name = extinf_attrs.get("name", "N/A")
                    group = extinf_attrs.get("group", "")
                elif "://" in line and not line.startswith("#"):
                    name, group, extinf_attrs = _parse_line_with_url(
                        line, name, group, extinf_attrs, source_name,
                        len(channels) + 1, url_seen, channels, errors, line_num,
                        source_category
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
