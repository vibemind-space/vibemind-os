"""
Retry Strategy — Exponential backoff with jitter for resilient LLM API calls.

Provides configurable retry logic for agent LLM calls with:
- Exponential backoff with configurable base/max delay
- Full jitter to prevent thundering herd
- Per-exception-type retry decisions (retry on rate limit, not on auth errors)
- Retry budget (max total retries across all agents per time window)
- Callback hooks for monitoring retries

Usage::

    strategy = RetryStrategy(max_retries=3, base_delay=1.0)

    @strategy.with_retry
    async def call_llm():
        return await client.messages.create(...)

    # Or use as context manager
    async for attempt in strategy.attempts():
        try:
            result = await call_llm()
            break
        except RateLimitError:
            await attempt.retry()
"""

import asyncio
import functools
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type

import structlog

logger = structlog.get_logger(__name__)


class RetryDecision(str, Enum):
    RETRY = "retry"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class RetryAttempt:
    """Metadata for a single retry attempt."""
    attempt_number: int
    max_retries: int
    delay: float
    error: Optional[Exception] = None
    decision: RetryDecision = RetryDecision.RETRY


@dataclass
class RetryStats:
    """Aggregate retry statistics."""
    total_calls: int = 0
    total_retries: int = 0
    total_failures: int = 0
    total_successes: int = 0
    retries_by_error: Dict[str, int] = field(default_factory=dict)
    last_retry_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_retries": self.total_retries,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "retry_rate": (self.total_retries / max(self.total_calls, 1)) * 100,
            "success_rate": (self.total_successes / max(self.total_calls, 1)) * 100,
            "retries_by_error": self.retries_by_error,
        }


class RetryBudget:
    """
    Global retry budget to prevent retry storms.

    Limits total retries across all agents within a sliding time window.
    """

    def __init__(self, max_retries_per_window: int = 50, window_seconds: float = 60.0):
        self.max_retries = max_retries_per_window
        self.window = window_seconds
        self._timestamps: List[float] = []

    def can_retry(self) -> bool:
        """Check if retry budget allows another retry."""
        now = time.time()
        cutoff = now - self.window
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        return len(self._timestamps) < self.max_retries

    def record_retry(self):
        """Record that a retry was consumed."""
        self._timestamps.append(time.time())

    @property
    def remaining(self) -> int:
        now = time.time()
        cutoff = now - self.window
        active = [t for t in self._timestamps if t > cutoff]
        return max(0, self.max_retries - len(active))


# Default retryable exceptions (common LLM API errors)
RETRYABLE_EXCEPTIONS: Set[str] = {
    "RateLimitError",
    "APIStatusError",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "ServiceUnavailableError",
    "ConnectionError",
    "TimeoutError",
    "OSError",
}

# Never retry these
NON_RETRYABLE_EXCEPTIONS: Set[str] = {
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "BadRequestError",
    "InvalidRequestError",
}


def _is_retryable(exc: Exception) -> bool:
    """Determine if an exception is retryable."""
    exc_name = type(exc).__name__

    if exc_name in NON_RETRYABLE_EXCEPTIONS:
        return False

    # Check HTTP status code FIRST — more specific than name-based matching
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status:
        if status == 429:  # Rate limit
            return True
        if 500 <= status <= 599:  # Server errors
            return True
        if 400 <= status <= 499:  # Client errors (not retryable)
            return False

    if exc_name in RETRYABLE_EXCEPTIONS:
        return True

    # Default: retry on connection/timeout errors
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    return False


class RetryStrategy:
    """
    Configurable retry strategy with exponential backoff and jitter.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter: Whether to add random jitter (prevents thundering herd)
        retry_budget: Optional global retry budget
        on_retry: Optional callback(attempt: RetryAttempt) for monitoring
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retry_budget: Optional[RetryBudget] = None,
        on_retry: Optional[Callable] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retry_budget = retry_budget
        self.on_retry = on_retry
        self.stats = RetryStats()

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for attempt N with exponential backoff + jitter."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            delay = random.uniform(0, delay)  # Full jitter
        return delay

    def _decide(self, exc: Exception, attempt: int) -> RetryDecision:
        """Decide whether to retry based on exception type and attempt count."""
        if attempt >= self.max_retries:
            return RetryDecision.FAIL

        if not _is_retryable(exc):
            return RetryDecision.FAIL

        if self.retry_budget and not self.retry_budget.can_retry():
            logger.warning("retry_budget_exhausted", attempt=attempt)
            return RetryDecision.FAIL

        return RetryDecision.RETRY

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with retry logic.

        Args:
            func: Async function to execute
            *args, **kwargs: Arguments to pass to the function

        Returns:
            The function's return value

        Raises:
            The last exception if all retries are exhausted
        """
        self.stats.total_calls += 1
        last_exc = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                self.stats.total_successes += 1
                return result
            except Exception as exc:
                last_exc = exc
                decision = self._decide(exc, attempt)

                retry_attempt = RetryAttempt(
                    attempt_number=attempt,
                    max_retries=self.max_retries,
                    delay=self._calculate_delay(attempt),
                    error=exc,
                    decision=decision,
                )

                if decision == RetryDecision.FAIL:
                    self.stats.total_failures += 1
                    logger.warning(
                        "retry_exhausted",
                        attempt=attempt,
                        error_type=type(exc).__name__,
                        error=str(exc)[:200],
                    )
                    raise

                # Record retry
                self.stats.total_retries += 1
                self.stats.last_retry_at = time.time()
                err_name = type(exc).__name__
                self.stats.retries_by_error[err_name] = (
                    self.stats.retries_by_error.get(err_name, 0) + 1
                )

                if self.retry_budget:
                    self.retry_budget.record_retry()

                if self.on_retry:
                    try:
                        self.on_retry(retry_attempt)
                    except Exception:
                        pass

                logger.info(
                    "retrying",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    delay=f"{retry_attempt.delay:.2f}s",
                    error_type=err_name,
                )
                await asyncio.sleep(retry_attempt.delay)

        self.stats.total_failures += 1
        raise last_exc

    def with_retry(self, func: Callable) -> Callable:
        """Decorator to wrap an async function with retry logic."""

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.execute(func, *args, **kwargs)

        return wrapper


# ---------------------------------------------------------------------------
# Global default retry strategy
# ---------------------------------------------------------------------------

_default_strategy: Optional[RetryStrategy] = None
_default_budget: Optional[RetryBudget] = None


def get_retry_strategy(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> RetryStrategy:
    """Get or create the default retry strategy (singleton)."""
    global _default_strategy, _default_budget
    if _default_strategy is None:
        _default_budget = RetryBudget(max_retries_per_window=100, window_seconds=60.0)
        _default_strategy = RetryStrategy(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            retry_budget=_default_budget,
        )
    return _default_strategy


def get_retry_budget() -> Optional[RetryBudget]:
    """Get the global retry budget."""
    return _default_budget
