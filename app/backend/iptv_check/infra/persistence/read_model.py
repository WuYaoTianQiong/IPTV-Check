import json
import logging
import re
import threading
from typing import Optional
from datetime import datetime

from cachetools import TTLCache

from sqlmodel import Session, select, func
from sqlalchemy import text as sa_text

from iptv_check.infra.persistence.event_store import EventStore, CheckEventModel
from iptv_check.infra.persistence.cn_county_keywords import CN_COUNTY_KEYWORDS

logger = logging.getLogger(__name__)

_JUNK_NAME_PREFIXES = ('<', ';', 'var ', 'var\t', '}', 'function ')

# 按需物化阈值：会话已写 channel_checked 事件超过该值时，查询前值得补一次物化，
# 避免回退到 check_events 的 JSON 慢路径（数万行逐行 json_extract 可达 7s+）
_MATERIALIZE_THRESHOLD = 2000


def _is_junk_name(name: str) -> bool:
    if not name:
        return True
    for prefix in _JUNK_NAME_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _junk_name_exclude_condition(name_col: str = "name") -> str:
    return (
        f"({name_col} != '' AND "
        f"SUBSTR({name_col}, 1, 1) NOT IN ('<', ';', '" + "}" + f"') AND "
        f"SUBSTR({name_col}, 1, 4) != 'var ' AND "
        f"SUBSTR({name_col}, 1, 5) != 'var\t' AND "
        f"SUBSTR({name_col}, 1, 9) != 'function ')"
    )


def _vod_content_sql(name_col: str = "name", url_col: str = "url") -> str:
    """点播/轮播类内容判定（hide_vod=1 时过滤掉的条目）。

    特征：
    - url 是单文件 mp4（快手上传 upic/其它内容平台的录制文件循环，多为"历年春晚"、
      "XX剧"等假直播源；注意 flv 不在此列——甘孜/番禺等县级台用 flv 做真直播）；
    - 名称含"第..集 / 合集 / 大结局 / 轮播 / 点播 / 重播 / 历年 / 全场 / 回放"等
      明显分集/点播语义（不是电视台）。
    仅作展示/复检范围过滤，不影响国家归属判定。
    """
    return (
        f"({url_col} LIKE '%.mp4%'"
        f" OR {name_col} LIKE '%第%集%'"
        f" OR {name_col} LIKE '%合集%'"
        f" OR {name_col} LIKE '%大结局%'"
        f" OR {name_col} LIKE '%轮播%'"
        f" OR {name_col} LIKE '%点播%'"
        f" OR {name_col} LIKE '%重播%'"
        f" OR {name_col} LIKE '%历年%'"
        f" OR {name_col} LIKE '%全场%'"
        f" OR {name_col} LIKE '%回放%'"
        f" OR {name_col} LIKE '%春晚%')"
    )


_CN_COUNTRY_CODES = {
    "CN", "CHN", "HK", "HKG", "MO", "MAC", "TW", "TWN",
}

# 历史遗留的“非标准国家码映射”全是错误映射（例如 "TR": "US" 会把土耳其台归成美国、
# "BM": "CN" 把百慕大归成中国），已整体清空。
# 标准 ISO 3166 代码一律原样保留，避免污染国家筛选与导出归属地标注。
_NON_STANDARD_COUNTRY_CODES = {}

_COUNTRY_NAME_ZH = {
    "CN": "中国", "HK": "中国香港", "MO": "中国澳门", "TW": "中国台湾",
    "US": "美国", "UK": "英国", "GB": "英国", "JP": "日本", "KR": "韩国",
    "FR": "法国", "DE": "德国", "IT": "意大利", "ES": "西班牙", "PT": "葡萄牙",
    "RU": "俄罗斯", "IN": "印度", "BR": "巴西", "CA": "加拿大", "AU": "澳大利亚",
    "SG": "新加坡", "MY": "马来西亚", "TH": "泰国", "VN": "越南", "PH": "菲律宾",
    "ID": "印尼", "TR": "土耳其", "SA": "沙特", "AE": "阿联酋", "EG": "埃及",
    "NG": "尼日利亚", "ZA": "南非", "AR": "阿根廷", "MX": "墨西哥", "CL": "智利",
    "CO": "哥伦比亚", "PE": "秘鲁", "PL": "波兰", "NL": "荷兰", "SE": "瑞典",
    "CH": "瑞士", "AT": "奥地利", "BE": "比利时", "DK": "丹麦", "NO": "挪威",
    "FI": "芬兰", "IE": "爱尔兰", "NZ": "新西兰", "IL": "以色列", "IQ": "伊拉克",
    "IR": "伊朗", "PK": "巴基斯坦", "BD": "孟加拉", "LK": "斯里兰卡", "MM": "缅甸",
    "KH": "柬埔寨", "LA": "老挝", "NP": "尼泊尔", "UA": "乌克兰", "CZ": "捷克",
    "RO": "罗马尼亚", "HU": "匈牙利", "GR": "希腊", "HR": "克罗地亚", "RS": "塞尔维亚",
    "BG": "保加利亚", "SK": "斯洛伐克", "SI": "斯洛文尼亚", "LT": "立陶宛",
    "LV": "拉脱维亚", "EE": "爱沙尼亚", "IS": "冰岛", "LU": "卢森堡",
    "MT": "马耳他", "CY": "塞浦路斯", "GE": "格鲁吉亚", "AM": "亚美尼亚",
    "AZ": "阿塞拜疆", "KZ": "哈萨克斯坦", "UZ": "乌兹别克斯坦",
}

_CN_REGION_MAP = {
    "BJ": {"name": "北京", "keywords": ["北京", "BTV", "btv"]},
    "SH": {"name": "上海", "keywords": ["上海", "东方"]},
    "TJ": {"name": "天津", "keywords": ["天津"]},
    "CQ": {"name": "重庆", "keywords": ["重庆"]},
    "HB": {"name": "河北", "keywords": ["河北", "石家庄"]},
    "SX": {"name": "山西", "keywords": ["山西", "太原"]},
    "LN": {"name": "辽宁", "keywords": ["辽宁", "沈阳", "大连"]},
    "JL": {"name": "吉林", "keywords": ["吉林", "长春"]},
    "HL": {"name": "黑龙江", "keywords": ["黑龙江", "哈尔滨"]},
    "JS": {"name": "江苏", "keywords": ["江苏", "南京", "苏州"]},
    "ZJ": {"name": "浙江", "keywords": ["浙江", "杭州", "宁波"]},
    "AH": {"name": "安徽", "keywords": ["安徽", "合肥"]},
    "FJ": {"name": "福建", "keywords": ["福建", "厦门", "福州", "泉州"]},
    "JX": {"name": "江西", "keywords": ["江西", "南昌"]},
    "SD": {"name": "山东", "keywords": ["山东", "济南", "青岛"]},
    "HA": {"name": "河南", "keywords": ["河南", "郑州"]},
    "HU": {"name": "湖北", "keywords": ["湖北", "武汉"]},
    "HN": {"name": "湖南", "keywords": ["湖南", "长沙"]},
    "GD": {"name": "广东", "keywords": ["广东", "广州", "深圳", "东莞", "佛山", "珠海", "中山", "惠州", "江门", "汕头", "肇庆", "湛江", "茂名", "梅州", "清远", "韶关", "阳江", "河源", "潮州", "揭阳", "云浮"]},
    "GX": {"name": "广西", "keywords": ["广西", "南宁"]},
    "HI": {"name": "海南", "keywords": ["海南", "海口"]},
    "SC": {"name": "四川", "keywords": ["四川", "成都"]},
    "GZ": {"name": "贵州", "keywords": ["贵州", "贵阳"]},
    "YN": {"name": "云南", "keywords": ["云南", "昆明"]},
    "XZ": {"name": "西藏", "keywords": ["西藏", "拉萨"]},
    "SN": {"name": "陕西", "keywords": ["陕西", "西安"]},
    "GS": {"name": "甘肃", "keywords": ["甘肃", "兰州"]},
    "QH": {"name": "青海", "keywords": ["青海", "西宁"]},
    "NX": {"name": "宁夏", "keywords": ["宁夏", "银川"]},
    "XJ": {"name": "新疆", "keywords": ["新疆", "乌鲁木齐"]},
    "NM": {"name": "内蒙古", "keywords": ["内蒙古", "呼和浩特"]},
    "HK": {"name": "香港", "keywords": ["香港", "HK", "ViuTV", "RTHK"]},
    "MO": {"name": "澳门", "keywords": ["澳门", "TDM"]},
    "TW": {"name": "台湾", "keywords": ["台湾", "台视", "中视", "华视", "民视", "公视", "CTS", "TTV", "FTV", "PTS"]},
}

_CONTENT_TYPE_KEYWORDS = {
    "央视": ["CCTV", "cctv", "央视", "中央"],
    "卫视": ["卫视", "湖南", "浙江", "江苏", "东方", "北京", "山东", "广东", "深圳", "湖北", "四川", "重庆", "天津", "辽宁", "安徽", "江西", "河南", "河北", "山西", "陕西", "甘肃", "青海", "宁夏", "新疆", "内蒙古", "广西", "西藏", "贵州", "云南", "海南", "吉林", "黑龙江", "福建"],
    "地方": ["地方", "本地", "市", "区", "县", "上海", "广州", "成都", "武汉", "杭州", "南京", "苏州", "长沙", "郑州", "西安", "沈阳", "大连", "青岛", "厦门", "宁波", "无锡", "合肥", "南昌", "昆明", "贵阳", "兰州", "太原", "石家庄", "哈尔滨", "长春", "呼和浩特", "乌鲁木齐", "银川", "西宁", "拉萨", "南宁", "海口", "福州", "济南", "天津", "重庆", "深圳", "东莞", "佛山", "珠海", "中山", "惠州", "江门", "汕头", "肇庆", "湛江", "茂名", "梅州", "清远", "韶关", "阳江", "河源", "潮州", "揭阳", "云浮", "南平", "三明", "龙岩", "莆田", "泉州", "漳州", "宁德"],
    "4K": ["4K", "4k", "UHD", "uhd", "超清"],
    "IPv6": ["IPv6", "ipv6"],
}

_SPECIALIZED_GROUP_KEYWORDS = [
    "电影", "体育", "动画", "少儿", "音乐", "游戏", "剧场", "经典",
    "纪录", "探索", "新闻", "财经", "法治", "军事", "戏曲", "综艺",
    "生活", "时尚", "旅游", "汽车", "美食", "健康", "养生", "教育",
    "NewTV", "数字", "网络", "春晚", "景区", "戏曲", "书画", "茶",
    "购物", "导视",
]

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
    "religion": "宗教", "religious": "宗教", "spiritual": "灵性", "christian": "基督教",
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
    "variety": "综合", "varied": "综合", "variada": "综合",
    "community": "社区", "public": "公共", "juvenile": "少儿", "juvenil": "少儿",
    "rap": "说唱",
    "adult": "成人", "new": "新", "baroque": "巴洛克", "npr": "美国国家公共电台",
    "soul": "灵魂乐", "funk": "放克", "schlager": "流行民谣", "ballads": "民谣", "chansons": "法国香颂",
    "club": "俱乐部", "dj": "DJ", "hard": "硬", "smooth": "平滑", "soft": "柔和",
    "traditional": "传统", "eclectic": "混合", "deep": "深邃", "experimental": "实验",
    "salsa": "萨尔萨", "tropical": "热带", "cumbia": "昆比亚", "merengue": "梅伦格",
    "celtic": "凯尔特", "swing": "摇摆", "groove": "律动", "ethnic": "民族",
    "opera": "歌剧", "soundtracks": "影视原声", "discofox": "迪斯科狐步",
    "hardcore": "硬核", "gothic": "哥特", "minimal": "极简", "downtempo": "缓拍",
    "ebm": "电子身体音乐", "indigenous": "原住民", "multicultural": "多元文化",
    "black": "黑人", "hiphop": "嘻哈", "r'n'b": "节奏蓝调", "drum'n'bass": "鼓打贝斯",
    "noticias": "新闻", "deportes": "体育", "information": "资讯", "charts": "排行榜",
    "catholic": "天主教", "orthodox": "东正教", "worship": "敬拜", "praise": "赞美",
    "romantic": "浪漫", "romantica": "浪漫", "baladas": "民谣", "grupera": "团体音乐",
    "italo": "意大利", "mixes": "混音", "active": "活力", "free": "自由",
    "ethnic": "民族", "speech": "演讲", "mpb": "巴西流行乐", "50s": "50年代",
    "60s": "60年代", "70s": "70年代", "80s": "80年代", "90s": "90年代",
    "70er": "70年代", "80er": "80年代", "90er": "90年代",
    "weihnachten": "圣诞", "chanson": "法国香颂", "turismo": "旅游",
    "freeform": "自由形式", "associative": "联合", "conservative": "保守",
    "non-commercial": "非商业", "multilingual": "多语种", "culture": "文化",
    "bbq": "烧烤", "pri": "公共电台国际",
    "paris": "巴黎", "banda": "班达", "musique du monde": "世界音乐",
    "outre-mer": "海外", "kultur": "文化", "dom-tom": "海外省",
    "turismo": "旅游", "tourism": "旅游", "traditional": "传统",
    "tradicional": "传统", "mexicana": "墨西哥", "mexican": "墨西哥",
    "bbc": "英国广播公司", "bible": "圣经",
    "ska": "斯卡", "zouk": "祖克", "bossa nova": "巴萨诺瓦",
    "xmas": "圣诞", "political": "政治", "dark": "暗黑", "decades": "年代",
    "piano": "钢琴", "avant-garde": "先锋", "volksmusik": "民谣音乐",
    "classique": "古典", "bachata": "巴恰塔", "underground": "地下",
    "futebol": "足球", "top 100": "百强", "guitar": "吉他",
    "40s": "40年代", "garage": "车库", "big band": "大乐队",
    "deutsch": "德语", "beats": "节拍", "fusion": "融合",
    "2000er": "2000年代", "afrobeats": "非洲节拍", "roots": "根源",
    "30s": "30年代", "literature": "文学", "cristiana": "基督教",
    "politique": "政治", "ecclesia": "教会", "klassik": "古典",
    "bluegrass": "蓝草", "darkwave": "暗潮", "outlaw": "亡命徒",
    "psychedelic": "迷幻", "standards": "标准曲目", "kinder": "儿童",
    "exitos": "热门", "20s": "20年代", "industrial": "工业",
    "automobile": "汽车", "chretienne": "基督教", "occiitaine": "奥克语",
    "quran": "古兰经", "concert": "演唱会", "death": "死亡",
    "breakbeat": "碎拍", "beat": "节拍",
    "hit-parade": "流行榜", "apm": "独立音乐", "orleans": "奥尔良",
    "occitaine": "奥克语",
}


