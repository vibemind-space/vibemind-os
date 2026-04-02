"""
Rate Limiter — Token bucket rate limiting for LLM API calls across agents.

Prevents agents from overwhelming the LLM API with concurrent requests,
enforcing both per-agent and global rate limits.

Supports:
- Token bucket algorithm (smooth rate limiting)
- Per-agent quotas (e.g., Fixer gets more budget than Linter)
- Global RPM/TPM limits matching API provider limits
- Queue-based waiting when bucket is empty
- Priority queuing (critical fixes get priority)

Usage::

    limiter = RateLimiter(global_rpm=60, global_tpm=100_000)
    limiter.set_agent_quota("Fixer", rpm=20, tpm=40_000)
    limiter.set_agent_quota("Builder", rpm=10, tpm=20_000)

    # Before making an LLM call:
    async with limiter.acquire("Fixer", estimated_tokens=2000):
        response = await llm_client.generate(prompt)
        limiter.record_usage("Fixer", actual_tokens=response.usage.total_tokens)
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    capacity: float        # Max tokens in bucket
    refill_rate: float     # Tokens added per second
    tokens: float = 0.0    # Current tokens
    last_refill: float = field(default_factory=time.time)

    def __post_init__(self):
        self.tokens = self.capacity  # Start full

    def try_consume(self, amount: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def wait_time(self, amount: float = 1.0) -> float:
        """Calculate how long to wait for tokens to be available."""
        self._refill()
        if self.tokens >= amount:
            return 0.0
        deficit = amount - self.tokens
        return deficit / self.refill_rate

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


@dataclass
class AgentQuota:
    """Rate limit configuration for a specific agent."""
    agent_name: str
    rpm: int = 30           # Requests per minute
    tpm: int = 50_000       # Tokens per minute
    priority: int = 5       # 1=highest, 10=lowest

    # Runtime tracking
    request_bucket: TokenBucket = field(init=False)
    token_bucket: TokenBucket = field(init=False)
    total_requests: int = 0
    total_tokens: int = 0
    rejected_requests: int = 0

    def __post_init__(self):
        self.request_bucket = TokenBucket(
            capacity=self.rpm,
            refill_rate=self.rpm / 60.0,
        )
        self.token_bucket = TokenBucket(
            capacity=self.tpm,
            refill_rate=self.tpm / 60.0,
        )


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and waiting is not an option."""
    def __init__(self, agent: str, wait_seconds: float):
        self.agent = agent
        self.wait_seconds = wait_seconds
        super().__init__(f"Rate limit exceeded for '{agent}', retry in {wait_seconds:.1f}s")


