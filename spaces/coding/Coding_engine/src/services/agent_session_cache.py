"""Agent Session Cache -- per-agent session-scoped cache for emergent pipelines.

Manages cached key-value entries per agent session with configurable TTLs.
Entries are keyed by agent_id and key, supporting expiry checks, deletion,
and automatic max-entries pruning.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _State:
    """Internal state for the session cache."""

    caches: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentSessionCache
# ---------------------------------------------------------------------------

class AgentSessionCache:
    """Per-agent session cache with TTL-based expiry, pruning, and callbacks."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = _State()
        self._max_entries = max_entries
        self._total_sets = 0
        self._total_gets = 0
        self._total_deletes = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"asc-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove expired entries if total count exceeds max_entries."""
        total = sum(
            len(keys) for keys in self._state.caches.values()
        )
        if total < self._max_entries:
            return
        now = time.time()
        for agent_id in list(self._state.caches.keys()):
            keys = self._state.caches[agent_id]
            expired = [k for k, entry in keys.items() if now > entry["expires_at"]]
            for k in expired:
                del keys[k]
            if not keys:
                del self._state.caches[agent_id]

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
    # Core API
    # ------------------------------------------------------------------

    def cache_set(
        self,
        agent_id: str,
        key: str,
        value: Any,
        ttl_seconds: float = 300.0,
    ) -> str:
        """Set a cache entry for an agent.

        Parameters
        ----------
        agent_id:
            The owning agent identifier.
        key:
            The cache key.
        value:
            Arbitrary value to cache.
        ttl_seconds:
            Time-to-live in seconds (default 300).

        Returns
        -------
        str
            The generated cache ID (prefixed ``asc-``), or empty string on
            invalid input.
        """
        if not agent_id or not key or ttl_seconds <= 0:
            logger.warning(
                "cache_set.invalid_input",
                agent_id=agent_id,
                key=key,
                ttl_seconds=ttl_seconds,
            )
            return ""

        self._prune_if_needed()

        cache_id = self._make_id(f"{agent_id}-{key}")
        now = time.time()
        entry = {
            "cache_id": cache_id,
            "key": key,
            "value": value,
            "ttl_seconds": ttl_seconds,
            "created_at": now,
            "expires_at": now + ttl_seconds,
        }

        if agent_id not in self._state.caches:
            self._state.caches[agent_id] = {}
        self._state.caches[agent_id][key] = entry
        self._total_sets += 1

        logger.info(
            "cache_set.ok",
            agent_id=agent_id,
            key=key,
            cache_id=cache_id,
            ttl_seconds=ttl_seconds,
        )
        self._fire(
            "cache_set",
            cache_id=cache_id,
            agent_id=agent_id,
            key=key,
            ttl_seconds=ttl_seconds,
        )
        return cache_id

    def cache_get(self, agent_id: str, key: str) -> Any:
        """Get a cached value by agent_id and key.

        Returns None if not found or expired.
        """
        self._total_gets += 1
        keys = self._state.caches.get(agent_id)
        if not keys:
            return None
        entry = keys.get(key)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            return None
        return entry["value"]

    def cache_delete(self, agent_id: str, key: str) -> bool:
        """Delete a cache entry.

        Returns True if the entry existed and was removed, False otherwise.
        """
        keys = self._state.caches.get(agent_id)
        if not keys:
            return False
        if key not in keys:
            return False

        entry = keys.pop(key)
        if not keys:
            del self._state.caches[agent_id]

        self._total_deletes += 1
        logger.info(
            "cache_delete.ok",
            agent_id=agent_id,
            key=key,
            cache_id=entry["cache_id"],
        )
        self._fire(
            "cache_deleted",
            cache_id=entry["cache_id"],
            agent_id=agent_id,
            key=key,
        )
        return True

    def cache_has(self, agent_id: str, key: str) -> bool:
        """Check if a cache key exists and is not expired."""
        keys = self._state.caches.get(agent_id)
        if not keys:
            return False
        entry = keys.get(key)
        if not entry:
            return False
        return time.time() <= entry["expires_at"]

    def get_cache_size(self, agent_id: str) -> int:
        """Get number of cached entries for a specific agent."""
        keys = self._state.caches.get(agent_id)
        return len(keys) if keys else 0

    def get_cache_count(self, agent_id: str = "") -> int:
        """Get total cache entries count (all or for a specific agent)."""
        if agent_id:
            keys = self._state.caches.get(agent_id)
            return len(keys) if keys else 0
        return sum(len(keys) for keys in self._state.caches.values())

    def list_agents(self) -> list:
        """Return list of agent IDs with cached entries."""
        return list(self._state.caches.keys())

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return aggregate statistics as a dict."""
        total_entries = sum(
            len(keys) for keys in self._state.caches.values()
        )
        now = time.time()
        total_active = sum(
            1
            for keys in self._state.caches.values()
            for entry in keys.values()
            if now <= entry["expires_at"]
        )
        return {
            "total_entries": total_entries,
            "total_active": total_active,
            "total_agents": len(self._state.caches),
            "total_sets": self._total_sets,
            "total_gets": self._total_gets,
            "total_deletes": self._total_deletes,
            "callbacks": len(self._state.callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._state.caches.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        self._total_sets = 0
        self._total_gets = 0
        self._total_deletes = 0
        logger.info("reset.ok")
