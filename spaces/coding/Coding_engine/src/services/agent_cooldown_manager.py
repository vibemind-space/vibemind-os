"""Agent Cooldown Manager -- manages cooldown periods for agent operations.

Tracks per-agent, per-operation cooldowns with configurable durations.
Supports querying remaining time, cancellation, and fires change callbacks
on cooldown mutations.
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
    """Internal state for the cooldown manager."""

    cooldowns: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentCooldownManager
# ---------------------------------------------------------------------------

class AgentCooldownManager:
    """Manages cooldown periods for agent operations."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = _State()
        self._max_entries = max_entries
        self._total_started = 0
        self._total_cancelled = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"acm-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove expired entries if total count exceeds max_entries."""
        total = sum(
            len(ops) for ops in self._state.cooldowns.values()
        )
        if total < self._max_entries:
            return
        now = time.time()
        for agent_id in list(self._state.cooldowns.keys()):
            ops = self._state.cooldowns[agent_id]
            expired = [op for op, entry in ops.items() if now >= entry["expires_at"]]
            for op in expired:
                del ops[op]
            if not ops:
                del self._state.cooldowns[agent_id]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def start_cooldown(
        self,
        agent_id: str,
        operation: str,
        duration_seconds: float = 60.0,
    ) -> str:
        """Start a cooldown period for an agent operation.

        Returns the cooldown ID (``acm-...``), or empty string on failure.
        """
        if not agent_id or not operation or duration_seconds <= 0:
            logger.warning(
                "start_cooldown.invalid_input",
                agent_id=agent_id,
                operation=operation,
                duration_seconds=duration_seconds,
            )
            return ""

        self._prune_if_needed()

        cooldown_id = self._make_id(f"{agent_id}-{operation}")
        now = time.time()
        entry = {
            "cooldown_id": cooldown_id,
            "agent_id": agent_id,
            "operation": operation,
            "duration_seconds": duration_seconds,
            "started_at": now,
            "expires_at": now + duration_seconds,
        }

        if agent_id not in self._state.cooldowns:
            self._state.cooldowns[agent_id] = {}
        self._state.cooldowns[agent_id][operation] = entry
        self._total_started += 1

        logger.info(
            "start_cooldown.ok",
            agent_id=agent_id,
            operation=operation,
            cooldown_id=cooldown_id,
            duration_seconds=duration_seconds,
        )
        self._fire(
            "cooldown_started",
            cooldown_id=cooldown_id,
            agent_id=agent_id,
            operation=operation,
            duration_seconds=duration_seconds,
        )
        return cooldown_id

    def is_cooled_down(self, agent_id: str, operation: str) -> bool:
        """Check if cooldown has expired.

        Returns True if the agent can proceed (no active cooldown or expired).
        """
        ops = self._state.cooldowns.get(agent_id)
        if not ops:
            return True
        entry = ops.get(operation)
        if not entry:
            return True
        return time.time() >= entry["expires_at"]

    def get_remaining(self, agent_id: str, operation: str) -> float:
        """Get remaining cooldown seconds.

        Returns 0.0 if expired or not found.
        """
        ops = self._state.cooldowns.get(agent_id)
        if not ops:
            return 0.0
        entry = ops.get(operation)
        if not entry:
            return 0.0
        return max(0.0, entry["expires_at"] - time.time())

    def cancel_cooldown(self, agent_id: str, operation: str) -> bool:
        """Cancel an active cooldown.

        Returns True if a cooldown was cancelled, False otherwise.
        """
        ops = self._state.cooldowns.get(agent_id)
        if not ops:
            return False
        if operation not in ops:
            return False

        entry = ops.pop(operation)
        if not ops:
            del self._state.cooldowns[agent_id]

        self._total_cancelled += 1
        logger.info(
            "cancel_cooldown.ok",
            agent_id=agent_id,
            operation=operation,
            cooldown_id=entry["cooldown_id"],
        )
        self._fire(
            "cooldown_cancelled",
            cooldown_id=entry["cooldown_id"],
            agent_id=agent_id,
            operation=operation,
        )
        return True

    def get_active_cooldowns(self, agent_id: str) -> list:
        """Get list of active (non-expired) cooldowns for an agent."""
        ops = self._state.cooldowns.get(agent_id)
        if not ops:
            return []
        now = time.time()
        active = []
        for entry in ops.values():
            if now < entry["expires_at"]:
                active.append(dict(entry))
        return active

    def get_cooldown_count(self, agent_id: str = "") -> int:
        """Count total cooldowns (all or for a specific agent)."""
        if agent_id:
            ops = self._state.cooldowns.get(agent_id)
            return len(ops) if ops else 0
        return sum(len(ops) for ops in self._state.cooldowns.values())

    def list_agents(self) -> list:
        """Return list of agent IDs with registered cooldowns."""
        return list(self._state.cooldowns.keys())

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
        total_cooldowns = sum(
            len(ops) for ops in self._state.cooldowns.values()
        )
        now = time.time()
        total_active = sum(
            1
            for ops in self._state.cooldowns.values()
            for entry in ops.values()
            if now < entry["expires_at"]
        )
        return {
            "total_cooldowns": total_cooldowns,
            "total_active": total_active,
            "total_agents": len(self._state.cooldowns),
            "total_started": self._total_started,
            "total_cancelled": self._total_cancelled,
            "callbacks": len(self._state.callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._state.cooldowns.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        self._total_started = 0
        self._total_cancelled = 0
        logger.info("reset.ok")
