"""代理 URL 编解码工具 —— 统一各模块分散的 base64 拼接实现。

历史问题：stream_proxy / hls_rewriter / m3u8_validator / player_renderer / async_engine
各自实现 base64 编码与代理 URL 拼接，格式略有差异且普遍漏掉 URL 编码。
base64 含 ``+`` ``/`` ``=``，在 query 参数中 ``+`` 会被服务端解析为空格，
未编码会导致目标 URL 解码错误。本模块提供唯一实现：
- ``encode_proxy_url`` 生成完整代理 URL（含 base64 的 URL 安全编码）；
- ``encode_proxy_param`` 仅返回编码后的参数值；
- ``decode_proxy_url`` 兼容「已编码 / 未编码」两种历史格式。
"""
import base64
import logging
from urllib.parse import quote, unquote

logger = logging.getLogger(__name__)


def encode_proxy_param(url: str) -> str:
    """把目标 URL 编码为代理 query 参数值（base64 + URL 安全编码）。"""
    if not url:
        return ""
    encoded = base64.b64encode(url.encode("utf-8")).decode("utf-8")
    return quote(encoded, safe="")


def encode_proxy_url(url: str, proxy_base: str = "/proxy") -> str:
    """把目标 URL 编码为完整代理 URL（如 ``/proxy?url=xxx%3D``）。"""
    if not url:
        return ""
    return f"{proxy_base}?url={encode_proxy_param(url)}"


def decode_proxy_url(encoded_url: str) -> str:
    """把代理 URL 的 ``url`` 参数解码为原始目标 URL。

    兼容两种历史编码方式：
    1) base64 直接传输（aiohttp 的 query_params 已自动 URL 解码，值内不含 ``%``）；
    2) base64 后再 URL quote（``encode_proxy_param`` 的标准形式）。
    """
    try:
        return unquote(base64.b64decode(encoded_url).decode("utf-8"))
    except Exception:
        try:
            decoded = unquote(encoded_url)
            return unquote(base64.b64decode(decoded).decode("utf-8"))
        except Exception as e2:
            logger.warning("URL 解码失败: %s", e2)
            raise ValueError(f"无效的代理 URL 编码: {e2}") from e2