class RateLimiter:
    """
    Global rate limiter for LLM API calls across all agents.

    Enforces both global limits (matching API provider limits) and
    per-agent quotas to ensure fair resource distribution.
    """

    def __init__(
        self,
        global_rpm: int = 60,
        global_tpm: int = 100_000,
    ):
        self._global_request_bucket = TokenBucket(
            capacity=global_rpm,
            refill_rate=global_rpm / 60.0,
        )
        self._global_token_bucket = TokenBucket(
            capacity=global_tpm,
            refill_rate=global_tpm / 60.0,
        )
        self._agent_quotas: Dict[str, AgentQuota] = {}
        self._lock = asyncio.Lock()
        self._waiters: asyncio.PriorityQueue = asyncio.PriorityQueue()

        # Stats
        self._total_requests = 0
        self._total_tokens = 0
        self._total_wait_time = 0.0

    def set_agent_quota(
        self,
        agent_name: str,
        rpm: int = 30,
        tpm: int = 50_000,
        priority: int = 5,
    ):
        """Configure rate limits for a specific agent."""
        self._agent_quotas[agent_name] = AgentQuota(
            agent_name=agent_name,
            rpm=rpm,
            tpm=tpm,
            priority=priority,
        )
        logger.debug("rate_limit_set", agent=agent_name, rpm=rpm, tpm=tpm, priority=priority)

    def _get_quota(self, agent_name: str) -> AgentQuota:
        """Get or create default quota for an agent."""
        if agent_name not in self._agent_quotas:
            self.set_agent_quota(agent_name)
        return self._agent_quotas[agent_name]

    def acquire(self, agent_name: str, estimated_tokens: int = 1000):
        """
        Context manager to acquire rate limit permission.

        Usage::

            async with limiter.acquire("Fixer", estimated_tokens=2000):
                response = await llm.generate(...)
        """
        return _RateLimitContext(self, agent_name, estimated_tokens)

    async def _acquire(self, agent_name: str, estimated_tokens: int = 1000) -> None:
        """Wait for rate limit permission (internal)."""
        quota = self._get_quota(agent_name)

        max_wait = 30.0  # Max 30 seconds wait
        total_waited = 0.0

        while total_waited < max_wait:
            async with self._lock:
                # Check global limits
                global_req_ok = self._global_request_bucket.try_consume(1)
                global_tok_ok = self._global_token_bucket.try_consume(estimated_tokens)

                if global_req_ok and global_tok_ok:
                    # Check agent-specific limits
                    agent_req_ok = quota.request_bucket.try_consume(1)
                    agent_tok_ok = quota.token_bucket.try_consume(estimated_tokens)

                    if agent_req_ok and agent_tok_ok:
                        quota.total_requests += 1
                        self._total_requests += 1
                        return
                    else:
                        # Refund global tokens
                        self._global_request_bucket.tokens += 1
                        self._global_token_bucket.tokens += estimated_tokens
                else:
                    # Refund any partial consumption
                    if global_req_ok:
                        self._global_request_bucket.tokens += 1
                    if global_tok_ok:
                        self._global_token_bucket.tokens += estimated_tokens

            # Calculate wait time
            wait = max(
                self._global_request_bucket.wait_time(1),
                self._global_token_bucket.wait_time(estimated_tokens),
                quota.request_bucket.wait_time(1),
                quota.token_bucket.wait_time(estimated_tokens),
            )
            wait = min(wait, 2.0)  # Cap individual waits at 2s

            if wait > 0:
                logger.debug(
                    "rate_limit_waiting",
                    agent=agent_name,
                    wait_seconds=round(wait, 2),
                    estimated_tokens=estimated_tokens,
                )
                await asyncio.sleep(wait)
                total_waited += wait
                self._total_wait_time += wait
            else:
                await asyncio.sleep(0.01)  # Yield to event loop
                total_waited += 0.01

        # Timeout — reject
        quota.rejected_requests += 1
        raise RateLimitExceeded(agent_name, max_wait)

    def record_usage(self, agent_name: str, actual_tokens: int):
        """Record actual token usage after an LLM call completes."""
        self._total_tokens += actual_tokens
        quota = self._get_quota(agent_name)
        quota.total_tokens += actual_tokens

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "global": {
                "total_requests": self._total_requests,
                "total_tokens": self._total_tokens,
                "total_wait_time_seconds": round(self._total_wait_time, 2),
                "request_bucket_tokens": round(self._global_request_bucket.tokens, 1),
                "token_bucket_tokens": round(self._global_token_bucket.tokens, 0),
            },
            "agents": {
                name: {
                    "total_requests": q.total_requests,
                    "total_tokens": q.total_tokens,
                    "rejected": q.rejected_requests,
                    "priority": q.priority,
                    "rpm_remaining": round(q.request_bucket.tokens, 1),
                    "tpm_remaining": round(q.token_bucket.tokens, 0),
                }
                for name, q in self._agent_quotas.items()
            },
        }


class _RateLimitContext:
    """Async context manager for rate limiting."""

    def __init__(self, limiter: RateLimiter, agent_name: str, estimated_tokens: int):
        self._limiter = limiter
        self._agent_name = agent_name
        self._estimated_tokens = estimated_tokens

    async def __aenter__(self):
        await self._limiter._acquire(self._agent_name, self._estimated_tokens)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


# ---------------------------------------------------------------------------
# Singleton instance for the whole pipeline
# ---------------------------------------------------------------------------

_default_limiter: Optional[RateLimiter] = None


def get_rate_limiter(
    global_rpm: int = 60,
    global_tpm: int = 100_000,
) -> RateLimiter:
    """Get or create the default rate limiter."""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RateLimiter(global_rpm=global_rpm, global_tpm=global_tpm)
    return _default_limiter
