import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    DNS = "dns"
    HTTP = "http"
    SSL = "ssl"
    STREAM_INVALID = "stream_invalid"
    MEDIA_PROBE_FAIL = "media_probe_fail"
    UNKNOWN = "unknown"


@dataclass
class ErrorInfo:
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    retryable: bool = False
    details: Optional[str] = None

    def is_retryable(self, max_retries: int = 3, current_attempt: int = 0) -> bool:
        return self.retryable and current_attempt < max_retries


class ErrorClassifier:
    @staticmethod
    def classify(exception: Exception) -> ErrorInfo:
        exc_type = type(exception).__name__
        exc_str = str(exception).lower()

        import asyncio
        import aiohttp

        if isinstance(exception, asyncio.TimeoutError):
            return ErrorInfo(
                severity=ErrorSeverity.TRANSIENT,
                category=ErrorCategory.TIMEOUT,
                message="请求超时",
                retryable=True,
            )

        if isinstance(exception, aiohttp.ClientSSLError):
            return ErrorInfo(
                severity=ErrorSeverity.PERMANENT,
                category=ErrorCategory.SSL,
                message=f"SSL错误: {str(exception)[:50]}",
                retryable=False,
            )

        if isinstance(exception, aiohttp.ClientConnectorError):
            if "dns" in exc_str or "name resolution" in exc_str:
                return ErrorInfo(
                    severity=ErrorSeverity.PERMANENT,
                    category=ErrorCategory.DNS,
                    message="DNS解析失败",
                    retryable=False,
                )
            if "refused" in exc_str or "actively refused" in exc_str:
                return ErrorInfo(
                    severity=ErrorSeverity.PERMANENT,
                    category=ErrorCategory.CONNECTION,
                    message="连接被拒绝",
                    retryable=False,
                )
            if "reset" in exc_str:
                return ErrorInfo(
                    severity=ErrorSeverity.TRANSIENT,
                    category=ErrorCategory.CONNECTION,
                    message="连接被重置",
                    retryable=True,
                )
            return ErrorInfo(
                severity=ErrorSeverity.PERMANENT,
                category=ErrorCategory.CONNECTION,
                message="连接失败",
                retryable=False,
            )

        if isinstance(exception, aiohttp.ClientResponseError):
            status = exception.status
            if status == 403:
                return ErrorInfo(
                    severity=ErrorSeverity.PERMANENT,
                    category=ErrorCategory.HTTP,
                    message="访问被拒绝(403)",
                    retryable=False,
                )
            if status == 404:
                return ErrorInfo(
                    severity=ErrorSeverity.PERMANENT,
                    category=ErrorCategory.HTTP,
                    message="资源不存在(404)",
                    retryable=False,
                )
            if status >= 500:
                return ErrorInfo(
                    severity=ErrorSeverity.TRANSIENT,
                    category=ErrorCategory.HTTP,
                    message=f"服务器错误({status})",
                    retryable=True,
                )
            return ErrorInfo(
                severity=ErrorSeverity.PERMANENT,
                category=ErrorCategory.HTTP,
                message=f"HTTP错误({status})",
                retryable=False,
            )

        if isinstance(exception, (aiohttp.ClientPayloadError, aiohttp.ClientConnectionError)):
            return ErrorInfo(
                severity=ErrorSeverity.TRANSIENT,
                category=ErrorCategory.CONNECTION,
                message="连接中断",
                retryable=True,
            )

        if isinstance(exception, aiohttp.ServerDisconnectedError):
            return ErrorInfo(
                severity=ErrorSeverity.TRANSIENT,
                category=ErrorCategory.CONNECTION,
                message="服务器断开连接",
                retryable=True,
            )

        if isinstance(exception, ValueError):
            return ErrorInfo(
                severity=ErrorSeverity.PERMANENT,
                category=ErrorCategory.STREAM_INVALID,
                message=str(exception),
                retryable=False,
            )

        if isinstance(exception, MemoryError):
            return ErrorInfo(
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.UNKNOWN,
                message="内存不足",
                retryable=False,
            )

        return ErrorInfo(
            severity=ErrorSeverity.UNKNOWN if hasattr(ErrorSeverity, 'UNKNOWN') else ErrorSeverity.PERMANENT,
            category=ErrorCategory.UNKNOWN,
            message=f"未知错误({exc_type}): {str(exception)[:50]}",
            retryable=False,
        )

    @staticmethod
    def from_media_probe_error(exception: Exception) -> ErrorInfo:
        return ErrorInfo(
            severity=ErrorSeverity.PERMANENT,
            category=ErrorCategory.MEDIA_PROBE_FAIL,
            message=f"流探测失败: {str(exception)[:50]}",
            retryable=False,
        )
