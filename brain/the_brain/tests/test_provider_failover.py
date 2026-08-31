"""
Unit tests for core.provider_failover.

Ported behaviour from ruvnet/agentic-flow's provider-manager.ts:
  - is_retryable: 429/502/503/timeout/connection → retryable; 400/401/403 → not.
  - backoff_delay: exponential (1,2,4,8...) capped at 30s; linear capped at 10s.
  - CircuitBreaker: opens after N consecutive failures, recovers after recovery_s.
  - call_with_failover: walks a model chain, retries retryable errors with
    backoff, skips open breakers, raises the last error when all fail.

These tests are fully self-contained — no httpx, no API keys, no live Brain.
Time is injected (clock=) so the recovery test never sleeps.
"""

import asyncio

import pytest

from core.provider_failover import (
    CircuitBreaker,
    ProviderFailover,
    backoff_delay,
    is_retryable,
)


# ─── is_retryable ──────────────────────────────────────────────────────────

class _FakeHTTPStatusError(Exception):
    """Mimics httpx.HTTPStatusError shape: .response.status_code + message."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message or f"HTTP {status_code}")

        class _Resp:
            pass

        self.response = _Resp()
        self.response.status_code = status_code


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_is_retryable_true_for_transient_status(code):
    assert is_retryable(_FakeHTTPStatusError(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_is_retryable_false_for_client_errors(code):
    assert is_retryable(_FakeHTTPStatusError(code)) is False


@pytest.mark.parametrize(
    "msg",
    ["rate limit exceeded", "Connection timeout", "network unreachable", "429 Too Many"],
)
def test_is_retryable_true_for_transient_messages(msg):
    assert is_retryable(RuntimeError(msg)) is True


def test_is_retryable_false_for_plain_error():
    assert is_retryable(ValueError("bad model name")) is False


# ─── backoff_delay ─────────────────────────────────────────────────────────

def test_backoff_exponential_progression():
    assert backoff_delay(0, mode="exponential") == 0.0  # no wait before first try
    assert backoff_delay(1, mode="exponential") == 1.0
    assert backoff_delay(2, mode="exponential") == 2.0
    assert backoff_delay(3, mode="exponential") == 4.0


def test_backoff_exponential_capped_at_30s():
    assert backoff_delay(20, mode="exponential") == 30.0


def test_backoff_linear_capped_at_10s():
    assert backoff_delay(1, mode="linear") == 1.0
    assert backoff_delay(5, mode="linear") == 5.0
    assert backoff_delay(50, mode="linear") == 10.0


# ─── CircuitBreaker ────────────────────────────────────────────────────────

def test_breaker_opens_after_threshold():
    clock = {"t": 0.0}
    cb = CircuitBreaker(max_failures=3, recovery_s=60, clock=lambda: clock["t"])
    assert cb.is_open("groq") is False
    for _ in range(3):
        cb.record_failure("groq")
    assert cb.is_open("groq") is True


def test_breaker_recovers_after_recovery_window():
    clock = {"t": 0.0}
    cb = CircuitBreaker(max_failures=2, recovery_s=60, clock=lambda: clock["t"])
    cb.record_failure("groq")
    cb.record_failure("groq")
    assert cb.is_open("groq") is True
    clock["t"] = 61.0  # advance past recovery window
    assert cb.is_open("groq") is False  # half-open: allowed to try again


def test_breaker_success_resets_failures():
    clock = {"t": 0.0}
    cb = CircuitBreaker(max_failures=3, recovery_s=60, clock=lambda: clock["t"])
    cb.record_failure("groq")
    cb.record_failure("groq")
    cb.record_success("groq")
    cb.record_failure("groq")
    assert cb.is_open("groq") is False  # only 1 consecutive failure now


# ─── call_with_failover ────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_failover_returns_first_success():
    fo = ProviderFailover(max_retries=0, sleep=_no_sleep)
    calls = []

    async def fn(model):
        calls.append(model)
        return f"ok:{model}"

    result = _run(fo.call_with_failover(["a", "b"], fn))
    assert result == "ok:a"
    assert calls == ["a"]  # b never tried


def test_failover_moves_to_next_model_on_retryable():
    fo = ProviderFailover(max_retries=0, sleep=_no_sleep)
    calls = []

    async def fn(model):
        calls.append(model)
        if model == "a":
            raise _FakeHTTPStatusError(429)
        return f"ok:{model}"

    result = _run(fo.call_with_failover(["a", "b"], fn))
    assert result == "ok:b"
    assert calls == ["a", "b"]


def test_failover_does_not_retry_non_retryable():
    fo = ProviderFailover(max_retries=3, sleep=_no_sleep)
    calls = []

    async def fn(model):
        calls.append(model)
        raise _FakeHTTPStatusError(401)  # auth error — not retryable

    with pytest.raises(_FakeHTTPStatusError):
        _run(fo.call_with_failover(["a", "b"], fn))
    # Non-retryable: still advances to next model (different key may work),
    # but never retries the SAME model. One call each.
    assert calls == ["a", "b"]


def test_failover_retries_same_model_then_advances():
    fo = ProviderFailover(max_retries=2, sleep=_no_sleep)
    calls = []

    async def fn(model):
        calls.append(model)
        raise _FakeHTTPStatusError(429)

    with pytest.raises(_FakeHTTPStatusError):
        _run(fo.call_with_failover(["a", "b"], fn))
    # 2 models × (1 try + 2 retries) = 6 calls
    assert calls == ["a", "a", "a", "b", "b", "b"]


def test_failover_skips_open_breaker():
    clock = {"t": 0.0}
    cb = CircuitBreaker(max_failures=1, recovery_s=60, clock=lambda: clock["t"])
    cb.record_failure("a")  # 'a' provider already open
    fo = ProviderFailover(max_retries=0, sleep=_no_sleep, breaker=cb,
                          provider_of=lambda m: m)
    calls = []

    async def fn(model):
        calls.append(model)
        return f"ok:{model}"

    result = _run(fo.call_with_failover(["a", "b"], fn))
    assert result == "ok:b"
    assert calls == ["b"]  # 'a' skipped because breaker open


def test_failover_all_fail_raises_last():
    fo = ProviderFailover(max_retries=0, sleep=_no_sleep)

    async def fn(model):
        raise _FakeHTTPStatusError(503, f"down:{model}")

    with pytest.raises(_FakeHTTPStatusError) as ei:
        _run(fo.call_with_failover(["a", "b"], fn))
    assert "down:b" in str(ei.value)  # last error propagates


async def _no_sleep(_seconds):
    return None
