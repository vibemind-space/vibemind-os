"""
Brain Exceptions: Custom Exception Classes for the_brain

Provides a hierarchy of domain-specific exceptions for better
error handling and debugging.

Usage:
    from core.exceptions import ToolExecutionError, CheckpointError

    try:
        execute_tool(...)
    except ToolExecutionError as e:
        logger.error(f"Tool failed: {e.tool_name} - {e.message}")
        if e.retryable:
            retry_execution()
"""

from typing import Optional, Dict, Any
from datetime import datetime


# =============================================================================
# BASE EXCEPTION
# =============================================================================

class BrainError(Exception):
    """
    Base exception for all brain-related errors.

    Attributes:
        message: Human-readable error message
        component: Component that raised the error
        timestamp: When the error occurred
        context: Additional context data
    """

    def __init__(
        self,
        message: str,
        component: str = "brain",
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.component = component
        self.timestamp = datetime.now()
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self):
        return f"[{self.component}] {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "component": self.component,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context
        }


# =============================================================================
# OSCILLATOR EXCEPTIONS
# =============================================================================

class OscillatorError(BrainError):
    """Base exception for oscillator-related errors."""

    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(message, component="oscillator", context=context)


class OscillatorStateError(OscillatorError):
    """Error related to oscillator state."""

    def __init__(self, message: str, channel: Optional[str] = None):
        context = {"channel": channel} if channel else {}
        super().__init__(message, context=context)


class SynchronyError(OscillatorError):
    """Error in synchrony vector computation."""

    def __init__(self, message: str, coherence: Optional[float] = None):
        context = {"coherence": coherence} if coherence else {}
        super().__init__(message, context=context)


# =============================================================================
# TOOL EXECUTION EXCEPTIONS
# =============================================================================

class ToolExecutionError(BrainError):
    """
    Error during tool execution.

    Attributes:
        tool_name: Name of the tool that failed
        retryable: Whether the operation can be retried
        retry_count: Number of retries attempted
        original_error: The underlying exception
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        retryable: bool = False,
        retry_count: int = 0,
        original_error: Optional[Exception] = None,
        context: Optional[Dict] = None
    ):
        self.tool_name = tool_name
        self.retryable = retryable
        self.retry_count = retry_count
        self.original_error = original_error

        ctx = context or {}
        ctx.update({
            "tool_name": tool_name,
            "retryable": retryable,
            "retry_count": retry_count,
            "original_error": str(original_error) if original_error else None
        })

        super().__init__(message, component="executor", context=ctx)


class ToolNotFoundError(ToolExecutionError):
    """Tool not registered in executor."""

    def __init__(self, tool_name: str):
        super().__init__(
            f"Tool not found: {tool_name}",
            tool_name=tool_name,
            retryable=False
        )


class ToolTimeoutError(ToolExecutionError):
    """Tool execution timed out."""

    def __init__(self, tool_name: str, timeout_ms: float):
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_ms}ms",
            tool_name=tool_name,
            retryable=True,
            context={"timeout_ms": timeout_ms}
        )


class ToolBlockedError(ToolExecutionError):
    """Tool execution was blocked by security policy."""

    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            f"Tool '{tool_name}' blocked: {reason}",
            tool_name=tool_name,
            retryable=False,
            context={"block_reason": reason}
        )


# =============================================================================
# CHECKPOINT EXCEPTIONS
# =============================================================================

class CheckpointError(BrainError):
    """Base exception for checkpoint-related errors."""

    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(message, component="checkpoint", context=context)


class CheckpointNotFoundError(CheckpointError):
    """Checkpoint file not found."""

    def __init__(self, checkpoint_name: str, path: Optional[str] = None):
        self.checkpoint_name = checkpoint_name
        context = {"checkpoint_name": checkpoint_name}
        if path:
            context["path"] = path
        super().__init__(f"Checkpoint not found: {checkpoint_name}", context=context)


class CheckpointCorruptedError(CheckpointError):
    """Checkpoint file is corrupted or invalid."""

    def __init__(self, checkpoint_name: str, reason: str):
        self.checkpoint_name = checkpoint_name
        super().__init__(
            f"Checkpoint corrupted: {checkpoint_name} - {reason}",
            context={"checkpoint_name": checkpoint_name, "reason": reason}
        )


class CheckpointRestoreError(CheckpointError):
    """Error restoring from checkpoint."""

    def __init__(self, checkpoint_name: str, reason: str):
        self.checkpoint_name = checkpoint_name
        super().__init__(
            f"Failed to restore checkpoint '{checkpoint_name}': {reason}",
            context={"checkpoint_name": checkpoint_name, "reason": reason}
        )


# =============================================================================
# ROUTING EXCEPTIONS
# =============================================================================

class RoutingError(BrainError):
    """Base exception for routing-related errors."""

    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(message, component="router", context=context)


class SecurityViolationError(RoutingError):
    """Security policy violation detected."""

    def __init__(self, message: str, violation_type: str):
        self.violation_type = violation_type
        super().__init__(
            f"Security violation ({violation_type}): {message}",
            context={"violation_type": violation_type}
        )


class InjectionAttemptError(SecurityViolationError):
    """Prompt injection attempt detected."""

    def __init__(self, suspicious_token: str):
        self.suspicious_token = suspicious_token
        super().__init__(
            f"Injection attempt detected: '{suspicious_token}'",
            violation_type="injection"
        )


class TemporalDecisionError(RoutingError):
    """Error in temporal decision making."""

    def __init__(self, message: str, confidence: Optional[float] = None):
        context = {"confidence": confidence} if confidence else {}
        super().__init__(message, context=context)


# =============================================================================
# TOKEN CLASSIFICATION EXCEPTIONS
# =============================================================================

class ClassificationError(BrainError):
    """Base exception for token classification errors."""

    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(message, component="adapter", context=context)


class TokenExtractionError(ClassificationError):
    """Error extracting tokens from text."""

    def __init__(self, message: str, text_snippet: Optional[str] = None):
        context = {"text_snippet": text_snippet[:50] if text_snippet else None}
        super().__init__(message, context=context)


class LLMClassificationError(ClassificationError):
    """Error in LLM-based classification."""

    def __init__(self, message: str, model: str, response: Optional[str] = None):
        self.model = model
        context = {"model": model}
        if response:
            context["response"] = response[:100]
        super().__init__(message, context=context)


class OllamaConnectionError(LLMClassificationError):
    """Cannot connect to Ollama service."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        super().__init__(
            f"Cannot connect to Ollama at {host}:{port}",
            model="ollama",
            response=None
        )


