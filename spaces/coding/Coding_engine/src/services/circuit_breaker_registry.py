"""
Circuit Breaker Registry — centralized management of circuit breakers for service protection.

Features:
- Multiple named circuit breakers with independent state
- Three states: closed (normal), open (blocking), half-open (testing)
- Configurable failure thresholds and recovery timeouts
- Success/failure tracking with sliding windows
- Health monitoring and status reporting
- Grouped circuit breakers for related services
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

STATES = ("closed", "open", "half_open")


@dataclass
class CircuitBreaker:
    """A single circuit breaker."""
    name: str
    state: str  # closed, open, half_open
    failure_threshold: int  # failures before opening
    success_threshold: int  # successes in half_open before closing
    timeout_seconds: float  # time in open before half_open
    failure_count: int
    success_count: int  # in half_open
    total_calls: int
    total_failures: int
    total_successes: int
    total_rejections: int
    last_failure_time: float
    last_state_change: float
    opened_at: float
    group: str
    metadata: Dict[str, Any]
    created_at: float


# ---------------------------------------------------------------------------
# Circuit Breaker Registry
# ---------------------------------------------------------------------------

class CircuitBreakerRegistry:
    """Centralized circuit breaker management."""

    def __init__(
        self,
        default_failure_threshold: int = 5,
        default_success_threshold: int = 3,
        default_timeout: float = 30.0,
        max_breakers: int = 1000,
    ):
        self._default_failure_threshold = default_failure_threshold
        self._default_success_threshold = default_success_threshold
        self._default_timeout = default_timeout
        self._max_breakers = max_breakers

        self._breakers: Dict[str, CircuitBreaker] = {}
        self._groups: Dict[str, Set[str]] = defaultdict(set)
        self._callbacks: Dict[str, Callable] = {}

        self._stats = {
            "total_created": 0,
            "total_removed": 0,
            "total_state_changes": 0,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        failure_threshold: int = 0,
        success_threshold: int = 0,
        timeout_seconds: float = 0.0,
        group: str = "",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Create a new circuit breaker."""
        if name in self._breakers:
            return False

        now = time.time()
        self._breakers[name] = CircuitBreaker(
            name=name,
            state="closed",
            failure_threshold=failure_threshold or self._default_failure_threshold,
            success_threshold=success_threshold or self._default_success_threshold,
            timeout_seconds=timeout_seconds or self._default_timeout,
            failure_count=0,
            success_count=0,
            total_calls=0,
            total_failures=0,
            total_successes=0,
            total_rejections=0,
            last_failure_time=0.0,
            last_state_change=now,
            opened_at=0.0,
            group=group,
            metadata=metadata or {},
            created_at=now,
        )

        if group:
            self._groups[group].add(name)

        self._stats["total_created"] += 1
        return True

    def remove(self, name: str) -> bool:
        """Remove a circuit breaker."""
        cb = self._breakers.get(name)
        if not cb:
            return False

        if cb.group and cb.group in self._groups:
            self._groups[cb.group].discard(name)
            if not self._groups[cb.group]:
                del self._groups[cb.group]

        del self._breakers[name]
        self._stats["total_removed"] += 1
        return True

    def get(self, name: str) -> Optional[Dict]:
        """Get circuit breaker info."""
        cb = self._breakers.get(name)
        if not cb:
            return None
        self._check_timeout(cb)
        return self._cb_to_dict(cb)

    # ------------------------------------------------------------------
    # Call flow
    # ------------------------------------------------------------------

    def allow(self, name: str) -> bool:
        """Check if a call is allowed through the circuit breaker."""
        cb = self._breakers.get(name)
        if not cb:
            return True  # Unknown breaker allows by default

        self._check_timeout(cb)

        if cb.state == "closed":
            return True
        elif cb.state == "half_open":
            return True  # Allow test calls
        else:  # open
            cb.total_rejections += 1
            return False

    def record_success(self, name: str) -> bool:
        """Record a successful call."""
        cb = self._breakers.get(name)
        if not cb:
            return False

        cb.total_calls += 1
        cb.total_successes += 1

        if cb.state == "half_open":
            cb.success_count += 1
            if cb.success_count >= cb.success_threshold:
                self._transition(cb, "closed")
                cb.failure_count = 0
                cb.success_count = 0
        elif cb.state == "closed":
            # Reset failure count on success
            cb.failure_count = 0

        return True

    def record_failure(self, name: str) -> bool:
        """Record a failed call."""
        cb = self._breakers.get(name)
        if not cb:
            return False

        cb.total_calls += 1
        cb.total_failures += 1
        cb.last_failure_time = time.time()

        if cb.state == "half_open":
            # Any failure in half_open re-opens
            self._transition(cb, "open")
            cb.success_count = 0
        elif cb.state == "closed":
            cb.failure_count += 1
            if cb.failure_count >= cb.failure_threshold:
                self._transition(cb, "open")

        return True

    # ------------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------------

    def force_open(self, name: str) -> bool:
        """Force a circuit breaker open."""
        cb = self._breakers.get(name)
        if not cb:
            return False
        if cb.state != "open":
            self._transition(cb, "open")
        return True

    def force_close(self, name: str) -> bool:
        """Force a circuit breaker closed."""
        cb = self._breakers.get(name)
        if not cb:
            return False
        if cb.state != "closed":
            self._transition(cb, "closed")
            cb.failure_count = 0
            cb.success_count = 0
        return True

    def force_half_open(self, name: str) -> bool:
        """Force a circuit breaker to half-open for testing."""
        cb = self._breakers.get(name)
        if not cb:
            return False
        if cb.state != "half_open":
            self._transition(cb, "half_open")
            cb.success_count = 0
        return True

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        name: str,
        failure_threshold: Optional[int] = None,
        success_threshold: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Update circuit breaker configuration."""
        cb = self._breakers.get(name)
        if not cb:
            return False
        if failure_threshold is not None:
            cb.failure_threshold = failure_threshold
        if success_threshold is not None:
            cb.success_threshold = success_threshold
        if timeout_seconds is not None:
            cb.timeout_seconds = timeout_seconds
        return True

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_state(self, name: str) -> Optional[str]:
        """Get current state of a circuit breaker."""
        cb = self._breakers.get(name)
        if not cb:
            return None
        self._check_timeout(cb)
        return cb.state

    def list_breakers(
        self,
        state: Optional[str] = None,
        group: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List circuit breakers with optional filters."""
        results = []
        for cb in self._breakers.values():
            self._check_timeout(cb)
            if state and cb.state != state:
                continue
            if group and cb.group != group:
                continue
            results.append(self._cb_to_dict(cb))
            if len(results) >= limit:
                break
        return results

    def get_open_breakers(self) -> List[Dict]:
        """Get all open circuit breakers."""
        return self.list_breakers(state="open")

    def get_group(self, group: str) -> List[Dict]:
        """Get all breakers in a group."""
        names = self._groups.get(group, set())
        return [self._cb_to_dict(self._breakers[n]) for n in names if n in self._breakers]

    def list_groups(self) -> Dict[str, int]:
        """List groups with counts."""
        return {g: len(names) for g, names in sorted(self._groups.items())}

    def get_summary(self) -> Dict[str, int]:
        """Get counts by state."""
        counts: Dict[str, int] = defaultdict(int)
        for cb in self._breakers.values():
            self._check_timeout(cb)
            counts[cb.state] += 1
        return dict(counts)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_state_change(self, name: str, callback: Callable) -> bool:
        """Register state change callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_timeout(self, cb: CircuitBreaker) -> None:
        """Check if open breaker should transition to half_open."""
        if cb.state == "open" and cb.opened_at > 0:
            if time.time() - cb.opened_at >= cb.timeout_seconds:
                self._transition(cb, "half_open")
                cb.success_count = 0

    def _transition(self, cb: CircuitBreaker, new_state: str) -> None:
        """Transition circuit breaker to new state."""
        old_state = cb.state
        cb.state = new_state
        cb.last_state_change = time.time()

        if new_state == "open":
            cb.opened_at = time.time()
        elif new_state == "closed":
            cb.opened_at = 0.0

        self._stats["total_state_changes"] += 1

        for callback in self._callbacks.values():
            try:
                callback(cb.name, old_state, new_state)
            except Exception:
                pass

    def _cb_to_dict(self, cb: CircuitBreaker) -> Dict:
        return {
            "name": cb.name,
            "state": cb.state,
            "failure_threshold": cb.failure_threshold,
            "success_threshold": cb.success_threshold,
            "timeout_seconds": cb.timeout_seconds,
            "failure_count": cb.failure_count,
            "success_count": cb.success_count,
            "total_calls": cb.total_calls,
            "total_failures": cb.total_failures,
            "total_successes": cb.total_successes,
            "total_rejections": cb.total_rejections,
            "last_failure_time": cb.last_failure_time,
            "last_state_change": cb.last_state_change,
            "group": cb.group,
            "metadata": cb.metadata,
            "created_at": cb.created_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_breakers": len(self._breakers),
            "total_groups": len(self._groups),
        }

    def reset(self) -> None:
        self._breakers.clear()
        self._groups.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
