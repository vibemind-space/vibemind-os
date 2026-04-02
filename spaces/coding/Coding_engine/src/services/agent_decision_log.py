"""Agent Decision Log -- records and queries agent decision entries.

Provides a central, in-memory log for agent decisions. Every logged
decision captures the agent, decision type, chosen option, alternatives
considered, reasoning, and arbitrary metadata. The log supports rich
filtering, per-agent queries, and automatic pruning when the entry limit
is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _DecisionRecord:
    """A single recorded decision entry."""

    decision_id: str = ""
    agent_id: str = ""
    decision_type: str = ""
    choice: str = ""
    alternatives: List[str] = field(default_factory=list)
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentDecisionLog:
    """In-memory decision log for agent choices.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When the limit is reached the
        oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, _DecisionRecord] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}

        # indexes for fast lookup
        self._agent_index: Dict[str, List[str]] = {}          # agent_id       -> [decision_id]
        self._type_index: Dict[str, List[str]] = {}           # decision_type  -> [decision_id]

        # stats counters
        self._stats: Dict[str, int] = {
            "total_logged": 0,
            "total_pruned": 0,
            "total_purged": 0,
            "total_queries": 0,
        }

        logger.debug("agent_decision_log.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, decision_type: str, now: float) -> str:
        """Create a collision-free decision ID using SHA-256 + _seq."""
        raw = f"{agent_id}-{decision_type}-{now}-{self._seq}"
        return "adl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Logging decisions
    # ------------------------------------------------------------------

    def log_decision(
        self,
        agent_id: str,
        decision_type: str,
        choice: str,
        alternatives: Optional[List[str]] = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log a decision and return its ``decision_id``.

        Returns the generated ``adl-...`` identifier for the new entry.
        """
        with self._lock:
            # prune if at capacity
            if len(self._entries) >= self._max_entries:
                self._prune()

            self._seq += 1
            now = time.time()
            decision_id = self._generate_id(agent_id, decision_type, now)

            record = _DecisionRecord(
                decision_id=decision_id,
                agent_id=agent_id,
                decision_type=decision_type,
                choice=choice,
                alternatives=list(alternatives) if alternatives else [],
                reason=reason,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                seq=self._seq,
            )
            self._entries[decision_id] = record

            # update indexes
            self._agent_index.setdefault(agent_id, []).append(decision_id)
            self._type_index.setdefault(decision_type, []).append(decision_id)

            self._stats["total_logged"] += 1

        logger.debug(
            "agent_decision_log.log_decision",
            decision_id=decision_id,
            agent_id=agent_id,
            decision_type=decision_type,
            choice=choice,
        )
        self._fire("decision_logged", {
            "decision_id": decision_id,
            "agent_id": agent_id,
            "decision_type": decision_type,
            "choice": choice,
        })
        return decision_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Return a single decision as a dict, or ``None``."""
        with self._lock:
            r = self._entries.get(decision_id)
            if r is None:
                return None
            return self._to_dict(r)

    def get_agent_decisions(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return decisions for *agent_id*, most recent first."""
        with self._lock:
            self._stats["total_queries"] += 1
            ids = self._agent_index.get(agent_id, [])
            records = [self._entries[did] for did in ids if did in self._entries]
            records.sort(key=lambda r: r.created_at, reverse=True)
            return [self._to_dict(r) for r in records]

    def get_decisions_by_type(self, decision_type: str) -> List[Dict[str, Any]]:
        """Return decisions matching *decision_type*, most recent first."""
        with self._lock:
            self._stats["total_queries"] += 1
            ids = self._type_index.get(decision_type, [])
            records = [self._entries[did] for did in ids if did in self._entries]
            records.sort(key=lambda r: r.created_at, reverse=True)
            return [self._to_dict(r) for r in records]

    def get_recent_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent *limit* decisions across all agents."""
        with self._lock:
            self._stats["total_queries"] += 1
            records = sorted(self._entries.values(), key=lambda r: r.created_at, reverse=True)
            return [self._to_dict(r) for r in records[:limit]]

    def search_decisions(
        self,
        agent_id: Optional[str] = None,
        decision_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Filter decisions by any combination of *agent_id* and *decision_type*.

        All supplied filters are AND-ed together.  Results are returned
        newest-first.
        """
        with self._lock:
            self._stats["total_queries"] += 1

            candidates: Optional[set] = None

            if agent_id is not None:
                ids = set(self._agent_index.get(agent_id, []))
                candidates = ids

            if decision_type is not None:
                ids = set(self._type_index.get(decision_type, []))
                candidates = ids if candidates is None else candidates & ids

            if candidates is None:
                pool = list(self._entries.values())
            else:
                pool = [
                    self._entries[did]
                    for did in candidates
                    if did in self._entries
                ]

            pool.sort(key=lambda r: r.created_at, reverse=True)
            return [self._to_dict(r) for r in pool]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_decision_count(self, agent_id: Optional[str] = None) -> int:
        """Count decisions, optionally filtered to a single agent."""
        with self._lock:
            if agent_id is None:
                return len(self._entries)
            ids = self._agent_index.get(agent_id, [])
            return sum(1 for did in ids if did in self._entries)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one decision."""
        with self._lock:
            return [
                aid
                for aid, ids in self._agent_index.items()
                if any(did in self._entries for did in ids)
            ]

    # ------------------------------------------------------------------
    # Purging
    # ------------------------------------------------------------------

    def purge(self, agent_id: str, keep_latest: int = 5) -> int:
        """Remove oldest decisions for *agent_id*, keeping the latest *keep_latest*.

        Returns the number of decisions removed.
        """
        with self._lock:
            ids = self._agent_index.get(agent_id, [])
            records = [self._entries[did] for did in ids if did in self._entries]
            records.sort(key=lambda r: r.created_at, reverse=True)

            to_remove = records[keep_latest:]
            for r in to_remove:
                self._remove_entry(r.decision_id)

            self._stats["total_purged"] += len(to_remove)

        if to_remove:
            logger.debug(
                "agent_decision_log.purge",
                agent_id=agent_id,
                removed=len(to_remove),
                kept=keep_latest,
            )
            self._fire("decisions_purged", {
                "agent_id": agent_id,
                "count": len(to_remove),
            })

        return len(to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._callbacks[name] = callback

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
                    if any(did in self._entries for did in ids)
                ]),
                "unique_types": len([
                    t for t, ids in self._type_index.items()
                    if any(did in self._entries for did in ids)
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._entries.clear()
            self._agent_index.clear()
            self._type_index.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_decision_log.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, r: _DecisionRecord) -> Dict[str, Any]:
        """Convert a decision record to a plain dict."""
        return {
            "decision_id": r.decision_id,
            "agent_id": r.agent_id,
            "decision_type": r.decision_type,
            "choice": r.choice,
            "alternatives": list(r.alternatives),
            "reason": r.reason,
            "metadata": dict(r.metadata),
            "created_at": r.created_at,
        }

    def _remove_entry(self, decision_id: str) -> None:
        """Remove a single entry from the store and all indexes."""
        r = self._entries.pop(decision_id, None)
        if r is None:
            return

        # clean agent index
        ids = self._agent_index.get(r.agent_id)
        if ids:
            try:
                ids.remove(decision_id)
            except ValueError:
                pass

        # clean type index
        ids = self._type_index.get(r.decision_type)
        if ids:
            try:
                ids.remove(decision_id)
            except ValueError:
                pass

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(self._entries.values(), key=lambda r: r.seq)
        to_remove = max(len(entries) // 4, 1)
        for r in entries[:to_remove]:
            self._remove_entry(r.decision_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_decision_log.prune", removed=to_remove)
