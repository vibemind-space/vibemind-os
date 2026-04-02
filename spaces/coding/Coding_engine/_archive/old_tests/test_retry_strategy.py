"""Test retry strategy — exponential backoff, jitter, budget, exception classification."""
import asyncio
import sys
import time
sys.path.insert(0, ".")

from src.services.retry_strategy import (
    RetryStrategy,
    RetryBudget,
    RetryDecision,
    RetryAttempt,
    RetryStats,
    _is_retryable,
    get_retry_strategy,
    get_retry_budget,
    RETRYABLE_EXCEPTIONS,
    NON_RETRYABLE_EXCEPTIONS,
)


# ---------------------------------------------------------------------------
# Helper exceptions that simulate real LLM API errors
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    pass

class APITimeoutError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class BadRequestError(Exception):
    pass

class InternalServerError(Exception):
    pass

class ServiceUnavailableError(Exception):
    pass

class APIStatusError(Exception):
    def __init__(self, msg="", status_code=500):
        super().__init__(msg)
        self.status_code = status_code

class UnknownWeirdError(Exception):
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_is_retryable_classification():
    """Exception classification works for known types."""
    assert _is_retryable(RateLimitError("rate limit")) is True
    assert _is_retryable(APITimeoutError("timeout")) is True
    assert _is_retryable(InternalServerError("500")) is True
    assert _is_retryable(ServiceUnavailableError("503")) is True

    assert _is_retryable(AuthenticationError("bad key")) is False
    assert _is_retryable(BadRequestError("invalid")) is False
    print("OK: exception classification")


async def test_is_retryable_status_code():
    """HTTP status code classification via attribute."""
    err_429 = APIStatusError("rate limit", status_code=429)
    err_500 = APIStatusError("server error", status_code=500)
    err_502 = APIStatusError("bad gateway", status_code=502)
    err_400 = APIStatusError("bad request", status_code=400)
    err_403 = APIStatusError("forbidden", status_code=403)

    assert _is_retryable(err_429) is True
    assert _is_retryable(err_500) is True
    assert _is_retryable(err_502) is True
    assert _is_retryable(err_400) is False
    assert _is_retryable(err_403) is False
    print("OK: status code classification")


async def test_is_retryable_builtin_exceptions():
    """Built-in ConnectionError, TimeoutError, OSError are retryable."""
    assert _is_retryable(ConnectionError("conn refused")) is True
    assert _is_retryable(TimeoutError("timed out")) is True
    assert _is_retryable(OSError("network unreachable")) is True
    print("OK: built-in exception classification")


async def test_is_retryable_unknown_exception():
    """Unknown exceptions default to non-retryable."""
    assert _is_retryable(UnknownWeirdError("wat")) is False
    assert _is_retryable(ValueError("bad value")) is False
    print("OK: unknown exceptions not retryable")


async def test_successful_call_no_retry():
    """Successful call returns immediately with no retries."""
    strategy = RetryStrategy(max_retries=3, base_delay=0.01)
    call_count = 0

    async def success_fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await strategy.execute(success_fn)
    assert result == "ok"
    assert call_count == 1
    assert strategy.stats.total_calls == 1
    assert strategy.stats.total_successes == 1
    assert strategy.stats.total_retries == 0
    print("OK: successful call no retry")


async def test_retry_then_succeed():
    """Fails twice then succeeds on third attempt."""
    strategy = RetryStrategy(max_retries=3, base_delay=0.01, max_delay=0.05)
    call_count = 0

    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RateLimitError("rate limited")
        return "recovered"

    result = await strategy.execute(flaky_fn)
    assert result == "recovered"
    assert call_count == 3
    assert strategy.stats.total_retries == 2
    assert strategy.stats.total_successes == 1
    assert strategy.stats.retries_by_error.get("RateLimitError") == 2
    print("OK: retry then succeed")


async def test_exhaust_retries():
    """All retries exhausted raises the original exception."""
    strategy = RetryStrategy(max_retries=2, base_delay=0.01, max_delay=0.02)

    async def always_fail():
        raise RateLimitError("always rate limited")

    try:
        await strategy.execute(always_fail)
        assert False, "Should have raised"
    except RateLimitError as e:
        assert "always rate limited" in str(e)

    assert strategy.stats.total_failures == 1
    assert strategy.stats.total_retries == 2
    print("OK: exhaust retries raises exception")


