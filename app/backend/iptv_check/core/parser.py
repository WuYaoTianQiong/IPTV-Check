import re
import os
import hashlib
import logging
from typing import List, Optional

from iptv_check.models.channel import Channel
from iptv_check.domain.parse_result import ParseResult, ParseError

try:
    from pypinyin import lazy_pinyin, Style
    _PYPINYIN_AVAILABLE = True
except ImportError:
    _PYPINYIN_AVAILABLE = False

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
_CLEAN_NAME_PATTERN = re.compile(r'^["\',;]+|["\',;]+$')
_CLEAN_GROUP_PATTERN = re.compile(r'^["\',;]+|["\',;]+$')
_CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')
_JUNK_IN_NAME_PATTERN = re.compile(
    r'(?:'
    r'image_[^\s,]*'
    r'|m_[a-z]+(?:,[a-z0-9_]+)*'
    r'|tvg-logo="[^"]*"'
    r'|tvg-id="[^"]*"'
    r'|tvg-name="[^"]*"'
    r'|tvg-language="[^"]*"'
    r'|tvg-country="[^"]*"'
    r'|group-title="[^"]*"'
    r'|catchup="[^"]*"'
    r'|group-title=[^\s,]*'
    r'|https?://\S+'
    r'|format[,/]\S+'
    r'|g_\d+(?:,xp_\d+,yp_\d+)?'
    r'|xp_\d+'
    r'|yp_\d+'
    r'|height=\S+'
    r'|fit=\S+'
    r'|q=\d+'
    r'|limit_\d+'
    r'|w_\d+'
    r'|/\S+'
    r')'
)
_CHANNEL_NAME_START = re.compile(
    r'(?:[\u4e00-\u9fff]|[A-Z][a-zA-Z]|\d+\s+[A-Z]|CCTV|CGTN|FM\s|AM\s)'
)

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
    "xinwen": "新闻", "yinyue": "音乐", "tiyu": "体育", "jiaotong": "交通",
    "dianying": "电影", "zongyi": "综艺", "caijing": "财经", "yule": "娱乐",
    "shaonian": "少儿", "jiaoyu": "教育", "guangbo": "广播", "diantai": "电台",
    "wenhua": "文化", "keji": "科技", "zonghe": "综合", "shenghuo": "生活",
    "lishi": "历史", "ziran": "自然", "jiankang": "健康", "meishi": "美食",
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
    cleaned = _JUNK_IN_NAME_PATTERN.sub("", name)
    cleaned = re.sub(r'\s*,\s*', ', ', cleaned)
    cleaned = re.sub(r'["\']+,\s*', '', cleaned)
    cleaned = re.sub(r',\s*["\']+', ',', cleaned)
    cleaned = re.sub(r'["\']+', '', cleaned)
    cleaned = re.sub(r'^[,\s]+', '', cleaned)
    cleaned = re.sub(r'[,\s]+$', '', cleaned)
    cleaned = cleaned.strip()
    ch_match = _CHANNEL_NAME_START.search(cleaned)
    if ch_match and ch_match.start() > 0:
        prefix = cleaned[:ch_match.start()].rstrip(', ')
        if not re.search(r'[A-Z]{2,}', prefix):
            cleaned = cleaned[ch_match.start():]
    cleaned = re.sub(r'^[,\s]+', '', cleaned).strip()
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


