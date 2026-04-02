"""Pipeline Rate Limiter – per-pipeline rate limiting with multiple strategies.

Supports token bucket, sliding window, and fixed window strategies for
controlling throughput across pipeline operations. Tracks usage statistics,
detects overloaded limiters, and supports dynamic reconfiguration.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _TokenBucketState:
    available_tokens: float
    last_refill_time: float


@dataclass
class _SlidingWindowState:
    timestamps: deque = field(default_factory=deque)


@dataclass
class _FixedWindowState:
    window_start: float = 0.0
    count: int = 0


@dataclass
class _Limiter:
    limiter_id: str
    name: str
    strategy: str
    max_rate: float
    window_seconds: float
    burst: float
    tags: List[str]
    created_at: float
    total_requests: int = 0
    allowed_count: int = 0
    denied_count: int = 0
    token_bucket: Optional[_TokenBucketState] = None
    sliding_window: Optional[_SlidingWindowState] = None
    fixed_window: Optional[_FixedWindowState] = None


# ---------------------------------------------------------------------------
# Pipeline Rate Limiter
# ---------------------------------------------------------------------------

class PipelineRateLimiter:
    """Per-pipeline rate limiting with multiple strategies."""

    def __init__(self, max_entries: int = 10000, max_history: int = 50000):
        self._limiters: Dict[str, _Limiter] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0
        self._total_created = 0
        self._total_removed = 0
        self._total_acquires = 0
        self._total_allowed = 0
        self._total_denied = 0

    # ── ID Generation ───────────────────────────────────────────────

    def _next_id(self, name: str) -> str:
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        return "prl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ── Limiter Creation ────────────────────────────────────────────

    def create_limiter(
        self,
        name: str,
        strategy: str = "token_bucket",
        max_rate: float = 100.0,
        window_seconds: float = 60.0,
        burst: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a rate limiter. Returns limiter ID or empty string on failure."""
        if not name or name in self._name_index:
            return ""
        if strategy not in ("token_bucket", "sliding_window", "fixed_window"):
            return ""
        if len(self._limiters) >= self._max_entries:
            self._prune_entries()
            if len(self._limiters) >= self._max_entries:
                return ""

        lid = self._next_id(name)
        effective_burst = burst if burst is not None else max_rate
        now = time.time()

        limiter = _Limiter(
            limiter_id=lid,
            name=name,
            strategy=strategy,
            max_rate=max_rate,
            window_seconds=window_seconds,
            burst=effective_burst,
            tags=tags or [],
            created_at=now,
        )

        if strategy == "token_bucket":
            limiter.token_bucket = _TokenBucketState(
                available_tokens=effective_burst,
                last_refill_time=now,
            )
        elif strategy == "sliding_window":
            limiter.sliding_window = _SlidingWindowState()
        elif strategy == "fixed_window":
            limiter.fixed_window = _FixedWindowState(window_start=now, count=0)

        self._limiters[lid] = limiter
        self._name_index[name] = lid
        self._total_created += 1
        self._record_history("limiter_created", {"name": name, "limiter_id": lid, "strategy": strategy})
        self._fire("limiter_created", {"name": name, "limiter_id": lid, "strategy": strategy})
        return lid

    # ── Acquire ─────────────────────────────────────────────────────

    def acquire(self, name: str, tokens: int = 1) -> Dict[str, Any]:
        """Try to acquire tokens from a limiter.

        Returns dict with allowed, remaining, retry_after.
        """
        lid = self._name_index.get(name)
        if not lid:
            return {"allowed": False, "remaining": 0.0, "retry_after": 0.0}
        limiter = self._limiters.get(lid)
        if not limiter:
            return {"allowed": False, "remaining": 0.0, "retry_after": 0.0}

        self._total_acquires += 1
        limiter.total_requests += 1

        if limiter.strategy == "token_bucket":
            result = self._acquire_token_bucket(limiter, tokens)
        elif limiter.strategy == "sliding_window":
            result = self._acquire_sliding_window(limiter, tokens)
        else:
            result = self._acquire_fixed_window(limiter, tokens)

        if result["allowed"]:
            limiter.allowed_count += 1
            self._total_allowed += 1
        else:
            limiter.denied_count += 1
            self._total_denied += 1

        return result

    def _acquire_token_bucket(self, limiter: _Limiter, tokens: int) -> Dict[str, Any]:
        tb = limiter.token_bucket
        now = time.time()
        elapsed = now - tb.last_refill_time
        refill_rate = limiter.max_rate / max(limiter.window_seconds, 0.001)
        tb.available_tokens = min(
            limiter.burst,
            tb.available_tokens + elapsed * refill_rate,
        )
        tb.last_refill_time = now

        if tb.available_tokens >= tokens:
            tb.available_tokens -= tokens
            return {
                "allowed": True,
                "remaining": round(tb.available_tokens, 4),
                "retry_after": 0.0,
            }
        else:
            deficit = tokens - tb.available_tokens
            retry_after = deficit / max(refill_rate, 0.0001)
            return {
                "allowed": False,
                "remaining": round(tb.available_tokens, 4),
                "retry_after": round(retry_after, 4),
            }

    def _acquire_sliding_window(self, limiter: _Limiter, tokens: int) -> Dict[str, Any]:
        sw = limiter.sliding_window
        now = time.time()
        cutoff = now - limiter.window_seconds

        while sw.timestamps and sw.timestamps[0] < cutoff:
            sw.timestamps.popleft()

        current_count = len(sw.timestamps)
        if current_count + tokens <= limiter.max_rate:
            for _ in range(tokens):
                sw.timestamps.append(now)
            return {
                "allowed": True,
                "remaining": round(limiter.max_rate - len(sw.timestamps), 4),
                "retry_after": 0.0,
            }
        else:
            if sw.timestamps:
                oldest = sw.timestamps[0]
                retry_after = oldest + limiter.window_seconds - now
            else:
                retry_after = limiter.window_seconds
            return {
                "allowed": False,
                "remaining": round(max(0.0, limiter.max_rate - current_count), 4),
                "retry_after": round(max(retry_after, 0.0), 4),
            }

    def _acquire_fixed_window(self, limiter: _Limiter, tokens: int) -> Dict[str, Any]:
        fw = limiter.fixed_window
        now = time.time()

        # Reset window if boundary crossed
        if now - fw.window_start >= limiter.window_seconds:
            fw.window_start = now
            fw.count = 0

        if fw.count + tokens <= limiter.max_rate:
            fw.count += tokens
            return {
                "allowed": True,
                "remaining": round(limiter.max_rate - fw.count, 4),
                "retry_after": 0.0,
            }
        else:
            retry_after = fw.window_start + limiter.window_seconds - now
            return {
                "allowed": False,
                "remaining": round(max(0.0, limiter.max_rate - fw.count), 4),
                "retry_after": round(max(retry_after, 0.0), 4),
            }

    # ── Get / Update / Reset Limiter ────────────────────────────────

    def get_limiter(self, name: str) -> Optional[Dict[str, Any]]:
        """Get limiter state as a dict."""
        lid = self._name_index.get(name)
        if not lid:
            return None
        limiter = self._limiters.get(lid)
        if not limiter:
            return None
        return self._limiter_to_dict(limiter)

    def update_limiter(
        self,
        name: str,
        max_rate: Optional[float] = None,
        window_seconds: Optional[float] = None,
        burst: Optional[float] = None,
    ) -> bool:
        """Update limiter configuration. Returns True on success."""
        lid = self._name_index.get(name)
        if not lid:
            return False
        limiter = self._limiters.get(lid)
        if not limiter:
            return False

        if max_rate is not None:
            limiter.max_rate = max_rate
        if window_seconds is not None:
            limiter.window_seconds = window_seconds
        if burst is not None:
            limiter.burst = burst
            if limiter.token_bucket and limiter.token_bucket.available_tokens > burst:
                limiter.token_bucket.available_tokens = burst

        self._record_history("limiter_updated", {"name": name, "limiter_id": lid})
        self._fire("limiter_updated", {"name": name, "limiter_id": lid})
        return True

    def reset_limiter(self, name: str) -> bool:
        """Reset a limiter's state without removing it."""
        lid = self._name_index.get(name)
        if not lid:
            return False
        limiter = self._limiters.get(lid)
        if not limiter:
            return False

        now = time.time()
        if limiter.token_bucket:
            limiter.token_bucket.available_tokens = limiter.burst
            limiter.token_bucket.last_refill_time = now
        if limiter.sliding_window:
            limiter.sliding_window.timestamps.clear()
        if limiter.fixed_window:
            limiter.fixed_window.window_start = now
            limiter.fixed_window.count = 0

        self._record_history("limiter_reset", {"name": name, "limiter_id": lid})
        self._fire("limiter_reset", {"name": name, "limiter_id": lid})
        return True

    # ── Usage ───────────────────────────────────────────────────────

    def get_usage(self, name: str) -> Dict[str, Any]:
        """Get usage statistics for a limiter."""
        lid = self._name_index.get(name)
        if not lid:
            return {"total_requests": 0, "allowed_count": 0, "denied_count": 0, "current_rate": 0.0}
        limiter = self._limiters.get(lid)
        if not limiter:
            return {"total_requests": 0, "allowed_count": 0, "denied_count": 0, "current_rate": 0.0}

        current_rate = 0.0
        if limiter.strategy == "token_bucket" and limiter.token_bucket:
            used = limiter.burst - limiter.token_bucket.available_tokens
            current_rate = round(used / max(limiter.burst, 0.001) * limiter.max_rate, 4)
        elif limiter.strategy == "sliding_window" and limiter.sliding_window:
            now = time.time()
            cutoff = now - limiter.window_seconds
            while limiter.sliding_window.timestamps and limiter.sliding_window.timestamps[0] < cutoff:
                limiter.sliding_window.timestamps.popleft()
            current_rate = float(len(limiter.sliding_window.timestamps))
        elif limiter.strategy == "fixed_window" and limiter.fixed_window:
            now = time.time()
            if now - limiter.fixed_window.window_start >= limiter.window_seconds:
                current_rate = 0.0
            else:
                current_rate = float(limiter.fixed_window.count)

        return {
            "total_requests": limiter.total_requests,
            "allowed_count": limiter.allowed_count,
            "denied_count": limiter.denied_count,
            "current_rate": current_rate,
        }

    # ── List / Remove ───────────────────────────────────────────────

    def list_limiters(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all limiters, optionally filtered by tag."""
        results = []
        for limiter in self._limiters.values():
            if tag and tag not in limiter.tags:
                continue
            results.append(self._limiter_to_dict(limiter))
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

    def remove_limiter(self, name: str) -> bool:
        """Remove a limiter by name."""
        lid = self._name_index.pop(name, None)
        if not lid:
            return False
        limiter = self._limiters.pop(lid, None)
        if not limiter:
            return False
        self._total_removed += 1
        self._record_history("limiter_removed", {"name": name, "limiter_id": lid})
        self._fire("limiter_removed", {"name": name, "limiter_id": lid})
        return True

    # ── Overloaded Detection ────────────────────────────────────────

    def get_overloaded(self, threshold: float = 0.9) -> List[Dict[str, Any]]:
        """Find limiters above the given usage threshold (0.0 to 1.0)."""
        overloaded = []
        for limiter in self._limiters.values():
            utilization = self._get_utilization(limiter)
            if utilization >= threshold:
                info = self._limiter_to_dict(limiter)
                info["utilization"] = round(utilization, 4)
                overloaded.append(info)
        overloaded.sort(key=lambda x: x["utilization"], reverse=True)
        return overloaded

    def _get_utilization(self, limiter: _Limiter) -> float:
        """Calculate utilization ratio (0.0 to 1.0) for a limiter."""
        if limiter.strategy == "token_bucket" and limiter.token_bucket:
            if limiter.burst <= 0:
                return 0.0
            return 1.0 - (limiter.token_bucket.available_tokens / limiter.burst)
        elif limiter.strategy == "sliding_window" and limiter.sliding_window:
            now = time.time()
            cutoff = now - limiter.window_seconds
            while limiter.sliding_window.timestamps and limiter.sliding_window.timestamps[0] < cutoff:
                limiter.sliding_window.timestamps.popleft()
            if limiter.max_rate <= 0:
                return 0.0
            return len(limiter.sliding_window.timestamps) / limiter.max_rate
        elif limiter.strategy == "fixed_window" and limiter.fixed_window:
            now = time.time()
            if now - limiter.fixed_window.window_start >= limiter.window_seconds:
                return 0.0
            if limiter.max_rate <= 0:
                return 0.0
            return limiter.fixed_window.count / limiter.max_rate
        return 0.0

    # ── History ─────────────────────────────────────────────────────

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{action}-{now}-{self._seq}"
        hid = "prl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        entry = {
            "history_id": hid,
            "action": action,
            "detail": detail,
            "timestamp": now,
        }
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(entry)

    def get_history(self, action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """Get history entries, newest first."""
        results = []
        for entry in reversed(self._history):
            if action and entry["action"] != action:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    # ── Callbacks ───────────────────────────────────────────────────

    def on_change(self, name: str, fn: Callable) -> bool:
        """Register a callback. Returns False if name already registered."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = fn
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ── Stats / Reset ───────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate counters."""
        strategies: Dict[str, int] = {}
        for limiter in self._limiters.values():
            strategies[limiter.strategy] = strategies.get(limiter.strategy, 0) + 1
        return {
            "current_limiters": len(self._limiters),
            "total_created": self._total_created,
            "total_removed": self._total_removed,
            "total_acquires": self._total_acquires,
            "total_allowed": self._total_allowed,
            "total_denied": self._total_denied,
            "strategies": strategies,
            "history_size": len(self._history),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._limiters.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_removed = 0
        self._total_acquires = 0
        self._total_allowed = 0
        self._total_denied = 0

    # ── Internal Helpers ────────────────────────────────────────────

    def _limiter_to_dict(self, limiter: _Limiter) -> Dict[str, Any]:
        """Convert a limiter to its dict representation."""
        result = {
            "limiter_id": limiter.limiter_id,
            "name": limiter.name,
            "strategy": limiter.strategy,
            "max_rate": limiter.max_rate,
            "window_seconds": limiter.window_seconds,
            "burst": limiter.burst,
            "tags": list(limiter.tags),
            "created_at": limiter.created_at,
            "total_requests": limiter.total_requests,
            "allowed_count": limiter.allowed_count,
            "denied_count": limiter.denied_count,
        }
        if limiter.token_bucket:
            result["available_tokens"] = round(limiter.token_bucket.available_tokens, 4)
        if limiter.sliding_window:
            result["current_window_count"] = len(limiter.sliding_window.timestamps)
        if limiter.fixed_window:
            result["fixed_window_count"] = limiter.fixed_window.count
            result["fixed_window_start"] = limiter.fixed_window.window_start
        return result

    def _prune_entries(self) -> None:
        """Remove oldest limiters when max_entries is exceeded."""
        if len(self._limiters) < self._max_entries:
            return
        sorted_lids = sorted(
            self._limiters.keys(),
            key=lambda lid: self._limiters[lid].created_at,
        )
        to_remove = len(self._limiters) - self._max_entries + 1
        for lid in sorted_lids[:to_remove]:
            limiter = self._limiters.pop(lid, None)
            if limiter:
                self._name_index.pop(limiter.name, None)
                self._total_removed += 1
