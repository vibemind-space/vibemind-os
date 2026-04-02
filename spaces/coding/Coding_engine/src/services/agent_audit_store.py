"""Agent Audit Store -- records and queries agent audit trail entries.

Provides a central, in-memory audit trail for agent actions. Every
recorded entry captures the agent, action verb, optional resource, free-form
details, and arbitrary metadata. The store supports rich filtering, per-agent
summaries, and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _AuditEntry:
    """A single recorded audit entry."""

    entry_id: str = ""
    agent_id: str = ""
    action: str = ""
    resource: str = ""
    details: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentAuditStore:
    """In-memory audit store for agent actions.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When the limit is reached the
        oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, _AuditEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}

        # indexes for fast lookup
        self._agent_index: Dict[str, List[str]] = {}    # agent_id -> [entry_id]
        self._action_index: Dict[str, List[str]] = {}   # action    -> [entry_id]
        self._resource_index: Dict[str, List[str]] = {} # resource  -> [entry_id]

        # stats counters
        self._stats: Dict[str, int] = {
            "total_recorded": 0,
            "total_pruned": 0,
            "total_purged": 0,
            "total_queries": 0,
        }

        logger.debug("agent_audit_store.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        action: str,
        resource: str = "",
        details: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record an audit entry and return its ``entry_id``.

        Returns an empty string when *agent_id* or *action* is falsy.
        """
        if not agent_id or not action:
            return ""

        with self._lock:
            # prune if at capacity
            if len(self._entries) >= self._max_entries:
                self._prune()

            self._seq += 1
            now = time.time()
            raw = f"{agent_id}-{action}-{now}-{self._seq}"
            entry_id = "aas-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            entry = _AuditEntry(
                entry_id=entry_id,
                agent_id=agent_id,
                action=action,
                resource=resource,
                details=details,
                metadata=dict(metadata) if metadata else {},
                timestamp=now,
                seq=self._seq,
            )
            self._entries[entry_id] = entry

            # update indexes
            self._agent_index.setdefault(agent_id, []).append(entry_id)
            self._action_index.setdefault(action, []).append(entry_id)
            if resource:
                self._resource_index.setdefault(resource, []).append(entry_id)

            self._stats["total_recorded"] += 1

        logger.debug(
            "agent_audit_store.record entry_id=%s agent_id=%s action=%s resource=%s",
            entry_id,
            agent_id,
            action,
            resource,
        )
        self._fire("entry_recorded", {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "action": action,
            "resource": resource,
        })
        return entry_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Return a single audit entry as a dict, or ``None``."""
        with self._lock:
            e = self._entries.get(entry_id)
            if e is None:
                return None
            return self._to_dict(e)

    def get_agent_audit(
        self,
        agent_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return audit trail for *agent_id*, most recent first."""
        with self._lock:
            self._stats["total_queries"] += 1
            ids = self._agent_index.get(agent_id, [])
            entries = [self._entries[eid] for eid in ids if eid in self._entries]
            entries.sort(key=lambda e: e.seq, reverse=True)
            return [self._to_dict(e) for e in entries[:limit]]

    def search_audit(
        self,
        action: Optional[str] = None,
        agent_id: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search audit entries with optional filters.

        All supplied filters are AND-ed together.  Results are returned
        newest-first.
        """
        with self._lock:
            self._stats["total_queries"] += 1

            candidates: Optional[set] = None

            if agent_id is not None:
                ids = set(self._agent_index.get(agent_id, []))
                candidates = ids

            if action is not None:
                ids = set(self._action_index.get(action, []))
                candidates = ids if candidates is None else candidates & ids

            if resource is not None:
                ids = set(self._resource_index.get(resource, []))
                candidates = ids if candidates is None else candidates & ids

            if candidates is None:
                pool = list(self._entries.values())
            else:
                pool = [
                    self._entries[eid]
                    for eid in candidates
                    if eid in self._entries
                ]

            pool.sort(key=lambda e: e.seq, reverse=True)
            return [self._to_dict(e) for e in pool]

    # ------------------------------------------------------------------
    # Counting / Summaries
    # ------------------------------------------------------------------

    def get_audit_count(self, agent_id: Optional[str] = None) -> int:
        """Count entries, optionally filtered to a single agent."""
        with self._lock:
            if agent_id is None:
                return len(self._entries)
            ids = self._agent_index.get(agent_id, [])
            return sum(1 for eid in ids if eid in self._entries)

    def get_actions_summary(self, agent_id: str) -> Dict[str, int]:
        """Return a mapping of ``{action: count}`` for *agent_id*."""
        with self._lock:
            ids = self._agent_index.get(agent_id, [])
            entries = [self._entries[eid] for eid in ids if eid in self._entries]
            summary: Dict[str, int] = {}
            for e in entries:
                summary[e.action] = summary.get(e.action, 0) + 1
            return summary

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one entry."""
        with self._lock:
            return [
                aid
                for aid, ids in self._agent_index.items()
                if any(eid in self._entries for eid in ids)
            ]

    # ------------------------------------------------------------------
    # Purging
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove entries older than *before_timestamp*.

        If *before_timestamp* is ``None`` every entry is removed.
        Returns the number of entries purged.
        """
        with self._lock:
            to_remove: List[str] = []
            for eid, e in self._entries.items():
                if before_timestamp is None:
                    to_remove.append(eid)
                elif e.timestamp < before_timestamp:
                    to_remove.append(eid)

            for eid in to_remove:
                self._remove_entry(eid)

            self._stats["total_purged"] += len(to_remove)

        if to_remove:
            logger.debug("agent_audit_store.purge count=%d", len(to_remove))
            self._fire("entries_purged", {"count": len(to_remove)})

        return len(to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns ``False`` if *name* is taken."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_entries": len(self._entries),
                "unique_agents": len([
                    a for a, ids in self._agent_index.items()
                    if any(eid in self._entries for eid in ids)
                ]),
                "unique_actions": len([
                    a for a, ids in self._action_index.items()
                    if any(eid in self._entries for eid in ids)
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._entries.clear()
            self._agent_index.clear()
            self._action_index.clear()
            self._resource_index.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_audit_store.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, e: _AuditEntry) -> Dict[str, Any]:
        """Convert an audit entry to a plain dict."""
        return {
            "entry_id": e.entry_id,
            "agent_id": e.agent_id,
            "action": e.action,
            "resource": e.resource,
            "details": e.details,
            "metadata": dict(e.metadata),
            "timestamp": e.timestamp,
            "seq": e.seq,
        }

    def _remove_entry(self, entry_id: str) -> None:
        """Remove a single entry from the store and all indexes."""
        e = self._entries.pop(entry_id, None)
        if e is None:
            return

        # clean agent index
        ids = self._agent_index.get(e.agent_id)
        if ids:
            try:
                ids.remove(entry_id)
            except ValueError:
                pass

        # clean action index
        ids = self._action_index.get(e.action)
        if ids:
            try:
                ids.remove(entry_id)
            except ValueError:
                pass

        # clean resource index
        if e.resource:
            ids = self._resource_index.get(e.resource)
            if ids:
                try:
                    ids.remove(entry_id)
                except ValueError:
                    pass

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(self._entries.values(), key=lambda e: e.seq)
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            self._remove_entry(e.entry_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_audit_store.prune removed=%d", to_remove)
