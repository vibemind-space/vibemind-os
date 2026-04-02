"""Agent Timeout Manager -- manages operation timeouts for agents.

Tracks per-agent, per-operation timeouts with configurable durations.
Supports checking if timed out, querying remaining time, cancellation,
and fires change callbacks on timeout mutations.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _State:
    """Internal state for the timeout manager."""

    timeouts: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentTimeoutManager
# ---------------------------------------------------------------------------

class AgentTimeoutManager:
    """Manages operation timeouts for agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = _State()
        self._max_entries = max_entries
        self._total_set = 0
        self._total_cancelled = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"atm-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove expired entries if total count exceeds max_entries."""
        total = sum(
            len(ops) for ops in self._state.timeouts.values()
        )
        if total < self._max_entries:
            return
        now = time.time()
        for agent_id in list(self._state.timeouts.keys()):
            ops = self._state.timeouts[agent_id]
            expired = [
                op for op, entry in ops.items()
                if now >= entry["start_time"] + entry["timeout_seconds"]
            ]
            for op in expired:
                del ops[op]
            if not ops:
                del self._state.timeouts[agent_id]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set_timeout(
        self,
        agent_id: str,
        operation: str,
        timeout_seconds: float,
    ) -> str:
        """Set a timeout for an agent operation.

        Returns the timeout ID (``atm-...``), or empty string on failure.
        """
        if not agent_id or not operation or timeout_seconds <= 0:
            logger.warning(
                "set_timeout.invalid_input",
                agent_id=agent_id,
                operation=operation,
                timeout_seconds=timeout_seconds,
            )
            return ""

        self._prune_if_needed()

        timeout_id = self._make_id(f"{agent_id}-{operation}")
        now = time.time()
        entry = {
            "timeout_id": timeout_id,
            "agent_id": agent_id,
            "operation": operation,
            "timeout_seconds": timeout_seconds,
            "start_time": now,
        }

        if agent_id not in self._state.timeouts:
            self._state.timeouts[agent_id] = {}
        self._state.timeouts[agent_id][operation] = entry
        self._total_set += 1

        logger.info(
            "set_timeout.ok",
            agent_id=agent_id,
            operation=operation,
            timeout_id=timeout_id,
            timeout_seconds=timeout_seconds,
        )
        self._fire(
            "timeout_set",
            timeout_id=timeout_id,
            agent_id=agent_id,
            operation=operation,
            timeout_seconds=timeout_seconds,
        )
        return timeout_id

    def is_timed_out(self, agent_id: str, operation: str) -> bool:
        """Check if an operation has exceeded its timeout.

        Returns True if timed out, False if still within limit or not found.
        """
        ops = self._state.timeouts.get(agent_id)
        if not ops:
            return False
        entry = ops.get(operation)
        if not entry:
            return False
        return time.time() >= entry["start_time"] + entry["timeout_seconds"]

    def get_remaining(self, agent_id: str, operation: str) -> float:
        """Get remaining seconds before timeout.

        Returns 0.0 if timed out or not found.
        """
        ops = self._state.timeouts.get(agent_id)
        if not ops:
            return 0.0
        entry = ops.get(operation)
        if not entry:
            return 0.0
        remaining = (entry["start_time"] + entry["timeout_seconds"]) - time.time()
        return max(0.0, remaining)

    def cancel_timeout(self, agent_id: str, operation: str) -> bool:
        """Cancel/remove a timeout.

        Returns True if a timeout was cancelled, False otherwise.
        """
        ops = self._state.timeouts.get(agent_id)
        if not ops:
            return False
        if operation not in ops:
            return False

        entry = ops.pop(operation)
        if not ops:
            del self._state.timeouts[agent_id]

        self._total_cancelled += 1
        logger.info(
            "cancel_timeout.ok",
            agent_id=agent_id,
            operation=operation,
            timeout_id=entry["timeout_id"],
        )
        self._fire(
            "timeout_cancelled",
            timeout_id=entry["timeout_id"],
            agent_id=agent_id,
            operation=operation,
        )
        return True

    def get_timeouts(self, agent_id: str) -> list:
        """Get list of all timeouts for an agent."""
        ops = self._state.timeouts.get(agent_id)
        if not ops:
            return []
        return [dict(entry) for entry in ops.values()]

    def get_timeout_count(self, agent_id: str = "") -> int:
        """Count total timeouts (all or for a specific agent)."""
        if agent_id:
            ops = self._state.timeouts.get(agent_id)
            return len(ops) if ops else 0
        return sum(len(ops) for ops in self._state.timeouts.values())

    def list_agents(self) -> list:
        """Return list of agent IDs with registered timeouts."""
        return list(self._state.timeouts.keys())

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback."""
        self._state.callbacks[name] = callback
        logger.debug("on_change.registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            logger.debug("remove_callback.ok", name=name)
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception(
                    "_fire.callback_error", callback=cb_name, action=action
                )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return aggregate statistics as a dict."""
        total_timeouts = sum(
            len(ops) for ops in self._state.timeouts.values()
        )
        now = time.time()
        total_active = sum(
            1
            for ops in self._state.timeouts.values()
            for entry in ops.values()
            if now < entry["start_time"] + entry["timeout_seconds"]
        )
        return {
            "total_timeouts": total_timeouts,
            "total_active": total_active,
            "total_agents": len(self._state.timeouts),
            "total_set": self._total_set,
            "total_cancelled": self._total_cancelled,
            "callbacks": len(self._state.callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._state.timeouts.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        self._total_set = 0
        self._total_cancelled = 0
        logger.info("reset.ok")
