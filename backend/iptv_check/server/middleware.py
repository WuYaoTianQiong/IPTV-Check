"""
Global exception handling middleware for FastAPI
Provides unified error response format and structured logging.
"""
import logging
import time
import uuid
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from iptv_check.infra.exceptions import AppBaseException
from iptv_check.infra.metrics import metrics

logger = logging.getLogger(__name__)


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing"""
    return str(uuid.uuid4())[:8]


def format_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Optional[dict] = None,
    correlation_id: Optional[str] = None,
) -> dict:
    """Format a standardized error response"""
    response = {
        "error": {
            "code": error_code,
            "message": message,
            "status": status_code,
        }
    }
    if details:
        response["error"]["details"] = details
    if correlation_id:
        response["error"]["correlation_id"] = correlation_id
    return response


async def app_exception_handler(request: Request, exc: AppBaseException) -> JSONResponse:
    """Handle all application-specific exceptions"""
    correlation_id = request.headers.get("X-Correlation-ID") or getattr(request.state, "correlation_id", None)
    
    logger.error(
        "Application error [%s]: %s",
        exc.error_code,
        exc.message,
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "method": request.method,
            "error_code": exc.error_code,
            "details": exc.details,
        },
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
            correlation_id=correlation_id,
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI request validation errors"""
    correlation_id = request.headers.get("X-Correlation-ID") or getattr(request.state, "correlation_id", None)
    
    logger.warning(
        "Request validation failed: %s",
        exc.errors(),
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "method": request.method,
        },
    )
    
    return JSONResponse(
        status_code=422,
        content=format_error_response(
            error_code="VALIDATION_ERROR",
            message="请求参数验证失败",
            status_code=422,
            details={"validation_errors": exc.errors()},
            correlation_id=correlation_id,
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions (4xx, 5xx)"""
    correlation_id = request.headers.get("X-Correlation-ID") or getattr(request.state, "correlation_id", None)
    
    if exc.status_code >= 500:
        logger.error(
            "HTTP error %d: %s",
            exc.status_code,
            exc.detail,
            extra={"correlation_id": correlation_id, "path": request.url.path},
        )
    else:
        logger.warning(
            "HTTP error %d: %s",
            exc.status_code,
            exc.detail,
            extra={"correlation_id": correlation_id, "path": request.url.path},
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(
            error_code=f"HTTP_{exc.status_code}",
            message=exc.detail if isinstance(exc.detail, str) else "HTTP error occurred",
            status_code=exc.status_code,
            correlation_id=correlation_id,
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any uncaught exceptions"""
    import traceback
    correlation_id = request.headers.get("X-Correlation-ID") or getattr(request.state, "correlation_id", None)

    tb_str = traceback.format_exc()
    logger.error(
        "Unhandled exception in %s %s: %s\n%s",
        request.method,
        request.url.path,
        str(exc),
        tb_str,
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "exception_msg": str(exc),
        },
    )

    return JSONResponse(
        status_code=500,
        content=format_error_response(
            error_code="INTERNAL_SERVER_ERROR",
            message="服务器内部错误",
            status_code=500,
            correlation_id=correlation_id,
            details={"exception": str(exc), "type": type(exc).__name__},
        ),
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to inject correlation ID into every request and record metrics"""

    SLOW_REQUEST_THRESHOLD = 2.0  # 2 seconds

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = generate_correlation_id()

        request.state.correlation_id = correlation_id

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))

        # Record HTTP metrics
        metrics.record_http_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=process_time,
        )

        # Slow request warning
        if process_time > self.SLOW_REQUEST_THRESHOLD:
            logger.warning(
                "Slow request detected: %s %s took %.2fs (threshold: %.2fs)",
                request.method,
                request.url.path,
                process_time,
                self.SLOW_REQUEST_THRESHOLD,
                extra={
                    "correlation_id": correlation_id,
                    "path": request.url.path,
                    "method": request.method,
                    "duration": process_time,
                    "threshold": self.SLOW_REQUEST_THRESHOLD,
                    "event": "slow_request",
                },
            )

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests"""
    
    async def dispatch(self, request: Request, call_next):
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        
        logger.info(
            "Request started: %s %s",
            request.method,
            request.url.path,
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.url.query) if request.url.query else None,
            },
        )
        
        response = await call_next(request)
        
        logger.info(
            "Request completed: %s %s -> %d",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "correlation_id": correlation_id,
                "status_code": response.status_code,
            },
        )
        
        return response


def register_exception_handlers(app):
    """Register all exception handlers on the FastAPI app"""
    app.add_exception_handler(AppBaseException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def register_middleware(app):
    """Register all middleware on the FastAPI app"""
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
