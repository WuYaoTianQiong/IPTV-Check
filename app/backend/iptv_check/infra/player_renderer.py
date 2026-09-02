"""
Unified player HTML renderer — single source of truth for all player entry points.
"""
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment

from iptv_check.infra.proxy_url import encode_proxy_param

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "server" / "templates"


class PlayerRenderer:
    """
    Renders the unified player HTML page.

    All three entry points (FastAPI /player route, PlayerService desktop window,
    and the legacy render_player_html() compat wrapper) converge here.
    """

    def __init__(self, template_dir: Optional[Path] = None):
        self._template_dir = template_dir or _TEMPLATE_DIR
        self._cached_template: Optional[str] = None
        # Jinja2 渲染：HTML 位置自动转义防 XSS；JS 位置由模板中的 |tojson 安全输出。
        self._env = Environment(autoescape=True, keep_trailing_newline=True)

    @property
    def template_path(self) -> Path:
        return self._template_dir / "player.html"

    def _read_template(self) -> str:
        tp = self.template_path
        if not tp.is_file():
            raise FileNotFoundError(f"Player template not found: {tp}")
        mtime = tp.stat().st_mtime
        if self._cached_template is None or getattr(self, '_cached_mtime', 0) != mtime:
            self._cached_template = tp.read_text(encoding="utf-8")
            self._cached_mtime = mtime
        return self._cached_template

    def _encode_proxy_url(self, stream_url: str) -> str:
        """Base64-encode then URL-quote for safe embedding in proxy query param."""
        return encode_proxy_param(stream_url)

    def render(
        self,
        stream_url: str = "",
        channel_name: str = "未知频道",
        sources: Optional[list] = None,
        is_radio: bool = False,
        channel_group: str = "",
        country_flag: str = "",
        frequency: str = "",
        tvg_id: str = "",
        tvg_name: str = "",
    ) -> str:
        """
        Render the complete player HTML page.

        Args:
            stream_url: Primary stream URL (typically an M3U8).
            channel_name: Human-readable channel name shown in the header.
            sources: Optional list of alternative source dicts, each with:
                     {url, latency, recommended (bool)}.
            is_radio: Whether this is a radio (audio-only) channel.
            frequency: Radio frequency info (e.g., "FM 104.5").
            tvg_id: XMLTV channel id used for EPG lookup (fallback by channel name).
            tvg_name: XMLTV display name used for EPG lookup (fallback by channel name).
        """
        template = self._read_template()
        proxy_url = f"/proxy?url={self._encode_proxy_url(stream_url)}" if stream_url else ""

        has_multi_sources = sources and len(sources) >= 1
        # 节目单优先按 tvg-name 匹配（命中率更高），否则回退到频道名
        epg_channel = tvg_name or channel_name

        variables = {
            "stream_url": stream_url,
            "channel_name": channel_name,
            "proxy_url": proxy_url,
            "sources": sources,
            "recommended_idx": self._find_recommended_idx(sources) if sources else -1,
            "source_selector_class": "visible" if has_multi_sources else "",
            "is_radio": is_radio,
            "channel_group": channel_group,
            "country_flag": country_flag,
            "frequency": frequency,
            "tvg_id": tvg_id,
            "tvg_name": tvg_name,
            "epg_channel": epg_channel,
        }

        template = self._env.from_string(self._read_template())
        return template.render(**variables)

    @staticmethod
    def _find_recommended_idx(sources: list) -> int:
        for i, src in enumerate(sources):
            if src.get("recommended"):
                return i
        return 0


# Module-level singleton — all callers share the same cached template.
player_renderer = PlayerRenderer()
