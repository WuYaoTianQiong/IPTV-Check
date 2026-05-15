"""
Structured logging configuration for IPTV-Check
Provides JSON-formatted logs with correlation IDs and context enrichment.
"""
import logging
import sys
import json
import time
from datetime import datetime, timezone
from typing import Optional


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def __init__(self, service_name: str = "iptv-check"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }
        
        # Add optional fields if present
        if hasattr(record, "correlation_id"):
            log_entry["correlation_id"] = record.correlation_id
        
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        
        # Add any extra fields from the record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "relativeCreated",
                "exc_info", "exc_text", "stack_info", "levelname",
                "levelno", "lineno", "pathname", "filename", "module",
                "funcName", "msecs", "process", "processName", "thread",
                "threadName", "message", "correlation_id", "request_id",
                "duration_ms",
            ]:
                if not key.startswith("_") and isinstance(value, (str, int, float, bool, dict, list)):
                    extra_fields[key] = value
        
        if extra_fields:
            log_entry["fields"] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False)


class ContextFilter(logging.Filter):
    """Add correlation ID and other context to log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Try to get correlation_id from various sources
        correlation_id = getattr(record, "correlation_id", None)
        if not correlation_id:
            try:
                from contextvars import copy_context
                ctx = copy_context()
                # This will be set by the middleware
                correlation_id = ctx.get("correlation_id", None)
            except Exception:
                pass
        
        if correlation_id:
            record.correlation_id = correlation_id
        
        return True


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    service_name: str = "iptv-check",
) -> None:
    """Configure structured logging for the application"""
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Set formatter
    if json_format:
        formatter = JsonFormatter(service_name=service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    
    handler.setFormatter(formatter)
    
    # Add context filter
    context_filter = ContextFilter()
    handler.addFilter(context_filter)
    
    # Add handler to root logger
    root_logger.addHandler(handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


class PerformanceLogger:
    """Context manager for logging performance of code blocks"""
    
    def __init__(self, logger_name: str, operation: str):
        self.logger = logging.getLogger(logger_name)
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug("Operation started: %s", self.operation)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        if exc_type:
            self.logger.error(
                "Operation failed: %s (%.2fms)",
                self.operation,
                duration_ms,
                exc_info=(exc_type, exc_val, exc_tb),
            )
        else:
            self.logger.info(
                "Operation completed: %s (%.2fms)",
                self.operation,
                duration_ms,
                extra={"duration_ms": round(duration_ms, 2)},
            )
        return False
