"""Agent rate limiter.

Enforces per-agent, per-operation rate limits using sliding time windows.
Each limiter tracks request timestamps and rejects requests that exceed
the configured maximum within the active window.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    """Internal state container."""
    limiters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentRateLimiter:
    """Enforces rate limits for agent operations."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._state = _State()
        self._stats = {
            "total_configured": 0,
            "total_allowed": 0,
            "total_rejected": 0,
            "total_resets": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._state._seq += 1
        raw = f"{seed}{time.time()}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"arl2-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest limiters when capacity is exceeded."""
        total = sum(
            len(ops) for ops in self._state.limiters.values()
        )
        if total <= self._max_entries:
            return
        # Flatten all limiter entries with their creation info and prune oldest
        all_entries: List[tuple] = []
        for agent_id, ops in self._state.limiters.items():
            for operation, entry in ops.items():
                all_entries.append((agent_id, operation, entry.get("created_at", 0)))
        all_entries.sort(key=lambda x: x[2])
        to_remove = total - self._max_entries
        for agent_id, operation, _ in all_entries[:to_remove]:
            if agent_id in self._state.limiters:
                self._state.limiters[agent_id].pop(operation, None)
                if not self._state.limiters[agent_id]:
                    del self._state.limiters[agent_id]
            logger.debug("limiter_pruned", agent_id=agent_id, operation=operation)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, agent_id: str, operation: str,
                  max_requests: int = 10,
                  window_seconds: float = 60.0) -> str:
        """Configure a rate limit for an agent operation.

        Returns the limiter_id.
        """
        limiter_id = self._make_id(f"{agent_id}:{operation}")

        if agent_id not in self._state.limiters:
            self._state.limiters[agent_id] = {}

        self._state.limiters[agent_id][operation] = {
            "limiter_id": limiter_id,
            "agent_id": agent_id,
            "operation": operation,
            "max_requests": max_requests,
            "window_seconds": window_seconds,
            "requests": [],
            "created_at": time.time(),
        }

        self._prune()
        self._stats["total_configured"] += 1

        logger.info(
            "limiter_configured",
            agent_id=agent_id,
            operation=operation,
            max_requests=max_requests,
            window_seconds=window_seconds,
            limiter_id=limiter_id,
        )
        self._fire("limiter_configured", {
            "limiter_id": limiter_id,
            "agent_id": agent_id,
            "operation": operation,
            "max_requests": max_requests,
            "window_seconds": window_seconds,
        })
        return limiter_id

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def is_allowed(self, agent_id: str, operation: str) -> bool:
        """Check if a request is within the rate limit.

        Records the request timestamp if allowed.
        Returns True if allowed, False if rate limited.
        """
        agent_ops = self._state.limiters.get(agent_id)
        if agent_ops is None:
            logger.warning("no_limiter_for_agent", agent_id=agent_id)
            return True

        entry = agent_ops.get(operation)
        if entry is None:
            logger.warning("no_limiter_for_operation",
                           agent_id=agent_id, operation=operation)
            return True

        now = time.time()
        cutoff = now - entry["window_seconds"]

        # Filter out expired timestamps
        entry["requests"] = [
            ts for ts in entry["requests"] if ts >= cutoff
        ]

        if len(entry["requests"]) >= entry["max_requests"]:
            self._stats["total_rejected"] += 1
            logger.debug(
                "request_rejected",
                agent_id=agent_id,
                operation=operation,
                current=len(entry["requests"]),
                max=entry["max_requests"],
            )
            self._fire("request_rejected", {
                "agent_id": agent_id,
                "operation": operation,
            })
            return False

        entry["requests"].append(now)
        self._stats["total_allowed"] += 1

        logger.debug(
            "request_allowed",
            agent_id=agent_id,
            operation=operation,
            current=len(entry["requests"]),
            max=entry["max_requests"],
        )
        self._fire("request_allowed", {
            "agent_id": agent_id,
            "operation": operation,
        })
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_remaining(self, agent_id: str, operation: str) -> int:
        """Get remaining requests in current window."""
        agent_ops = self._state.limiters.get(agent_id)
        if agent_ops is None:
            return 0

        entry = agent_ops.get(operation)
        if entry is None:
            return 0

        now = time.time()
        cutoff = now - entry["window_seconds"]
        current = len([ts for ts in entry["requests"] if ts >= cutoff])
        return max(0, entry["max_requests"] - current)

    def get_usage(self, agent_id: str, operation: str) -> dict:
        """Returns usage info: used, max, window_seconds."""
        agent_ops = self._state.limiters.get(agent_id)
        if agent_ops is None:
            return {"used": 0, "max": 0, "window_seconds": 0.0}

        entry = agent_ops.get(operation)
        if entry is None:
            return {"used": 0, "max": 0, "window_seconds": 0.0}

        now = time.time()
        cutoff = now - entry["window_seconds"]
        current = len([ts for ts in entry["requests"] if ts >= cutoff])
        return {
            "used": current,
            "max": entry["max_requests"],
            "window_seconds": entry["window_seconds"],
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_limiter(self, agent_id: str, operation: str) -> bool:
        """Reset a specific rate limiter. Returns True if found and reset."""
        agent_ops = self._state.limiters.get(agent_id)
        if agent_ops is None:
            return False

        entry = agent_ops.get(operation)
        if entry is None:
            return False

        entry["requests"] = []
        self._stats["total_resets"] += 1

        logger.info("limiter_reset", agent_id=agent_id, operation=operation)
        self._fire("limiter_reset", {
            "agent_id": agent_id,
            "operation": operation,
        })
        return True

    # ------------------------------------------------------------------
    # Counting / listing
    # ------------------------------------------------------------------

    def get_limiter_count(self, agent_id: str = "") -> int:
        """Count limiters. If agent_id given, count only that agent's."""
        if agent_id:
            agent_ops = self._state.limiters.get(agent_id)
            if agent_ops is None:
                return 0
            return len(agent_ops)
        return sum(len(ops) for ops in self._state.limiters.values())

    def list_agents(self) -> list:
        """Return list of agent IDs that have configured limiters."""
        return list(self._state.limiters.keys())

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: dict) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        total_limiters = sum(
            len(ops) for ops in self._state.limiters.values()
        )
        return {
            **self._stats,
            "current_limiters": total_limiters,
            "current_agents": len(self._state.limiters),
            "callbacks_registered": len(self._state.callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.limiters.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        for key in self._stats:
            self._stats[key] = 0
        logger.info("rate_limiter_reset")
