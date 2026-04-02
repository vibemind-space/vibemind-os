"""Agent Workflow Cacher – caches workflow execution results for reuse.

Stores workflow results keyed by a SHA-256-based ID with an ``awca-`` prefix.
Supports TTL-based expiration, filtering by agent and workflow name, automatic
pruning when the store exceeds *MAX_ENTRIES*, and callback notifications.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowCacherState:
    """Internal store for cached workflow entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowCacher:
    """Caches workflow execution results for reuse.

    Supports caching, retrieval, filtering, TTL expiration, automatic pruning,
    and callback-based change notifications.
    """

    PREFIX = "awca-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowCacherState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict the oldest quarter of entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("seq", 0)),
        )
        remove_count = len(sorted_entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke on_change first, then all registered callbacks.

        Exceptions are silently ignored.
        """
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Return True if the entry has a positive TTL and is past expiry."""
        ttl = entry.get("ttl", 0)
        if ttl <= 0:
            return False
        return time.time() > entry["created_at"] + ttl

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def cache(
        self,
        agent_id: str,
        workflow_name: str,
        result: Any,
        ttl: int = 0,
    ) -> str:
        """Cache a workflow execution result.

        Parameters
        ----------
        agent_id:
            Identifier of the agent that produced the result.
        workflow_name:
            Name of the workflow whose result is being cached.
        result:
            The result payload to cache.
        ttl:
            Time-to-live in seconds.  ``0`` means no expiration.

        Returns
        -------
        str
            The generated cache entry ID (``awca-`` prefix).
        """
        self._prune()
        cache_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "cache_id": cache_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "result": result,
            "ttl": ttl,
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[cache_id] = entry
        self._fire("cached", entry)
        logger.debug(
            "Cached result: %s for agent=%s workflow=%s ttl=%s",
            cache_id,
            agent_id,
            workflow_name,
            ttl,
        )
        return cache_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_cached(self, cache_id: str) -> Optional[dict]:
        """Retrieve a cached entry by ID.

        Returns ``None`` if not found or expired.
        """
        entry = self._state.entries.get(cache_id)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._state.entries[cache_id]
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_cache_entries(
        self,
        agent_id: str = "",
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query cache entries, newest first.

        Optionally filter by *agent_id* and/or *workflow_name*.
        Expired entries are excluded.  Returns at most *limit* results.
        """
        # Collect non-expired, matching entries
        expired_ids: List[str] = []
        candidates: List[Dict[str, Any]] = []

        for eid, entry in self._state.entries.items():
            if self._is_expired(entry):
                expired_ids.append(eid)
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if workflow_name and entry["workflow_name"] != workflow_name:
                continue
            candidates.append(entry)

        # Clean up expired entries encountered during scan
        for eid in expired_ids:
            del self._state.entries[eid]

        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)),
            reverse=True,
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_cache_count(self, agent_id: str = "") -> int:
        """Return the number of non-expired cached entries.

        Optionally filter by *agent_id*.
        """
        count = 0
        expired_ids: List[str] = []
        for eid, entry in self._state.entries.items():
            if self._is_expired(entry):
                expired_ids.append(eid)
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            count += 1
        for eid in expired_ids:
            del self._state.entries[eid]
        return count

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the cacher service."""
        agents: set = set()
        workflows: set = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
            workflows.add(entry["workflow_name"])
        return {
            "total_entries": len(self._state.entries),
            "unique_agents": len(agents),
            "unique_workflows": len(workflows),
            "callbacks_registered": len(self._callbacks),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all cached entries, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
