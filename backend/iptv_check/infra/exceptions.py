"""
Application-level exception hierarchy for IPTV-Check
Provides structured exception handling with error codes and metadata.
"""
from typing import Optional, Dict, Any


class AppBaseException(Exception):
    """Base exception for all application errors"""
    
    error_code: str = "UNKNOWN_ERROR"
    status_code: int = 500
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class BusinessLogicError(AppBaseException):
    """Business logic validation errors"""
    error_code = "BUSINESS_ERROR"
    status_code = 400


class ResourceNotFoundError(AppBaseException):
    """Resource not found errors"""
    error_code = "NOT_FOUND"
    status_code = 404


class AuthenticationError(AppBaseException):
    """Authentication/authorization errors"""
    error_code = "UNAUTHORIZED"
    status_code = 401


class PermissionDeniedError(AppBaseException):
    """Insufficient permissions errors"""
    error_code = "FORBIDDEN"
    status_code = 403


class ExternalServiceError(AppBaseException):
    """External service communication errors"""
    error_code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502


class RateLimitError(AppBaseException):
    """Rate limit exceeded errors"""
    error_code = "RATE_LIMITED"
    status_code = 429


class DatabaseError(AppBaseException):
    """Database operation errors"""
    error_code = "DATABASE_ERROR"
    status_code = 500


class ChannelNotFoundError(ResourceNotFoundError):
    """Channel not found"""
    error_code = "CHANNEL_NOT_FOUND"
    
    def __init__(self, channel_id: Optional[int] = None):
        message = f"Channel not found (ID: {channel_id})" if channel_id else "Channel not found"
        super().__init__(message, details={"channel_id": channel_id})


class SourceNotFoundError(ResourceNotFoundError):
    """Source not found"""
    error_code = "SOURCE_NOT_FOUND"
    
    def __init__(self, source_id: Optional[str] = None):
        message = f"Source not found (ID: {source_id})" if source_id else "Source not found"
        super().__init__(message, details={"source_id": source_id})


class CheckAlreadyRunningError(BusinessLogicError):
    """Check operation already in progress"""
    error_code = "CHECK_ALREADY_RUNNING"
    
    def __init__(self):
        super().__init__("检测任务正在运行中")


class CheckNotRunningError(BusinessLogicError):
    """Check operation not running"""
    error_code = "CHECK_NOT_RUNNING"
    
    def __init__(self):
        super().__init__("没有正在运行的检测任务")


class InvalidChannelDataError(BusinessLogicError):
    """Invalid channel data format"""
    error_code = "INVALID_CHANNEL_DATA"
    
    def __init__(self, reason: str = ""):
        message = f"Invalid channel data: {reason}" if reason else "Invalid channel data"
        super().__init__(message, details={"reason": reason})


class ExportFailedError(ExternalServiceError):
    """Export operation failed"""
    error_code = "EXPORT_FAILED"
    
    def __init__(self, reason: str = ""):
        message = f"Export failed: {reason}" if reason else "Export failed"
        super().__init__(message, details={"reason": reason})


class StreamProxyError(ExternalServiceError):
    """Stream proxy operation failed"""
    error_code = "STREAM_PROXY_ERROR"
    
    def __init__(self, reason: str = ""):
        message = f"Stream proxy error: {reason}" if reason else "Stream proxy error"
        super().__init__(message, details={"reason": reason})