_CITY_PINYIN_MAP = {
    "beijing": "北京", "shanghai": "上海", "guangzhou": "广州", "shenzhen": "深圳",
    "tianjin": "天津", "chongqing": "重庆", "chengdu": "成都", "wuhan": "武汉",
    "nanjing": "南京", "hangzhou": "杭州", "xian": "西安", "kunming": "昆明",
    "qingdao": "青岛", "shenyang": "沈阳", "dalian": "大连", "jinan": "济南",
    "fuzhou": "福州", "xiamen": "厦门", "changsha": "长沙", "zhengzhou": "郑州",
    "haerbin": "哈尔滨", "harbin": "哈尔滨", "hefei": "合肥", "changchun": "长春",
    "nanchang": "南昌", "taiyuan": "太原", "guiyang": "贵阳", "nanning": "南宁",
    "lanzhou": "兰州", "hohhot": "呼和浩特", "yinchuan": "银川", "xining": "西宁",
    "lhasa": "拉萨", "urumqi": "乌鲁木齐", "shijiazhuang": "石家庄",
    "suzhou": "苏州", "wuxi": "无锡", "ningbo": "宁波", "zhuhai": "珠海",
    "huizhou": "惠州", "dongguan": "东莞", "foshan": "佛山", "zhongshan": "中山",
    "yangzhou": "扬州", "shaoxing": "绍兴", "wenzhou": "温州", "jiaxing": "嘉兴",
    "huzhou": "湖州", "changzhou": "常州", "nantong": "南通", "zhenjiang": "镇江",
    "taizhou": "泰州", "yancheng": "盐城", "huaian": "淮安", "lianyungang": "连云港",
    "xuzhou": "徐州", "quanzhou": "泉州", "zhangzhou": "漳州", "putian": "莆田",
    "shantou": "汕头", "jieyang": "揭阳", "chaozhou": "潮州", "meizhou": "梅州",
    "zhanjiang": "湛江", "maoming": "茂名", "qingyuan": "清远", "shaoguan": "韶关",
    "heyuan": "河源", "shanwei": "汕尾", "yangjiang": "阳江", "jiangmen": "江门",
    "yunfu": "云浮", "zhaoqing": "肇庆", "sanya": "三亚", "haikou": "海口",
    "baoding": "保定", "handan": "邯郸", "tangshan": "唐山", "qinhuangdao": "秦皇岛",
    "langfang": "廊坊", "chengde": "承德", "zhangjiakou": "张家口", "cangzhou": "沧州",
    "hengshui": "衡水", "xingtai": "邢台", "luoyang": "洛阳", "kaifeng": "开封",
    "anyang": "安阳", "xinxiang": "新乡", "jiaozuo": "焦作", "nanyang": "南阳",
    "shangqiu": "商丘", "xinyang": "信阳", "zhoukou": "周口", "zhumadian": "驻马店",
    "pingdingshan": "平顶山", "sanmenxia": "三门峡", "hebi": "鹤壁", "puyang": "濮阳",
    "weifang": "潍坊", "yantai": "烟台", "weihai": "威海", "zibo": "淄博",
    "linyi": "临沂", "rizhao": "日照", "dezhou": "德州", "liaocheng": "聊城",
    "binzhou": "滨州", "heze": "菏泽", "jining": "济宁", "taian": "泰安",
    "zaozhuang": "枣庄", "dongying": "东营",
    "jiayuguan": "嘉峪关", "jinchang": "金昌", "baiyin": "白银",
    "pingliang": "平凉", "jiuquan": "酒泉", "longnan": "陇南", "dingxi": "定西",
    "mianyang": "绵阳", "tianshui": "天水", "dali": "大理", "lijiang": "丽江",
    "tsingtao": "青岛", "tsinghua": "清华",
    "hubei": "湖北", "hunan": "湖南", "henan": "河南", "hebei": "河北",
    "shandong": "山东", "shanxi": "山西", "shaanxi": "陕西",
    "jiangsu": "江苏", "jiangxi": "江西", "zhejiang": "浙江", "anhui": "安徽",
    "sichuan": "四川", "guizhou": "贵州", "yunnan": "云南", "guangdong": "广东",
    "guangxi": "广西", "fujian": "福建", "gansu": "甘肃", "qinghai": "青海",
    "liaoning": "辽宁", "jilin": "吉林", "hainan": "海南", "tibet": "西藏",
    "xinjiang": "新疆", "neimenggu": "内蒙古", "ningxia": "宁夏",
    "hongkong": "香港", "macau": "澳门", "taiwan": "台湾",
    "chaoyang": "朝阳", "laoshan": "崂山", "wuhu": "芜湖",
}