# =============================================================================
# DASHBOARD/API EXCEPTIONS
# =============================================================================

class APIError(BrainError):
    """Base exception for API-related errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        context: Optional[Dict] = None
    ):
        self.status_code = status_code
        ctx = context or {}
        ctx["status_code"] = status_code
        super().__init__(message, component="dashboard", context=ctx)


class ValidationError(APIError):
    """Request validation failed."""

    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        context = {"field": field} if field else {}
        super().__init__(message, status_code=400, context=context)


class ServiceUnavailableError(APIError):
    """Backend service is unavailable."""

    def __init__(self, service: str):
        self.service = service
        super().__init__(
            f"Service unavailable: {service}",
            status_code=503,
            context={"service": service}
        )


# =============================================================================
# EXCEPTION REGISTRY
# =============================================================================

# Map exception types to HTTP status codes (for API responses)
EXCEPTION_STATUS_CODES = {
    BrainError: 500,
    OscillatorError: 500,
    ToolExecutionError: 500,
    ToolNotFoundError: 404,
    ToolBlockedError: 403,
    ToolTimeoutError: 504,
    CheckpointError: 500,
    CheckpointNotFoundError: 404,
    RoutingError: 500,
    SecurityViolationError: 403,
    ClassificationError: 500,
    APIError: 500,
    ValidationError: 400,
    ServiceUnavailableError: 503,
}


def get_status_code(exception: Exception) -> int:
    """Get HTTP status code for an exception."""
    for exc_type, code in EXCEPTION_STATUS_CODES.items():
        if isinstance(exception, exc_type):
            return code
    return 500


def format_error_response(exception: Exception) -> Dict[str, Any]:
    """Format exception as API error response."""
    if isinstance(exception, BrainError):
        return {
            "error": True,
            "error_type": exception.__class__.__name__,
            "message": exception.message,
            "component": exception.component,
            "status_code": get_status_code(exception),
            "context": exception.context
        }
    else:
        return {
            "error": True,
            "error_type": type(exception).__name__,
            "message": str(exception),
            "status_code": 500
        }


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  BRAIN EXCEPTIONS TEST")
    print("=" * 60)

    # Test various exceptions
    exceptions = [
        OscillatorStateError("Invalid amplitude", channel="A"),
        ToolNotFoundError("unknown_tool"),
        ToolTimeoutError("slow_tool", 5000),
        ToolBlockedError("dangerous_tool", "Security policy violation"),
        CheckpointNotFoundError("missing_checkpoint", "/path/to/checkpoint"),
        SecurityViolationError("Suspicious pattern detected", "injection"),
        ValidationError("Missing required field", field="text"),
    ]

    for exc in exceptions:
        print(f"\n{exc.__class__.__name__}:")
        print(f"  Message: {exc}")
        print(f"  Status Code: {get_status_code(exc)}")
        print(f"  Dict: {exc.to_dict()}")

    print("\n" + "=" * 60)
    print("  Exception test complete")
    print("=" * 60)
