"""
Unified player HTML renderer — single source of truth for all player entry points.
"""
import base64
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Optional

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

    @property
    def template_path(self) -> Path:
        return self._template_dir / "player.html"

    def _read_template(self) -> str:
        if self._cached_template is None:
            tp = self.template_path
            if not tp.is_file():
                raise FileNotFoundError(f"Player template not found: {tp}")
            self._cached_template = tp.read_text(encoding="utf-8")
            logger.info("Player template loaded from: %s", tp)
        return self._cached_template

    def _encode_proxy_url(self, stream_url: str) -> str:
        """Base64-encode then URL-quote for safe embedding in proxy query param."""
        if not stream_url:
            return ""
        encoded = base64.b64encode(stream_url.encode("utf-8")).decode("utf-8")
        return urllib.parse.quote(encoded, safe="")

    def render(
        self,
        stream_url: str = "",
        channel_name: str = "未知频道",
        sources: Optional[list] = None,
        is_radio: bool = False,
        channel_group: str = "",
        country_flag: str = "",
        frequency: str = "",
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
        """
        template = self._read_template()
        proxy_url = f"/proxy?url={self._encode_proxy_url(stream_url)}" if stream_url else ""

        has_multi_sources = sources and len(sources) > 1

        variables = {
            "stream_url": stream_url,
            "channel_name": channel_name,
            "proxy_url": proxy_url,
            "sources": sources,
            "sources_json": json.dumps(sources, ensure_ascii=False) if sources else "null",
            "recommended_idx": self._find_recommended_idx(sources) if sources else -1,
            "source_selector_class": "visible" if has_multi_sources else "",
            "is_radio": "true" if is_radio else "false",
            "channel_group": channel_group,
            "country_flag": country_flag,
            "frequency": frequency,
        }

        html = template
        for key, value in variables.items():
            html = html.replace("{{ " + key + " }}", str(value))
        return html

    @staticmethod
    def _find_recommended_idx(sources: list) -> int:
        for i, src in enumerate(sources):
            if src.get("recommended"):
                return i
        return 0


# Module-level singleton — all callers share the same cached template.
player_renderer = PlayerRenderer()
