"""
Provider failover + circuit breaker for Brain LLM calls.

Ported from the genuinely-complete logic in ruvnet/agentic-flow
(src/core/provider-manager.ts). The companion router.ts there is mostly
`TODO: implement`; this module deliberately ports only the parts that are real:

  - is_retryable(exc)         — transient (429/5xx/timeout/connection) vs fatal.
  - backoff_delay(retry, ...) — exponential (cap 30s) / linear (cap 10s).
  - CircuitBreaker            — opens after N consecutive failures per provider,
                                half-opens after recovery_s.
  - ProviderFailover          — walks a model chain, retries retryable errors on
                                the same model with backoff, skips open breakers,
                                advances to the next model, raises the last error.

Design notes
------------
* Zero hard dependencies (no httpx/openai import) so it unit-tests in isolation
  without API keys or a live Brain. Error classification is structural: it reads
  ``exc.response.status_code`` if present and falls back to message regex — this
  matches both httpx.HTTPStatusError and requests.HTTPError shapes used in
  multi_llm_router.py.
* Time is injectable (``clock=`` / ``sleep=``) so tests never actually sleep.
* This wraps the EXISTING per-provider semaphores in multi_llm_router.py rather
  than replacing them: the failover sits OUTSIDE the call, the semaphore stays
  INSIDE _acall_openrouter(). Concurrency limiting and failover are orthogonal.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional

# Status codes worth retrying. 429 = rate limit (the Groq chokepoint), 5xx =
# upstream/provider transient failures.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Message patterns for errors that don't carry a clean status code.
_RETRYABLE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (r"rate.?limit", r"timeout", r"timed out", r"connection",
              r"network", r"\b429\b", r"\b50[234]\b", r"temporarily")
]


def is_retryable(exc: BaseException) -> bool:
    """True if the error is transient and worth retrying / failing over.

    Reads a status code from ``exc.response.status_code`` when present
    (httpx.HTTPStatusError / requests.HTTPError), else matches the message.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS
    msg = str(exc)
    return any(p.search(msg) for p in _RETRYABLE_PATTERNS)


def backoff_delay(retry: int, mode: str = "exponential") -> float:
    """Seconds to wait before attempt ``retry`` (0 = first attempt, no wait).

    exponential: 0, 1, 2, 4, 8, ... capped at 30s.
    linear:      0, 1, 2, 3, ...    capped at 10s.
    """
    if retry <= 0:
        return 0.0
    if mode == "linear":
        return float(min(retry, 10))
    return float(min(2 ** (retry - 1), 30))


class CircuitBreaker:
    """Per-provider circuit breaker.

    Opens after ``max_failures`` consecutive failures; ``is_open`` returns True
    until ``recovery_s`` has elapsed, then half-opens (allows one trial). A
    success resets the failure count and closes the breaker.
    """

    def __init__(
        self,
        max_failures: int = 3,
        recovery_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_failures = max_failures
        self.recovery_s = recovery_s
        self._clock = clock
        self._consecutive: Dict[str, int] = {}
        self._open_since: Dict[str, float] = {}

    def is_open(self, provider: str) -> bool:
        opened = self._open_since.get(provider)
        if opened is None:
            return False
        if self._clock() - opened >= self.recovery_s:
            # Half-open: stop reporting open so the caller may try once more.
            self._open_since.pop(provider, None)
            return False
        return True

    def record_failure(self, provider: str) -> None:
        n = self._consecutive.get(provider, 0) + 1
        self._consecutive[provider] = n
        if n >= self.max_failures and provider not in self._open_since:
            self._open_since[provider] = self._clock()

    def record_success(self, provider: str) -> None:
        self._consecutive[provider] = 0
        self._open_since.pop(provider, None)


class ProviderFailover:
    """Walk a model chain with retries, backoff, and circuit breaking."""

    def __init__(
        self,
        max_retries: int = 2,
        backoff_mode: str = "exponential",
        breaker: Optional[CircuitBreaker] = None,
        provider_of: Optional[Callable[[str], str]] = None,
        sleep: Optional[Callable[[float], Awaitable[None]]] = None,
    ):
        self.max_retries = max_retries
        self.backoff_mode = backoff_mode
        self.breaker = breaker
        # Maps a model string to a provider bucket for breaker keying. Defaults
        # to identity (each model is its own bucket).
        self.provider_of = provider_of or (lambda m: m)
        # Default sleep resolves asyncio.sleep at call time (not bound here), so
        # tests can monkeypatch asyncio.sleep and the backoff loop honours it.
        self._sleep = sleep

    async def call_with_failover(
        self,
        models: List[str],
        fn: Callable[[str], Awaitable[str]],
    ):
        """Try each model in ``models`` until one succeeds.

        For each model: up to (1 + max_retries) attempts, but only retryable
        errors trigger a retry/advance. A non-retryable error stops retrying the
        current model and advances to the next (a different provider key may
        still work). Open breakers are skipped. Raises the last error if all
        models are exhausted.
        """
        last_error: Optional[BaseException] = None
        attempted_any = False

        for model in models:
            provider = self.provider_of(model)
            if self.breaker is not None and self.breaker.is_open(provider):
                continue

            for attempt in range(self.max_retries + 1):
                delay = backoff_delay(attempt, self.backoff_mode)
                if delay > 0:
                    sleeper = self._sleep if self._sleep is not None else asyncio.sleep
                    await sleeper(delay)
                attempted_any = True
                try:
                    result = await fn(model)
                    if self.breaker is not None:
                        self.breaker.record_success(provider)
                    return result
                except BaseException as exc:  # noqa: BLE001 — classify, re-raise below
                    last_error = exc
                    if self.breaker is not None:
                        self.breaker.record_failure(provider)
                    if not is_retryable(exc):
                        break  # don't retry this model; advance to next
                    # retryable: loop to retry same model (until retries exhausted)

        if last_error is not None:
            raise last_error
        if not attempted_any:
            raise RuntimeError(
                "ProviderFailover: every provider in the chain has an open "
                "circuit breaker; no model was attempted"
            )
        # Unreachable: attempted_any with no error means we returned already.
        raise RuntimeError("ProviderFailover: no models provided")


# ─── Chain config (env-driven, ready for the multi_llm_router wiring) ────────

def default_chain(primary: str) -> List[str]:
    """Build the model chain: primary first, then BRAIN_LLM_FALLBACK_CHAIN.

    BRAIN_LLM_FALLBACK_CHAIN is a comma-separated list of model strings using
    the same syntax _acall_openrouter understands (e.g. 'groq::llama-3.3-70b',
    'openai/gpt-4o-mini'). Duplicates of the primary are dropped, order kept.
    """
    chain = [primary]
    raw = os.environ.get("BRAIN_LLM_FALLBACK_CHAIN", "").strip()
    if raw:
        for m in (x.strip() for x in raw.split(",")):
            if m and m not in chain:
                chain.append(m)
    return chain


def breaker_from_env() -> CircuitBreaker:
    """CircuitBreaker configured from env (BRAIN_CB_*), defaults match TS port."""
    return CircuitBreaker(
        max_failures=int(os.environ.get("BRAIN_CB_MAX_FAILURES", "3")),
        recovery_s=float(os.environ.get("BRAIN_CB_RECOVERY_S", "60")),
    )
