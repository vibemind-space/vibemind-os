"""
Circuit Breaker — Protects external service calls from cascading failures.

Implements the three-state circuit breaker pattern:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is failing, requests are rejected immediately
- HALF_OPEN: Probe requests allowed to test if service has recovered

Used by Minibook connector, DaveLovable bridge, and OpenClaw bridge
to prevent hanging on unavailable external services.

Usage::

    breaker = CircuitBreaker("minibook", failure_threshold=5, recovery_timeout=30)

    async with breaker:
        response = await session.get("http://minibook:8080/api/health")

    # Or with the decorator:
    @circuit_protected("minibook")
    async def call_minibook(url):
        ...
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal - requests pass through
    OPEN = "open"            # Failing - requests rejected
    HALF_OPEN = "half_open"  # Testing - limited requests allowed


@dataclass
class CircuitStats:
    """Statistics for a circuit breaker instance."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    state_changes: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit is open and request is rejected."""
    def __init__(self, service_name: str, state: CircuitState, retry_after: float):
        self.service_name = service_name
        self.state = state
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker OPEN for '{service_name}' - "
            f"retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.

    Args:
        service_name: Identifier for the protected service
        failure_threshold: Number of consecutive failures to trip the circuit
        recovery_timeout: Seconds to wait before testing recovery (OPEN → HALF_OPEN)
        half_open_max_calls: Max probe calls allowed in HALF_OPEN state
        success_threshold: Successes needed in HALF_OPEN to close circuit
        excluded_exceptions: Exception types that don't count as failures
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 2,
        excluded_exceptions: tuple = (),
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        self.excluded_exceptions = excluded_exceptions

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Get current state, auto-transitioning OPEN → HALF_OPEN if timeout elapsed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def stats(self) -> CircuitStats:
        return self._stats

    @property
    def is_available(self) -> bool:
        """Check if the circuit will allow a request."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changes += 1

        logger.info(
            "circuit_breaker_state_change",
            service=self.service_name,
            from_state=old_state.value,
            to_state=new_state.value,
            consecutive_failures=self._stats.consecutive_failures,
        )

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0

    def _on_success(self):
        """Record a successful call."""
        self._stats.total_calls += 1
        self._stats.successful_calls += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = time.time()

        state = self.state
        if state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def _on_failure(self, error: Exception):
        """Record a failed call."""
        # Don't count excluded exceptions as failures
        if isinstance(error, self.excluded_exceptions):
            return

        self._stats.total_calls += 1
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.last_failure_time = time.time()

        state = self.state
        if state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN immediately opens the circuit again
            self._transition_to(CircuitState.OPEN)
        elif state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    async def __aenter__(self):
        """Enter the circuit breaker context."""
        state = self.state
        if state == CircuitState.OPEN:
            retry_after = self.recovery_timeout - (time.time() - self._opened_at)
            self._stats.rejected_calls += 1
            raise CircuitBreakerError(self.service_name, state, max(0, retry_after))

        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                self._stats.rejected_calls += 1
                raise CircuitBreakerError(self.service_name, state, self.recovery_timeout)
            self._half_open_calls += 1

            # Auto-transition from OPEN to HALF_OPEN on first probe
            if self._state == CircuitState.OPEN:
                self._transition_to(CircuitState.HALF_OPEN)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the circuit breaker context."""
        if exc_type is None:
            self._on_success()
        elif exc_val is not None:
            self._on_failure(exc_val)
        return False  # Don't suppress exceptions

    def to_dict(self) -> dict:
        """Get circuit breaker status as a dictionary."""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful": self._stats.successful_calls,
                "failed": self._stats.failed_calls,
                "rejected": self._stats.rejected_calls,
                "consecutive_failures": self._stats.consecutive_failures,
            },
            "config": {
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
            },
        }


# ---------------------------------------------------------------------------
# Registry — shared circuit breakers for all services
# ---------------------------------------------------------------------------

_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    service_name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    **kwargs,
) -> CircuitBreaker:
    """Get or create a circuit breaker for a service (singleton per name)."""
    if service_name not in _breakers:
        _breakers[service_name] = CircuitBreaker(
            service_name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            **kwargs,
        )
    return _breakers[service_name]


def get_all_breaker_status() -> Dict[str, dict]:
    """Get status of all circuit breakers."""
    return {name: breaker.to_dict() for name, breaker in _breakers.items()}


def reset_circuit_breaker(service_name: str):
    """Force-reset a circuit breaker to CLOSED state."""
    if service_name in _breakers:
        breaker = _breakers[service_name]
        breaker._transition_to(CircuitState.CLOSED)
        breaker._stats.consecutive_failures = 0
        logger.info("circuit_breaker_force_reset", service=service_name)


# ---------------------------------------------------------------------------
# Decorator for convenience
# ---------------------------------------------------------------------------

def circuit_protected(
    service_name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    fallback: Optional[Callable] = None,
):
    """
    Decorator to protect an async function with a circuit breaker.

    Usage::

        @circuit_protected("minibook", failure_threshold=3)
        async def call_minibook(url):
            ...

        # With fallback:
        @circuit_protected("minibook", fallback=lambda *a, **kw: {"status": "unavailable"})
        async def call_minibook(url):
            ...
    """
    breaker = get_circuit_breaker(service_name, failure_threshold, recovery_timeout)

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                async with breaker:
                    return await func(*args, **kwargs)
            except CircuitBreakerError:
                if fallback:
                    return fallback(*args, **kwargs)
                raise
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper._circuit_breaker = breaker
        return wrapper
    return decorator
