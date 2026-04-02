"""Agent Audit Trail -- tracks agent actions for auditing purposes.

Records what agents did, when, and with what parameters. Provides a
central, in-memory audit trail with rich querying, automatic pruning,
and change-notification callbacks.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# State dataclass
# ------------------------------------------------------------------

@dataclass
class AgentAuditTrailState:
    """Holds the mutable state for the audit trail."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentAuditTrail:
    """In-memory audit trail for agent actions.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When the limit is reached the
        oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = AgentAuditTrailState()
        self._callbacks: Dict[str, Callable] = {}

        # stats counters
        self._stats: Dict[str, int] = {
            "total_recorded": 0,
            "total_pruned": 0,
            "total_queries": 0,
        }

        logger.debug("agent_audit_trail.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, agent_id: str, action: str) -> str:
        self._state._seq += 1
        raw = f"{agent_id}-{action}-{time.time()}-{self._state._seq}"
        return "aat-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        action: str,
        resource: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record an audit entry and return its entry ID (``aat-xxx``).

        Returns an empty string when *agent_id* or *action* is falsy.
        """
        if not agent_id or not action:
            return ""

        with self._lock:
            # prune if at capacity
            if len(self._state.entries) >= self._max_entries:
                self._prune()

            entry_id = self._next_id(agent_id, action)
            entry = {
                "entry_id": entry_id,
                "agent_id": agent_id,
                "action": action,
                "resource": resource,
                "details": dict(details) if details else {},
                "timestamp": time.time(),
                "_seq_num": self._state._seq,
            }
            self._state.entries[entry_id] = entry
            self._stats["total_recorded"] += 1

        logger.debug(
            "agent_audit_trail.record",
            entry_id=entry_id,
            agent_id=agent_id,
            action=action,
            resource=resource,
        )
        self._fire("entry_recorded", {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "action": action,
        })
        return entry_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_entries(self, agent_id: str, action: str = "") -> List[Dict[str, Any]]:
        """Get entries for *agent_id*, optionally filtered by *action*.

        Returns entries sorted newest-first.
        """
        with self._lock:
            self._stats["total_queries"] += 1
            result = [
                dict(e)
                for e in self._state.entries.values()
                if e["agent_id"] == agent_id
                and (not action or e["action"] == action)
            ]
            result.sort(key=lambda e: e["_seq_num"], reverse=True)
            return result

    def get_latest_entry(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent entry for *agent_id*.

        Uses ``_seq_num`` for deterministic tie-breaking.
        Returns ``None`` if no entries exist for the agent.
        """
        with self._lock:
            candidates = [
                e for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            ]
            if not candidates:
                return None
            best = max(candidates, key=lambda e: e["_seq_num"])
            return dict(best)

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_entry_count(self, agent_id: str = "") -> int:
        """Count entries, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return len(self._state.entries)
            return sum(
                1 for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            )

    # ------------------------------------------------------------------
    # Clearing
    # ------------------------------------------------------------------

    def clear_entries(self, agent_id: str) -> int:
        """Clear entries for *agent_id*. Returns the number removed."""
        with self._lock:
            to_remove = [
                eid for eid, e in self._state.entries.items()
                if e["agent_id"] == agent_id
            ]
            for eid in to_remove:
                del self._state.entries[eid]
        count = len(to_remove)
        if count:
            self._fire("entries_cleared", {"agent_id": agent_id, "count": count})
        return count

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one entry."""
        with self._lock:
            seen: Dict[str, bool] = {}
            for e in self._state.entries.values():
                seen[e["agent_id"]] = True
            return list(seen.keys())

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, action: str = "", resource: str = "") -> List[Dict[str, Any]]:
        """Search entries by *action* and/or *resource* across all agents.

        Returns matching entries sorted newest-first.
        """
        with self._lock:
            self._stats["total_queries"] += 1
            result = []
            for e in self._state.entries.values():
                if action and e["action"] != action:
                    continue
                if resource and e["resource"] != resource:
                    continue
                result.append(dict(e))
            result.sort(key=lambda e: e["_seq_num"], reverse=True)
            return result

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback under *name*."""
        with self._lock:
            self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name. Returns ``True`` if removed, ``False`` otherwise."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail_dict: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail_dict)
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
                "current_entries": len(self._state.entries),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.entries.clear()
            self._state._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_audit_trail.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(self._state.entries.values(), key=lambda e: e["_seq_num"])
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            del self._state.entries[e["entry_id"]]
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_audit_trail.prune", removed=to_remove)
