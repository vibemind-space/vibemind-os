"""
Logging Infrastructure for TRAE Backend

Centralized logging setup with structured logging, correlation IDs,
and performance monitoring.
"""

import functools
import logging
import logging.config
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .config import get_settings

# Global logger instances
_loggers: Dict[str, logging.Logger] = {}
_correlation_id: Optional[str] = None


class CorrelationFilter(logging.Filter):
    """Add correlation ID to log records"""

    def filter(self, record):
        record.correlation_id = get_correlation_id() or "N/A"
        return True


class PerformanceFilter(logging.Filter):
    """Add performance metrics to log records"""

    def filter(self, record):
        record.timestamp = datetime.utcnow().isoformat()
        return True


def setup_logging():
    """Setup logging configuration"""
    settings = get_settings()

    # Get logging config from settings
    config = settings.get_logging_config()

    # Add custom filters
    config["filters"] = {
        "correlation": {"()": CorrelationFilter},
        "performance": {"()": PerformanceFilter},
    }

    # Update formatters to include custom fields
    config["formatters"]["default"][
        "format"
    ] = "%(timestamp)s - %(correlation_id)s - %(name)s - %(levelname)s - %(message)s"
    config["formatters"]["detailed"]["format"] = (
        "%(timestamp)s - %(correlation_id)s - %(name)s - %(levelname)s - "
        "%(module)s:%(lineno)d - %(funcName)s - %(message)s"
    )

    # Add filters to handlers
    for handler_name, handler_config in config["handlers"].items():
        handler_config["filters"] = ["correlation", "performance"]

    # Apply configuration
    logging.config.dictConfig(config)

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.info("Logging system initialized")


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger instance"""
    if name not in _loggers:
        _loggers[name] = logging.getLogger(f"trae.{name}")
    return _loggers[name]


def set_correlation_id(correlation_id: str):
    """Set correlation ID for request tracking"""
    global _correlation_id
    _correlation_id = correlation_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID"""
    return _correlation_id


def clear_correlation_id():
    """Clear correlation ID"""
    global _correlation_id
    _correlation_id = None


@contextmanager
def correlation_context(correlation_id: Optional[str] = None):
    """Context manager for correlation ID"""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    old_id = get_correlation_id()
    set_correlation_id(correlation_id)
    try:
        yield correlation_id
    finally:
        if old_id:
            set_correlation_id(old_id)
        else:
            clear_correlation_id()


def log_performance(logger: logging.Logger = None):
    """Decorator for performance logging"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)

            start_time = time.time()
            func_logger.debug(
                f"Starting {func.__name__}",
                extra={
                    "function": func.__name__,
                    "module": func.__module__,
                    "args_count": len(args),
                    "kwargs_count": len(kwargs),
                },
            )

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                func_logger.info(
                    f"Completed {func.__name__} in {duration:.3f}s",
                    extra={
                        "function": func.__name__,
                        "module": func.__module__,
                        "duration": duration,
                        "success": True,
                    },
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                func_logger.error(
                    f"Failed {func.__name__} after {duration:.3f}s: {str(e)}",
                    extra={
                        "function": func.__name__,
                        "module": func.__module__,
                        "duration": duration,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)

            start_time = time.time()
            func_logger.debug(
                f"Starting async {func.__name__}",
                extra={
                    "function": func.__name__,
                    "module": func.__module__,
                    "args_count": len(args),
                    "kwargs_count": len(kwargs),
                    "async": True,
                },
            )

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                func_logger.info(
                    f"Completed async {func.__name__} in {duration:.3f}s",
                    extra={
                        "function": func.__name__,
                        "module": func.__module__,
                        "duration": duration,
                        "success": True,
                        "async": True,
                    },
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                func_logger.error(
                    f"Failed async {func.__name__} after {duration:.3f}s: {str(e)}",
                    extra={
                        "function": func.__name__,
                        "module": func.__module__,
                        "duration": duration,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "async": True,
                    },
                    exc_info=True,
                )

                raise

        # Return appropriate wrapper based on function type
        if hasattr(func, "_is_coroutine"):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_api_request(logger: logging.Logger = None):
    """Decorator for API request logging"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            func_logger = logger or get_logger("api")

            # Extract request information
            request_info = {}
            if args and hasattr(args[0], "method"):
                request = args[0]
                request_info = {
                    "method": request.method,
                    "url": str(request.url),
                    "client": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                }

            start_time = time.time()

            with correlation_context():
                func_logger.info(
                    f"API Request: {func.__name__}",
                    extra={"endpoint": func.__name__, "request_info": request_info},
                )

                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time

                    func_logger.info(
                        f"API Response: {func.__name__} completed in {duration:.3f}s",
                        extra={
                            "endpoint": func.__name__,
                            "duration": duration,
                            "success": True,
                            "request_info": request_info,
                        },
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time

                    func_logger.error(
                        f"API Error: {func.__name__} failed after {duration:.3f}s: {str(e)}",
                        extra={
                            "endpoint": func.__name__,
                            "duration": duration,
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "request_info": request_info,
                        },
                        exc_info=True,
                    )

                    raise

        return wrapper

    return decorator


class LoggerMixin:
    """Mixin class to add logging capabilities to any class"""

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class"""
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__.lower())
        return self._logger

    def log_info(self, message: str, **kwargs):
        """Log info message with extra context"""
        self.logger.info(message, extra=kwargs)

    def log_debug(self, message: str, **kwargs):
        """Log debug message with extra context"""
        self.logger.debug(message, extra=kwargs)

    def log_warning(self, message: str, **kwargs):
        """Log warning message with extra context"""
        self.logger.warning(message, extra=kwargs)

    def log_error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error message with extra context"""
        self.logger.error(message, exc_info=exc_info, extra=kwargs)

    def log_critical(self, message: str, exc_info: bool = False, **kwargs):
        """Log critical message with extra context"""
        self.logger.critical(message, exc_info=exc_info, extra=kwargs)


# Convenience functions
def get_api_logger() -> logging.Logger:
    """Get API logger"""
    return get_logger("api")


def get_service_logger(service_name: str) -> logging.Logger:
    """Get service logger"""
    return get_logger(f"service.{service_name}")


def get_websocket_logger() -> logging.Logger:
    """Get WebSocket logger"""
    return get_logger("websocket")


def get_database_logger() -> logging.Logger:
    """Get database logger"""
    return get_logger("database")


def get_security_logger() -> logging.Logger:
    """Get security logger"""
    return get_logger("security")


# Initialize logging on import
setup_logging()
