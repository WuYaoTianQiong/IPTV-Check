import asyncio
import base64
import logging
import re
import time
from typing import Optional, Set
from urllib.parse import unquote, urljoin

import aiohttp
from aiohttp import web
from fastapi.responses import Response as FastAPIResponse, StreamingResponse

logger = logging.getLogger(__name__)

FORWARD_HEADERS = {
    "referer", "origin", "cookie", "authorization",
    "x-requested-with", "x-token", "x-api-key",
}

STREAM_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/octet-stream",
    "video/mp2t",
    "video/MP2T",
    "application/mp4",
    "video/mp4",
}


class StreamProxy:
    def __init__(
        self,
        max_connections: int = 100,
        timeout_connect: float = 10,
        timeout_read: float = 60,
    ):
        self._session: Optional[aiohttp.ClientSession] = None
        self._max_connections = max_connections
        self._timeout_playlist = aiohttp.ClientTimeout(
            connect=timeout_connect,
            sock_read=timeout_connect,
        )
        self._timeout_stream = aiohttp.ClientTimeout(
            connect=timeout_connect,
            sock_read=timeout_read,
        )
        self._request_count = 0
        self._error_count = 0
        self._last_stats_time = time.time()
        self._proxy_base = "/proxy"

    async def initialize(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self._max_connections,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True,
                enable_cleanup_closed=True,
                force_close=False,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout_stream,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "*/*",
                },
            )
            logger.info("StreamProxy 会话已初始化，最大连接数: %d", self._max_connections)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("StreamProxy 会话已关闭")

    def decode_proxy_url(self, encoded_url: str) -> str:
        try:
            decoded = base64.b64decode(encoded_url).decode("utf-8")
            return unquote(decoded)
        except Exception as e:
            logger.warning("URL 解码失败: %s", e)
            raise ValueError(f"无效的代理 URL 编码: {str(e)}")

    def _build_forward_headers(self, request: web.Request) -> dict:
        headers = {}
        for key, value in request.headers.items():
            if key.lower() in FORWARD_HEADERS:
                headers[key] = value
        if "referer" not in headers:
            headers["referer"] = "https://www.baidu.com"
        return headers

    def _encode_url(self, url: str) -> str:
        return base64.b64encode(url.encode()).decode()

    async def proxy_unified(self, target_url: str, request: web.Request, custom_headers: dict = None):
        self._request_count += 1
        self._maybe_log_stats()
        forward_headers = self._build_forward_headers(request)
        if custom_headers:
            forward_headers.update(custom_headers)
        try:
            response = await self._session.get(
                target_url,
                headers=forward_headers,
                timeout=self._timeout_playlist,
                ssl=False,
                allow_redirects=True,
            )
        except aiohttp.ClientError as e:
            self._error_count += 1
            logger.warning("代理请求失败 [%s]: %s", target_url, e)
            raise

        content_type = response.headers.get("Content-Type", "").lower()

        if "mpegurl" in content_type or target_url.lower().endswith(".m3u8"):
            try:
                playlist_content = await response.text()
            except Exception as e:
                logger.warning("读取播放列表内容失败: %s", e)
                raise
            modified_playlist = self._rewrite_hls_urls(playlist_content, target_url)
            return FastAPIResponse(
                content=modified_playlist,
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                },
            )
        else:
            return StreamingResponse(
                self._stream_content(response),
                media_type=content_type or "application/octet-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                },
            )

    async def _stream_content(self, response):
        try:
            async for chunk in response.content.iter_chunked(65536):
                if chunk:
                    yield chunk
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            response.close()

    def _rewrite_hls_urls(self, playlist_content: str, original_url: str) -> str:
        m3u8_url = original_url.split("?")[0]
        base_url = m3u8_url.rsplit("/", 1)[0] + "/"

        def replace_url(match):
            url = match.group(0)
            if url.startswith(("http://", "https://")):
                encoded = self._encode_url(url)
                return f"{self._proxy_base}?url={encoded}"
            elif not url.startswith("#"):
                full_url = urljoin(base_url, url)
                encoded = self._encode_url(full_url)
                return f"{self._proxy_base}?url={encoded}"
            return url

        pattern = r'(?:https?://[^\s"\'#,]+|[^\s"\'#,]+\.(?:m3u8|ts|aac|mp4|mp3)[^\s"\'#,]*)'
        return re.sub(pattern, replace_url, playlist_content)

    async def proxy_stream(self, target_url: str, request: web.Request):
        self._request_count += 1
        self._maybe_log_stats()

        forward_headers = self._build_forward_headers(request)

        try:
            response = await self._session.get(
                target_url,
                headers=forward_headers,
                timeout=self._timeout_stream,
                ssl=False,
                allow_redirects=True,
            )
        except aiohttp.ClientError as e:
            self._error_count += 1
            logger.warning("代理请求失败 [%s]: %s", target_url, e)
            raise

        content_type = response.headers.get("Content-Type", "application/octet-stream")

        response_headers = {
            "Content-Type": content_type,
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Origin, Accept, X-Requested-With",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range",
        }

        stream_response = web.StreamResponse(
            status=response.status,
            headers=response_headers,
        )
        await stream_response.prepare(request)

        try:
            async for chunk in response.content.iter_chunked(65536):
                if chunk:
                    await stream_response.write(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            response.close()
            await stream_response.write_eof()

        return stream_response

    async def proxy_hls_playlist(self, target_url: str, request: web.Request):
        self._request_count += 1

        forward_headers = self._build_forward_headers(request)

        try:
            response = await self._session.get(
                target_url,
                headers=forward_headers,
                timeout=self._timeout_playlist,
                ssl=False,
                allow_redirects=True,
            )
        except aiohttp.ClientError as e:
            self._error_count += 1
            logger.warning("HLS 播放列表获取失败 [%s]: %s", target_url, e)
            raise

        try:
            playlist_content = await response.text()
        except Exception as e:
            logger.warning("读取播放列表内容失败: %s", e)
            raise

        modified_playlist = self._rewrite_hls_urls(playlist_content, target_url)

        return web.Response(
            text=modified_playlist,
            content_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )

    def _maybe_log_stats(self):
        now = time.time()
        if now - self._last_stats_time > 60:
            error_rate = (self._error_count / self._request_count * 100) if self._request_count > 0 else 0
            logger.info(
                "StreamProxy 统计: 请求=%d, 错误=%d, 错误率=%.2f%%",
                self._request_count,
                self._error_count,
                error_rate,
            )
            self._request_count = 0
            self._error_count = 0
            self._last_stats_time = now

    def get_stats(self) -> dict:
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "session_open": self._session is not None and not self._session.closed,
        }