_BROADCAST_TERM_MAP = {
    "comprehensive broadcasting": "综合广播", "comprehensive": "综合",
    "broadcasting station": "广播电台", "broadcasting": "广播",
    "peoples broadcasting": "人民广播", "peoples": "人民",
    "traffic broadcasting": "交通广播", "traffic radio": "交通广播",
    "traffic": "交通",
    "news comprehensive": "新闻综合", "news radio": "新闻广播", "news": "新闻",
    "economics radio": "经济广播", "economics": "经济", "economy": "经济",
    "economic radio": "经济广播", "economic": "经济",
    "science and technology": "科技", "science": "科学", "technology": "技术",
    "life broadcasting": "生活广播", "life radio": "生活广播", "life": "生活",
    "information radio": "资讯广播", "information": "资讯",
    "music radio": "音乐广播", "music": "音乐",
    "entertainment": "娱乐", "sports radio": "体育广播", "sports": "体育",
    "culture": "文化", "education": "教育", "education radio": "教育广播",
    "agriculture": "农业", "agriculture radio": "农业广播",
    "station": "台", "radio": "广播", "fm": "FM", "am": "AM",
    "channel": "频道", "network": "网",
    "golden songs": "金曲", "golden": "金曲", "songs": "歌曲",
    "chinese": "中文", "classic": "经典", "classic radio": "经典广播",
    "hit": "热门", "hits": "热门金曲",
    "family radio": "家庭广播", "family": "家庭",
    "city": "市", "provincial": "省", "county": "县",
    "urban radio": "城市广播", "urban": "城市",
    "public radio": "公共广播", "public": "公共",
    "community radio": "社区广播", "community": "社区",
    "youth radio": "青年广播", "youth": "青年",
    "literary radio": "文艺广播", "literary": "文艺",
    "art radio": "文艺广播", "art": "文艺",
    "drama": "戏剧",
    "talk radio": "谈话广播", "talk": "谈话",
    "childrens radio": "少儿广播", "childrens": "少儿",
    "folk music": "民乐", "folk": "民谣",
    "pop music": "流行音乐", "pop": "流行",
    "rock music": "摇滚音乐", "rock": "摇滚",
    "jazz radio": "爵士广播", "jazz": "爵士",
    "classical music": "古典音乐",
    "easy listening": "轻音乐",
    "oldies radio": "怀旧广播", "oldies": "怀旧",
    "love radio": "爱情广播",
    "sunshine": "阳光", "happy": "快乐", "green": "绿色",
    "variety": "综合", "variety radio": "综合广播",
    "rock radio": "摇滚广播", "pop radio": "流行广播",
    "talk": "谈话",
    "indonesia": "印度尼西亚", "colombia": "哥伦比亚", "brazil": "巴西",
    "argentina": "阿根廷", "mexico": "墨西哥", "peru": "秘鲁",
    "chile": "智利", "venezuela": "委内瑞拉", "ecuador": "厄瓜多尔",
    "cuba": "古巴", "bolivia": "玻利维亚", "paraguay": "巴拉圭",
    "uruguay": "乌拉圭", "costa rica": "哥斯达黎加", "panama": "巴拿马",
    "guatemala": "危地马拉", "honduras": "洪都拉斯", "nicaragua": "尼加拉瓜",
    "el salvador": "萨尔瓦多", "dominican": "多米尼加",
    "thailand": "泰国", "vietnam": "越南", "philippines": "菲律宾",
    "malaysia": "马来西亚", "singapore": "新加坡", "myanmar": "缅甸",
    "cambodia": "柬埔寨", "laos": "老挝", "bangladesh": "孟加拉国",
    "pakistan": "巴基斯坦", "nepal": "尼泊尔", "sri lanka": "斯里兰卡",
    "turkey": "土耳其", "iran": "伊朗", "iraq": "伊拉克",
    "egypt": "埃及", "morocco": "摩洛哥", "tunisia": "突尼斯",
    "algeria": "阿尔及利亚", "nigeria": "尼日利亚", "kenya": "肯尼亚",
    "south africa": "南非", "ethiopia": "埃塞俄比亚", "ghana": "加纳",
    "romania": "罗马尼亚", "serbia": "塞尔维亚", "croatia": "克罗地亚",
    "bulgaria": "保加利亚", "hungary": "匈牙利", "czech republic": "捷克",
    "slovakia": "斯洛伐克", "poland": "波兰", "ukraine": "乌克兰",
    "russia": "俄罗斯", "belarus": "白俄罗斯", "moldova": "摩尔多瓦",
    "georgia": "格鲁吉亚", "armenia": "亚美尼亚", "azerbaijan": "阿塞拜疆",
    "portugal": "葡萄牙", "greece": "希腊", "cyprus": "塞浦路斯",
    "iceland": "冰岛", "ireland": "爱尔兰", "austria": "奥地利",
    "switzerland": "瑞士", "belgium": "比利时", "netherlands": "荷兰",
    "luxembourg": "卢森堡", "denmark": "丹麦", "norway": "挪威",
    "sweden": "瑞典", "finland": "芬兰",
    "australia": "澳大利亚", "new zealand": "新西兰",
    "canada": "加拿大",
    "tiempo": "时间", "música": "音乐", "musica": "音乐",
    "deportes": "体育", "noticias": "新闻", "información": "资讯",
    "informacion": "资讯", "entretenimiento": "娱乐",
    "educación": "教育", "educacion": "教育",
    "cultura": "文化", "ciencia": "科学", "tecnología": "技术",
    "tecnologia": "技术", "vida": "生活", "familia": "家庭",
    "religión": "宗教", "religion": "宗教",
    "clásica": "古典", "clasica": "古典",
    "dangdut": "当杜特", "berita": "新闻", "hiburan": "娱乐",
    "pendidikan": "教育", "budaya": "文化", "olahraga": "体育",
    "musik": "音乐", "anak": "少儿", "religi": "宗教",
    "rádio": "广播", "radio station": "广播电台",
    "estación": "台", "estacion": "台",
    "emisora": "电台", "cadena": "频道",
    "fm radio": "调频广播", "am radio": "调幅广播",
}

_BRAND_NAMES = frozenset({
    "cctv", "cctv1", "cctv2", "cctv3", "cctv4", "cctv5", "cctv6", "cctv7",
    "cctv8", "cctv9", "cctv10", "cctv11", "cctv12", "cctv13", "cctv14",
    "cctv15", "cctv16", "cctv17", "cgtn", "bbc", "cnn", "fox", "abc", "nbc",
    "cbs", "hbo", "espn", "mtv", "vh1", "nhk", "kbs", "sbs", "mbc",
    "dw", "rt", "cri",
})

