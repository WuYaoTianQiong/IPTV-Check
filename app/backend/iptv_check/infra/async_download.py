"""带轻量重试的 HTTP 文本下载（aiohttp + tenacity）。

此前 fetch_service / check_service 各自使用裸 ``session.get``，网络瞬断、
超时、5xx 直接丢源，无任何重试。本模块提供唯一实现，统一重试策略。

重试语义（关键：不影响批量拉取在线源的性能）：
- **不重试**：读超时（``aiohttp.ServerTimeoutError``，源慢/不可达时重试只会放大
  单源耗时）与 4xx 客户端错误——这两类失败重试收益低、拖慢全量同步；
- **重试**：连接建立失败（``ClientConnectorError``）、服务器断连
  （``ServerDisconnectedError``）、5xx / 429（``RetryableHttpError``）。
"""
import asyncio
import logging

import aiohttp
from tenacity import AsyncRetrying, before_sleep_log, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class NonRetryableHttpError(Exception):
    """HTTP 状态码不可重试（如 4xx 客户端错误），无需继续尝试。"""


class RetryableHttpError(Exception):
    """HTTP 状态码可重试（5xx / 429）。"""


async def fetch_text_with_retry(session: aiohttp.ClientSession, url: str, timeout,
                                attempts: int = 2) -> str:
    """下载 URL 文本，带轻量指数退避重试。

    重试条件：连接建立失败 / 服务器断连 / 5xx / 429（见模块 docstring）。
    4xx 抛 ``NonRetryableHttpError``；重试耗尽后抛原始异常（``reraise=True``）。
    """
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
        retry=retry_if_exception_type((
            aiohttp.ClientConnectorError,
            aiohttp.ServerDisconnectedError,
            RetryableHttpError,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            async with session.get(url, timeout=timeout, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.text()
                if resp.status >= 500 or resp.status == 429:
                    raise RetryableHttpError(f"HTTP {resp.status}")
                raise NonRetryableHttpError(f"HTTP {resp.status}")