def _map_group_name(group: str) -> str:
    if not group:
        return ""
    parts = re.split(r'[;,]\s*', group.strip())
    mapped = []
    for part in parts:
        lower = part.strip().lower()
        if not lower:
            continue
        found = False
        if lower in _GROUP_NAME_MAP:
            mapped.append(_GROUP_NAME_MAP[lower])
            found = True
        else:
            for key, cn in _GROUP_NAME_MAP.items():
                if key in lower:
                    mapped.append(cn)
                    found = True
                    break
        if not found:
            mapped.append(part.strip())
    return ";".join(mapped) if mapped else ""


_INTERNATIONAL_GROUP_KEYWORDS = [
    "国际", "海外", "境外", "外国",
    "USA", "UK", "BBC", "CNN", "HBO", "NHK", "KBS", "SBS", "MBC",
    "France", "Germany", "Euro", "Sky", "Fox", "ABC", "NBC", "CBS",
    "Discovery", "National", "ESPN", "MTV", "VH1", "Cartoon", "Disney",
    "Al Jazeera", "DW", "RT", "CNA", "NDTV", "Zee", "Sony",
    "Globo", "Telemundo", "Univision", "Caracol", "RCN",
    # 2026-05-17: 移除"CGTN"，因为CGTN是国内外语频道，归属央视而非国际电视（REQ-DOMESTIC-004）
]

_LOCAL_CHANNEL_KEYWORDS = [
    "地方", "本地", "地市", "县级", "区级", "市级",
    "频道", "港澳台", "港·澳·台", "香港", "澳门", "台湾",
]

_INTERNATIONAL_COUNTRY_GROUPS = {
    "美国": ["US", "USA", "美国", "American", "USA"],
    "英国": ["UK", "GB", "英国", "British", "BBC"],
    "日本": ["JP", "JPN", "日本", "Japanese", "NHK"],
    "韩国": ["KR", "KOR", "韩国", "Korean", "KBS", "SBS", "MBC"],
    "德国": ["DE", "DEU", "德国", "German", "DW", "ZDF"],
    "法国": ["FR", "FRA", "法国", "French", "France"],
    "印度": ["IN", "IND", "印度", "Indian"],
    "中东": ["AE", "SA", "IR", "IQ", "阿拉伯", "中东", "Al Jazeera"],
    "拉美": ["MX", "AR", "BR", "拉美", "拉丁", "Spanish"],
    "俄罗斯": ["RU", "RUS", "俄罗斯", "Russian", "RT"],
}


def _normalize_country_code(code: str) -> str:
    """将非标准国家代码映射为ISO 3166-1标准代码"""
    code_upper = code.upper().strip()
    return _NON_STANDARD_COUNTRY_CODES.get(code_upper, code)


def _country_to_flag(code: str) -> str:
    code = _normalize_country_code(code)
    if not code or len(code) != 2:
        return ""
    try:
        offset = 0x1F1E6 - ord('A')
        c1 = chr(ord(code[0]) + offset)
        c2 = chr(ord(code[1]) + offset)
        return c1 + c2
    except Exception:
        return ""


def _infer_region_from_group(grp_name: str, country_code: str, is_radio: bool, content_type: str) -> str:
    """从分组名称和元数据推断频道区域分类"""
    if content_type in ["央视", "卫视", "4K", "IPv6"]:
        return content_type
    
    if is_radio:
        return "广播"
    
    grp_lower = grp_name.lower()
    
    # REQ-DOMESTIC-003: CGTN是央视外语频道，必须优先于国际关键词匹配
    if "CGTN" in grp_name or "cgtn" in grp_lower:
        return "央视"
    
    if any(kw in grp_name for kw in _CONTENT_TYPE_KEYWORDS["央视"]):
        return "央视"
    
    if any(kw in grp_name for kw in _CONTENT_TYPE_KEYWORDS["卫视"]):
        return "卫视"
    
    if any(kw in grp_lower for kw in ["4k", "uhd", "超清"]):
        return "4K"
    
    if any(kw in grp_name for kw in _INTERNATIONAL_GROUP_KEYWORDS):
        return "国际电视"
    
    if any(kw in grp_name for kw in _SPECIALIZED_GROUP_KEYWORDS):
        return "专题"
    
    if any(kw in grp_name for kw in _CONTENT_TYPE_KEYWORDS["地方"]):
        return "地方"
    
    if any(kw in grp_name for kw in _LOCAL_CHANNEL_KEYWORDS):
        return "地方"
    
    codes = [c.strip() for c in country_code.split(";") if c.strip()]
    normalized_codes = [_normalize_country_code(c) for c in codes]
    is_cn = any(c in _CN_COUNTRY_CODES for c in normalized_codes) if normalized_codes else False
    
    if is_cn:
        if "卫视" in grp_name:
            return "卫视"
        return "地方"
    
    if codes:
        return "国际电视"
    
    for country_name, keywords in _INTERNATIONAL_COUNTRY_GROUPS.items():
        if any(kw in grp_name for kw in keywords):
            return "国际电视"
    
    return "未分类"


