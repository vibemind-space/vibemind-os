"""
Pipeline Rate Controller — adaptive rate control for pipeline operations.

Features:
- Token bucket rate limiting per operation/agent
- Sliding window rate tracking
- Burst allowance with refill
- Rate limit groups (shared limits)
- Adaptive rate adjustment based on error rates
- Rate limit status and monitoring
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """A token bucket for rate limiting."""
    name: str
    capacity: float  # Max tokens
    tokens: float  # Current tokens
    refill_rate: float  # Tokens per second
    last_refill: float
    group: str
    total_allowed: int = 0
    total_denied: int = 0


@dataclass
class SlidingWindow:
    """Sliding window counter."""
    name: str
    window_seconds: float
    max_requests: int
    timestamps: deque = field(default_factory=deque)


# ---------------------------------------------------------------------------
# Pipeline Rate Controller
# ---------------------------------------------------------------------------

class PipelineRateController:
    """Adaptive rate control for pipeline operations."""

    def __init__(self, max_limiters: int = 5000):
        self._max_limiters = max_limiters
        self._buckets: Dict[str, TokenBucket] = {}
        self._windows: Dict[str, SlidingWindow] = {}
        self._groups: Dict[str, Set[str]] = {}  # group -> set of bucket names

        self._stats = {
            "total_allowed": 0,
            "total_denied": 0,
            "total_limiters": 0,
        }

    # ------------------------------------------------------------------
    # Token bucket
    # ------------------------------------------------------------------

    def create_bucket(
        self,
        name: str,
        capacity: float = 10.0,
        refill_rate: float = 1.0,
        group: str = "",
    ) -> bool:
        """Create a token bucket rate limiter."""
        if name in self._buckets:
            return False
        now = time.time()
        self._buckets[name] = TokenBucket(
            name=name,
            capacity=capacity,
            tokens=capacity,
            refill_rate=refill_rate,
            last_refill=now,
            group=group,
        )
        if group:
            if group not in self._groups:
                self._groups[group] = set()
            self._groups[group].add(name)
        self._stats["total_limiters"] += 1
        return True

    def remove_bucket(self, name: str) -> bool:
        """Remove a token bucket."""
        bucket = self._buckets.pop(name, None)
        if not bucket:
            return False
        if bucket.group and bucket.group in self._groups:
            self._groups[bucket.group].discard(name)
            if not self._groups[bucket.group]:
                del self._groups[bucket.group]
        return True

    def try_acquire(self, name: str, tokens: float = 1.0) -> Dict:
        """Try to acquire tokens. Returns result dict."""
        bucket = self._buckets.get(name)
        if not bucket:
            return {"allowed": False, "reason": "bucket_not_found"}

        self._refill(bucket)

        if bucket.tokens >= tokens:
            bucket.tokens -= tokens
            bucket.total_allowed += 1
            self._stats["total_allowed"] += 1
            return {
                "allowed": True,
                "remaining": round(bucket.tokens, 2),
                "capacity": bucket.capacity,
            }
        else:
            bucket.total_denied += 1
            self._stats["total_denied"] += 1
            wait = (tokens - bucket.tokens) / max(bucket.refill_rate, 0.001)
            return {
                "allowed": False,
                "reason": "rate_limited",
                "remaining": round(bucket.tokens, 2),
                "retry_after": round(wait, 2),
            }

    def get_bucket(self, name: str) -> Optional[Dict]:
        """Get bucket status."""
        bucket = self._buckets.get(name)
        if not bucket:
            return None
        self._refill(bucket)
        return {
            "name": bucket.name,
            "capacity": bucket.capacity,
            "tokens": round(bucket.tokens, 2),
            "refill_rate": bucket.refill_rate,
            "group": bucket.group,
            "total_allowed": bucket.total_allowed,
            "total_denied": bucket.total_denied,
            "utilization": round(
                (1 - bucket.tokens / max(bucket.capacity, 0.01)) * 100, 1
            ),
        }

    def _refill(self, bucket: TokenBucket) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(
                bucket.capacity,
                bucket.tokens + elapsed * bucket.refill_rate,
            )
            bucket.last_refill = now

    # ------------------------------------------------------------------
    # Sliding window
    # ------------------------------------------------------------------

    def create_window(
        self,
        name: str,
        window_seconds: float = 60.0,
        max_requests: int = 100,
    ) -> bool:
        """Create a sliding window rate limiter."""
        if name in self._windows:
            return False
        self._windows[name] = SlidingWindow(
            name=name,
            window_seconds=window_seconds,
            max_requests=max_requests,
        )
        self._stats["total_limiters"] += 1
        return True

    def remove_window(self, name: str) -> bool:
        """Remove a sliding window."""
        if name not in self._windows:
            return False
        del self._windows[name]
        return True

    def window_check(self, name: str) -> Dict:
        """Check and record a request against a sliding window."""
        w = self._windows.get(name)
        if not w:
            return {"allowed": False, "reason": "window_not_found"}

        now = time.time()
        cutoff = now - w.window_seconds

        # Remove old entries
        while w.timestamps and w.timestamps[0] < cutoff:
            w.timestamps.popleft()

        if len(w.timestamps) < w.max_requests:
            w.timestamps.append(now)
            self._stats["total_allowed"] += 1
            return {
                "allowed": True,
                "current": len(w.timestamps),
                "max": w.max_requests,
                "window": w.window_seconds,
            }
        else:
            self._stats["total_denied"] += 1
            oldest = w.timestamps[0] if w.timestamps else now
            retry_after = oldest + w.window_seconds - now
            return {
                "allowed": False,
                "reason": "rate_limited",
                "current": len(w.timestamps),
                "max": w.max_requests,
                "retry_after": round(max(retry_after, 0), 2),
            }

    def get_window(self, name: str) -> Optional[Dict]:
        """Get window status."""
        w = self._windows.get(name)
        if not w:
            return None
        now = time.time()
        cutoff = now - w.window_seconds
        while w.timestamps and w.timestamps[0] < cutoff:
            w.timestamps.popleft()
        return {
            "name": w.name,
            "window_seconds": w.window_seconds,
            "max_requests": w.max_requests,
            "current_requests": len(w.timestamps),
            "remaining": max(0, w.max_requests - len(w.timestamps)),
        }

    # ------------------------------------------------------------------
    # Rate adjustment
    # ------------------------------------------------------------------

    def adjust_rate(
        self,
        name: str,
        new_capacity: Optional[float] = None,
        new_refill_rate: Optional[float] = None,
    ) -> bool:
        """Dynamically adjust a bucket's rate."""
        bucket = self._buckets.get(name)
        if not bucket:
            return False
        if new_capacity is not None:
            bucket.capacity = new_capacity
            bucket.tokens = min(bucket.tokens, new_capacity)
        if new_refill_rate is not None:
            bucket.refill_rate = new_refill_rate
        return True

    def adjust_window(
        self,
        name: str,
        max_requests: Optional[int] = None,
    ) -> bool:
        """Dynamically adjust a window's limit."""
        w = self._windows.get(name)
        if not w:
            return False
        if max_requests is not None:
            w.max_requests = max_requests
        return True

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def get_group(self, group: str) -> List[Dict]:
        """Get all buckets in a group."""
        names = self._groups.get(group, set())
        return [self.get_bucket(n) for n in sorted(names) if n in self._buckets]

    def list_groups(self) -> Dict[str, int]:
        """List groups with member counts."""
        return {g: len(members) for g, members in sorted(self._groups.items())}

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_buckets(self, group: Optional[str] = None) -> List[Dict]:
        """List all token buckets."""
        results = []
        for b in self._buckets.values():
            if group and b.group != group:
                continue
            self._refill(b)
            results.append(self.get_bucket(b.name))
        return results

    def list_windows(self) -> List[Dict]:
        """List all sliding windows."""
        return [self.get_window(w.name) for w in self._windows.values()]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_buckets": len(self._buckets),
            "total_windows": len(self._windows),
            "total_groups": len(self._groups),
        }

    def reset(self) -> None:
        self._buckets.clear()
        self._windows.clear()
        self._groups.clear()
        self._stats = {k: 0 for k in self._stats}