async def test_non_retryable_fails_immediately():
    """Non-retryable exception fails without any retry."""
    strategy = RetryStrategy(max_retries=5, base_delay=0.01)
    call_count = 0

    async def auth_fail():
        nonlocal call_count
        call_count += 1
        raise AuthenticationError("bad api key")

    try:
        await strategy.execute(auth_fail)
        assert False, "Should have raised"
    except AuthenticationError:
        pass

    assert call_count == 1  # No retries
    assert strategy.stats.total_retries == 0
    assert strategy.stats.total_failures == 1
    print("OK: non-retryable fails immediately")


async def test_exponential_backoff_delays():
    """Delays increase exponentially (without jitter for predictability)."""
    strategy = RetryStrategy(max_retries=5, base_delay=1.0, max_delay=60.0, jitter=False)

    delays = [strategy._calculate_delay(i) for i in range(5)]
    # Expected: 1, 2, 4, 8, 16
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]
    print("OK: exponential backoff delays")


async def test_max_delay_cap():
    """Delay is capped at max_delay."""
    strategy = RetryStrategy(max_retries=10, base_delay=1.0, max_delay=10.0, jitter=False)

    delay_at_10 = strategy._calculate_delay(10)  # 1.0 * 2^10 = 1024, capped at 10
    assert delay_at_10 == 10.0
    print("OK: max delay cap")


async def test_jitter_produces_variation():
    """With jitter enabled, delays vary between runs."""
    strategy = RetryStrategy(max_retries=5, base_delay=1.0, max_delay=60.0, jitter=True)

    # Generate many delays for same attempt to check jitter
    delays = [strategy._calculate_delay(2) for _ in range(20)]
    # All should be in [0, 4.0] since base * 2^2 = 4.0
    assert all(0 <= d <= 4.0 for d in delays)
    # With 20 samples, highly unlikely they're all identical
    assert len(set(round(d, 6) for d in delays)) > 1
    print("OK: jitter produces variation")


async def test_retry_budget_limits_retries():
    """RetryBudget prevents retries when budget exhausted."""
    budget = RetryBudget(max_retries_per_window=3, window_seconds=60.0)

    assert budget.can_retry() is True
    assert budget.remaining == 3

    budget.record_retry()
    budget.record_retry()
    budget.record_retry()

    assert budget.can_retry() is False
    assert budget.remaining == 0
    print("OK: retry budget limits retries")


async def test_retry_budget_sliding_window():
    """RetryBudget resets after window expires."""
    budget = RetryBudget(max_retries_per_window=2, window_seconds=0.2)

    budget.record_retry()
    budget.record_retry()
    assert budget.can_retry() is False

    # Wait for window to expire
    await asyncio.sleep(0.3)

    assert budget.can_retry() is True
    assert budget.remaining == 2
    print("OK: retry budget sliding window")


async def test_strategy_with_budget():
    """Strategy respects retry budget."""
    budget = RetryBudget(max_retries_per_window=1, window_seconds=60.0)
    strategy = RetryStrategy(max_retries=5, base_delay=0.01, retry_budget=budget)
    call_count = 0

    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise RateLimitError("rate limited")

    try:
        await strategy.execute(always_fail)
        assert False, "Should have raised"
    except RateLimitError:
        pass

    # Budget allows 1 retry, so 2 total calls (initial + 1 retry)
    assert call_count == 2
    assert strategy.stats.total_retries == 1
    print("OK: strategy with budget")


async def test_on_retry_callback():
    """on_retry callback fires for each retry."""
    callback_attempts = []

    def on_retry(attempt: RetryAttempt):
        callback_attempts.append({
            "num": attempt.attempt_number,
            "delay": attempt.delay,
            "error": type(attempt.error).__name__,
        })

    strategy = RetryStrategy(max_retries=3, base_delay=0.01, on_retry=on_retry)
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RateLimitError("limit")
        return "ok"

    await strategy.execute(flaky)

    assert len(callback_attempts) == 2
    assert callback_attempts[0]["num"] == 0
    assert callback_attempts[1]["num"] == 1
    assert callback_attempts[0]["error"] == "RateLimitError"
    print("OK: on_retry callback")


async def test_with_retry_decorator():
    """@strategy.with_retry decorator works."""
    strategy = RetryStrategy(max_retries=2, base_delay=0.01)
    call_count = 0

    @strategy.with_retry
    async def decorated_fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("once")
        return "decorated_result"

    result = await decorated_fn()
    assert result == "decorated_result"
    assert call_count == 2
    assert strategy.stats.total_retries == 1
    print("OK: with_retry decorator")