_COUNTRY_CODE_MAP = {
    "cctv": "CN", "cgtn": "CN", "cri": "CN", "卫视": "CN",
    "bbc": "GB", "itv": "GB", "sky": "GB", "channel 4": "GB", "channel 5": "GB",
    "cnn": "US", "fox": "US", "abc": "US", "nbc": "US", "cbs": "US",
    "hbo": "US", "espn": "US", "pbs": "US", "npr": "US", "cnbc": "US",
    "bloomberg": "US", "mtv": "US", "vh1": "US",
    "nhk": "JP", "tbs": "JP", "fuji": "JP", "asahi": "JP", "tv asahi": "JP",
    "kbs": "KR", "sbs": "KR", "mbc": "KR", "jtbc": "KR",
    "dw": "DE", "zdf": "DE", "ard": "DE",
    "france": "FR", "rfi": "FR", "tf1": "FR", "canal+": "FR",
    "rt": "RU", "channel one": "RU",
    "rai": "IT",
    "rte": "IE",
    "tve": "ES", "rtve": "ES",
    "rtp": "PT",
    "svt": "SE", "nrk": "NO", "yle": "FI", "dr": "DK",
    "tvb": "HK", "ats": "HK", "phoenix": "HK",
    "al jazeera": "QA", "al arabiya": "SA",
    "zee": "IN", "ndtv": "IN",
    "indonesia": "ID", "rcti": "ID", "sctv": "ID",
    "colombia": "CO", "caracol": "CO", "rcn": "CO",
    "brazil": "BR", "globo": "BR",
    "argentina": "AR",
    "mexico": "MX", "televisa": "MX", "azteca": "MX",
    "australia": "AU", "abc au": "AU",
    "canada": "CA", "cbc": "CA", "ctv": "CA",
    "star": "SG", "mediacorp": "SG",
}

_CN_KEYWORDS = {"cctv", "cgtn", "cri", "卫视", "央视", "中央", "湖南", "浙江", "江苏",
    "东方", "北京", "山东", "广东", "深圳", "湖北", "四川", "重庆", "天津", "辽宁",
    "安徽", "江西", "河南", "河北", "山西", "陕西", "甘肃", "青海", "宁夏", "新疆",
    "内蒙古", "广西", "西藏", "贵州", "云南", "海南", "吉林", "黑龙江", "福建",
    "上海", "广州", "成都", "武汉", "杭州", "南京", "苏州", "长沙"}


def _infer_country_code(name: str, group: str = "", country: str = "") -> str:
    if country:
        code = country.strip().upper().split(";")[0].strip()
        if code:
            return code
    lower_name = name.lower()
    for kw in _CN_KEYWORDS:
        if kw.lower() in lower_name:
            return "CN"
    for kw, code in sorted(_COUNTRY_CODE_MAP.items(), key=lambda x: -len(x[0])):
        if kw in lower_name:
            return code
    lower_group = group.lower()
    for kw, code in sorted(_COUNTRY_CODE_MAP.items(), key=lambda x: -len(x[0])):
        if kw in lower_group:
            return code
    return ""


def _country_to_flag(code: str) -> str:
    if not code or len(code) != 2:
        return ""
    try:
        offset = 0x1F1E6 - ord('A')
        return chr(ord(code[0].upper()) + offset) + chr(ord(code[1].upper()) + offset)
    except Exception:
        return ""


_COUNTRY_NAME_ZH = {
    "CN": "中国", "HK": "中国香港", "MO": "中国澳门", "TW": "中国台湾",
    "US": "美国", "GB": "英国", "JP": "日本", "KR": "韩国",
    "FR": "法国", "DE": "德国", "RU": "俄罗斯", "IT": "意大利",
    "ES": "西班牙", "PT": "葡萄牙", "NL": "荷兰", "BE": "比利时",
    "SE": "瑞典", "NO": "挪威", "FI": "芬兰", "DK": "丹麦",
    "IE": "爱尔兰", "AT": "奥地利", "CH": "瑞士", "PL": "波兰",
    "CZ": "捷克", "HU": "匈牙利", "RO": "罗马尼亚", "BG": "保加利亚",
    "UA": "乌克兰", "HR": "克罗地亚", "RS": "塞尔维亚", "GR": "希腊",
    "IN": "印度", "PK": "巴基斯坦", "BD": "孟加拉国", "LK": "斯里兰卡",
    "TH": "泰国", "VN": "越南", "PH": "菲律宾", "MY": "马来西亚",
    "SG": "新加坡", "ID": "印度尼西亚", "MM": "缅甸", "KH": "柬埔寨",
    "TR": "土耳其", "IR": "伊朗", "IQ": "伊拉克", "SA": "沙特阿拉伯",
    "AE": "阿联酋", "QA": "卡塔尔", "IL": "以色列",
    "EG": "埃及", "NG": "尼日利亚", "ZA": "南非", "KE": "肯尼亚",
    "MA": "摩洛哥", "TN": "突尼斯",
    "AU": "澳大利亚", "NZ": "新西兰", "CA": "加拿大",
    "BR": "巴西", "AR": "阿根廷", "MX": "墨西哥", "CO": "哥伦比亚",
    "CL": "智利", "PE": "秘鲁", "VE": "委内瑞拉", "CU": "古巴",
}


def _infer_country_flag(name: str, group: str = "", country: str = "") -> str:
    code = _infer_country_code(name, group, country)
    return _country_to_flag(code)


def _infer_country_zh(name: str, group: str = "", country: str = "") -> str:
    code = _infer_country_code(name, group, country)
    return _COUNTRY_NAME_ZH.get(code, "")


