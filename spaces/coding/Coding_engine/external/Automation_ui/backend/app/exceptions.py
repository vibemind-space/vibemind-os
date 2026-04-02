"""
Exception Handling for TRAE Backend

Custom exceptions, error handling utilities, and standardized error responses.
"""

import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from .logger_config import get_logger

logger = get_logger("exceptions")


class TRAEBaseException(Exception):
    """Base exception for all TRAE-specific errors"""

    def __init__(
        self,
        message: str,
        error_code: str = "TRAE_ERROR",
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary"""
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class ValidationError(TRAEBaseException):
    """Validation error"""

    def __init__(self, message: str, field: str = None, value: Any = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)

        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
            status_code=400,
        )


class ServiceError(TRAEBaseException):
    """Service operation error"""

    def __init__(self, service_name: str, message: str, operation: str = None):
        details = {"service": service_name}
        if operation:
            details["operation"] = operation

        super().__init__(
            message=message,
            error_code="SERVICE_ERROR",
            details=details,
            status_code=500,
        )


class ConfigurationError(TRAEBaseException):
    """Configuration error"""

    def __init__(self, message: str, config_key: str = None):
        details = {}
        if config_key:
            details["config_key"] = config_key

        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details,
            status_code=500,
        )


class ResourceNotFoundError(TRAEBaseException):
    """Resource not found error"""

    def __init__(self, resource_type: str, resource_id: str = None):
        message = f"{resource_type} not found"
        details = {"resource_type": resource_type}
        if resource_id:
            message += f" with ID: {resource_id}"
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            details=details,
            status_code=404,
        )


class ResourceExistsError(TRAEBaseException):
    """Resource already exists error"""

    def __init__(self, resource_type: str, resource_id: str = None):
        message = f"{resource_type} already exists"
        details = {"resource_type": resource_type}
        if resource_id:
            message += f" with ID: {resource_id}"
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            error_code="RESOURCE_EXISTS",
            details=details,
            status_code=409,
        )


class PermissionError(TRAEBaseException):
    """Permission denied error"""

    def __init__(self, operation: str, resource: str = None):
        message = f"Permission denied for operation: {operation}"
        details = {"operation": operation}
        if resource:
            message += f" on resource: {resource}"
            details["resource"] = resource

        super().__init__(
            message=message,
            error_code="PERMISSION_DENIED",
            details=details,
            status_code=403,
        )


class RateLimitError(TRAEBaseException):
    """Rate limit exceeded error"""

    def __init__(self, limit: int, window: str, current_count: int = None):
        message = f"Rate limit exceeded: {limit} requests per {window}"
        details = {"limit": limit, "window": window}
        if current_count is not None:
            details["current_count"] = current_count

        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
            status_code=429,
        )


class ExternalServiceError(TRAEBaseException):
    """External service error"""

    def __init__(self, service_name: str, message: str, status_code: int = None):
        details = {"external_service": service_name}
        if status_code:
            details["external_status_code"] = status_code

        super().__init__(
            message=f"External service error from {service_name}: {message}",
            error_code="EXTERNAL_SERVICE_ERROR",
            details=details,
            status_code=502,
        )


class TimeoutError(TRAEBaseException):
    """Operation timeout error"""

    def __init__(self, operation: str, timeout_seconds: float):
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds} seconds",
            error_code="OPERATION_TIMEOUT",
            details={"operation": operation, "timeout_seconds": timeout_seconds},
            status_code=408,
        )


class NodeExecutionError(TRAEBaseException):
    """Node execution error"""

    def __init__(self, node_id: str, node_type: str, message: str):
        super().__init__(
            message=f"Node execution failed: {message}",
            error_code="NODE_EXECUTION_ERROR",
            details={"node_id": node_id, "node_type": node_type},
            status_code=500,
        )


class GraphValidationError(TRAEBaseException):
    """Graph validation error"""

    def __init__(self, message: str, graph_id: str = None):
        details = {}
        if graph_id:
            details["graph_id"] = graph_id

        super().__init__(
            message=f"Graph validation error: {message}",
            error_code="GRAPH_VALIDATION_ERROR",
            details=details,
            status_code=400,
        )


class OCRError(TRAEBaseException):
    """OCR processing error"""

    def __init__(self, message: str, language: str = None, region: Dict = None):
        details = {}
        if language:
            details["language"] = language
        if region:
            details["region"] = region

        super().__init__(
            message=f"OCR processing error: {message}",
            error_code="OCR_ERROR",
            details=details,
            status_code=500,
        )


class DesktopStreamingError(TRAEBaseException):
    """Desktop streaming error"""

    def __init__(self, message: str, client_id: str = None):
        details = {}
        if client_id:
            details["client_id"] = client_id

        super().__init__(
            message=f"Desktop streaming error: {message}",
            error_code="DESKTOP_STREAMING_ERROR",
            details=details,
            status_code=500,
        )


class ClickAutomationError(TRAEBaseException):
    """Click automation error"""

    def __init__(self, message: str, coordinates: Dict = None):
        details = {}
        if coordinates:
            details["coordinates"] = coordinates

        super().__init__(
            message=f"Click automation error: {message}",
            error_code="CLICK_AUTOMATION_ERROR",
            details=details,
            status_code=500,
        )


class FileWatcherError(TRAEBaseException):
    """File watcher error"""

    def __init__(self, message: str, path: str = None, watcher_id: str = None):
        details = {}
        if path:
            details["path"] = path
        if watcher_id:
            details["watcher_id"] = watcher_id

        super().__init__(
            message=f"File watcher error: {message}",
            error_code="FILE_WATCHER_ERROR",
            details=details,
            status_code=500,
        )


class WebSocketError(TRAEBaseException):
    """WebSocket error"""

    def __init__(self, message: str, connection_id: str = None):
        details = {}
        if connection_id:
            details["connection_id"] = connection_id

        super().__init__(
            message=f"WebSocket error: {message}",
            error_code="WEBSOCKET_ERROR",
            details=details,
            status_code=500,
        )


# Error response utilities


def create_error_response(
    error: Union[TRAEBaseException, HTTPException, Exception], request: Request = None
) -> JSONResponse:
    """Create standardized error response"""

    # Extract request information if available
    request_info = {}
    if request:
        request_info = {
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else None,
        }

    if isinstance(error, TRAEBaseException):
        # Custom TRAE exception
        response_data = error.to_dict()
        response_data["request_info"] = request_info

        logger.error(
            f"TRAE Error: {error.error_code} - {error.message}",
            extra={
                "error_code": error.error_code,
                "details": error.details,
                "request_info": request_info,
            },
        )

        return JSONResponse(status_code=error.status_code, content=response_data)

    elif isinstance(error, HTTPException):
        # FastAPI HTTP exception
        response_data = {
            "error": True,
            "error_code": "HTTP_ERROR",
            "message": error.detail,
            "details": {"status_code": error.status_code},
            "request_info": request_info,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.error(
            f"HTTP Error: {error.status_code} - {error.detail}",
            extra={"status_code": error.status_code, "request_info": request_info},
        )

        return JSONResponse(status_code=error.status_code, content=response_data)

    else:
        # Generic exception
        error_message = str(error)
        error_type = type(error).__name__

        response_data = {
            "error": True,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {"error_type": error_type, "error_message": error_message},
            "request_info": request_info,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.error(
            f"Unexpected Error: {error_type} - {error_message}",
            extra={"error_type": error_type, "request_info": request_info},
            exc_info=True,
        )

        return JSONResponse(status_code=500, content=response_data)


def handle_validation_errors(errors: List[Dict[str, Any]]) -> ValidationError:
    """Convert Pydantic validation errors to TRAEBaseException"""
    error_messages = []

    for error in errors:
        field = ".".join(str(loc) for loc in error.get("loc", []))
        message = error.get("msg", "Invalid value")
        error_messages.append(f"{field}: {message}")

    combined_message = "; ".join(error_messages)

    # Create ValidationError and manually set details
    validation_error = ValidationError(message=f"Validation failed: {combined_message}")
    validation_error.details["validation_errors"] = errors

    return validation_error


# Exception handler decorators


def handle_service_errors(service_name: str):
    """Decorator to handle service errors"""

    def decorator(func):
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except TRAEBaseException:
                raise
            except Exception as e:
                raise ServiceError(
                    service_name=service_name, message=str(e), operation=func.__name__
                )

        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except TRAEBaseException:
                raise
            except Exception as e:
                raise ServiceError(
                    service_name=service_name, message=str(e), operation=func.__name__
                )

        if hasattr(func, "_is_coroutine"):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def handle_timeout(timeout_seconds: float):
    """Decorator to handle operation timeouts"""
    import asyncio

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    operation=func.__name__, timeout_seconds=timeout_seconds
                )

        return wrapper

    return decorator


# Error aggregation utilities


class ErrorCollector:
    """Collect and manage multiple errors"""

    def __init__(self):
        self.errors: List[TRAEBaseException] = []

    def add_error(self, error: Union[TRAEBaseException, str, Exception]):
        """Add an error to the collection"""
        if isinstance(error, TRAEBaseException):
            self.errors.append(error)
        elif isinstance(error, str):
            self.errors.append(TRAEBaseException(error))
        else:
            self.errors.append(TRAEBaseException(str(error)))

    def has_errors(self) -> bool:
        """Check if any errors were collected"""
        return len(self.errors) > 0

    def get_errors(self) -> List[TRAEBaseException]:
        """Get all collected errors"""
        return self.errors

    def raise_if_errors(self):
        """Raise aggregated error if any errors were collected"""
        if self.has_errors():
            if len(self.errors) == 1:
                raise self.errors[0]
            else:
                error_messages = [error.message for error in self.errors]
                combined_message = "; ".join(error_messages)
                details = {
                    "individual_errors": [error.to_dict() for error in self.errors]
                }

                raise TRAEBaseException(
                    message=f"Multiple errors occurred: {combined_message}",
                    error_code="MULTIPLE_ERRORS",
                    details=details,
                )
