import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, List

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class PathSettings(BaseSettings):
    """统一路径管理，所有路径集中配置并自动校验"""
    
    """Base directory of the backend package"""
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent,
        alias="IPTV_BASE_DIR"
    )
    
    """Data directory for databases, caches, exports"""
    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "data",
        alias="IPTV_DATA_DIR"
    )
    
    """Static files directory (frontend build output)"""
    static_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "static",
        alias="IPTV_STATIC_DIR"
    )
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "IPTV_",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def validate_paths(self) -> "PathSettings":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self

    def ensure_dirs(self):
        """确保所有配置的目录存在"""
        for dir_path in [self.data_dir, self.static_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.debug("Directory ensured: %s", dir_path)

    @property
    def cache_store_dir(self) -> Path:
        return self.data_dir / "cache_store"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def static_assets_dir(self) -> Path:
        return self.static_dir / "assets"

    @property
    def data_assets_dir(self) -> Path:
        return self.data_dir / "assets"


class AppSettings(BaseSettings):
    cache_expiry_hours: int = Field(24, alias="CACHE_EXPIRY_HOURS")
    pages_per_view: int = Field(50, alias="PAGES_PER_VIEW")

    max_threads: int = Field(80, alias="MAX_THREADS")
    min_threads: int = Field(5, alias="MIN_THREADS")

    download_timeout: int = Field(30, alias="DOWNLOAD_TIMEOUT")
    download_retries: int = Field(3, alias="DOWNLOAD_RETRIES")
    download_concurrency: int = Field(5, alias="DOWNLOAD_CONCURRENCY")

    breaker_fail_max: int = Field(5, alias="BREAKER_FAIL_MAX")
    breaker_reset_timeout: int = Field(60, alias="BREAKER_RESET_TIMEOUT")

    reconciliation_interval_ms: int = Field(5000, alias="RECONCILIATION_INTERVAL_MS")

    http_pool_connections: int = Field(10, alias="HTTP_POOL_CONNECTIONS")
    http_pool_maxsize: int = Field(30, alias="HTTP_POOL_MAXSIZE")
    http_max_retries: int = Field(3, alias="HTTP_MAX_RETRIES")

    check_timeout_connect: int = Field(3, alias="CHECK_TIMEOUT_CONNECT")
    check_timeout_read: int = Field(8, alias="CHECK_TIMEOUT_READ")

    stream_proxy_max_connections: int = Field(100, alias="STREAM_PROXY_MAX_CONNECTIONS")
    stream_proxy_timeout_connect: int = Field(10, alias="STREAM_PROXY_TIMEOUT_CONNECT")
    stream_proxy_timeout_read: int = Field(30, alias="STREAM_PROXY_TIMEOUT_READ")

    db_path: Optional[str] = Field(None, alias="DB_PATH")

    cors_origins: list[str] = Field(["*"], alias="CORS_ORIGINS")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "IPTV_",
        "populate_by_name": True,
        "extra": "ignore",
    }


settings = AppSettings()
path_settings = PathSettings()

APP_VERSION = "4.0"
APP_TITLE = f"电视直播源检测工具 V{APP_VERSION}"

CACHE_FILE = "check_cache.json"
CACHE_EXPIRY_HOURS = settings.cache_expiry_hours
PAGES_PER_VIEW = settings.pages_per_view
SETTINGS_FILE = "user_settings.json"


def get_app_path():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_base_dir():
    return str(path_settings.base_dir)


def get_data_dir():
    return str(path_settings.data_dir)


def get_static_dir():
    return str(path_settings.static_dir)


def get_asset_path(filename):
    return str(path_settings.data_assets_dir / filename)


_DEFAULT_ISP_KEYWORDS = {
    "移动": ["移动", "chinamobile", "cmcc", "cmcci", "cncmcc", "mobile", "mobaibox", "中国移动", "211.136", "223.110"],
    "电信": ["电信", "chinatelecom", "ctc", "chinanet", "中国电信", "telecom", "202.96", "202.101", "116.", "222.7"],
    "联通": ["联通", "chinaunicom", "cucc", "unicom", "中国联通", "cnc", "221.2", "221.12", "221.13", "123.1"],
    "广电": ["广电", "cbn", "chinabroadnet", "broadnet", "中国广电"],
    "其他": ["鹏博士", "长城宽带", "中信网络", "铁通", "教育网"],
}