async def test_retry_stats_tracking():
    """RetryStats tracks all metrics correctly."""
    stats = RetryStats()
    assert stats.to_dict()["retry_rate"] == 0.0
    assert stats.to_dict()["success_rate"] == 0.0

    stats.total_calls = 10
    stats.total_retries = 3
    stats.total_successes = 8
    stats.total_failures = 2
    stats.retries_by_error = {"RateLimitError": 2, "TimeoutError": 1}

    d = stats.to_dict()
    assert d["retry_rate"] == 30.0
    assert d["success_rate"] == 80.0
    assert d["retries_by_error"]["RateLimitError"] == 2
    print("OK: retry stats tracking")


async def test_retry_decision_enum():
    """RetryDecision enum values."""
    assert RetryDecision.RETRY == "retry"
    assert RetryDecision.FAIL == "fail"
    assert RetryDecision.SKIP == "skip"
    print("OK: retry decision enum")


async def test_singleton_get_retry_strategy():
    """get_retry_strategy returns singleton."""
    # Reset globals for clean test
    import src.services.retry_strategy as mod
    mod._default_strategy = None
    mod._default_budget = None

    s1 = get_retry_strategy(max_retries=3)
    s2 = get_retry_strategy(max_retries=5)  # Should return same instance
    assert s1 is s2
    assert s1.max_retries == 3  # First call's params stick

    budget = get_retry_budget()
    assert budget is not None
    assert budget.max_retries == 100

    # Clean up
    mod._default_strategy = None
    mod._default_budget = None
    print("OK: singleton get_retry_strategy")


async def test_concurrent_retries():
    """Multiple concurrent tasks retry independently."""
    strategy = RetryStrategy(max_retries=2, base_delay=0.01, max_delay=0.02)
    results = []

    async def flaky_task(task_id):
        call_count = 0
        async def inner():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(f"task-{task_id}")
            return f"task-{task_id}-done"
        result = await strategy.execute(inner)
        results.append(result)

    await asyncio.gather(
        flaky_task(1),
        flaky_task(2),
        flaky_task(3),
    )

    assert len(results) == 3
    assert set(results) == {"task-1-done", "task-2-done", "task-3-done"}
    print("OK: concurrent retries")


async def test_mixed_exception_types():
    """Different exception types during retries are handled correctly."""
    strategy = RetryStrategy(max_retries=5, base_delay=0.01)
    call_count = 0

    async def mixed_errors():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("rate limit")
        if call_count == 2:
            raise ConnectionError("conn reset")
        if call_count == 3:
            raise TimeoutError("timed out")
        return "finally"

    result = await strategy.execute(mixed_errors)
    assert result == "finally"
    assert call_count == 4
    assert strategy.stats.total_retries == 3
    assert strategy.stats.retries_by_error.get("RateLimitError") == 1
    assert strategy.stats.retries_by_error.get("ConnectionError") == 1
    assert strategy.stats.retries_by_error.get("TimeoutError") == 1
    print("OK: mixed exception types")


async def test_retry_timing():
    """Actual delay roughly matches calculated delay."""
    strategy = RetryStrategy(max_retries=1, base_delay=0.1, jitter=False)
    call_count = 0

    async def fail_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("once")
        return "ok"

    start = time.time()
    await strategy.execute(fail_once)
    elapsed = time.time() - start

    # Should have waited ~0.1s for the retry
    assert 0.05 <= elapsed <= 0.5, f"Elapsed {elapsed} not in expected range"
    print("OK: retry timing")


async def main():
    print("=== Retry Strategy Tests ===\n")
    await test_is_retryable_classification()
    await test_is_retryable_status_code()
    await test_is_retryable_builtin_exceptions()
    await test_is_retryable_unknown_exception()
    await test_successful_call_no_retry()
    await test_retry_then_succeed()
    await test_exhaust_retries()
    await test_non_retryable_fails_immediately()
    await test_exponential_backoff_delays()
    await test_max_delay_cap()
    await test_jitter_produces_variation()
    await test_retry_budget_limits_retries()
    await test_retry_budget_sliding_window()
    await test_strategy_with_budget()
    await test_on_retry_callback()
    await test_with_retry_decorator()
    await test_retry_stats_tracking()
    await test_retry_decision_enum()
    await test_singleton_get_retry_strategy()
    await test_concurrent_retries()
    await test_mixed_exception_types()
    await test_retry_timing()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