_FREQ_IN_NAME_PATTERN = re.compile(
    r'(?:^|[^a-zA-Z0-9])(?:FM\s*)?(\d{2,3}\.\d)\s*(?:MHz|FM|fm)?'
    r'|(?:^|[^a-zA-Z0-9])(?:AM\s*)?(\d{3,4})\s*(?:kHz|AM|am|KHz)',
    re.IGNORECASE
)


def _extract_freq_from_name(name: str) -> tuple:
    m = _FREQ_IN_NAME_PATTERN.search(name)
    if not m:
        return "", name
    if m.group(1):
        try:
            v = float(m.group(1))
            if 70.0 <= v <= 108.0:
                freq = f"FM {m.group(1)}"
            else:
                return "", name
        except ValueError:
            return "", name
    elif m.group(2):
        try:
            v = int(m.group(2))
            if 500 <= v <= 1700:
                freq = f"AM {m.group(2)}"
            else:
                return "", name
        except ValueError:
            return "", name
    else:
        return "", name
    remaining = name[:m.start()] + name[m.end():]
    remaining = re.sub(r'\s+', ' ', remaining).strip()
    return freq, remaining


def _find_city_in_name(lower: str) -> tuple:
    for pinyin, hanzi in sorted(_CITY_PINYIN_MAP.items(), key=lambda x: -len(x[0])):
        idx = lower.find(pinyin)
        if idx < 0:
            continue
        before = lower[idx - 1] if idx > 0 else ' '
        after = lower[idx + len(pinyin)] if idx + len(pinyin) < len(lower) else ' '
        if not before.isalpha() and not after.isalpha():
            return hanzi, pinyin, idx
    for pinyin, hanzi in sorted(_CITY_PINYIN_MAP.items(), key=lambda x: -len(x[0])):
        idx = lower.find(pinyin)
        if idx < 0:
            continue
        if idx == 0 or not lower[idx - 1].isalpha():
            after_char = lower[idx + len(pinyin)] if idx + len(pinyin) < len(lower) else ''
            if after_char and after_char in 'aeiou':
                continue
            return hanzi, pinyin, idx
    return None, None, -1


