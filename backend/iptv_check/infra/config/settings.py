"""
Unified application settings using pydantic-settings.
All configuration is centralized here with type validation.
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field, model_validator

# ============================================================
# Path Settings
# ============================================================

class PathSettings(BaseSettings):
    """统一路径管理，所有路径集中配置并自动校验"""
    
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent,
        description="Base directory of the backend package"
    )
    
    data_dir: Optional[Path] = Field(
        default=None,
        description="Data directory for databases, caches, exports"
    )
    
    static_dir: Optional[Path] = Field(
        default=None,
        description="Static files directory (frontend build output)"
    )
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "IPTV_",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def set_defaults_and_validate(self) -> "PathSettings":
        """Set default paths and ensure directories exist"""
        if self.data_dir is None:
            self.data_dir = self.base_dir / "data"
        if self.static_dir is None:
            self.static_dir = self.base_dir / "static"
        # Ensure all configured directories exist
        for dir_path in [self.data_dir, self.static_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        return self

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


# ============================================================
# Application Settings
# ============================================================

class AppSettings(BaseSettings):
    """Application configuration with type validation"""
    
    # Cache settings
    cache_expiry_hours: int = Field(default=24, ge=1, le=720)
    
    # Pagination
    pages_per_view: int = Field(default=50, ge=10, le=200)
    
    # Thread pool settings
    max_threads: int = Field(default=80, ge=1, le=500)
    min_threads: int = Field(default=5, ge=1, le=50)
    
    # Download settings
    download_timeout: int = Field(default=30, ge=5, le=300)
    download_retries: int = Field(default=3, ge=0, le=10)
    download_concurrency: int = Field(default=5, ge=1, le=50)
    
    # Circuit breaker settings
    breaker_fail_max: int = Field(default=5, ge=1, le=100)
    breaker_reset_timeout: int = Field(default=60, ge=10, le=600)
    
    # Task reconciliation
    reconciliation_interval_ms: int = Field(default=5000, ge=1000, le=60000)
    
    # HTTP client settings
    http_pool_connections: int = Field(default=10, ge=1, le=100)
    http_pool_maxsize: int = Field(default=30, ge=1, le=500)
    http_max_retries: int = Field(default=3, ge=0, le=10)
    
    # Check settings
    check_timeout_connect: int = Field(default=3, ge=1, le=30)
    check_timeout_read: int = Field(default=8, ge=1, le=60)
    
    # Stream proxy settings
    stream_proxy_max_connections: int = Field(default=100, ge=1, le=1000)
    stream_proxy_timeout_connect: int = Field(default=10, ge=1, le=60)
    stream_proxy_timeout_read: int = Field(default=30, ge=1, le=120)
    
    # Database
    db_path: Optional[str] = Field(default=None)
    
    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "IPTV_",
        "extra": "ignore",
    }


# ============================================================
# App metadata
# ============================================================

APP_VERSION = "4.1.0"
APP_TITLE = f"电视直播源检测工具 V{APP_VERSION}"


# ============================================================
# Global settings instances (initialized once)
# ============================================================

path_settings: PathSettings = None  # type: ignore
settings: AppSettings = None  # type: ignore


def initialize_settings() -> tuple[PathSettings, AppSettings]:
    """Initialize and return global settings instances"""
    global path_settings, settings
    
    path_settings = PathSettings()
    settings = AppSettings()
    
    return path_settings, settings


def get_settings() -> AppSettings:
    """Get app settings (initialize if needed)"""
    global settings
    if settings is None:
        _, settings = initialize_settings()
    return settings


def get_path_settings() -> PathSettings:
    """Get path settings (initialize if needed)"""
    global path_settings
    if path_settings is None:
        path_settings, _ = initialize_settings()
    return path_settings


# ============================================================
# ISP Configuration (loaded from file or defaults)
# ============================================================

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


def load_isp_config():
    """Load ISP configuration from file or use defaults"""
    ps = get_path_settings()
    config_path = ps.data_dir / "isp_config.json"
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
            import logging
            logging.getLogger(__name__).warning("加载 isp_config.json 失败，使用默认值: %s", e)
    return _DEFAULT_ISP_KEYWORDS, _DEFAULT_ISP_APIS, _DEFAULT_IP_PREFIXES


ISP_KEYWORDS, ISP_APIS, IP_PREFIXES = load_isp_config()


# ============================================================
# Backward compatibility constants
# ============================================================
# New code should use `settings.*` and `path_settings.*`
# These are kept for gradual migration of existing code

# These get updated when initialize_settings() is called
CACHE_FILE: str = "cache.db"
CACHE_EXPIRY_HOURS: int = 24
SETTINGS_FILE: str = "settings.json"
PLAYER_HTML_TEMPLATE: str = "player.html"


def render_player_html(stream_url: str = "", channel_name: str = "", **kwargs) -> str:
    """Render player HTML page for streaming (delegates to PlayerRenderer)"""
    from iptv_check.infra.player_renderer import player_renderer
    sources = kwargs.get("sources")
    return player_renderer.render(stream_url, channel_name, sources=sources)


def _update_compat_constants():
    """Update backward compatibility constants after settings are initialized"""
    global CACHE_FILE, CACHE_EXPIRY_HOURS, SETTINGS_FILE, PLAYER_HTML_TEMPLATE
    
    ps = get_path_settings()
    s = get_settings()
    CACHE_FILE = str(ps.data_dir / "cache.db")
    CACHE_EXPIRY_HOURS = s.cache_expiry_hours
    SETTINGS_FILE = "settings.json"
    PLAYER_HTML_TEMPLATE = str(ps.data_dir / "player.html")


# Call during import to ensure constants have valid values
# (They'll be updated again when initialize_settings() is called)
try:
    _update_compat_constants()
except Exception:
    # During early import, settings may not be fully initialized yet
    pass