_DEFAULT_ISP_APIS = [
    {"url": "https://myip.ipip.net/json", "fields": ["data", "location"], "priority": 1},
    {"url": "https://httpbin.org/ip", "fields": ["origin"], "priority": 2},
    {"url": "https://ip.360.cn/IPQuery/ipquery", "fields": ["data", "loc"], "priority": 3},
    {"url": "https://whois.pconline.com.cn/ipJson.jsp?json=true", "fields": ["company", "isp", "org"], "priority": 4},
    {"url": "https://qifu-api.baidubce.com/ip/local/geo/v1/district", "fields": ["isp", "org"], "priority": 5},
    {"url": "https://ipapi.co/json/", "fields": ["org", "isp", "asn"], "priority": 6},
]

_DEFAULT_IP_PREFIXES = {
    "移动": [
        "211.136", "211.137", "211.138", "211.139", "211.140", "211.142",
        "211.143", "211.144", "211.145", "211.146", "211.147", "211.148",
        "223.110", "223.111", "223.112", "223.113", "223.114", "223.115",
        "223.116", "223.117", "223.118", "223.119", "223.120", "223.121",
        "117.136", "117.137", "117.138", "117.139", "117.140", "117.141",
        "117.142", "117.143", "117.144", "117.145", "117.146", "117.147",
        "117.148", "117.149", "117.150", "117.151", "117.152", "117.153",
        "117.154", "117.155", "117.156", "117.157", "117.158", "117.159",
        "117.160", "117.161", "117.162", "117.163", "117.164", "117.165",
        "117.166", "117.167", "117.168", "117.169", "117.170", "117.171",
        "117.172", "117.173", "117.174", "117.175", "117.176", "117.177",
        "117.178", "117.179", "117.180", "117.181", "117.182", "117.183",
    ],
    "电信": [
        "202.96", "202.97", "202.98", "202.99", "202.100", "202.101",
        "202.102", "202.103", "202.104", "202.105", "202.106", "202.107",
        "202.108", "202.109", "202.110", "202.111", "202.112", "202.113",
        "202.114", "202.115", "202.116", "202.117", "202.118", "202.119",
        "202.120", "202.121", "202.122", "202.123", "202.124", "202.125",
        "202.126", "202.127", "202.128", "202.129", "202.130", "202.131",
        "222.72", "222.73", "222.74", "222.75", "222.76", "222.77",
        "222.78", "222.79", "222.80", "222.81", "222.82", "222.83",
        "222.84", "222.85", "222.86", "222.87", "222.88", "222.89",
        "222.90", "222.91", "222.92", "222.93", "222.94", "222.95",
    ],
    "联通": [
        "221.2", "221.3", "221.4", "221.5", "221.6", "221.7",
        "221.8", "221.9", "221.10", "221.11", "221.12", "221.13",
        "221.14", "221.15", "221.16", "221.17", "221.18", "221.19",
        "221.20", "221.21", "221.22", "221.23", "221.24", "221.25",
        "123.1", "123.2", "123.3", "123.4", "123.5", "123.6",
        "123.7", "123.8", "123.9", "123.10", "123.11", "123.12",
        "123.13", "123.14", "123.15", "123.16", "123.17", "123.18",
        "123.19", "123.20", "123.21", "123.22", "123.23", "123.24",
        "123.25", "123.26", "123.27", "123.28", "123.29", "123.30",
    ],
}


def _load_isp_config():
    config_path = path_settings.data_dir / "isp_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("isp_keywords", _DEFAULT_ISP_KEYWORDS),
                data.get("isp_apis", _DEFAULT_ISP_APIS),
                data.get("ip_prefixes", _DEFAULT_IP_PREFIXES),
            )
        except Exception as e:
            logger.warning("加载 isp_config.json 失败，使用默认值: %s", e)
    return _DEFAULT_ISP_KEYWORDS, _DEFAULT_ISP_APIS, _DEFAULT_IP_PREFIXES


ISP_KEYWORDS, ISP_APIS, IP_PREFIXES = _load_isp_config()


def _load_player_template() -> str:
    template_path = path_settings.data_assets_dir / "player.html"
    if template_path.exists():
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning("加载 player.html 失败，使用内嵌模板: %s", e)
    return _DEFAULT_PLAYER_HTML


