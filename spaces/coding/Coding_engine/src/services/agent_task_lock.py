"""Agent Task Lock – distributed-style locks for agent tasks.

Prevents concurrent execution of the same task by managing exclusive
locks on named resources with automatic expiration.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskLockState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskLock:
    """Manages distributed-style locks for agent tasks."""

    PREFIX = "atl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskLockState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Callable | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self, resource: str, agent_id: str) -> str:
        self._state._seq += 1
        raw = f"{resource}-{agent_id}-{time.time()}-{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        released = [
            k for k, v in self._state.entries.items() if v["status"] != "held"
        ]
        for k in released:
            del self._state.entries[k]
            if len(self._state.entries) <= self.MAX_ENTRIES:
                return

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Callable | None:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Callable | None) -> None:
        self._on_change = value

    def remove_callback(self, callback_id: str) -> bool:
        return self._callbacks.pop(callback_id, None) is not None

    # ------------------------------------------------------------------
    # Lock operations
    # ------------------------------------------------------------------

    def acquire(self, agent_id: str, resource: str, ttl_seconds: float = 60) -> str:
        """Acquire a lock on *resource* for *agent_id*.

        Returns the lock id on success or ``""`` if the resource is already
        locked by a different agent and the lock has not expired.
        """
        if not agent_id or not resource:
            return ""

        now = time.time()

        # Check for existing held lock on the same resource
        for lid, entry in self._state.entries.items():
            if (
                entry["resource"] == resource
                and entry["status"] == "held"
                and entry["expires_at"] > now
            ):
                if entry["agent_id"] == agent_id:
                    # Same agent already holds it – return existing lock
                    return lid
                # Different agent holds it – deny
                return ""

        # Release any expired lock on this resource first
        for lid, entry in list(self._state.entries.items()):
            if (
                entry["resource"] == resource
                and entry["status"] == "held"
                and entry["expires_at"] <= now
            ):
                entry["status"] = "released"

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        lock_id = self._generate_id(resource, agent_id)
        self._state.entries[lock_id] = {
            "lock_id": lock_id,
            "agent_id": agent_id,
            "resource": resource,
            "acquired_at": now,
            "expires_at": now + ttl_seconds,
            "status": "held",
        }
        self._fire("acquired", self._state.entries[lock_id])
        logger.debug("Lock acquired: %s by %s on %s", lock_id, agent_id, resource)
        return lock_id

    def release(self, lock_id: str) -> bool:
        """Release a lock by its id."""
        entry = self._state.entries.get(lock_id)
        if entry is None or entry["status"] != "held":
            return False
        entry["status"] = "released"
        self._fire("released", entry)
        logger.debug("Lock released: %s", lock_id)
        return True

    def is_locked(self, resource: str) -> bool:
        """Return True if *resource* is currently locked (held and not expired)."""
        now = time.time()
        for entry in self._state.entries.values():
            if (
                entry["resource"] == resource
                and entry["status"] == "held"
                and entry["expires_at"] > now
            ):
                return True
        return False

    def get_lock(self, lock_id: str) -> dict:
        """Return the lock entry or empty dict."""
        entry = self._state.entries.get(lock_id)
        return dict(entry) if entry else {}

    def get_locks(self, agent_id: str = "", status: str = "") -> list:
        """Return locks matching optional filters."""
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def get_lock_holder(self, resource: str) -> str:
        """Return the agent_id holding the lock on *resource*, or ``""``."""
        now = time.time()
        for entry in self._state.entries.values():
            if (
                entry["resource"] == resource
                and entry["status"] == "held"
                and entry["expires_at"] > now
            ):
                return entry["agent_id"]
        return ""

    def renew(self, lock_id: str, ttl_seconds: float = 60) -> bool:
        """Extend the expiry of a held lock."""
        entry = self._state.entries.get(lock_id)
        if entry is None or entry["status"] != "held":
            return False
        entry["expires_at"] = time.time() + ttl_seconds
        self._fire("renewed", entry)
        logger.debug("Lock renewed: %s", lock_id)
        return True

    def get_lock_count(self, agent_id: str = "", status: str = "") -> int:
        """Return the number of locks matching optional filters."""
        return len(self.get_locks(agent_id=agent_id, status=status))

    def cleanup_expired(self) -> int:
        """Release all expired held locks. Return count cleaned."""
        now = time.time()
        count = 0
        for entry in self._state.entries.values():
            if entry["status"] == "held" and entry["expires_at"] <= now:
                entry["status"] = "released"
                count += 1
                self._fire("expired", entry)
        logger.debug("Cleaned up %d expired locks", count)
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._state.entries)
        held = sum(1 for e in self._state.entries.values() if e["status"] == "held")
        released = sum(
            1 for e in self._state.entries.values() if e["status"] == "released"
        )
        return {
            "total_locks": total,
            "held_locks": held,
            "released_locks": released,
            "expired_cleaned": released,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskLockState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskLock reset")