_CN_REGION_KEYWORDS = [
    ("北京", ["北京", "BTV", "btv", "北京卫视"]),
    ("上海", ["上海", "东方"]),
    ("天津", ["天津"]),
    ("重庆", ["重庆"]),
    ("河北", ["河北", "石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口", "承德", "沧州", "廊坊", "衡水"]),
    ("山西", ["山西", "太原", "大同", "阳泉", "长治", "晋城", "朔州", "晋中", "运城", "忻州", "临汾", "吕梁"]),
    ("内蒙古", ["内蒙古", "呼和浩特", "包头", "乌海", "赤峰", "通辽", "鄂尔多斯", "呼伦贝尔", "巴彦淖尔", "乌兰察布", "兴安", "锡林郭勒", "阿拉善"]),
    ("辽宁", ["辽宁", "沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口", "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛"]),
    ("吉林", ["吉林", "长春", "四平", "辽源", "通化", "白山", "松原", "白城", "延边", "长白山"]),
    ("黑龙江", ["黑龙江", "哈尔滨", "齐齐哈尔", "鸡西", "鹤岗", "双鸭山", "大庆", "伊春", "佳木斯", "七台河", "牡丹江", "黑河", "绥化", "大兴安岭"]),
    ("江苏", ["江苏", "南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁", "江阴", "昆山", "常熟", "张家港", "吴江", "太仓", "宜兴", "溧阳", "丹阳", "启东", "如皋", "海门", "东台", "靖江", "泰兴", "兴化"]),
    ("浙江", ["浙江", "杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州", "舟山", "台州", "丽水", "萧山", "余杭", "余姚", "慈溪", "象山", "宁海", "奉化", "瑞安", "乐清", "永嘉", "平阳", "苍南", "文成", "泰顺", "海宁", "平湖", "桐乡", "嘉善", "海盐", "诸暨", "上虞", "嵊州", "新昌", "兰溪", "义乌", "东阳", "永康", "武义", "浦江", "磐安", "江山市", "龙游", "常山", "开化", "温岭", "临海", "玉环", "天台", "仙居", "三门", "龙泉", "青田", "缙云", "遂昌", "松阳", "云和", "庆元", "景宁", "定海", "普陀", "岱山", "嵊泗", "安吉", "德清", "长兴", "柯桥", "南浔"]),
    ("安徽", ["安徽", "合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "淮北", "铜陵", "安庆", "黄山", "滁州", "阜阳", "宿州", "六安", "亳州", "池州", "宣城"]),
    ("福建", ["福建", "福州", "厦门", "莆田", "三明", "泉州", "漳州", "南平", "龙岩", "宁德", "福清", "晋江", "石狮"]),
    ("江西", ["江西", "南昌", "景德镇", "萍乡", "九江", "新余", "鹰潭", "赣州", "吉安", "宜春", "抚州", "上饶"]),
    ("山东", ["山东", "济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁", "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽"]),
    ("河南", ["河南", "郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡", "焦作", "濮阳", "许昌", "漯河", "三门峡", "南阳", "商丘", "信阳", "周口", "驻马店"]),
    ("湖北", ["湖北", "武汉", "黄石", "十堰", "宜昌", "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁", "随州", "恩施", "江夏", "仙桃", "潜江", "天门"]),
    ("湖南", ["湖南", "长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "张家界", "益阳", "郴州", "永州", "怀化", "娄底", "湘西"]),
    ("广东", ["广东", "广州", "深圳", "东莞", "佛山", "珠海", "中山", "惠州", "江门", "汕头", "肇庆", "湛江", "茂名", "梅州", "清远", "韶关", "阳江", "河源", "潮州", "揭阳", "云浮", "汕尾"]),
    ("广西", ["广西", "南宁", "柳州", "桂林", "梧州", "北海", "防城港", "钦州", "贵港", "玉林", "百色", "贺州", "河池", "来宾", "崇左"]),
    ("海南", ["海南", "海口", "三亚", "三沙", "儋州", "琼海", "五指山"]),
    ("四川", ["四川", "成都", "自贡", "攀枝花", "泸州", "德阳", "绵阳", "广元", "遂宁", "内江", "乐山", "南充", "眉山", "宜宾", "广安", "达州", "雅安", "巴中", "资阳", "阿坝", "甘孜", "凉山"]),
    ("贵州", ["贵州", "贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁", "黔西南", "黔东南", "黔南"]),
    ("云南", ["云南", "昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧", "楚雄", "红河", "文山", "西双版纳", "大理", "德宏", "怒江", "迪庆"]),
    ("西藏", ["西藏", "拉萨", "日喀则", "昌都", "林芝", "山南", "那曲", "阿里"]),
    ("陕西", ["陕西", "西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中", "榆林", "安康", "商洛"]),
    ("甘肃", ["甘肃", "兰州", "嘉峪关", "金昌", "白银", "天水", "武威", "张掖", "平凉", "酒泉", "庆阳", "定西", "陇南", "临夏", "甘南"]),
    ("青海", ["青海", "西宁", "海东", "海北", "黄南", "果洛", "玉树", "海西"]),
    ("宁夏", ["宁夏", "银川", "石嘴山", "吴忠", "固原", "中卫"]),
    ("新疆", ["新疆", "乌鲁木齐", "克拉玛依", "吐鲁番", "哈密", "昌吉", "博尔塔拉", "巴音郭楞", "阿克苏", "克孜勒苏", "喀什", "和田", "伊犁", "塔城", "阿勒泰"]),
    ("香港", ["香港", "ViuTV", "RTHK", "TVB", "凤凰卫视", "凤凰资讯", "无线", "明珠台", "翡翠台"]),
    ("澳门", ["澳门", "TDM"]),
    ("台湾", ["台湾", "台视", "中视", "华视", "民视", "公视", "CTS", "TTV", "FTV", "PTS", "八大", "三立", "东森", "纬来", "TVBS"]),
]

_COUNTRY_NAME_ZH = {
    "CN": "中国", "HK": "中国香港", "MO": "中国澳门", "TW": "中国台湾",
    "US": "美国", "UK": "英国", "GB": "英国", "JP": "日本", "KR": "韩国",
    "FR": "法国", "DE": "德国", "IT": "意大利", "ES": "西班牙", "PT": "葡萄牙",
    "RU": "俄罗斯", "IN": "印度", "BR": "巴西", "CA": "加拿大", "AU": "澳大利亚",
    "SG": "新加坡", "MY": "马来西亚", "TH": "泰国", "VN": "越南", "PH": "菲律宾",
    "ID": "印尼", "TR": "土耳其", "SA": "沙特", "AE": "阿联酋", "EG": "埃及",
    "NG": "尼日利亚", "ZA": "南非", "AR": "阿根廷", "MX": "墨西哥", "CL": "智利",
    "CO": "哥伦比亚", "PE": "秘鲁", "PL": "波兰", "NL": "荷兰", "SE": "瑞典",
    "CH": "瑞士", "AT": "奥地利", "BE": "比利时", "DK": "丹麦", "NO": "挪威",
    "FI": "芬兰", "IE": "爱尔兰", "NZ": "新西兰", "IL": "以色列", "IQ": "伊拉克",
    "IR": "伊朗", "PK": "巴基斯坦", "BD": "孟加拉", "LK": "斯里兰卡", "MM": "缅甸",
    "KH": "柬埔寨", "LA": "老挝", "NP": "尼泊尔", "UA": "乌克兰", "CZ": "捷克",
    "RO": "罗马尼亚", "HU": "匈牙利", "GR": "希腊", "HR": "克罗地亚", "RS": "塞尔维亚",
    "BG": "保加利亚", "SK": "斯洛伐克", "SI": "斯洛文尼亚", "LT": "立陶宛",
    "LV": "拉脱维亚", "EE": "爱沙尼亚", "IS": "冰岛", "LU": "卢森堡",
    "MT": "马耳他", "CY": "塞浦路斯", "GE": "格鲁吉亚", "AM": "亚美尼亚",
    "AZ": "阿塞拜疆", "KZ": "哈萨克斯坦", "UZ": "乌兹别克斯坦",
}


def _infer_region(name: str, group: str, country_code: str) -> str:
    """从频道名称、分组和国家代码推断具体地区名称

    优先级：
    1. 中国大陆省份/城市（从名称关键词匹配）
    2. 港澳台（中国香港/中国澳门/中国台湾）
    3. 国外国家名称（从country_code转中文名）
    4. 兜底：从频道名中的品牌词推断国家代码
    """
    text = f"{name or ''} {group or ''}".lower()

    # 1. 优先匹配中国大陆省份/城市
    for region_name, keywords in _CN_REGION_KEYWORDS:
        for kw in keywords:
            if kw.lower() in text:
                return region_name

    # 2. 港澳台处理
    normalized = _normalize_country_code(country_code or "")
    if normalized in ("HK", "HKG"):
        return "中国香港"
    if normalized in ("MO", "MAC"):
        return "中国澳门"
    if normalized in ("TW", "TWN"):
        return "中国台湾"

    # 3. 国外国家代码转中文名
    if normalized and normalized != "CN":
        return _COUNTRY_NAME_ZH.get(normalized, normalized)

    # 4. 从频道名中的品牌词推断国家代码
    from iptv_check.core.parser import _COUNTRY_CODE_MAP, _CN_KEYWORDS, _country_kw_matches

    lower_name = (name or "").lower()
    lower_group = (group or "").lower()

    # 先检查是否为中国频道
    for kw in _CN_KEYWORDS:
        if kw.lower() in lower_name or kw.lower() in lower_group:
            return "中国"

    # 按关键词长度降序匹配（英文关键词要求词边界，避免 rt 命中 puerto 等误伤）
    for kw, code in sorted(_COUNTRY_CODE_MAP.items(), key=lambda x: -len(x[0])):
        if _country_kw_matches(lower_name, kw) or _country_kw_matches(lower_group, kw):
            return _COUNTRY_NAME_ZH.get(code, code)

    return ""


def _scalar(session, query):
    result = session.execute(query)
    return result.scalar()


class ReadModel:
    def __init__(self, event_store: EventStore):
        self._store = event_store
        self._lock = threading.Lock()
        # 按需物化互斥锁：同一时刻只允许一个线程补物化，避免并发重复物化
        self._mat_lock = threading.Lock()
        # 筛选项结果缓存（按 session+参数），避免页面加载/筛选切换时反复全量聚合。
        # 用 cachetools.TTLCache 替代手写过期时间戳字典：自带容量上限与过期逐出，
        # 避免长期运行内存无限增长（现有调用点统一使用 120s TTL）。
        self._filter_cache: TTLCache = TTLCache(maxsize=1024, ttl=120)

    def _session(self) -> Session:
        return self._store.get_session()

    def _cached_filter(self, key: str, ttl: float, fn):
        """TTL 缓存：检测/复检完成后数据才变化，短 TTL 内直接复用聚合结果。"""
        try:
            return self._filter_cache[key]
        except KeyError:
            val = fn()
            self._filter_cache[key] = val
            return val

    def clear_filter_cache(self) -> None:
        self._filter_cache.clear()

    _CN_NAME_KEYWORDS = [
        "CCTV", "cctv", "央视", "中央", "卫视",
        "湖南", "浙江", "江苏", "东方", "北京", "山东", "广东", "深圳",
        "湖北", "四川", "重庆", "天津", "辽宁", "安徽", "江西", "河南",
        "河北", "山西", "陕西", "甘肃", "青海", "宁夏", "新疆", "内蒙古",
        "广西", "西藏", "贵州", "云南", "海南", "吉林", "黑龙江", "福建",
        "上海", "广州", "成都", "武汉", "杭州", "南京", "苏州", "长沙",
        "春晚", "CGTN",
        # 中国大陆地方台通用命名特征（县级台名称多以 XX综合/XX新闻 结尾，词表无法穷举）
        "综合", "新闻", "中国",
        # 高频广电特征词：数字频道命名（敦化一套）、党政频道（党建）、电影厂频道（长影）
        "一套", "二套", "三套", "党建", "长影",
        # 中央广播电视总台外宣（CRI/CNR 系列英文台）与中国广电品牌/景区内容
        "CRI", "CNR", "快乐垂钓", "梨园", "风景区",
    ]

    _COUNTRY_KEYWORDS = {
        "US": ["USA", "American", "CNN", "HBO", "ABC", "NBC", "CBS", "Fox", "ESPN", "PBS"],
        "GB": ["UK", "British", "BBC", "Sky", "ITV", "Channel4"],
        "JP": ["JP", "JPN", "Japanese", "NHK", "TBS", "Fuji", "Asahi"],
        "KR": ["KR", "KOR", "Korean", "KBS", "SBS", "MBC", "JTBC"],
        "FR": ["FR", "FRA", "French", "France", "TF1", "Canal+"],
        "DE": ["DE", "DEU", "German", "DW", "ZDF", "ARD"],
        "RU": ["RU", "RUS", "Russian", "RT", "Channel One"],
        "IN": ["IN", "IND", "Indian", "Zee", "Sony", "NDTV"],
        "AE": ["AE", "阿联酋", "Al Arabiya"],
        "SA": ["SA", "沙特", "Al Jazeera"],
    }

    def _cn_match_keywords(self) -> list[str]:
        """中国频道判定的完整关键词集：主关键词 + 全量省市区县词 + 县级名录地名词。

        仅用大省/大市关键词会漏掉名称只含地市/区县名的国内地方台（如"湖州公共民生"、
        "龙泉新闻综合"、"龙井一套"），反向排除中国时这些台会残留。
        此处并入 UI 省级联动用的 _CN_REGION_KEYWORDS 全量词表（省/市/区县/港澳台），
        以及国家广电总局《县级广播电视播出机构名录》提取的全国县级标准地名
        （CN_COUNTY_KEYWORDS），使中国判定覆盖到纯县名命名的地方台。
        """
        seen = set(self._CN_NAME_KEYWORDS)
        kws = list(self._CN_NAME_KEYWORDS)
        for _rname, _rkws in _CN_REGION_KEYWORDS:
            for kw in _rkws:
                if kw not in seen:
                    seen.add(kw)
                    kws.append(kw)
        for kw in CN_COUNTY_KEYWORDS:
            if kw not in seen:
                seen.add(kw)
                kws.append(kw)
        return kws

    # 央视/卫视类主词：同时匹配分组列，兜底"分组含关键词但名称不含"的源
    _CN_GROUP_KW = ("CCTV", "cctv", "央视", "中央", "卫视")

    @staticmethod
    def _lit_like(col: str, kw: str) -> str:
        # 内部常量词直接拼为 SQL 字面量（非用户输入，无注入风险）
        return f"{col} LIKE '%{kw.replace(chr(39), chr(39) * 2)}%'"

    def _cn_name_like_clause(self, name_col: str) -> tuple[str, str]:
        """中国名称关键词拆分为 (ascii_or, multibyte_or) 两个 SQL 片段。

        - ascii_or：CCTV/CGTN/CRI/CNR 等纯 ASCII 词（中国外宣/央视台为英文名），
          不设多字节前置，否则这些纯英文名的中国台会被误判为非中国；
        - multibyte_or：中文为主的省市区县+县级名录词（约 2400 个），按 180/组分块
          OR 拼接。单个 OR 表达式会让 SQLite 报 "Expression tree is too large
          (maximum depth 1000)"，故分块后组间再 OR；并配合调用方的"含多字节字符"
          前置条件，让纯英文频道快速短路数千个 LIKE。
        """
        words = self._cn_match_keywords()
        ascii_words = [w for w in words if all(ord(ch) < 128 for ch in w)]
        mb_words = [w for w in words if not all(ord(ch) < 128 for ch in w)]
        ascii_or = " OR ".join(self._lit_like(name_col, w) for w in ascii_words) if ascii_words else ""
        parts = [
            "(" + " OR ".join(self._lit_like(name_col, w) for w in mb_words[i:i + 180]) + ")"
            for i in range(0, len(mb_words), 180)
        ]
        return ascii_or, " OR ".join(parts)

    def _cn_group_like_or(self, group_col: str) -> str:
        return "(" + " OR ".join(self._lit_like(group_col, kw) for kw in self._CN_GROUP_KW) + ")"

    def _get_country_condition(self, country_codes: list[str], name_col: str = "name", group_col: str = "channel_group", country_col: str = "country", exclude: bool = False) -> tuple:
        """生成国家筛选的SQL条件。

        筛选逻辑：
        - CN：country字段匹配CN/CHN/HK/MO/TW **或** 名称含中国关键词（主词+省市区县+县级名录）
            央视/卫视主词同时匹配分组列，兜底"分组含央视/卫视、名称不含"的源
        - 其他国家：country字段匹配 **或** 名称/分组含该国特征关键词
        - exclude=True 时返回 NOT(...)（反向筛选：排除这些国家的频道）

        country_codes 中他国代码来自用户请求参数，用 :name 绑定参数；中国关键词为
        内部常量（非用户输入），直接拼字面量以规避数千绑定参数/表达式深度限制。
        返回 (SQL 片段, 参数 dict)；无条件时返回 ("", {})。
        """
        is_cn_filter = any(c.upper() in _CN_COUNTRY_CODES for c in country_codes)
        non_cn_codes = [c for c in country_codes if c.upper() not in _CN_COUNTRY_CODES]

        conditions = []
        params = {}
        pi = 0

        def _like_param(col: str, value: str) -> str:
            nonlocal pi
            key = f"country_{pi}"
            params[key] = f"%{value}%"
            pi += 1
            return f"{col} LIKE :{key}"

        if is_cn_filter:
            # 中国频道：country 元数据命中 OR 名称含中国关键词 OR 央视/卫视词命中分组。
            # 名称关键词拆两段：ASCII 词（CCTV/CRI/CNR 等）不设多字节前置；
            # 中文为主的词带"含多字节字符"前置条件，纯英文频道快速短路数千 LIKE。
            cn_code_lits = " OR ".join(f"{country_col} LIKE '%{c}%'" for c in _CN_COUNTRY_CODES)
            ascii_or, mb_or = self._cn_name_like_clause(name_col)
            mb_guard = f"length({name_col}) < length(CAST({name_col} AS BLOB))"
            _cn_segs = [f"({cn_code_lits})"]
            if ascii_or:
                _cn_segs.append(f"({ascii_or})")
            _cn_segs.append(f"({mb_guard} AND ({mb_or}))")
            _cn_segs.append(self._cn_group_like_or(group_col))
            conditions.append("(" + " OR ".join(_cn_segs) + ")")

        for code in non_cn_codes:
            upper_code = code.upper()
            code_conds = [_like_param(country_col, upper_code)]
            keywords = self._COUNTRY_KEYWORDS.get(upper_code, [])
            for kw in keywords:
                if len(kw) > 2:
                    code_conds.append(_like_param(name_col, kw))
                    code_conds.append(_like_param(group_col, kw))
            conditions.append(f"({' OR '.join(code_conds)})")

        if conditions:
            cond_sql = f"({' OR '.join(conditions)})"
            if exclude:
                cond_sql = f"NOT {cond_sql}"
            return cond_sql, params
        return "", params

    def _get_country_condition_for_json(self, country_codes: list[str], exclude: bool = False) -> tuple:
        """生成针对check_events表中JSON字段的国家筛选SQL条件（参数化）
        exclude=True 时返回 NOT(...)（反向筛选：排除这些国家的频道）"""
        is_cn_filter = any(c.upper() in _CN_COUNTRY_CODES for c in country_codes)
        non_cn_codes = [c for c in country_codes if c.upper() not in _CN_COUNTRY_CODES]

        n = "json_extract(payload, '$.name')"
        g = "json_extract(payload, '$.group')"
        c = "json_extract(payload, '$.country')"

        conditions = []
        params = {}
        pi = 0

        def _like_param(col: str, value: str) -> str:
            nonlocal pi
            key = f"countryj_{pi}"
            params[key] = f"%{value}%"
            pi += 1
            return f"{col} LIKE :{key}"

        if is_cn_filter:
            # 与物化表版本同构：country 元数据 OR 名称关键词 OR 央视/卫视命中分组
            cn_code_lits = " OR ".join(f"{c} LIKE '%{code}%'" for code in _CN_COUNTRY_CODES)
            ascii_or, mb_or = self._cn_name_like_clause(n)
            mb_guard = f"length({n}) < length(CAST({n} AS BLOB))"
            _cn_segs = [f"({cn_code_lits})"]
            if ascii_or:
                _cn_segs.append(f"({ascii_or})")
            _cn_segs.append(f"({mb_guard} AND ({mb_or}))")
            _cn_segs.append(self._cn_group_like_or(g))
            conditions.append("(" + " OR ".join(_cn_segs) + ")")

        for code in non_cn_codes:
            upper_code = code.upper()
            code_conds = [_like_param(c, upper_code)]
            keywords = self._COUNTRY_KEYWORDS.get(upper_code, [])
            for kw in keywords:
                if len(kw) > 2:
                    code_conds.append(_like_param(n, kw))
                    code_conds.append(_like_param(g, kw))
            conditions.append(f"({' OR '.join(code_conds)})")

        if conditions:
            cond_sql = f"({' OR '.join(conditions)})"
            if exclude:
                cond_sql = f"NOT {cond_sql}"
            return cond_sql, params
        return "", params

    def _get_region_condition(self, region_code: str, name_col: str = "name", group_col: str = "channel_group") -> str:
        """生成中国省级行政区筛选的SQL条件（物化表版本）"""
        region_info = _CN_REGION_MAP.get(region_code.upper())
        if not region_info:
            return ""
        conds = []
        for kw in region_info["keywords"]:
            conds.append(f"{name_col} LIKE '%{kw}%'")
            conds.append(f"{group_col} LIKE '%{kw}%'")
        return f"({' OR '.join(conds)})"

    def _get_region_condition_for_json(self, region_code: str) -> str:
        """生成中国省级行政区筛选的SQL条件（JSON字段版本）"""
        region_info = _CN_REGION_MAP.get(region_code.upper())
        if not region_info:
            return ""
        n = "json_extract(payload, '$.name')"
        g = "json_extract(payload, '$.group')"
        conds = []
        for kw in region_info["keywords"]:
            conds.append(f"{n} LIKE '%{kw}%'")
            conds.append(f"{g} LIKE '%{kw}%'")
        return f"({' OR '.join(conds)})"

    def _get_category_condition(self, category: str) -> str:
        """生成内容分类筛选的SQL条件（内容来源维度）"""
        if category == "央视":
            return "(name LIKE '%CCTV%' OR name LIKE '%央视%' OR name LIKE '%中央%')"
        elif category == "卫视":
            return "(name LIKE '%卫视%' OR channel_group LIKE '%卫视%')"
        elif category == "地方":
            return "(name LIKE '%地方%' OR name LIKE '%本地%' OR name LIKE '%市%' OR name LIKE '%区%' OR name LIKE '%县%')"
        elif category == "国际电视":
            non_cn_country_conds = []
            for code in _CN_COUNTRY_CODES:
                non_cn_country_conds.append(f"country NOT LIKE '%{code}%'")
            country_cond = f"(country != '' AND {' AND '.join(non_cn_country_conds)})"
            name_conds = []
            for country_name, keywords in _INTERNATIONAL_COUNTRY_GROUPS.items():
                for kw in keywords:
                    if len(kw) > 2:
                        name_conds.append(f"(name LIKE '%{kw}%' OR channel_group LIKE '%{kw}%')")
            for kw in _INTERNATIONAL_GROUP_KEYWORDS:
                if len(kw) > 2:
                    name_conds.append(f"(name LIKE '%{kw}%' OR channel_group LIKE '%{kw}%')")
            if name_conds:
                return f"({country_cond} OR ({' OR '.join(name_conds)}))"
            else:
                return country_cond
        elif category == "专题":
            conditions = []
            for kw in _SPECIALIZED_GROUP_KEYWORDS:
                conditions.append(f"(name LIKE '%{kw}%' OR channel_group LIKE '%{kw}%')")
            if conditions:
                return f"({' OR '.join(conditions)})"
        elif category == "未分类":
            all_cats = ["央视", "卫视", "地方", "国际电视", "专题"]
            exclude_conditions = []
            for c in all_cats:
                exc = self._get_category_condition(c)
                if exc:
                    exclude_conditions.append(f"NOT ({exc})")
            if exclude_conditions:
                return f"({' AND '.join(exclude_conditions)})"
        return ""

    def _get_category_condition_for_json(self, category: str) -> str:
        """生成针对check_events表JSON字段的内容分类筛选SQL条件"""
        n = "json_extract(payload, '$.name')"
        g = "json_extract(payload, '$.group')"
        c = "json_extract(payload, '$.country')"
        if category == "央视":
            return f"({n} LIKE '%CCTV%' OR {n} LIKE '%央视%' OR {n} LIKE '%中央%')"
        elif category == "卫视":
            return f"({n} LIKE '%卫视%' OR {g} LIKE '%卫视%')"
        elif category == "地方":
            return f"({n} LIKE '%地方%' OR {n} LIKE '%本地%' OR {n} LIKE '%市%' OR {n} LIKE '%区%' OR {n} LIKE '%县%')"
        elif category == "国际电视":
            non_cn = []
            for code in _CN_COUNTRY_CODES:
                non_cn.append(f"{c} NOT LIKE '%{code}%'")
            cc = f"({c} != '' AND {' AND '.join(non_cn)})"
            nc = []
            for country_name, keywords in _INTERNATIONAL_COUNTRY_GROUPS.items():
                for kw in keywords:
                    if len(kw) > 2:
                        nc.append(f"({n} LIKE '%{kw}%' OR {g} LIKE '%{kw}%')")
            for kw in _INTERNATIONAL_GROUP_KEYWORDS:
                if len(kw) > 2:
                    nc.append(f"({n} LIKE '%{kw}%' OR {g} LIKE '%{kw}%')")
            if nc:
                return f"({cc} OR ({' OR '.join(nc)}))"
            else:
                return cc
        elif category == "专题":
            conditions = []
            for kw in _SPECIALIZED_GROUP_KEYWORDS:
                conditions.append(f"({n} LIKE '%{kw}%' OR {g} LIKE '%{kw}%')")
            if conditions:
                return f"({' OR '.join(conditions)})"
        elif category == "未分类":
            all_cats = ["央视", "卫视", "地方", "国际电视", "专题"]
            exclude = []
            for ct in all_cats:
                exc = self._get_category_condition_for_json(ct)
                if exc:
                    exclude.append(f"NOT ({exc})")
            if exclude:
                return f"({' AND '.join(exclude)})"
        return ""

    def _get_quality_condition(self, quality: str) -> str:
        """生成画质筛选的SQL条件"""
        if quality == "4K":
            return "(name LIKE '%4K%' OR name LIKE '%UHD%' OR name LIKE '%超清%' OR channel_group LIKE '%4K%' OR channel_group LIKE '%UHD%' OR channel_group LIKE '%超清%')"
        elif quality == "HD":
            return "(name LIKE '%HD%' OR name LIKE '%高清%' OR channel_group LIKE '%HD%' OR channel_group LIKE '%高清%')"
        elif quality == "SD":
            return "(name NOT LIKE '%4K%' AND name NOT LIKE '%UHD%' AND name NOT LIKE '%超清%' AND name NOT LIKE '%HD%' AND name NOT LIKE '%高清%' AND channel_group NOT LIKE '%4K%' AND channel_group NOT LIKE '%UHD%' AND channel_group NOT LIKE '%超清%' AND channel_group NOT LIKE '%HD%' AND channel_group NOT LIKE '%高清%')"
        return ""

    def _get_quality_condition_for_json(self, quality: str) -> str:
        """生成针对check_events表JSON字段的画质筛选SQL条件"""
        n = "json_extract(payload, '$.name')"
        g = "json_extract(payload, '$.group')"
        if quality == "4K":
            return f"({n} LIKE '%4K%' OR {n} LIKE '%UHD%' OR {n} LIKE '%超清%' OR {g} LIKE '%4K%' OR {g} LIKE '%UHD%' OR {g} LIKE '%超清%')"
        elif quality == "HD":
            return f"({n} LIKE '%HD%' OR {n} LIKE '%高清%' OR {g} LIKE '%HD%' OR {g} LIKE '%高清%')"
        elif quality == "SD":
            return f"({n} NOT LIKE '%4K%' AND {n} NOT LIKE '%UHD%' AND {n} NOT LIKE '%超清%' AND {n} NOT LIKE '%HD%' AND {n} NOT LIKE '%高清%' AND {g} NOT LIKE '%4K%' AND {g} NOT LIKE '%UHD%' AND {g} NOT LIKE '%超清%' AND {g} NOT LIKE '%HD%' AND {g} NOT LIKE '%高清%')"
        return ""

    def _get_protocol_condition(self, protocol: str) -> str:
        """生成协议筛选的SQL条件"""
        if protocol == "IPv6":
            return "(name LIKE '%IPv6%' OR name LIKE '%ipv6%' OR channel_group LIKE '%IPv6%' OR channel_group LIKE '%ipv6%')"
        elif protocol == "IPv4":
            return "(name NOT LIKE '%IPv6%' AND name NOT LIKE '%ipv6%' AND channel_group NOT LIKE '%IPv6%' AND channel_group NOT LIKE '%ipv6%')"
        return ""

    def _get_protocol_condition_for_json(self, protocol: str) -> str:
        """生成针对check_events表JSON字段的协议筛选SQL条件"""
        n = "json_extract(payload, '$.name')"
        g = "json_extract(payload, '$.group')"
        if protocol == "IPv6":
            return f"({n} LIKE '%IPv6%' OR {n} LIKE '%ipv6%' OR {g} LIKE '%IPv6%' OR {g} LIKE '%ipv6%')"
        elif protocol == "IPv4":
            return f"({n} NOT LIKE '%IPv6%' AND {n} NOT LIKE '%ipv6%' AND {g} NOT LIKE '%IPv6%' AND {g} NOT LIKE '%ipv6%')"
        return ""

    def get_check_progress(self, session_id: str = None) -> dict:
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"total": 0, "checked": 0, "valid": 0, "likely_valid": 0, "invalid": 0, "is_running": False, "progress_percent": 0.0}
        with self._session() as session:
            row = session.exec(sa_text("""
                SELECT
                    (SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_submitted') AS total,
                    (SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked') AS checked,
                    (SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.is_valid') = 1 AND COALESCE(json_extract(payload, '$.quality_tier'), 'valid') = 'valid') AS valid,
                    (SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND COALESCE(json_extract(payload, '$.quality_tier'), 'invalid') = 'likely_valid') AS likely_valid,
                    (SELECT COUNT(*) FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.quality_tier') = 'stopped') AS stopped,
                    (SELECT 1 FROM check_events WHERE session_id = :sid AND event_type = 'check_started' LIMIT 1) AS started,
                    (SELECT event_type FROM check_events WHERE session_id = :sid AND event_type IN ('check_completed', 'check_stopped', 'check_failed') ORDER BY created_at DESC LIMIT 1) AS final_event
            """).bindparams(sid=sid)).first()

            total_result = row[0] or 0
            checked_result = row[1] or 0
            valid_result = row[2] or 0
            likely_valid_result = row[3] or 0
            stopped_result = row[4] or 0
            is_running = row[5] is not None and row[6] is None

            progress = min((checked_result / total_result * 100) if total_result > 0 else 0.0, 100.0)

            return {
                "total": total_result,
                "checked": min(checked_result, total_result) if total_result > 0 else checked_result,
                "valid": valid_result,
                "likely_valid": likely_valid_result,
                "invalid": checked_result - valid_result - likely_valid_result - stopped_result,
                "is_running": is_running,
                "progress_percent": round(progress, 1),
            }

    def get_phase(self, session_id: str = None) -> str:
        sid = session_id or self._store.current_session_id
        if not sid:
            return "idle"

        with self._session() as session:
            row = session.exec(sa_text("""
                SELECT
                    (SELECT event_type FROM check_events WHERE session_id = :sid AND event_type IN ('check_completed', 'check_stopped', 'check_failed') ORDER BY created_at DESC LIMIT 1) AS final_event,
                    (SELECT 1 FROM check_events WHERE session_id = :sid AND event_type = 'check_started' LIMIT 1) AS started,
                    (SELECT 1 FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' LIMIT 1) AS checking
            """).bindparams(sid=sid)).first()

            if row[0] is not None:
                etype = row[0][0] if isinstance(row[0], tuple) else row[0]
                if etype == "check_stopped":
                    return "stopped"
                if etype == "check_failed":
                    return "failed"
                return "completed"

            if row[1] is None:
                return "idle"

            if row[2] is not None:
                return "checking"

            return "downloading"

    def get_source_download_stats(self, session_id: str = None) -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            results = session.exec(
                sa_text("""
                    SELECT
                        json_extract(payload, '$.source_name') as source_name,
                        json_extract(payload, '$.channel_count') as channel_count,
                        json_extract(payload, '$.success') as success
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'source_downloaded'
                    ORDER BY created_at ASC
                """).bindparams(sid=sid)
            ).all()

            return [
                {"source_name": r[0] or "unknown", "channel_count": r[1] or 0, "success": bool(r[2])}
                for r in results
            ]

    def get_available_sources(self, session_id: str = None) -> list:
        """返回当前 session 实际下载过的来源源列表（来自 source_downloaded 事件）。

        修复前从每个 channel 的 sources 字段去重提取，但旧版本曾把 M3U 频道名碎片写入
        sources，导致来源筛选出现上万个无意义条目。改为读取 source_downloaded 事件中
        的真实下载源名（排除"频道级源"等占位符），语义更准确且天然去脏。
        """
        sid = session_id or self._store.current_session_id
        if not sid:
            return []
        try:
            with self._session() as session:
                rows = session.exec(sa_text("""
                    SELECT DISTINCT json_extract(payload, '$.source_name') AS source_name
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'source_downloaded'
                      AND json_extract(payload, '$.source_name') IS NOT NULL
                """).bindparams(sid=sid)).all()
                sources = set()
                for (name,) in rows:
                    name = (name or "").strip()
                    if name and name not in ("频道级源", "列表级源", "N/A"):
                        sources.add(name)
                return sorted(sources)
        except Exception:
            return []

    def get_full_state(self, session_id: str = None) -> dict:
        progress = self.get_check_progress(session_id)
        phase = self.get_phase(session_id)
        sources = self.get_source_download_stats(session_id)
        return {
            "phase": phase,
            **progress,
            "sources": sources,
        }

    @staticmethod
    def _build_source_condition(column: str, source: str):
        """构造来源源筛选条件（channel_results.sources 为 JSON 数组字符串）"""
        sources_list = [s.strip() for s in source.split(",") if s.strip()]
        if not sources_list:
            return "", {}
        clauses = []
        params = {}
        for i, s in enumerate(sources_list):
            p = f"source_like_{i}"
            clauses.append(f"{column} LIKE :{p}")
            params[p] = f"%{s}%"
        return "(" + " OR ".join(clauses) + ")", params

    def _build_mat_conditions(self, tab: str, media_type: str, language: str,
                               country: str, region: str, category: str,
                               quality: str, protocol: str, source: str,
                               latency_min: float, latency_max: float,
                               speed_min: float, speed_max: float,
                               params: dict, country_exclude: str = "",
                               hide_vod: bool = False) -> list:
        """构建物化表 channel_results 的筛选 WHERE 条件（不含 search，供查询与取 URL 复用）。
        country_exclude 非空时对指定国家做反向筛选（排除）；hide_vod=True 过滤点播/轮播假台。"""
        conditions = ["session_id = :sid"]
        if tab == "valid":
            conditions.append("is_valid = 1 AND quality_tier = 'valid'")
        elif tab == "invalid":
            conditions.append("COALESCE(quality_tier, CASE WHEN is_valid = 1 THEN 'valid' ELSE 'invalid' END) = 'invalid'")
        elif tab == "likely_valid":
            conditions.append("quality_tier = 'likely_valid'")
        conditions.append(_junk_name_exclude_condition("name"))
        if hide_vod:
            conditions.append(f"NOT {_vod_content_sql()}")
        if media_type == "tv":
            conditions.append("is_radio = 0")
        elif media_type == "radio":
            conditions.append("is_radio = 1")
        if language:
            conditions.append("LOWER(language) = LOWER(:language)")
            params["language"] = language
        if country_exclude:
            countries = [c.strip() for c in country_exclude.split(",") if c.strip()]
            if countries:
                country_condition, country_params = self._get_country_condition(countries, exclude=True)
                if country_condition:
                    conditions.append(country_condition)
                    params.update(country_params)
        elif country:
            countries = [c.strip() for c in country.split(",") if c.strip()]
            if countries:
                country_condition, country_params = self._get_country_condition(countries)
                if country_condition:
                    conditions.append(country_condition)
                    params.update(country_params)
        if region:
            region_condition = self._get_region_condition(region)
            if region_condition:
                conditions.append(region_condition)
        if category:
            cat_condition = self._get_category_condition(category)
            if cat_condition:
                conditions.append(cat_condition)
        if quality:
            q_condition = self._get_quality_condition(quality)
            if q_condition:
                conditions.append(q_condition)
        if protocol:
            p_condition = self._get_protocol_condition(protocol)
            if p_condition:
                conditions.append(p_condition)
        if source:
            src_condition, src_params = self._build_source_condition("sources", source)
            if src_condition:
                conditions.append(src_condition)
                params.update(src_params)
        if latency_min >= 0:
            conditions.append("latency >= :latency_min")
            params["latency_min"] = latency_min
        if latency_max >= 0 and latency_max >= latency_min:
            conditions.append("latency <= :latency_max")
            params["latency_max"] = latency_max
        if speed_min >= 0:
            conditions.append("speed != '-'")
            params["speed_min"] = speed_min
        if speed_max >= 0 and speed_max >= speed_min:
            conditions.append("speed != '-'")
            params["speed_max"] = speed_max
        return conditions

    def fetch_filtered_urls(self, session_id: str = None, tab: str = "all",
                            media_type: str = "all", language: str = "",
                            country: str = "", region: str = "",
                            category: str = "", quality: str = "", protocol: str = "",
                            source: str = "",
                            latency_min: float = -1, latency_max: float = -1,
                            speed_min: float = -1, speed_max: float = -1,
                            search: str = "", country_exclude: str = "",
                            hide_vod: bool = False):
        """返回符合筛选条件的全部频道 URL（跨页全集）及去重后的频道数。
        返回 (urls: list[str], channel_count: int)。供彻底版检测/跨页全选使用。
        复用 get_checked_channels 的筛选逻辑（兼容物化表与 check_events 两条路径）。
        注：始终走平铺(flat)路径——分组(get_grouped_channels)路径的分页无法覆盖全集（既有 bug），
        而 flat 路径对任意筛选条件/规模都准确，且返回的每个 URL 都是可独立检测的流地址。"""
        sid = session_id or self._store.current_session_id
        if not sid:
            return [], 0
        result = self.get_checked_channels(
            session_id=sid, tab=tab, page=1, per_page=1_000_000, search=search, sort="best",
            media_type=media_type, language=language, country=country, region=region,
            category=category, quality=quality, protocol=protocol, source=source,
            latency_min=latency_min, latency_max=latency_max,
            speed_min=speed_min, speed_max=speed_max,
            country_exclude=country_exclude,
            hide_vod=hide_vod,
        )
        items = result.get("items", [])
        urls = [item["url"] for item in items if item.get("url")]
        names = {item.get("name") or "" for item in items}
        names.discard("")
        return urls, len(names)

    def fetch_filtered_counts(self, session_id: str = None, tab: str = "all",
                              media_type: str = "all", language: str = "",
                              country: str = "", region: str = "",
                              category: str = "", quality: str = "", protocol: str = "",
                              source: str = "",
                              latency_min: float = -1, latency_max: float = -1,
                              speed_min: float = -1, speed_max: float = -1,
                              search: str = "", country_exclude: str = "",
                              hide_vod: bool = False):
        """轻量返回符合筛选条件的 (频道数, 源地址数)，不拉取 URL 列表。
        复检对话框/确认框用于同时展示"几个频道 / 几个源地址"。"""
        sid = session_id or self._store.current_session_id
        if not sid:
            return 0, 0
        result = self.get_checked_channels(
            session_id=sid, tab=tab, page=1, per_page=1, search=search, sort="best",
            media_type=media_type, language=language, country=country, region=region,
            category=category, quality=quality, protocol=protocol, source=source,
            latency_min=latency_min, latency_max=latency_max,
            speed_min=speed_min, speed_max=speed_max,
            with_tab_counts=True,
            country_exclude=country_exclude,
            hide_vod=hide_vod,
        )
        tc = result.get("tab_counts") or {}
        src = tc.get("source") or {}
        key = tab if tab in ("all", "valid", "likely_valid", "invalid") else "all"
        return tc.get(key, 0) or 0, src.get(key, 0) or 0

    def get_checked_channels(self, session_id: str = None, tab: str = "all",
                             page: int = 1, per_page: int = 50, search: str = "",
                             sort: str = "best",
                             media_type: str = "all", language: str = "",
                             country: str = "", region: str = "",
                             category: str = "", quality: str = "", protocol: str = "",
                             source: str = "",
                             latency_min: float = -1, latency_max: float = -1,
                             speed_min: float = -1, speed_max: float = -1,
                             with_tab_counts: bool = False,
                             country_exclude: str = "",
                             hide_vod: bool = False) -> dict:
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"total": 0, "page": page, "per_page": per_page, "items": []}

        self._ensure_materialized(sid)
        with self._session() as session:
            use_mat = self._has_materialized(session, sid)
            params = {"sid": sid}

            if use_mat:
                conditions = self._build_mat_conditions(
                    tab, media_type, language, country, region, category,
                    quality, protocol, source, latency_min, latency_max, speed_min, speed_max, params,
                    country_exclude=country_exclude,
                    hide_vod=hide_vod,
                )

                where_sql = " AND ".join(conditions)
                total = _scalar(session,
                    sa_text(f"SELECT COUNT(*) FROM channel_results WHERE {where_sql}").bindparams(**params)
                ) or 0

                # 单次 SQL 计算 4 个 tab 的计数（与列表同筛选条件），避免路由层 4 次全表聚合
                tab_counts = None
                if with_tab_counts:
                    count_params = {"sid": sid}
                    all_conds = self._build_mat_conditions(
                        "all", media_type, language, country, region, category,
                        quality, protocol, source, latency_min, latency_max, speed_min, speed_max, count_params,
                        country_exclude=country_exclude,
                        hide_vod=hide_vod,
                    )
                    if search:
                        all_conds.append(
                            "(LOWER(CASE WHEN name = 'N/A' THEN COALESCE(source_name, name) ELSE name END) LIKE :search OR LOWER(url) LIKE :search)"
                        )
                        count_params["search"] = f"%{search.lower()}%"
                    all_where = " AND ".join(all_conds)
                    row = session.exec(sa_text(f"""
                        SELECT
                            COUNT(*) AS src_all,
                            COUNT(DISTINCT CASE WHEN COALESCE(name, '') != '' THEN name END) AS ch_all,
                            COALESCE(SUM(CASE WHEN is_valid = 1 AND quality_tier = 'valid' THEN 1 ELSE 0 END), 0) AS src_valid,
                            COUNT(DISTINCT CASE WHEN is_valid = 1 AND quality_tier = 'valid' AND COALESCE(name, '') != '' THEN name END) AS ch_valid,
                            COALESCE(SUM(CASE WHEN quality_tier = 'likely_valid' THEN 1 ELSE 0 END), 0) AS src_likely,
                            COUNT(DISTINCT CASE WHEN quality_tier = 'likely_valid' AND COALESCE(name, '') != '' THEN name END) AS ch_likely,
                            COALESCE(SUM(CASE WHEN COALESCE(quality_tier, CASE WHEN is_valid = 1 THEN 'valid' ELSE 'invalid' END) = 'invalid' THEN 1 ELSE 0 END), 0) AS src_invalid,
                            COUNT(DISTINCT CASE WHEN COALESCE(quality_tier, CASE WHEN is_valid = 1 THEN 'valid' ELSE 'invalid' END) = 'invalid' AND COALESCE(name, '') != '' THEN name END) AS ch_invalid
                        FROM channel_results WHERE {all_where}
                    """).bindparams(**count_params)).first()
                    tab_counts = {
                        "all": row[1] or 0, "valid": row[3] or 0,
                        "likely_valid": row[5] or 0, "invalid": row[7] or 0,
                        "source": {
                            "all": row[0] or 0, "valid": row[2] or 0,
                            "likely_valid": row[4] or 0, "invalid": row[6] or 0,
                        },
                    }

                search_conditions = list(conditions)
                search_params = dict(params)
                if search:
                    search_conditions.append("(LOWER(CASE WHEN name = 'N/A' THEN COALESCE(source_name, name) ELSE name END) LIKE :search OR LOWER(url) LIKE :search)")
                    search_params["search"] = f"%{search.lower()}%"

                search_where = " AND ".join(search_conditions)
                total_with_search = _scalar(session,
                    sa_text(f"SELECT COUNT(*) FROM channel_results WHERE {search_where}").bindparams(**search_params)
                ) or 0

                offset = (page - 1) * per_page
                query_params = dict(search_params)
                query_params["limit"] = per_page
                query_params["offset"] = offset

                _sort_map_mat = {
                    "best": "CASE WHEN quality_tier = 'valid' THEN 0 WHEN quality_tier = 'likely_valid' THEN 1 ELSE 2 END, CASE WHEN latency IS NULL OR latency < 0 THEN 999999 ELSE latency END ASC",
                    "name_asc":   "name ASC",
                    "name_desc":  "name DESC",
                    "latency_asc":  "CASE WHEN latency IS NULL OR latency < 0 THEN 999999 ELSE latency END ASC",
                    "latency_desc": "latency DESC",
                    "speed_asc":  "CASE WHEN speed = '-' THEN 999999999 ELSE CAST(speed AS REAL) END ASC",
                    "speed_desc": "CAST(speed AS REAL) DESC",
                }
                _order = _sort_map_mat.get(sort, _sort_map_mat["best"])

                results = session.exec(sa_text(f"""
                    SELECT name, url, is_valid, latency, speed, details, channel_group, sources, quality_tier, is_radio, tvg_name, clean_name, country, frequency
                    FROM channel_results
                    WHERE {search_where}
                    ORDER BY {_order}
                    LIMIT :limit OFFSET :offset
                """).bindparams(**query_params)).all()

                items = []
                for idx, r in enumerate(results):
                    is_valid = bool(r[2])
                    quality_tier = r[8] or ("valid" if is_valid else "invalid")
                    clean_name_val = r[11] or ""
                    raw_name = r[0] or ""
                    name_val = raw_name
                    if name_val == "N/A":
                        sources_val = r[7] or ""
                        if sources_val and sources_val != "N/A" and sources_val != "[]":
                            try:
                                src_list = json.loads(sources_val)
                                if src_list and isinstance(src_list, list):
                                    name_val = str(src_list[0])
                            except (json.JSONDecodeError, TypeError):
                                name_val = sources_val
                    name_cn_val = clean_name_val
                    if clean_name_val and clean_name_val != name_val:
                        pass
                    elif clean_name_val and clean_name_val == name_val:
                        name_cn_val = ""
                    if not name_cn_val:
                        from iptv_check.core.parser import _translate_channel_name
                        name_cn_val = _translate_channel_name(raw_name, r[10] or "")
                    from iptv_check.core.parser import _infer_country_code
                    country_val = r[12] or ""
                    country_code = _infer_country_code(raw_name, r[6] or "", country_val)
                    region_val = _infer_region(raw_name, r[6] or "", country_code)
                    items.append({
                        "index": offset + idx + 1,
                        "name": name_val,
                        "name_cn": name_cn_val,
                        "url": r[1] or "",
                        "group": _map_group_name(r[6] or ""),
                        "region": region_val,
                        "sources": r[7] or "",
                        "is_valid": is_valid,
                        "quality_tier": quality_tier,
                        "status": "有效" if quality_tier == "valid" else ("疑似有效" if quality_tier == "likely_valid" else "无效"),
                        "latency": str(int(r[3])) if r[3] is not None and r[3] >= 0 else "-",
                        "speed": r[4] or "-",
                        "details": r[5] or "",
                        "is_radio": bool(r[9]),
                        "tvg_name": r[10] or "",
                        "clean_name": clean_name_val,
                        "country": country_code,
                        "frequency": r[13] or "",
                    })

                ret = {"total": total_with_search, "page": page, "per_page": per_page, "items": items}
                if with_tab_counts and tab_counts:
                    ret["tab_counts"] = tab_counts
                return ret

            conditions = ["session_id = :sid", "event_type = 'channel_checked'"]

            if tab == "valid":
                conditions.append("json_extract(payload, '$.is_valid') = 1 AND COALESCE(json_extract(payload, '$.quality_tier'), 'valid') = 'valid'")
            elif tab == "invalid":
                conditions.append("COALESCE(json_extract(payload, '$.quality_tier'), CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 'valid' ELSE 'invalid' END) = 'invalid'")
            elif tab == "likely_valid":
                conditions.append("COALESCE(json_extract(payload, '$.quality_tier'), 'invalid') = 'likely_valid'")

            conditions.append(_junk_name_exclude_condition("json_extract(payload, '$.name')"))
            if hide_vod:
                _vod_sql = _vod_content_sql(
                    name_col="json_extract(payload, '$.name')",
                    url_col="json_extract(payload, '$.url')",
                )
                conditions.append(f"NOT {_vod_sql}")

            if media_type == "tv":
                conditions.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
            elif media_type == "radio":
                conditions.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")

            if language:
                conditions.append("LOWER(json_extract(payload, '$.language')) = LOWER(:language)")
                params["language"] = language
            if country_exclude:
                countries = [c.strip() for c in country_exclude.split(",") if c.strip()]
                if countries:
                    country_condition, country_params = self._get_country_condition_for_json(countries, exclude=True)
                    if country_condition:
                        conditions.append(country_condition)
                        params.update(country_params)
            elif country:
                countries = [c.strip() for c in country.split(",") if c.strip()]
                if countries:
                    country_condition, country_params = self._get_country_condition_for_json(countries)
                    if country_condition:
                        conditions.append(country_condition)
                        params.update(country_params)
            if region:
                region_condition = self._get_region_condition_for_json(region)
                if region_condition:
                    conditions.append(region_condition)
            if category:
                cat_condition = self._get_category_condition_for_json(category)
                if cat_condition:
                    conditions.append(cat_condition)
            if quality:
                q_condition = self._get_quality_condition_for_json(quality)
                if q_condition:
                    conditions.append(q_condition)
            if protocol:
                p_condition = self._get_protocol_condition_for_json(protocol)
                if p_condition:
                    conditions.append(p_condition)
            if source:
                src_condition, src_params = self._build_source_condition("json_extract(payload, '$.sources')", source)
                if src_condition:
                    conditions.append(src_condition)
                    params.update(src_params)
            if latency_min >= 0:
                conditions.append("CAST(json_extract(payload, '$.latency') AS REAL) >= :latency_min")
                params["latency_min"] = latency_min
            if latency_max >= 0 and latency_max >= latency_min:
                conditions.append("CAST(json_extract(payload, '$.latency') AS REAL) <= :latency_max")
                params["latency_max"] = latency_max
            if speed_min >= 0:
                conditions.append("json_extract(payload, '$.speed') != '-'")
                params["speed_min"] = speed_min
            if speed_max >= 0 and speed_max >= speed_min:
                conditions.append("json_extract(payload, '$.speed') != '-'")
                params["speed_max"] = speed_max

            where_sql = " AND ".join(conditions)
            total = _scalar(session,
                sa_text(f"SELECT COUNT(*) FROM check_events WHERE {where_sql}").bindparams(**params)
            ) or 0

            search_conditions = list(conditions)
            search_params = dict(params)
            if search:
                search_conditions.append(
                    "(LOWER(CASE WHEN json_extract(payload, '$.name') = 'N/A' THEN COALESCE(json_extract(payload, '$.sources'), 'N/A') ELSE json_extract(payload, '$.name') END) LIKE :search OR LOWER(json_extract(payload, '$.url')) LIKE :search)"
                )
                search_params["search"] = f"%{search.lower()}%"

            search_where = " AND ".join(search_conditions)
            total_with_search = _scalar(session,
                sa_text(f"SELECT COUNT(*) FROM check_events WHERE {search_where}").bindparams(**search_params)
            ) or 0

            search_conditions = list(conditions)
            search_params = dict(params)
            if search:
                search_conditions.append(
                    "(LOWER(CASE WHEN json_extract(payload, '$.name') = 'N/A' THEN COALESCE(json_extract(payload, '$.sources'), 'N/A') ELSE json_extract(payload, '$.name') END) LIKE :search OR LOWER(json_extract(payload, '$.url')) LIKE :search)"
                )
                search_params["search"] = f"%{search.lower()}%"

            search_where = " AND ".join(search_conditions)
            total_with_search = _scalar(session,
                sa_text(f"SELECT COUNT(*) FROM check_events WHERE {search_where}").bindparams(**search_params)
            ) or 0

            offset = (page - 1) * per_page
            query_params = dict(search_params)
            query_params["limit"] = per_page
            query_params["offset"] = offset

            _sort_map_raw = {
                "best": "CASE WHEN json_extract(payload, '$.quality_tier') = 'valid' THEN 0 WHEN json_extract(payload, '$.quality_tier') = 'likely_valid' THEN 1 ELSE 2 END, CASE WHEN CAST(json_extract(payload, '$.latency') AS REAL) IS NULL OR CAST(json_extract(payload, '$.latency') AS REAL) < 0 THEN 999999 ELSE CAST(json_extract(payload, '$.latency') AS REAL) END ASC",
                "name_asc":   "json_extract(payload, '$.name') ASC",
                "name_desc":  "json_extract(payload, '$.name') DESC",
                "latency_asc":  "CASE WHEN CAST(json_extract(payload, '$.latency') AS REAL) IS NULL OR CAST(json_extract(payload, '$.latency') AS REAL) < 0 THEN 999999 ELSE CAST(json_extract(payload, '$.latency') AS REAL) END ASC",
                "latency_desc": "CAST(json_extract(payload, '$.latency') AS REAL) DESC",
                "speed_asc":  "CASE WHEN json_extract(payload, '$.speed') = '-' THEN 999999999 ELSE CAST(json_extract(payload, '$.speed') AS REAL) END ASC",
                "speed_desc": "CAST(json_extract(payload, '$.speed') AS REAL) DESC",
            }
            _order = _sort_map_raw.get(sort, _sort_map_raw["best"])

            results = session.exec(
                sa_text(f"""
                    SELECT
                        json_extract(payload, '$.name') as name,
                        json_extract(payload, '$.url') as url,
                        json_extract(payload, '$.is_valid') as is_valid,
                        json_extract(payload, '$.latency') as latency,
                        json_extract(payload, '$.speed') as speed,
                        json_extract(payload, '$.details') as details,
                        json_extract(payload, '$.group') as grp,
                        json_extract(payload, '$.sources') as sources,
                        json_extract(payload, '$.quality_tier') as quality_tier,
                        json_extract(payload, '$.is_radio') as is_radio,
                        json_extract(payload, '$.tvg_name') as tvg_name,
                        json_extract(payload, '$.clean_name') as clean_name,
                        json_extract(payload, '$.country') as country,
                        json_extract(payload, '$.frequency') as frequency,
                        json_extract(payload, '$.media_type') as media_type
                    FROM check_events
                    WHERE {search_where}
                    ORDER BY {_order}
                    LIMIT :limit OFFSET :offset
                """).bindparams(**query_params)
            ).all()

            items = []
            for idx, r in enumerate(results):
                is_valid = bool(r[2])
                quality_tier = r[8] or ("valid" if is_valid else "invalid")
                clean_name_val = r[11] or ""
                raw_name = r[0] or ""
                name_val = raw_name
                if name_val == "N/A":
                    sources_val = r[7] or ""
                    if sources_val and sources_val != "N/A":
                        name_val = sources_val
                name_cn_val = clean_name_val
                if clean_name_val and clean_name_val != name_val:
                    pass
                elif clean_name_val and clean_name_val == name_val:
                    name_cn_val = ""
                if not name_cn_val:
                    from iptv_check.core.parser import _translate_channel_name
                    name_cn_val = _translate_channel_name(raw_name, r[10] or "")
                from iptv_check.core.parser import _infer_country_code
                country_val = r[12] or ""
                country_code = _infer_country_code(raw_name, r[6] or "", country_val)
                region_val = _infer_region(raw_name, r[6] or "", country_code)
                # 检测事实优先：media_type（流首包/Content-Type 判定）是电视/电台的权威依据
                is_radio_val = bool(r[9])
                media_type_val = (r[14] or "").lower()
                if media_type_val == "audio":
                    is_radio_val = True
                elif media_type_val == "video":
                    is_radio_val = False
                items.append({
                    "index": offset + idx + 1,
                    "name": name_val,
                    "name_cn": name_cn_val,
                    "url": r[1] or "",
                    "group": _map_group_name(r[6] or ""),
                    "region": region_val,
                    "sources": r[7] or "",
                    "is_valid": is_valid,
                    "quality_tier": quality_tier,
                    "status": "有效" if quality_tier == "valid" else ("疑似有效" if quality_tier == "likely_valid" else "无效"),
                    "latency": str(int(r[3])) if r[3] and r[3] != "-" and int(r[3]) >= 0 else "-",
                    "speed": r[4] or "-",
                    "details": r[5] or "",
                    "is_radio": is_radio_val,
                    "tvg_name": r[10] or "",
                    "clean_name": clean_name_val,
                    "country": country_code,
                    "frequency": r[13] or "",
                })

            return {"total": total_with_search, "page": page, "per_page": per_page, "items": items}

    def _has_materialized(self, session: Session, sid: str) -> bool:
        try:
            cnt = session.exec(
                sa_text("SELECT COUNT(*) FROM channel_results WHERE session_id = :sid").bindparams(sid=sid)
            ).scalar()
            return bool(cnt)
        except Exception:
            return False

    def _ensure_materialized(self, session_id: str) -> None:
        """查询前按需物化兜底。

        检测完成时物化可能因 60s 超时/写锁竞争未生效，若此时查询结果页会回退到
        check_events 的 JSON 慢路径（数万行逐行 json_extract，接口可达 7s+）。
        此处检测到"检测已完成但物化缺失"时补一次物化，之后查询走物化快路径。
        检测进行中（check_history 尚无记录）不物化，保持实时查看语义。
        """
        try:
            if not session_id:
                return
            if not self._mat_lock.acquire(blocking=False):
                # 已有线程正在物化，本次直接走原路径
                return
            try:
                with self._session() as s:
                    if self._has_materialized(s, session_id):
                        return
                    hist = s.exec(
                        sa_text("SELECT COUNT(*) FROM check_history WHERE session_id = :sid").bindparams(sid=session_id)
                    ).scalar() or 0
                    if not hist:
                        return  # 检测尚未落历史，视为进行中，不物化
                    cnt = s.exec(
                        sa_text(
                            "SELECT COUNT(*) FROM check_events "
                            "WHERE session_id = :sid AND event_type = 'channel_checked'"
                        ).bindparams(sid=session_id)
                    ).scalar() or 0
                    if cnt < _MATERIALIZE_THRESHOLD:
                        return
                from iptv_check.infra.persistence.materialization import MaterializationService
                mat = MaterializationService(self._store)
                count = mat.materialize_session(session_id)
                logger.info("[按需物化] 会话 %s 补物化 %d 条", session_id, count)
            finally:
                self._mat_lock.release()
        except Exception as e:
            logger.warning("[按需物化] 失败，回退慢路径: %s", e)

    def get_checked_results_raw(self, session_id: str = None) -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            if self._has_materialized(session, sid):
                results = session.exec(
                    sa_text("""
                        SELECT name, url, is_valid, latency, speed, details,
                               channel_group, sources, url_key, quality_tier,
                               is_radio, tvg_name, country, resolution
                        FROM channel_results
                        WHERE session_id = :sid
                        ORDER BY created_at ASC
                    """).bindparams(sid=sid)
                ).all()

                return [
                    {
                        "channel": {
                            "name": r[0] or "",
                            "url": r[1] or "",
                            "group": r[6] or "",
                            "sources": [r[7]] if r[7] else [],
                            "url_key": r[8] or "",
                            "is_radio": bool(r[10]),
                            "tvg_id": "",
                            "tvg_name": r[11] or "",
                            "country": r[12] or "",
                            "resolution": r[13] or "",
                        },
                        "is_valid": bool(r[2]),
                        "quality_tier": r[9] or ("valid" if bool(r[2]) else "invalid"),
                        "latency": float(r[3]) if r[3] is not None and r[3] >= 0 else -1,
                        "speed": r[4] or "-",
                        "details": r[5] or "",
                    }
                    for r in results
                ]

            results = session.exec(
                sa_text("""
                    SELECT
                        json_extract(payload, '$.name'),
                        json_extract(payload, '$.url'),
                        json_extract(payload, '$.is_valid'),
                        json_extract(payload, '$.latency'),
                        json_extract(payload, '$.speed'),
                        json_extract(payload, '$.details'),
                        json_extract(payload, '$.group'),
                        json_extract(payload, '$.sources'),
                        json_extract(payload, '$.url_key'),
                        json_extract(payload, '$.quality_tier'),
                        json_extract(payload, '$.resolution'),
                        json_extract(payload, '$.is_radio'),
                        json_extract(payload, '$.tvg_id'),
                        json_extract(payload, '$.tvg_name'),
                        json_extract(payload, '$.country')
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                    ORDER BY created_at ASC
                """).bindparams(sid=sid)
            ).all()

            return [
                {
                    "channel": {
                        "name": r[0] or "",
                        "url": r[1] or "",
                        "group": r[6] or "",
                        "sources": [r[7]] if r[7] else [],
                        "url_key": r[8] or "",
                        "resolution": r[10] or "",
                        "is_radio": bool(r[11]),
                        "tvg_id": r[12] or "",
                        "tvg_name": r[13] or "",
                        "country": r[14] or "",
                    },
                    "is_valid": bool(r[2]),
                    "quality_tier": r[9] or ("valid" if bool(r[2]) else "invalid"),
                    "latency": float(r[3]) if r[3] and r[3] != "-" and float(r[3]) >= 0 else -1,
                    "speed": r[4] or "-",
                    "details": r[5] or "",
                }
                for r in results
            ]

    def get_grouped_channels(self, session_id: str = None, tab: str = "all",
                             group_path: str = "", page: int = 1, per_page: int = 50,
                             search: str = "", sort: str = "best", media_type: str = "all",
                             language: str = "", country: str = "", region: str = "",
                             category: str = "", quality: str = "", protocol: str = "",
                             source: str = "",
                             latency_min: float = -1, latency_max: float = -1,
                             speed_min: float = -1, speed_max: float = -1,
                             with_tab_counts: bool = False,
                             country_exclude: str = "",
                             hide_vod: bool = False) -> dict:
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"total": 0, "page": page, "per_page": per_page, "items": []}

        self._ensure_materialized(sid)
        with self._session() as session:
            use_mat = self._has_materialized(session, sid)
            having_clauses = []
            if tab == "valid":
                having_clauses.append("valid_count > 0")
            elif tab == "invalid":
                having_clauses.append("valid_count = 0 AND likely_valid_count = 0")
            elif tab == "likely_valid":
                having_clauses.append("valid_count = 0 AND likely_valid_count > 0")

            params = {"sid": sid}

            if use_mat:
                filters = ["session_id = :sid"]
                filters.append(_junk_name_exclude_condition("name"))
                if hide_vod:
                    filters.append(f"NOT {_vod_content_sql()}")
                if group_path:
                    filters.append("channel_group = :group_path")
                    params["group_path"] = group_path
                if search:
                    filters.append("(LOWER(name) LIKE :search OR LOWER(url) LIKE :search)")
                    params["search"] = f"%{search.lower()}%"
                if media_type == "tv":
                    filters.append("is_radio = 0")
                elif media_type == "radio":
                    filters.append("is_radio = 1")
                if language:
                    filters.append("LOWER(language) = LOWER(:language)")
                    params["language"] = language
                if country_exclude:
                    countries = [c.strip() for c in country_exclude.split(",") if c.strip()]
                    if countries:
                        country_condition, country_params = self._get_country_condition(countries, exclude=True)
                        if country_condition:
                            filters.append(country_condition)
                            params.update(country_params)
                elif country:
                    countries = [c.strip() for c in country.split(",") if c.strip()]
                    if countries:
                        country_condition, country_params = self._get_country_condition(countries)
                        if country_condition:
                            filters.append(country_condition)
                            params.update(country_params)
                if region:
                    region_condition = self._get_region_condition(region)
                    if region_condition:
                        filters.append(region_condition)
                if category:
                    cat_condition = self._get_category_condition(category)
                    if cat_condition:
                        filters.append(cat_condition)
                if quality:
                    q_condition = self._get_quality_condition(quality)
                    if q_condition:
                        filters.append(q_condition)
                if protocol:
                    p_condition = self._get_protocol_condition(protocol)
                    if p_condition:
                        filters.append(p_condition)
                if source:
                    src_condition, src_params = self._build_source_condition("sources", source)
                    if src_condition:
                        filters.append(src_condition)
                        params.update(src_params)
                if latency_min >= 0:
                    filters.append("latency >= :latency_min")
                    params["latency_min"] = latency_min
                if latency_max >= 0 and latency_max >= latency_min:
                    filters.append("latency <= :latency_max")
                    params["latency_max"] = latency_max
                if speed_min >= 0:
                    filters.append("speed != '-'")
                    params["speed_min"] = speed_min
                if speed_max >= 0 and speed_max >= speed_min:
                    filters.append("speed != '-'")
                    params["speed_max"] = speed_max

                having_sql = (" HAVING " + " AND ".join(having_clauses)) if having_clauses else ""
                where_sql = " AND ".join(filters)

                # 不带 HAVING 的 base 用于 tab 计数（4 个 tab 在无 HAVING 的子查询上一次性聚合）
                base_no_having = f"""
                    SELECT
                        CASE WHEN clean_name != '' THEN clean_name
                             WHEN name = 'N/A' THEN COALESCE(source_name, name)
                             ELSE name END as ch_name,
                        channel_group as ch_group,
                        COUNT(*) as source_count,
                        SUM(is_valid) as valid_count,
                        SUM(CASE WHEN quality_tier = 'likely_valid' THEN 1 ELSE 0 END) as likely_valid_count,
                        MIN(CASE WHEN is_valid = 1 AND latency > 0 THEN latency END) as best_latency,
                        MAX(is_radio) as is_radio,
                        MAX(resolution) as resolution,
                        MAX(frequency) as frequency
                    FROM channel_results
                    WHERE {where_sql}
                    GROUP BY ch_name, resolution
                """
                base = base_no_having + (f"\n{having_sql}" if having_sql else "")

                total = _scalar(session, sa_text(f"SELECT COUNT(*) FROM ({base}) sub").bindparams(**params)) or 0

                tab_counts = None
                if with_tab_counts:
                    row = session.exec(sa_text(f"""
                        SELECT
                            COUNT(*) AS total,
                            COALESCE(SUM(CASE WHEN valid_count > 0 THEN 1 ELSE 0 END), 0) AS valid,
                            COALESCE(SUM(CASE WHEN valid_count = 0 AND likely_valid_count > 0 THEN 1 ELSE 0 END), 0) AS likely,
                            COALESCE(SUM(CASE WHEN valid_count = 0 AND likely_valid_count = 0 THEN 1 ELSE 0 END), 0) AS invalid
                        FROM ({base_no_having}) sub
                    """).bindparams(**params)).first()
                    tab_counts = {"all": row[0] or 0, "valid": row[1] or 0,
                                  "likely_valid": row[2] or 0, "invalid": row[3] or 0}

                _group_sort = {
                    "best": "best_latency ASC, valid_count DESC",
                    "name_asc": "ch_name ASC",
                    "name_desc": "ch_name DESC",
                    "latency_asc": "best_latency ASC",
                    "latency_desc": "best_latency DESC",
                    "speed_asc": "ch_name ASC",
                    "speed_desc": "ch_name DESC",
                }
                order_sql = _group_sort.get(sort, _group_sort["best"])
                offset = (page - 1) * per_page
                page_params = {**params, "limit": per_page, "offset": offset}

                groups = session.exec(sa_text(f"""
                    SELECT ch_name, ch_group, source_count, valid_count, likely_valid_count, best_latency, is_radio, resolution, frequency FROM ({base}) sub
                    ORDER BY {order_sql}
                    LIMIT :limit OFFSET :offset
                """).bindparams(**page_params)).all()

                page_names = [g[0] for g in groups]
                if page_names:
                    name_placeholders = ",".join(f":name_{i}" for i in range(len(page_names)))
                    name_params = {f"name_{i}": n for i, n in enumerate(page_names)}
                    all_sources = session.exec(sa_text(f"""
                        SELECT name, url, is_valid, latency, speed, details, source_name, quality_tier, clean_name, resolution, country
                        FROM channel_results
                        WHERE session_id = :sid AND (name IN ({name_placeholders}) OR clean_name IN ({name_placeholders}))
                        ORDER BY name, CASE WHEN latency IS NULL THEN 1 ELSE 0 END, latency ASC
                    """).bindparams(sid=sid, **name_params)).all()
                else:
                    all_sources = []

                sources_by_name = {}
                best_url_by_key = {}
                group_country = {}
                for sr in all_sources:
                    ch_name = (sr[8] or "") if (sr[8] or "") else ((sr[6] or sr[0]) if sr[0] == "N/A" else sr[0])
                    resolution = sr[9] or ""
                    group_key = f"{ch_name}@{resolution}" if resolution else ch_name
                    if group_key not in sources_by_name:
                        sources_by_name[group_key] = []
                    if group_key not in group_country and (sr[10] or "").strip():
                        group_country[group_key] = (sr[10] or "").strip()
                    is_valid = bool(sr[2])
                    quality_tier = sr[7] or ("valid" if is_valid else "invalid")
                    try:
                        lat = float(sr[3]) if sr[3] is not None else None
                    except (ValueError, TypeError):
                        lat = None
                    lat_val = lat if lat is not None and lat >= 0 else 9999
                    # 内存计算该频道最佳有效源 URL（替代逐频道 N+1 查询）
                    if is_valid and lat is not None and lat > 0:
                        cur_best = best_url_by_key.get(group_key)
                        if cur_best is None or lat < cur_best[0]:
                            best_url_by_key[group_key] = (lat, sr[1] or "")
                    tier_score = 2000 if quality_tier == "valid" else (1000 if quality_tier == "likely_valid" else 0)
                    sources_by_name[group_key].append({
                        "url": sr[1] or "",
                        "is_valid": is_valid,
                        "quality_tier": quality_tier,
                        "latency": str(int(sr[3])) if sr[3] is not None and sr[3] >= 0 else "-",
                        "speed": sr[4] or "-",
                        "details": sr[5] or "",
                        "source_name": sr[6] or "",
                        "clean_name": sr[8] or "",
                        "resolution": resolution,
                        "_score": tier_score + max(0, 1000 - lat_val),
                    })
                items = []
                for idx, g in enumerate(groups):
                    name = g[0] or ""
                    grp = g[1] or ""
                    source_count = g[2] or 0
                    valid_count = g[3] or 0
                    likely_valid_count = g[4] or 0
                    best_latency = g[5]
                    resolution = g[7] or ""
                    frequency_val = g[8] or ""

                    group_key = f"{name}@{resolution}" if resolution else name
                    sources = sources_by_name.get(group_key, [])
                    recommended_idx = -1
                    best_score = -1
                    if sources:
                        for si, s in enumerate(sources):
                            score = s.pop("_score")
                            if score > best_score:
                                best_score = score
                                recommended_idx = si

                    display_name = f"{name} [{resolution}]" if resolution else name

                    best_url = best_url_by_key.get(group_key, (None, ""))[1]

                    # 归属地：优先取组内源记录的 country 列，再按频道名/分组名二次推断
                    from iptv_check.core.parser import _infer_country_code
                    country_code = _infer_country_code(name, grp, group_country.get(group_key, ""))
                    region_val = _infer_region(name, grp, country_code)

                    items.append({
                        "index": offset + idx + 1,
                        "name": display_name,
                        "url": best_url,
                        "resolution": resolution,
                        "group": _map_group_name(grp),
                        "country": country_code,
                        "region": region_val,
                        "source_count": source_count,
                        "valid_count": valid_count,
                        "best_latency": str(int(best_latency)) if best_latency and str(best_latency) != "-" and best_latency > 0 else "-",
                        "has_valid": valid_count > 0,
                        "is_valid": valid_count > 0,
                        "quality_tier": "valid" if valid_count > 0 else ("likely_valid" if likely_valid_count > 0 else "invalid"),
                        "latency": str(int(best_latency)) if best_latency and str(best_latency) != "-" and best_latency > 0 else "-",
                        "sources": sources,
                        "recommended_source_idx": recommended_idx,
                        "is_radio": bool(g[6]),
                        "frequency": frequency_val,
                    })

                ret = {"total": total, "page": page, "per_page": per_page, "items": items}
                if with_tab_counts and tab_counts:
                    ret["tab_counts"] = tab_counts
                return ret

            filters = ["session_id = :sid", "event_type = 'channel_checked'"]
            filters.append(_junk_name_exclude_condition("json_extract(payload, '$.name')"))
            if hide_vod:
                _vod_sql = _vod_content_sql(
                    name_col="json_extract(payload, '$.name')",
                    url_col="json_extract(payload, '$.url')",
                )
                filters.append(f"NOT {_vod_sql}")

            if group_path:
                filters.append("json_extract(payload, '$.group') = :group_path")
                params["group_path"] = group_path

            if search:
                filters.append("(LOWER(json_extract(payload, '$.name')) LIKE :search OR LOWER(json_extract(payload, '$.url')) LIKE :search)")
                params["search"] = f"%{search.lower()}%"

            if media_type == "tv":
                filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
            elif media_type == "radio":
                filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")

            if language:
                filters.append("LOWER(json_extract(payload, '$.language')) = LOWER(:language)")
                params["language"] = language
            if country_exclude:
                countries = [c.strip() for c in country_exclude.split(",") if c.strip()]
                if countries:
                    country_condition, country_params = self._get_country_condition_for_json(countries, exclude=True)
                    if country_condition:
                        filters.append(country_condition)
                        params.update(country_params)
            elif country:
                countries = [c.strip() for c in country.split(",") if c.strip()]
                if countries:
                    country_condition, country_params = self._get_country_condition_for_json(countries)
                    if country_condition:
                        filters.append(country_condition)
                        params.update(country_params)
            if region:
                region_condition = self._get_region_condition_for_json(region)
                if region_condition:
                    filters.append(region_condition)
            if category:
                cat_condition = self._get_category_condition_for_json(category)
                if cat_condition:
                    filters.append(cat_condition)
            if quality:
                q_condition = self._get_quality_condition_for_json(quality)
                if q_condition:
                    filters.append(q_condition)
            if protocol:
                p_condition = self._get_protocol_condition_for_json(protocol)
                if p_condition:
                    filters.append(p_condition)
            if source:
                src_condition, src_params = self._build_source_condition("json_extract(payload, '$.sources')", source)
                if src_condition:
                    filters.append(src_condition)
                    params.update(src_params)
            if latency_min >= 0:
                filters.append("CAST(json_extract(payload, '$.latency') AS REAL) >= :latency_min")
                params["latency_min"] = latency_min
            if latency_max >= 0 and latency_max >= latency_min:
                filters.append("CAST(json_extract(payload, '$.latency') AS REAL) <= :latency_max")
                params["latency_max"] = latency_max
            if speed_min >= 0:
                filters.append("json_extract(payload, '$.speed') != '-'")
                params["speed_min"] = speed_min
            if speed_max >= 0 and speed_max >= speed_min:
                filters.append("json_extract(payload, '$.speed') != '-'")
                params["speed_max"] = speed_max

            having_sql = (" HAVING " + " AND ".join(having_clauses)) if having_clauses else ""
            where_sql = " AND ".join(filters)

            base = f"""
                SELECT
                    CASE WHEN json_extract(payload, '$.clean_name') != '' AND json_extract(payload, '$.clean_name') IS NOT NULL
                         THEN json_extract(payload, '$.clean_name')
                         WHEN json_extract(payload, '$.name') = 'N/A' OR json_extract(payload, '$.name') IS NULL
                         THEN COALESCE(json_extract(payload, '$.sources'), 'N/A')
                         ELSE json_extract(payload, '$.name') END as ch_name,
                    json_extract(payload, '$.group') as ch_group,
                    COUNT(*) as source_count,
                    SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid_count,
                    SUM(CASE WHEN json_extract(payload, '$.quality_tier') = 'likely_valid' THEN 1 ELSE 0 END) as likely_valid_count,
                    MIN(CASE WHEN json_extract(payload, '$.is_valid') = 1 AND CAST(json_extract(payload, '$.latency') AS REAL) > 0 THEN CAST(json_extract(payload, '$.latency') AS REAL) END) as best_latency,
                    MAX(COALESCE(json_extract(payload, '$.is_radio'), 0)) as is_radio,
                    MAX(COALESCE(json_extract(payload, '$.frequency'), '')) as frequency
                FROM check_events
                WHERE {where_sql}
                GROUP BY ch_name
                {having_sql}
            """

            total = _scalar(session, sa_text(f"SELECT COUNT(*) FROM ({base}) sub").bindparams(**params)) or 0

            _group_sort = {
                "best": "best_latency ASC, valid_count DESC",
                "name_asc": "ch_name ASC",
                "name_desc": "ch_name DESC",
                "latency_asc": "best_latency ASC",
                "latency_desc": "best_latency DESC",
                "speed_asc": "ch_name ASC",
                "speed_desc": "ch_name DESC",
            }
            order_sql = _group_sort.get(sort, _group_sort["best"])
            offset = (page - 1) * per_page
            page_params = {**params, "limit": per_page, "offset": offset}

            groups = session.exec(sa_text(f"""
                SELECT ch_name, ch_group, source_count, valid_count, likely_valid_count, best_latency, is_radio, frequency FROM ({base}) sub
                ORDER BY {order_sql}
                LIMIT :limit OFFSET :offset
            """).bindparams(**page_params)).all()

            page_names = [g[0] for g in groups]
            if page_names:
                name_placeholders = ",".join(f":name_{i}" for i in range(len(page_names)))
                name_params = {f"name_{i}": n for i, n in enumerate(page_names)}
                all_sources = session.exec(sa_text(f"""
                    SELECT
                        json_extract(payload, '$.name') as ch_name,
                        json_extract(payload, '$.url'),
                        json_extract(payload, '$.is_valid'),
                        json_extract(payload, '$.latency'),
                        json_extract(payload, '$.speed'),
                        json_extract(payload, '$.details'),
                        json_extract(payload, '$.sources'),
                        json_extract(payload, '$.quality_tier'),
                        json_extract(payload, '$.clean_name') as clean_name,
                        json_extract(payload, '$.country') as country
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                      AND (json_extract(payload, '$.name') IN ({name_placeholders}) OR json_extract(payload, '$.clean_name') IN ({name_placeholders}))
                    ORDER BY ch_name, CASE WHEN json_extract(payload, '$.latency') IS NULL THEN 1 ELSE 0 END, CAST(json_extract(payload, '$.latency') AS REAL) ASC
                """).bindparams(sid=sid, **name_params)).all()
            else:
                all_sources = []

            sources_by_name = {}
            group_country = {}
            for sr in all_sources:
                raw_name = sr[0] or ""
                raw_clean = sr[8] or ""
                ch_name = raw_clean if raw_clean else ((sr[6] or raw_name) if raw_name == "N/A" else raw_name)
                if ch_name not in sources_by_name:
                    sources_by_name[ch_name] = []
                if ch_name not in group_country and (sr[9] or "").strip():
                    group_country[ch_name] = (sr[9] or "").strip()
                is_valid = bool(sr[2])
                quality_tier = sr[7] or ("valid" if is_valid else "invalid")
                try:
                    lat = float(sr[3]) if sr[3] else None
                except (ValueError, TypeError):
                    lat = None
                lat_val = lat if lat is not None and lat >= 0 else 9999
                tier_score = 2000 if quality_tier == "valid" else (1000 if quality_tier == "likely_valid" else 0)
                sources_by_name[ch_name].append({
                    "url": sr[1] or "",
                    "is_valid": is_valid,
                    "quality_tier": quality_tier,
                    "latency": str(int(sr[3])) if sr[3] and sr[3] != "-" else "-",
                    "speed": sr[4] or "-",
                    "details": sr[5] or "",
                    "source_name": sr[6] or "",
                    "clean_name": sr[8] or "",
                    "_score": tier_score + max(0, 1000 - lat_val),
                })

            items = []
            for idx, g in enumerate(groups):
                name = g[0] or ""
                grp = g[1] or ""
                source_count = g[2] or 0
                valid_count = g[3] or 0
                likely_valid_count = g[4] or 0
                best_latency = g[5]

                sources = sources_by_name.get(name, [])
                recommended_idx = -1
                best_score = -1
                if sources:
                    for si, s in enumerate(sources):
                        score = s.pop("_score")
                        if score > best_score:
                            best_score = score
                            recommended_idx = si

                best_url = ""
                all_sources_for_url = sources_by_name.get(name, [])
                if all_sources_for_url:
                    temp_idx = -1
                    temp_score = -1
                    for si, s in enumerate(all_sources_for_url):
                        sc = s.get("_score", 0)
                        if s.get("is_valid") and sc > temp_score:
                            temp_score = sc
                            temp_idx = si
                    if 0 <= temp_idx < len(all_sources_for_url):
                        best_url = all_sources_for_url[temp_idx].get("url", "")

                    # 归属地：优先取组内源记录的 country 列，再按频道名/分组名二次推断
                    from iptv_check.core.parser import _infer_country_code
                    country_code = _infer_country_code(name, grp, group_country.get(name, ""))
                    region_val = _infer_region(name, grp, country_code)

                items.append({
                    "index": offset + idx + 1,
                    "name": name,
                    "url": best_url,
                    "group": _map_group_name(grp),
                    "country": country_code,
                    "region": region_val,
                    "source_count": source_count,
                    "valid_count": valid_count,
                    "best_latency": str(int(best_latency)) if best_latency and str(best_latency) != "-" and best_latency > 0 else "-",
                    "has_valid": valid_count > 0,
                    "is_valid": valid_count > 0,
                    "quality_tier": "valid" if valid_count > 0 else ("likely_valid" if likely_valid_count > 0 else "invalid"),
                    "latency": str(int(best_latency)) if best_latency and str(best_latency) != "-" and best_latency > 0 else "-",
                    "sources": sources,
                    "recommended_source_idx": recommended_idx,
                    "is_radio": bool(g[6]),
                    "frequency": g[7] or "",
                })

            return {"total": total, "page": page, "per_page": per_page, "items": items}

    def get_category_tree(self, session_id: str = None, media_type: str = "all") -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []
        return self._cached_filter(
            f"category:{sid}:{media_type}", 120,
            lambda: self._get_category_tree_uncached(sid, media_type),
        )

    def _get_category_tree_uncached(self, sid: str, media_type: str) -> list[dict]:
        with self._session() as session:
            params = {"sid": sid}
            if self._has_materialized(session, sid):
                filters = ["session_id = :sid"]
                if media_type == "tv":
                    filters.append("is_radio = 0")
                elif media_type == "radio":
                    filters.append("is_radio = 1")
                where_sql = " AND ".join(filters)
                rows = session.exec(sa_text(f"""
                    SELECT
                        channel_group as grp,
                        country as country,
                        is_radio as is_radio,
                        COALESCE(content_type, '其他') as content_type,
                        COUNT(*) as total,
                        SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) as valid
                    FROM channel_results
                    WHERE {where_sql}
                    GROUP BY grp, country, is_radio, content_type
                    ORDER BY valid DESC, total DESC
                """).bindparams(**params)).all()
            else:
                filters = ["session_id = :sid", "event_type = 'channel_checked'"]
                if media_type == "tv":
                    filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
                elif media_type == "radio":
                    filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")
                where_sql = " AND ".join(filters)
                rows = session.exec(sa_text(f"""
                    SELECT
                        json_extract(payload, '$.group') as grp,
                        json_extract(payload, '$.country') as country,
                        json_extract(payload, '$.is_radio') as is_radio,
                        COALESCE(json_extract(payload, '$.content_type'), '其他') as content_type,
                        COUNT(*) as total,
                        SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid
                    FROM check_events
                    WHERE {where_sql}
                    GROUP BY grp, country, is_radio, content_type
                    ORDER BY valid DESC, total DESC
                """).bindparams(**params)).all()

            tree = {
                "央视": {"count": 0, "valid": 0, "children": {}},
                "卫视": {"count": 0, "valid": 0, "children": {}},
                "地方": {"count": 0, "valid": 0, "children": {}},
                "专题": {"count": 0, "valid": 0, "children": {}},
                "4K": {"count": 0, "valid": 0, "children": {}},
                "IPv6": {"count": 0, "valid": 0, "children": {}},
                "国际电视": {"count": 0, "valid": 0, "children": {}},
                "广播": {"count": 0, "valid": 0, "children": {}},
                "未分类": {"count": 0, "valid": 0, "children": {}},
            }

            for g in rows:
                grp_name = g[0] or "未分组"
                country_code = (g[1] or "").strip().upper()
                is_radio = bool(g[2])
                content_type = g[3] or "其他"
                total = g[4] or 0
                valid = g[5] or 0

                codes = [c.strip() for c in country_code.split(";") if c.strip()]
                normalized_codes = [_normalize_country_code(c) for c in codes]
                is_cn = any(c in _CN_COUNTRY_CODES for c in normalized_codes) if normalized_codes else False

                primary_code = normalized_codes[0] if normalized_codes else ""
                flag_emoji = _country_to_flag(primary_code)
                country_zh = _COUNTRY_NAME_ZH.get(primary_code, "")

                grp_display = grp_name
                if country_zh and not is_cn:
                    grp_display = f"{flag_emoji} {grp_name}"

                region = _infer_region_from_group(grp_name, country_code, is_radio, content_type)

                tree[region]["count"] += total
                tree[region]["valid"] += valid
                existing = tree[region]["children"].get(grp_display, {"count": 0, "valid": 0, "country": primary_code, "flag": flag_emoji, "country_zh": country_zh})
                tree[region]["children"][grp_display] = {
                    "count": existing["count"] + total,
                    "valid": existing["valid"] + valid,
                    "country": primary_code,
                    "flag": flag_emoji,
                    "country_zh": country_zh,
                }

            result = []
            region_order = ["央视", "卫视", "地方", "专题", "4K", "IPv6", "国际电视", "广播", "未分类"]
            for region_name in region_order:
                region_data = tree[region_name]
                if region_data["count"] == 0:
                    continue
                children = []
                for grp_name, grp_data in sorted(region_data["children"].items(), key=lambda x: x[1]["valid"], reverse=True):
                    child = {
                        "name": grp_name,
                        "count": grp_data["count"],
                        "valid": grp_data["valid"],
                    }
                    if grp_data.get("flag"):
                        child["flag"] = grp_data["flag"]
                    if grp_data.get("country_zh"):
                        child["country_zh"] = grp_data["country_zh"]
                    children.append(child)
                result.append({
                    "name": region_name,
                    "count": region_data["count"],
                    "valid": region_data["valid"],
                    "children": children,
                })

            return result

    def get_available_languages(self, session_id: str = None) -> list[dict]:
        sid = session_id or self._store.current_session_id
        if not sid:
            return []

        with self._session() as session:
            if self._has_materialized(session, sid):
                rows = session.exec(sa_text("""
                    SELECT language, COUNT(*) as total, SUM(is_valid) as valid
                    FROM channel_results
                    WHERE session_id = :sid AND language IS NOT NULL AND language != ''
                    GROUP BY language
                    ORDER BY total DESC
                """).bindparams(sid=sid)).all()
            else:
                rows = session.exec(sa_text("""
                    SELECT
                        json_extract(payload, '$.language') as lang,
                        COUNT(*) as total,
                        SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                      AND json_extract(payload, '$.language') IS NOT NULL
                      AND json_extract(payload, '$.language') != ''
                    GROUP BY lang
                    ORDER BY total DESC
                """).bindparams(sid=sid)).all()

            return [
                {"language": r[0] or "", "count": r[1] or 0, "valid": r[2] or 0}
                for r in rows
                if r[0]
            ]

    def get_available_countries(self, session_id: str = None) -> list[dict]:
        """获取当前数据中可用的国家/地区列表（基于country字段和名称推断）"""
        sid = session_id or self._store.current_session_id
        if not sid:
            return []
        return self._cached_filter(
            f"countries:{sid}", 120,
            lambda: self._get_available_countries_uncached(sid),
        )

    def _get_available_countries_uncached(self, sid: str) -> list[dict]:
        with self._session() as session:
            use_mat = self._has_materialized(session, sid)
            
            if use_mat:
                rows = session.exec(sa_text("""
                    SELECT country, COUNT(*) as total, SUM(is_valid) as valid
                    FROM channel_results
                    WHERE session_id = :sid
                    GROUP BY country
                    ORDER BY total DESC
                """).bindparams(sid=sid)).all()
                
                name_rows = session.exec(sa_text("""
                    SELECT name, channel_group, is_valid
                    FROM channel_results
                    WHERE session_id = :sid
                """).bindparams(sid=sid)).all()
            else:
                rows = session.exec(sa_text("""
                    SELECT
                        json_extract(payload, '$.country') as country,
                        COUNT(*) as total,
                        SUM(CASE WHEN json_extract(payload, '$.is_valid') = 1 THEN 1 ELSE 0 END) as valid
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                    GROUP BY country
                    ORDER BY total DESC
                """).bindparams(sid=sid)).all()
                
                name_rows = session.exec(sa_text("""
                    SELECT
                        json_extract(payload, '$.name'),
                        json_extract(payload, '$.group'),
                        json_extract(payload, '$.is_valid')
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                """).bindparams(sid=sid)).all()
            
            # 统计各国家频道数
            country_stats = {}
            
            # 从country字段统计
            for r in rows:
                code = (r[0] or "").strip()
                if not code:
                    continue
                codes = [c.strip().upper() for c in code.split(";") if c.strip()]
                for c in codes:
                    if any('\u4e00' <= ch <= '\u9fff' for ch in c):
                        continue
                    if len(c) > 3 and c not in _COUNTRY_NAME_ZH and c not in _NON_STANDARD_COUNTRY_CODES:
                        continue
                    normalized = _normalize_country_code(c)
                    if normalized not in country_stats:
                        country_stats[normalized] = {"count": 0, "valid": 0}
                    country_stats[normalized]["count"] += r[1] or 0
                    country_stats[normalized]["valid"] += r[2] or 0
            
            # 从频道名称推断
            cn_kw = [k.lower() for k in self._CN_NAME_KEYWORDS if k]
            cn_pattern = re.compile("|".join(re.escape(k) for k in cn_kw))
            # 预编译国际关键词正则（keywords[0] 为国际代码，其余为关键词）
            intl_patterns = []
            for _cname, _kws in _INTERNATIONAL_COUNTRY_GROUPS.items():
                _code = _kws[0] if _kws else _cname
                _valid_kws = [k.lower() for k in _kws if len(k) > 2]
                if _valid_kws:
                    intl_patterns.append((_code, re.compile("|".join(re.escape(k) for k in _valid_kws))))
            cn_count = 0
            cn_valid = 0

            for r in name_rows:
                name = (r[0] or "").lower()
                group = (r[1] or "").lower()
                is_valid = bool(r[2])

                # 检查是否为中国频道
                is_cn = bool(cn_pattern.search(name))
                if not is_cn and "卫视" in group:
                    is_cn = True
                if not is_cn and "cctv" in group:
                    is_cn = True

                if is_cn:
                    cn_count += 1
                    if is_valid:
                        cn_valid += 1
                else:
                    # 检查国际关键词
                    for _code, _pat in intl_patterns:
                        if _pat.search(name) or _pat.search(group):
                            if _code not in country_stats:
                                country_stats[_code] = {"count": 0, "valid": 0}
                            country_stats[_code]["count"] += 1
                            if is_valid:
                                country_stats[_code]["valid"] += 1
                            break
            
            # 如果通过名称推断到中国频道，添加CN
            if cn_count > 0:
                if "CN" not in country_stats:
                    country_stats["CN"] = {"count": 0, "valid": 0}
                country_stats["CN"]["count"] += cn_count
                country_stats["CN"]["valid"] += cn_valid
            
            # 构建结果
            valid_codes = set(_COUNTRY_NAME_ZH.keys()) | _CN_COUNTRY_CODES
            result = []
            for code, stats in sorted(country_stats.items(), key=lambda x: x[1]["count"], reverse=True):
                if code not in valid_codes:
                    continue
                zh_name = _COUNTRY_NAME_ZH.get(code, "")
                flag = _country_to_flag(code) if len(code) == 2 else ""
                result.append({
                    "code": code,
                    "name": zh_name or code,
                    "flag": flag,
                    "count": stats["count"],
                    "valid": stats["valid"],
                })
            
            # 如果有名称推断的中国频道但country字段没有CN，确保CN出现在列表中
            if cn_count > 0 and not any(r["code"] == "CN" for r in result):
                result.insert(0, {
                    "code": "CN",
                    "name": "中国",
                    "flag": "🇨🇳",
                    "count": cn_count,
                    "valid": cn_valid,
                })
            
            return result

    def get_available_regions(self, session_id: str = None) -> list[dict]:
        """获取中国各省级行政区的频道统计，用于二级筛选"""
        sid = session_id or self._store.current_session_id
        if not sid:
            return []
        return self._cached_filter(
            f"regions:{sid}", 120,
            lambda: self._get_available_regions_uncached(sid),
        )

    def _get_available_regions_uncached(self, sid: str) -> list[dict]:
        with self._session() as session:
            use_mat = self._has_materialized(session, sid)

            if use_mat:
                rows = session.exec(sa_text("""
                    SELECT name, channel_group, is_valid
                    FROM channel_results
                    WHERE session_id = :sid
                """).bindparams(sid=sid)).all()
            else:
                rows = session.exec(sa_text("""
                    SELECT
                        json_extract(payload, '$.name'),
                        json_extract(payload, '$.group'),
                        json_extract(payload, '$.is_valid')
                    FROM check_events
                    WHERE session_id = :sid AND event_type = 'channel_checked'
                """).bindparams(sid=sid)).all()

            region_stats = {}
            for code, info in _CN_REGION_MAP.items():
                region_stats[code] = {"name": info["name"], "count": 0, "valid": 0}

            # 预编译各省份关键词正则，替代逐关键词匹配
            region_patterns = []
            for code, info in _CN_REGION_MAP.items():
                kws = [k.lower() for k in info["keywords"] if k]
                if kws:
                    region_patterns.append((code, re.compile("|".join(re.escape(k) for k in kws))))

            for r in rows:
                name = (r[0] or "").lower()
                group = (r[1] or "").lower()
                is_valid = bool(r[2])
                for _code, _pat in region_patterns:
                    if _pat.search(name) or _pat.search(group):
                        region_stats[_code]["count"] += 1
                        if is_valid:
                            region_stats[_code]["valid"] += 1
                        break

            result = []
            for code, stats in region_stats.items():
                if stats["count"] > 0:
                    result.append({
                        "code": code,
                        "name": stats["name"],
                        "count": stats["count"],
                        "valid": stats["valid"],
                    })
            result.sort(key=lambda x: x["count"], reverse=True)
            return result

    def get_live_channels(self, session_id: str = None, media_type: str = "all") -> dict:
        """获取有效频道列表，按频道名取最优源，按分组聚合"""
        sid = session_id or self._store.current_session_id
        if not sid:
            return {"groups": [], "total": 0}

        with self._session() as session:
            use_mat = self._has_materialized(session, sid)

            if use_mat:
                filters = ["session_id = :sid", "is_valid = 1"]
                if media_type == "tv":
                    filters.append("is_radio = 0")
                elif media_type == "radio":
                    filters.append("is_radio = 1")
                where_sql = " AND ".join(filters)
                params = {"sid": sid}

                rows = session.exec(sa_text(f"""
                    SELECT name, channel_group, url, latency
                    FROM channel_results
                    WHERE {where_sql}
                    ORDER BY name, latency ASC
                """).bindparams(**params)).all()
            else:
                filters = ["session_id = :sid", "event_type = 'channel_checked'", "json_extract(payload, '$.is_valid') = 1"]
                if media_type == "tv":
                    filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 0")
                elif media_type == "radio":
                    filters.append("COALESCE(json_extract(payload, '$.is_radio'), 0) = 1")

                where_sql = " AND ".join(filters)
                params = {"sid": sid}

                rows = session.exec(sa_text(f"""
                    SELECT
                        json_extract(payload, '$.name') as ch_name,
                        json_extract(payload, '$.group') as ch_group,
                        json_extract(payload, '$.url') as ch_url,
                        CAST(json_extract(payload, '$.latency') AS REAL) as ch_latency
                    FROM check_events
                    WHERE {where_sql}
                    ORDER BY ch_name, ch_latency ASC
                """).bindparams(**params)).all()

            valid_map = {}
            for r in rows:
                name = r[0] or ""
                group = r[1] or ""
                url = r[2] or ""
                try:
                    lat = float(r[3]) if r[3] is not None and float(r[3]) >= 0 else -1
                except (ValueError, TypeError):
                    lat = -1
                if name not in valid_map:
                    valid_map[name] = {"name": name, "url": url, "group": group, "latency": lat}
                else:
                    existing = valid_map[name]
                    if 0 <= lat < existing["latency"] or existing["latency"] < 0:
                        valid_map[name] = {"name": name, "url": url, "group": group, "latency": lat}

            channels = sorted(valid_map.values(), key=lambda x: (x["group"], x["name"]))
            group_map = {}
            for ch in channels:
                g = ch["group"] or "未分组"
                if g not in group_map:
                    group_map[g] = []
                group_map[g].append({"name": ch["name"], "url": ch["url"], "latency": ch["latency"]})

            groups = [{"name": k, "channels": v} for k, v in sorted(group_map.items())]
            return {"groups": groups, "total": len(channels)}