_DEFAULT_PLAYER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>播放：__NAME__</title>
<script src="/hls-static/hls.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#000;color:#fff;font-family:system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;height:100vh}
.video-wrap{flex:1;display:flex;align-items:center;justify-content:center;position:relative}
video{width:100%;max-height:100%}
.bar{background:rgba(0,0,0,0.85);padding:8px 12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,0.1);min-height:40px}
.bar .label{font-size:12px;color:#aaa;white-space:nowrap}
.bar .src-btn{font-size:11px;padding:3px 8px;border:1px solid rgba(255,255,255,0.2);border-radius:4px;background:transparent;color:#ccc;cursor:pointer;white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis}
.bar .src-btn:hover{border-color:rgba(255,255,255,0.5);color:#fff}
.bar .src-btn.active{border-color:#4CAF50;color:#4CAF50;background:rgba(76,175,80,0.1)}
.bar .src-btn.recommended::after{content:"★";margin-left:2px;color:#FFD700;font-size:9px}
.toast{position:absolute;top:12px;left:50%;transform:translateX(-50%);background:rgba(76,175,80,0.9);color:#fff;padding:6px 14px;border-radius:6px;font-size:12px;opacity:0;transition:opacity 0.3s;pointer-events:none;z-index:10}
.toast.show{opacity:1}
.toast.warn{background:rgba(255,152,0,0.9)}
</style>
</head>
<body>
<div class="video-wrap">
  <video id="video" controls autoplay></video>
  <div id="toast" class="toast"></div>
</div>
<div class="bar" id="bar">
  <span class="label">源列表:</span>
</div>
<script>
var video=document.getElementById('video');
var bar=document.getElementById('bar');
var toastEl=document.getElementById('toast');
var sources=JSON.parse('__SOURCES__');
var currentIdx=0;
var hls=null;
var fallbackTimer=null;

function showToast(msg,type){
  toastEl.textContent=msg;
  toastEl.className='toast show'+(type==='warn'?' warn':'');
  clearTimeout(toastEl._t);
  toastEl._t=setTimeout(function(){toastEl.className='toast'},3000);
}

function loadSource(idx){
  if(idx<0||idx>=sources.length)return;
  currentIdx=idx;
  var src=sources[idx];
  if(hls){hls.destroy();hls=null;}
  video.onerror=function(){onSourceError(idx)};
  if(typeof Hls!=='undefined'&&Hls.isSupported()&&src.url.indexOf('.m3u8')>0){
    hls=new Hls({enableWorker:true,lowLatencyMode:true});
    hls.loadSource(src.url);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED,function(){video.play();showToast('源'+(idx+1)+' 播放中')});
    hls.on(Hls.Events.ERROR,function(e,data){if(data.fatal)onSourceError(idx)});
  }else{
    video.src=src.url;
    video.play().catch(function(){});
    showToast('源'+(idx+1)+' 播放中');
  }
  updateBar();
  clearTimeout(fallbackTimer);
  fallbackTimer=setTimeout(function(){
    if(video.paused||video.readyState<2){onSourceError(idx)}
  },15000);
}

function onSourceError(idx){
  showToast('源'+(idx+1)+' 不可用，尝试下一个...','warn');
  var next=idx+1;
  while(next<sources.length){
    if(sources[next].is_valid){loadSource(next);return}
    next++;
  }
  if(idx>0){loadSource(0);return}
  showToast('所有源均不可用','warn');
}

function updateBar(){
  var btns=bar.querySelectorAll('.src-btn');
  btns.forEach(function(b,i){
    b.className='src-btn'+(i===currentIdx?' active':'')+(sources[i].recommended?' recommended':'');
  });
}

sources.forEach(function(src,i){
  var btn=document.createElement('button');
  btn.className='src-btn'+(i===0?' active':'')+(src.recommended?' recommended':'');
  btn.textContent='源'+(i+1)+(src.latency?' ('+src.latency+'ms)':'');
  btn.title=src.url;
  btn.onclick=function(){loadSource(i)};
  bar.appendChild(btn);
});

if(sources.length>0)loadSource(0);
</script>
</body>
</html>"""

PLAYER_HTML_TEMPLATE_RAW = _load_player_template()

PLAYER_HTML_TEMPLATE = ""


def render_player_html(url: str, name: str, sources: list = None) -> str:
    import json

    if sources and len(sources) > 1 and "__SOURCES__" in PLAYER_HTML_TEMPLATE_RAW:
        html = PLAYER_HTML_TEMPLATE_RAW.replace("__NAME__", name)
        src_json = json.dumps(sources, ensure_ascii=False).replace("'", "\\'")
        html = html.replace("__URL__", sources[0].get("url", url) if sources else url)
        html = html.replace("'__SOURCES__'", src_json)
        return html

    if sources and "__SOURCES__" in _DEFAULT_PLAYER_HTML:
        html = _DEFAULT_PLAYER_HTML.replace("__NAME__", name)
        src_json = json.dumps(sources, ensure_ascii=False).replace("'", "\\'")
        html = html.replace("__URL__", sources[0].get("url", url) if sources else url)
        html = html.replace("'__SOURCES__'", src_json)
        return html

    html = PLAYER_HTML_TEMPLATE_RAW.replace("__NAME__", name)
    html = html.replace("__URL__", url)
    return html
