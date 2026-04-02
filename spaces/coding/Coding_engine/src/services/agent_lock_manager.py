"""Agent Lock Manager – manages exclusive locks on resources for agents.

Agents acquire time-limited locks on named resources.  Only one agent may
hold a given resource lock at a time; expired locks are automatically
reclaimed on access.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

log = structlog.get_logger(__name__)


@dataclass
class _State:
    locks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentLockManager:
    """Manages exclusive resource locks for agents."""

    _MAX = 10000
    _PREFIX = "alm-"

    def __init__(self) -> None:
        self._state = _State()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, resource: str, agent_id: str) -> str:
        self._state._seq += 1
        raw = f"{resource}-{agent_id}-{time.time()}-{self._state._seq}"
        return self._PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Acquire / Release
    # ------------------------------------------------------------------

    def acquire_lock(
        self,
        agent_id: str,
        resource: str,
        timeout_seconds: float = 300.0,
    ) -> str:
        """Acquire a lock on *resource* for *agent_id*.

        Returns the lock id (``alm-...``) on success or ``""`` if the
        resource is already locked by a different agent and the lock has
        not yet expired.
        """
        if not agent_id or not resource:
            return ""

        now = time.time()
        existing = self._state.locks.get(resource)

        if existing is not None:
            if existing["agent_id"] != agent_id and now < existing["expires_at"]:
                return ""
            # Same agent re-acquiring or expired lock – remove old entry
            self._state.locks.pop(resource, None)

        if len(self._state.locks) >= self._MAX:
            return ""

        lock_id = self._next_id(resource, agent_id)
        self._state.locks[resource] = {
            "lock_id": lock_id,
            "agent_id": agent_id,
            "resource": resource,
            "acquired_at": now,
            "expires_at": now + timeout_seconds,
            "timeout_seconds": timeout_seconds,
        }

        log.debug("lock_acquired", lock_id=lock_id, agent_id=agent_id, resource=resource)
        self._fire("lock_acquired", {"lock_id": lock_id, "agent_id": agent_id, "resource": resource})
        return lock_id

    def release_lock(self, agent_id: str, resource: str) -> bool:
        """Release a lock held by *agent_id* on *resource*."""
        existing = self._state.locks.get(resource)
        if existing is None or existing["agent_id"] != agent_id:
            return False

        self._state.locks.pop(resource, None)
        log.debug("lock_released", agent_id=agent_id, resource=resource)
        self._fire("lock_released", {"agent_id": agent_id, "resource": resource})
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_locked(self, resource: str) -> bool:
        """Return ``True`` if *resource* is currently locked (not expired)."""
        entry = self._state.locks.get(resource)
        if entry is None:
            return False
        if time.time() >= entry["expires_at"]:
            self._state.locks.pop(resource, None)
            return False
        return True

    def get_lock_holder(self, resource: str) -> str:
        """Return the ``agent_id`` holding the lock on *resource*, or ``""``."""
        entry = self._state.locks.get(resource)
        if entry is None:
            return ""
        if time.time() >= entry["expires_at"]:
            self._state.locks.pop(resource, None)
            return ""
        return entry["agent_id"]

    def get_locks(self, agent_id: str) -> list:
        """Return all active (non-expired) lock entries for *agent_id*."""
        now = time.time()
        results: List[Dict[str, Any]] = []
        expired_keys: List[str] = []

        for resource, entry in self._state.locks.items():
            if now >= entry["expires_at"]:
                expired_keys.append(resource)
                continue
            if entry["agent_id"] == agent_id:
                results.append(dict(entry))

        for key in expired_keys:
            self._state.locks.pop(key, None)

        return results

    def get_lock_count(self, agent_id: str = "") -> int:
        """Return the number of active locks, optionally filtered by *agent_id*."""
        now = time.time()
        expired_keys = [r for r, e in self._state.locks.items() if now >= e["expires_at"]]
        for key in expired_keys:
            self._state.locks.pop(key, None)

        if not agent_id:
            return len(self._state.locks)
        return sum(1 for e in self._state.locks.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        """Return a sorted list of distinct agent ids that currently hold locks."""
        now = time.time()
        expired_keys = [r for r, e in self._state.locks.items() if now >= e["expires_at"]]
        for key in expired_keys:
            self._state.locks.pop(key, None)

        agents = sorted({e["agent_id"] for e in self._state.locks.values()})
        return agents

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        now = time.time()
        expired_keys = [r for r, e in self._state.locks.items() if now >= e["expires_at"]]
        for key in expired_keys:
            self._state.locks.pop(key, None)

        agents = {e["agent_id"] for e in self._state.locks.values()}
        return {
            "total_locks": len(self._state.locks),
            "total_agents": len(agents),
            "max_locks": self._MAX,
            "callbacks": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all locks, sequence counter, and callbacks."""
        self._state.locks.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        log.debug("lock_manager_reset")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback under *name*.  Returns ``False`` if already registered."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove callback by *name*.  Returns ``True`` if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: dict) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                log.warning("callback_error", action=action, exc_info=True)