def _translate_city_and_terms(name: str) -> str:
    lower = name.lower().strip()
    freq_str, name_no_freq = _extract_freq_from_name(lower)
    lower_no_freq = name_no_freq.lower().strip()

    city_hanzi, city_pinyin, _ = _find_city_in_name(lower_no_freq)
    if city_hanzi:
        rest = lower_no_freq.replace(city_pinyin, '', 1).strip()
        rest = re.sub(r'^[\s,;\-]+', '', rest)
        for eng, cn in sorted(_BROADCAST_TERM_MAP.items(), key=lambda x: -len(x[0])):
            pattern = re.compile(re.escape(eng), re.IGNORECASE)
            if pattern.search(rest):
                rest = pattern.sub(cn, rest, count=1)
        for p, h in sorted(_CITY_PINYIN_MAP.items(), key=lambda x: -len(x[0])):
            if p == city_pinyin:
                continue
            idx = rest.find(p)
            if idx >= 0:
                before_c = rest[idx - 1] if idx > 0 else ' '
                after_c = rest[idx + len(p)] if idx + len(p) < len(rest) else ' '
                if not before_c.isalpha() and not after_c.isalpha():
                    rest = rest[:idx] + h + rest[idx + len(p):]
                    break
        for pw, cn in sorted(_PINYIN_WORD_MAP.items(), key=lambda x: -len(x[0])):
            if pw in rest:
                rest = rest.replace(pw, cn, 1)
                break
        result = f"{city_hanzi}{rest}".strip()
    else:
        result = lower_no_freq
        translated_any = False
        for eng, cn in sorted(_BROADCAST_TERM_MAP.items(), key=lambda x: -len(x[0])):
            pattern = re.compile(re.escape(eng), re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(cn, result, count=1)
                translated_any = True
        for pw, cn in sorted(_PINYIN_WORD_MAP.items(), key=lambda x: -len(x[0])):
            if pw in result:
                result = result.replace(pw, cn, 1)
                translated_any = True
                break
        if not translated_any:
            return ""

    if freq_str:
        result = f"{result} {freq_str}".strip()
    result = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', result)
    result = re.sub(r'([\u4e00-\u9fff])\s+(FM|AM)', r'\1 \2', result)
    if not _has_chinese(result):
        return ""
    return result


_PINYIN_SYLLABLES = frozenset({
    "a", "ai", "an", "ang", "ao", "ba", "bai", "ban", "bang", "bao",
    "bei", "ben", "beng", "bi", "bian", "biao", "bie", "bin", "bing",
    "bo", "bu", "ca", "cai", "can", "cang", "cao", "ce", "cen", "ceng",
    "cha", "chai", "chan", "chang", "chao", "che", "chen", "cheng",
    "chi", "chong", "chou", "chu", "chua", "chuai", "chuan", "chuang",
    "chui", "chun", "chuo", "ci", "cong", "cou", "cu", "cuan", "cui",
    "cun", "cuo", "da", "dai", "dan", "dang", "dao", "de", "dei",
    "den", "deng", "di", "dia", "dian", "diao", "die", "ding", "diu",
    "dong", "dou", "du", "duan", "dui", "dun", "duo", "e", "ei", "en",
    "eng", "er", "fa", "fan", "fang", "fei", "fen", "feng", "fo", "fou",
    "fu", "ga", "gai", "gan", "gang", "gao", "ge", "gei", "gen", "geng",
    "gong", "gou", "gu", "gua", "guai", "guan", "guang", "gui", "gun",
    "guo", "ha", "hai", "han", "hang", "hao", "he", "hei", "hen", "heng",
    "hong", "hou", "hu", "hua", "huai", "huan", "huang", "hui", "hun",
    "huo", "ji", "jia", "jian", "jiang", "jiao", "jie", "jin", "jing",
    "jiong", "jiu", "ju", "juan", "jue", "jun", "ka", "kai", "kan",
    "kang", "kao", "ke", "ken", "keng", "kong", "kou", "ku", "kua",
    "kuai", "kuan", "kuang", "kui", "kun", "kuo", "la", "lai", "lan",
    "lang", "lao", "le", "lei", "leng", "li", "lia", "lian", "liang",
    "liao", "lie", "lin", "ling", "liu", "lo", "long", "lou", "lu",
    "lv", "luan", "lve", "lue", "lun", "luo", "ma", "mai", "man", "mang",
    "mao", "me", "mei", "men", "meng", "mi", "mian", "miao", "mie",
    "min", "ming", "miu", "mo", "mou", "mu", "na", "nai", "nan", "nang",
    "nao", "ne", "nei", "nen", "neng", "ni", "nian", "niang", "niao",
    "nie", "nin", "ning", "niu", "nong", "nou", "nu", "nv", "nuan",
    "nve", "nuo", "o", "ou", "pa", "pai", "pan", "pang", "pao", "pei",
    "pen", "peng", "pi", "pian", "piao", "pie", "pin", "ping", "po",
    "pou", "pu", "qi", "qia", "qian", "qiang", "qiao", "qie", "qin",
    "qing", "qiong", "qiu", "qu", "quan", "que", "qun", "ran", "rang",
    "rao", "re", "ren", "reng", "ri", "rong", "rou", "ru", "rua",
    "ruan", "rui", "run", "ruo", "sa", "sai", "san", "sang", "sao",
    "se", "sen", "seng", "sha", "shai", "shan", "shang", "shao", "she",
    "shei", "shen", "sheng", "shi", "shou", "shu", "shua", "shuai",
    "shuan", "shuang", "shui", "shun", "shuo", "si", "song", "sou",
    "su", "suan", "sui", "sun", "suo", "ta", "tai", "tan", "tang",
    "tao", "te", "teng", "ti", "tian", "tiao", "tie", "ting", "tong",
    "tou", "tu", "tuan", "tui", "tun", "tuo", "wa", "wai", "wan", "wang",
    "wei", "wen", "weng", "wo", "wu", "xi", "xia", "xian", "xiang",
    "xiao", "xie", "xin", "xing", "xiong", "xiu", "xu", "xuan", "xue",
    "xun", "ya", "yan", "yang", "yao", "ye", "yi", "yin", "ying", "yo",
    "yong", "you", "yu", "yuan", "yue", "yun", "za", "zai", "zan",
    "zang", "zao", "ze", "zei", "zen", "zeng", "zha", "zhai", "zhan",
    "zhang", "zhao", "zhe", "zhei", "zhen", "zheng", "zhi", "zhong",
    "zhou", "zhu", "zhua", "zhuai", "zhuan", "zhuang", "zhui", "zhun",
    "zhuo", "zi", "zong", "zou", "zu", "zuan", "zui", "zun", "zuo",
})


def _split_pinyin(text: str) -> list:
    if not text or len(text) < 2:
        return []
    lower = text.lower().strip()
    if any(c.isdigit() for c in lower):
        return []
    results = []
    def _greedy(s, acc):
        if not s:
            results.append(acc[:])
            return
        matched = False
        for end in range(min(6, len(s)), 0, -1):
            candidate = s[:end]
            if candidate in _PINYIN_SYLLABLES:
                acc.append(candidate)
                _greedy(s[end:], acc)
                acc.pop()
                matched = True
                break
        if not matched:
            return
    _greedy(lower, [])
    if not results:
        return []
    original = lower
    for r in results:
        if "".join(r) == original:
            return r
    return results[0] if results else []


def _pypinyin_reverse(name: str) -> str:
    if not _PYPINYIN_AVAILABLE:
        return ""
    clean = re.sub(r'[^a-zA-Z\s]', ' ', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean or len(clean) < 2:
        return ""
    words = clean.split()
    if any(w.lower() in _BRAND_NAMES for w in words):
        return ""
    all_syllables = []
    for word in words:
        syllables = _split_pinyin(word)
        if syllables:
            all_syllables.extend(syllables)
        else:
            all_syllables.append(word)
    try:
        from pypinyin import pinyin, Style
        chars = []
        for s in all_syllables:
            if s.lower() in _PINYIN_SYLLABLES:
                candidates = pinyin(s, style=Style.NORMAL, heteronym=True)
                if candidates and candidates[0]:
                    chars.append(candidates[0][0])
                else:
                    chars.append(s)
            else:
                return ""
        result = "".join(chars)
        if result == clean.lower().replace(" ", ""):
            return ""
        if not _has_chinese(result):
            return ""
        return result
    except Exception:
        return ""


_BRAND_CHANNEL_MAP = {
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
    "hunantv": "湖南卫视", "zhejiangtv": "浙江卫视",
    "jiangsutv": "江苏卫视", "beijingtv": "北京卫视",
    "shanghaitv": "上海东方卫视", "guangdongtv": "广东卫视",
    "shandongtv": "山东卫视", "hubeitv": "湖北卫视",
    "sichuantv": "四川卫视", "anhuitv": "安徽卫视",
    "henantv": "河南卫视",
    "fujiantv": "福建卫视", "jiangxitv": "江西卫视",
    "liaoningtv": "辽宁卫视", "jilintv": "吉林卫视",
    "heilongjiangtv": "黑龙江卫视", "shanxitv": "山西卫视",
    "shaanxitv": "陕西卫视", "gansutv": "甘肃卫视",
    "qinghaitv": "青海卫视", "tianjintv": "天津卫视",
    "chongqingtv": "重庆卫视", "guizhoutv": "贵州卫视",
    "yunnantv": "云南卫视", "hainantv": "海南卫视",
    "hunan television": "湖南卫视", "zhejiang television": "浙江卫视",
    "jiangsu television": "江苏卫视", "beijing television": "北京卫视",
    "shanghai television": "上海东方卫视", "guangdong television": "广东卫视",
    "shandong television": "山东卫视", "anhui television": "安徽卫视",
    "sichuan television": "四川卫视", "hubei television": "湖北卫视",
    "henan television": "河南卫视", "hebei television": "河北卫视",
    "shanxi television": "山西卫视", "shaanxi television": "陕西卫视",
    "liaoning television": "辽宁卫视", "jilin television": "吉林卫视",
    "fujian television": "福建卫视", "jiangxi television": "江西卫视",
    "chongqing television": "重庆卫视", "tianjin television": "天津卫视",
    "guizhou television": "贵州卫视", "yunnan television": "云南卫视",
    "heilongjiang television": "黑龙江卫视", "gansu television": "甘肃卫视",
    "qinghai television": "青海卫视", "hainan television": "海南卫视",
    "discovery channel": "探索频道", "discovery": "探索频道", "national geographic": "国家地理",
    "nat geo": "国家地理", "nat geo wild": "国家地理野生", "nat geo people": "国家地理人物",
    "bbc": "英国广播公司", "bbc world": "BBC 世界", "bbc news": "BBC 新闻",
    "bbc one": "BBC 一台", "bbc two": "BBC 二台", "bbc four": "BBC 四台",
    "cnn": "美国有线电视新闻网", "cnn international": "CNN 国际", "cnn news": "CNN 新闻",
    "fox": "福克斯", "fox news": "福克斯新闻", "fox sports": "福克斯体育",
    "abc": "美国广播公司", "abc news": "ABC 新闻",
    "nbc": "全国广播公司", "nbc news": "NBC 新闻",
    "cbs": "哥伦比亚广播公司", "hbo": "家庭票房", "hbo max": "HBO Max",
    "espn": "娱乐与体育节目网", "espn2": "ESPN 2",
    "mtv": "音乐电视", "vh1": "VH1 音乐",
    "nhk": "日本放送协会", "nhk world": "NHK 世界",
    "kbs": "韩国放送公社", "kbs world": "KBS 世界",
    "sbs": "首尔广播", "mbc": "文化广播",
    "al jazeera": "半岛电视台", "al jazeera english": "半岛电视台英语",
    "dw": "德国之声", "dw news": "德国之声新闻",
    "rt": "今日俄罗斯", "rtp": "葡萄牙广播电视",
    "france 24": "法国 24", "france 24 english": "法国 24 英语",
    "euronews": "欧洲新闻", "sky news": "天空新闻", "sky sports": "天空体育",
    "bloomberg": "彭博社", "cnbc": "消费者新闻与商业频道",
    "cspan": "C-SPAN", "pbs": "美国公共广播", "npr": "美国国家公共电台",
    "cartoon network": "卡通频道", "disney channel": "迪士尼频道",
    "nickelodeon": "尼克儿童频道", "comedy central": "喜剧中心",
    "sci": "科学频道", "history channel": "历史频道", "h2": "历史二台",
    "tlc": "TLC 频道", "food network": "美食频道", "travel channel": "旅游频道",
    "animal planet": "动物星球", "science channel": "科学频道",
    "lifetime": "一生频道", "a&e": "A&E 频道", "usa network": "USA 频道",
    "tnt": "TNT 频道", "tbs": "TBS 频道", "amc": "AMC 频道",
    "fx": "FX 频道", "syfy": "Syfy 频道", "bravo": "Bravo 频道",
    "trutv": "truTV", "spike": "Spike 频道",
    "star tv": "星空卫视", "star movies": "星空电影", "star world": "星空国际",
    "phoenix tv": "凤凰卫视", "phoenix info": "凤凰资讯",
    "tvb": "电视广播有限公司", "ats": "亚洲电视",
    "cctv news": "CCTV-13 新闻", "cctv5 plus": "CCTV-5+ 体育赛事",
    "cri": "中国国际广播电台",
    "radio france": "法国广播电台", "rfi": "法国国际广播电台",
    "rte": "爱尔兰广播电视", "rai": "意大利广播电视",
    "zdf": "德国电视二台", "ard": "德国公共广播联盟",
    "itv": "英国独立电视", "channel 4": "英国第四频道", "channel 5": "英国第五频道",
    "svt": "瑞典电视台", "nrk": "挪威广播公司", "yle": "芬兰广播公司",
    "dr": "丹麦广播公司", "tv2": "TV2", "tv3": "TV3", "tv4": "TV4",
}

_PINYIN_WORD_MAP = {
    "xinwen": "新闻", "yinyue": "音乐", "tiyu": "体育",
    "jiaotong": "交通", "dianshi": "电视", "dianying": "电影",
    "zongyi": "综艺", "caijing": "财经", "yule": "娱乐",
    "shaonian": "少儿", "jiaoyu": "教育", "guangbo": "广播",
    "diantai": "电台", "wenhua": "文化", "keji": "科技",
    "zonghe": "综合", "quanqiu": "全球", "guonei": "国内",
    "guoji": "国际", "difang": "地方", "shenghuo": "生活",
    "dili": "地理", "lishi": "历史", "ziran": "自然",
    "tiantan": "谈话", "jiankang": "健康", "lvyou": "旅游",
    "meishi": "美食", "shishang": "时尚", "yishu": "艺术",
    "minyao": "民谣", "yaogun": "摇滚", "dianzi": "电子",
    "jueshi": "爵士", "gudian": "古典", "liuxing": "流行",
    "xiangcun": "乡村", "luding": "路顶",
    "wangluo": "网络", "zaixian": "在线", "zhibo": "直播",
    "guojia": "国家", "renmin": "人民", "zhongyang": "中央",
    "jiaotong guangbo": "交通广播", "jiaotongguangbo": "交通广播",
    "xinwen guangbo": "新闻广播", "xinwenguangbo": "新闻广播",
    "yinyue guangbo": "音乐广播", "yinyueguangbo": "音乐广播",
    "tiyu guangbo": "体育广播", "tiyuguangbo": "体育广播",
    "caijing guangbo": "财经广播", "caijingguangbo": "财经广播",
    "shenghuo guangbo": "生活广播", "shenghuoguangbo": "生活广播",
    "guangbo diantai": "广播电台", "guangbodiantai": "广播电台",
    "weishi": "卫视", "weishidianshi": "卫视",
    "weishi dianshi": "卫视",
}

_PINYIN_WORD_BOUNDARY = re.compile(
    r'(?:(?<=\s)|(?<=^)|(?<=[,;\-]))(' +
    '|'.join(re.escape(k) for k in sorted(_PINYIN_WORD_MAP.keys(), key=lambda x: -len(x))) +
    r')(?:(?=\s)|(?=$)|(?=[,;\-]))'
)


def _translate_channel_name(name: str, tvg_name: str = "") -> str:
    if _has_chinese(name):
        return ""
    if tvg_name and _has_chinese(tvg_name):
        return tvg_name
    clean = name.strip().lower()

    for key in sorted(_BRAND_CHANNEL_MAP.keys(), key=lambda k: -len(k)):
        if key in clean:
            return _BRAND_CHANNEL_MAP[key]

    for key in sorted(_PINYIN_WORD_MAP.keys(), key=lambda k: -len(k)):
        if key == clean or re.search(r'(?:(?<=\s)|(?<=^))' + re.escape(key) + r'(?:(?=\s)|(?=$))', clean):
            return _PINYIN_WORD_MAP[key]

    city_result = _translate_city_and_terms(name)
    if city_result:
        return city_result

    pypinyin_result = _pypinyin_reverse(name)
    if pypinyin_result:
        return pypinyin_result

    for key in sorted(_PINYIN_WORD_MAP.keys(), key=lambda k: -len(k)):
        if key in clean:
            return _PINYIN_WORD_MAP[key]

    return ""


def _find_name_comma_pos(line: str) -> int:
    in_quotes = False
    last_comma = -1
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ',' and not in_quotes:
            last_comma = i
    return last_comma


def _parse_extinf_line(line: str, source_category: str = "") -> dict:
    attrs = {}
    comma_pos = _find_name_comma_pos(line)
    if comma_pos >= 0:
        raw_name = line[comma_pos + 1:].strip()
        attrs["name"] = _clean_name(raw_name)

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

    frequency = Channel._extract_frequency(name, group)
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
