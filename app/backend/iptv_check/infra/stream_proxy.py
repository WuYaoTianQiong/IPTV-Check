import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional, Set

import aiohttp
from aiohttp import web
from fastapi.responses import Response as FastAPIResponse, StreamingResponse
from pybreaker import CircuitBreaker

from iptv_check.infra.hls_rewriter import rewrite_hls_urls
from iptv_check.infra.proxy_url import decode_proxy_url as _decode_proxy_url

logger = logging.getLogger(__name__)

FORWARD_HEADERS = {
    "referer", "origin", "cookie", "authorization",
    "x-requested-with", "x-token", "x-api-key",
    "range",
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

KNOWN_REFERER_MAP = {
    "nntv.cn": "https://www.nntv.cn/",
    "livehwc4.com": "https://www.nntv.cn/",
    "kankanlive.com": "https://www.nntv.cn/",
    "mobaibox.com": "https://www.baidu.com/",
    "cntv.cn": "https://www.cctv.com/",
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
            sock_read=timeout_read,
        )
        self._timeout_stream = aiohttp.ClientTimeout(
            connect=timeout_connect,
            sock_read=timeout_read,
        )
        self._request_count = 0
        self._error_count = 0
        self._last_stats_time = time.time()
        self._proxy_base = "/proxy"
        # Per-source error tracking for automatic circuit breaking.
        # 熔断状态由 pybreaker 的 per-domain CircuitBreaker 维护（替代此前手写
        # 连续错误计数 + 时间戳判定），此处仅保留累计错误数供 get_stats 展示。
        self._source_errors: dict[str, int] = defaultdict(int)
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._circuit_threshold = 20
        self._circuit_cooldown_secs = 15

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
        return _decode_proxy_url(encoded_url)

    def _infer_referer(self, target_url: str) -> str:
        """根据目标 URL 推断正确的 Referer"""
        url_lower = target_url.lower()
        for domain, referer in KNOWN_REFERER_MAP.items():
            if domain in url_lower:
                return referer
        return "https://www.baidu.com/"

    def _build_forward_headers(self, request: web.Request, target_url: str = "") -> dict:
        headers = {}
        for key, value in request.headers.items():
            if key.lower() in FORWARD_HEADERS:
                headers[key] = value
        if "referer" not in headers:
            if target_url:
                headers["referer"] = self._infer_referer(target_url)
            else:
                headers["referer"] = "https://www.baidu.com"
        return headers

    async def proxy_unified(self, target_url: str, request: web.Request, custom_headers: dict = None):
        self._request_count += 1
        self._maybe_log_stats()

        source_domain = self._extract_domain(target_url)
        if self._is_source_circuit_open(source_domain):
            logger.warning("Source circuit OPEN for %s — fast-failing request", source_domain)
            raise aiohttp.ClientError(f"Circuit open for {source_domain}")

        forward_headers = self._build_forward_headers(request, target_url)
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
        except aiohttp.ServerTimeoutError as e:
            self._error_count += 1
            self._record_source_error(source_domain, e)
            logger.warning("代理请求超时 [%s → %s]: %s", source_domain, target_url[:80], e)
            raise
        except aiohttp.ClientConnectorError as e:
            self._error_count += 1
            self._record_source_error(source_domain, e)
            logger.warning("代理连接拒绝 [%s → %s]: %s", source_domain, target_url[:80], e)
            raise
        except aiohttp.ClientSSLError as e:
            self._error_count += 1
            logger.warning("代理SSL错误 [%s → %s]: %s", source_domain, target_url[:80], e)
            raise
        except aiohttp.ClientError as e:
            self._error_count += 1
            self._record_source_error(source_domain, e)
            logger.warning("代理请求失败 [%s → %s]: %s", source_domain, target_url[:80], e)
            raise

        self._record_source_ok(source_domain)

        content_type = response.headers.get("Content-Type", "").lower()

        if "mpegurl" in content_type or target_url.lower().endswith(".m3u8"):
            try:
                playlist_content = await response.text()
            except Exception as e:
                logger.warning("读取播放列表内容失败: %s", e)
                raise
            modified_playlist = self._rewrite_hls_urls(
                playlist_content, target_url,
                request_scheme=request.url.scheme,
                request_host=request.url.netloc,
            )
            return FastAPIResponse(
                content=modified_playlist,
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                },
            )
        else:
            # 透传 Range/206 相关头：支持浏览器对点播文件（如直连 MP4）seek，
            # 否则 video 元素发 Range 被忽略、只能从头拉全量且无法拖动进度。
            passthrough = {
                k: v for k, v in response.headers.items()
                if k.lower() in ("content-range", "accept-ranges", "content-length",
                                 "content-disposition", "etag", "last-modified")
            }
            return StreamingResponse(
                self._stream_content(response),
                status_code=response.status,
                media_type=content_type or "application/octet-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                    **passthrough,
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

    def _rewrite_hls_urls(self, playlist_content: str, original_url: str, request_scheme: str = "http", request_host: str = "") -> str:
        """Rewrite HLS URLs to use proxy (delegates to hls_rewriter module)."""
        proxy_base = f"{request_scheme}://{request_host}/proxy" if request_host else self._proxy_base
        return rewrite_hls_urls(playlist_content, original_url, proxy_base=proxy_base)

    async def proxy_stream(self, target_url: str, request: web.Request):
        self._request_count += 1
        self._maybe_log_stats()

        source_domain = self._extract_domain(target_url)
        if self._is_source_circuit_open(source_domain):
            logger.warning("Source circuit OPEN for %s — fast-failing stream", source_domain)
            raise aiohttp.ClientError(f"Circuit open for {source_domain}")

        forward_headers = self._build_forward_headers(request, target_url)

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
            self._record_source_error(source_domain, e)
            logger.warning("代理请求失败 [%s]: %s", target_url, e)
            raise

        self._record_source_ok(source_domain)
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

        source_domain = self._extract_domain(target_url)
        if self._is_source_circuit_open(source_domain):
            logger.warning("Source circuit OPEN for %s — fast-failing playlist", source_domain)
            raise aiohttp.ClientError(f"Circuit open for {source_domain}")

        forward_headers = self._build_forward_headers(request, target_url)

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
            self._record_source_error(source_domain, e)
            logger.warning("HLS 播放列表获取失败 [%s]: %s", target_url, e)
            raise

        self._record_source_ok(source_domain)

        try:
            playlist_content = await response.text()
        except Exception as e:
            logger.warning("读取播放列表内容失败: %s", e)
            raise

        modified_playlist = self._rewrite_hls_urls(playlist_content, target_url, request_scheme=request.scheme, request_host=request.host)

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
        circuits_open = [d for d, b in self._circuit_breakers.items() if b.current_state == "open"]
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "session_open": self._session is not None and not self._session.closed,
            "source_errors": dict(self._source_errors),
            "circuits_open": circuits_open,
        }

    # ──── source health tracking (circuit breaker) ────

    def _get_circuit_breaker(self, source_domain: str) -> CircuitBreaker:
        breaker = self._circuit_breakers.get(source_domain)
        if breaker is None:
            breaker = CircuitBreaker(
                fail_max=self._circuit_threshold,
                reset_timeout=self._circuit_cooldown_secs,
            )
            self._circuit_breakers[source_domain] = breaker
        return breaker

    @staticmethod
    def _raise_call_exc(exc: BaseException):
        raise exc

    def _record_source_ok(self, source_domain: str):
        """Clear error state for a healthy source."""
        # pybreaker 的 call() 在成功时重置失败计数 / half-open 时关闭熔断
        self._get_circuit_breaker(source_domain).call(lambda: None)

    def _record_source_error(self, source_domain: str, exception: BaseException):
        """Increment error counter; pybreaker opens the circuit after fail_max failures."""
        self._source_errors[source_domain] += 1
        breaker = self._get_circuit_breaker(source_domain)
        try:
            # 通过 call() 走 pybreaker 失败计数（公开 API，状态机内部处理熔断/半开）
            breaker.call(self._raise_call_exc, exception)
        except Exception:
            pass  # 计数/熔断已由 pybreaker 处理，原始异常由调用方负责

    def _is_source_circuit_open(self, source_domain: str) -> bool:
        """Check if the circuit for a source is currently open (blocked)."""
        return self._get_circuit_breaker(source_domain).current_state == "open"

    def _extract_domain(self, url: str) -> str:
        """Extract a simplified domain key from a URL for tracking."""
        url_lower = url.lower()
        for prefix in ("http://", "https://"):
            if url_lower.startswith(prefix):
                rest = url_lower[len(prefix):]
                domain = rest.split("/")[0].split(":")[0].split("?")[0]
                return domain
        return url_lower.split("/")[0].split("?")[0]
