"""Agent Collaboration Store -- tracks agent collaborations.

Records which agents work together on tasks, manages collaboration
lifecycle (active -> completed | cancelled), and provides queries
for finding collaborators and filtering by agent or status.

Usage::

    store = AgentCollaborationStore()

    # Start a collaboration
    cid = store.start_collaboration(["planner", "coder"], "Implement auth")
    store.end_collaboration(cid, result={"files": ["auth.py"]})

    # Query
    active = store.get_active_collaborations()
    partners = store.find_collaborators("planner")
    stats = store.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class CollaborationRecord:
    """A single collaboration between multiple agents."""

    collab_id: str
    agent_ids: List[str]
    task: str
    status: str  # active | completed | cancelled
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    seq: int = 0


# ======================================================================
# Store
# ======================================================================

class AgentCollaborationStore:
    """Tracks agent collaborations with full lifecycle management.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # primary storage
        self._records: Dict[str, CollaborationRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_started: int = 0
        self._total_ended: int = 0
        self._total_cancelled: int = 0
        self._total_lookups: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_collaboration_store.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, agent_ids: List[str], task: str) -> str:
        """Generate a unique collaboration ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{':'.join(agent_ids)}:{task}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"aco-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is reached.

        Prefers removing terminal records (completed / cancelled)
        first, falling back to the oldest overall entries if necessary.
        """
        if len(self._records) < self._max_entries:
            return

        terminal = [
            (rid, rec)
            for rid, rec in self._records.items()
            if rec.status in ("completed", "cancelled")
        ]
        terminal.sort(key=lambda pair: pair[1].seq)

        to_remove = max(1, len(self._records) - self._max_entries + 1)

        if len(terminal) >= to_remove:
            victims = terminal[:to_remove]
        else:
            all_sorted = sorted(
                self._records.items(), key=lambda pair: pair[1].seq,
            )
            victims = all_sorted[:to_remove]

        for rid, _rec in victims:
            del self._records[rid]
            self._total_evictions += 1

        logger.debug(
            "agent_collaboration_store.pruned removed=%d remaining=%d",
            len(victims),
            len(self._records),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback.

        If *name* already exists the callback is silently replaced.
        """
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("agent_collaboration_store.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("agent_collaboration_store.callback_removed name=%s", name)
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *detail*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break store operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception(
                    "agent_collaboration_store.callback_error callback=%s action=%s",
                    cb_name,
                    action,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, rec: CollaborationRecord) -> Dict[str, Any]:
        """Convert a CollaborationRecord to a plain dict for external use."""
        return {
            "collab_id": rec.collab_id,
            "agent_ids": list(rec.agent_ids),
            "task": rec.task,
            "status": rec.status,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
            "metadata": dict(rec.metadata),
            "result": rec.result,
        }

    # ------------------------------------------------------------------
    # Core API -- collaboration lifecycle
    # ------------------------------------------------------------------

    def start_collaboration(
        self,
        agent_ids: List[str],
        task: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new collaboration between agents.

        Parameters
        ----------
        agent_ids:
            List of agent identifiers participating in the collaboration.
        task:
            A human-readable description of the collaborative task.
        metadata:
            Arbitrary key-value pairs attached to the collaboration.

        Returns
        -------
        str
            The generated collaboration ID (prefix ``"aco-"``), or an empty
            string if required arguments are missing.
        """
        if not agent_ids or not task:
            logger.warning(
                "agent_collaboration_store.start.invalid_args "
                "agent_ids=%s task=%s",
                agent_ids,
                task,
            )
            return ""

        with self._lock:
            self._prune_if_needed()

            now = time.time()
            collab_id = self._gen_id(agent_ids, task)

            rec = CollaborationRecord(
                collab_id=collab_id,
                agent_ids=list(agent_ids),
                task=task,
                status="active",
                created_at=now,
                updated_at=now,
                metadata=dict(metadata) if metadata else {},
                seq=self._seq,
            )
            self._records[collab_id] = rec
            self._total_started += 1

            detail = self._to_dict(rec)

        logger.debug(
            "agent_collaboration_store.collaboration_started id=%s agents=%s",
            collab_id,
            agent_ids,
        )
        self._fire("collaboration_started", detail)
        return collab_id

    def end_collaboration(self, collab_id: str, result: Any = None) -> bool:
        """End an active collaboration, marking it as completed.

        Returns ``False`` if the collaboration is not found or is not in
        ``"active"`` status.
        """
        if not collab_id:
            return False

        with self._lock:
            rec = self._records.get(collab_id)
            if rec is None:
                logger.debug(
                    "agent_collaboration_store.end.not_found id=%s",
                    collab_id,
                )
                return False

            if rec.status != "active":
                logger.debug(
                    "agent_collaboration_store.end.wrong_status id=%s status=%s",
                    collab_id,
                    rec.status,
                )
                return False

            rec.status = "completed"
            rec.result = result
            rec.updated_at = time.time()
            self._total_ended += 1
            detail = self._to_dict(rec)

        logger.debug(
            "agent_collaboration_store.collaboration_ended id=%s", collab_id,
        )
        self._fire("collaboration_ended", detail)
        return True

    def cancel_collaboration(self, collab_id: str) -> bool:
        """Cancel an active collaboration.

        Returns ``False`` if the collaboration is not found or is not in
        ``"active"`` status.
        """
        if not collab_id:
            return False

        with self._lock:
            rec = self._records.get(collab_id)
            if rec is None:
                logger.debug(
                    "agent_collaboration_store.cancel.not_found id=%s",
                    collab_id,
                )
                return False

            if rec.status != "active":
                logger.debug(
                    "agent_collaboration_store.cancel.wrong_status id=%s status=%s",
                    collab_id,
                    rec.status,
                )
                return False

            rec.status = "cancelled"
            rec.updated_at = time.time()
            self._total_cancelled += 1
            detail = self._to_dict(rec)

        logger.debug(
            "agent_collaboration_store.collaboration_cancelled id=%s", collab_id,
        )
        self._fire("collaboration_cancelled", detail)
        return True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_collaboration(self, collab_id: str) -> Optional[Dict[str, Any]]:
        """Return a collaboration record as a dict, or ``None`` if not found."""
        with self._lock:
            self._total_lookups += 1
            rec = self._records.get(collab_id)
            if rec is None:
                return None
            return self._to_dict(rec)

    def get_agent_collaborations(
        self, agent_id: str, status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all collaborations involving the given agent.

        Parameters
        ----------
        agent_id:
            The agent to look up.
        status:
            If provided, only return collaborations matching this status.
        """
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            return [
                self._to_dict(rec)
                for rec in self._records.values()
                if agent_id in rec.agent_ids
                and (status is None or rec.status == status)
            ]

    def get_active_collaborations(self) -> List[Dict[str, Any]]:
        """Return all active collaborations."""
        with self._lock:
            self._total_lookups += 1
            return [
                self._to_dict(rec)
                for rec in self._records.values()
                if rec.status == "active"
            ]

    def get_collaboration_count(self, agent_id: Optional[str] = None) -> int:
        """Count collaborations, optionally filtered by agent.

        Parameters
        ----------
        agent_id:
            If provided, only count collaborations involving this agent.
        """
        with self._lock:
            self._total_lookups += 1
            if agent_id is None:
                return len(self._records)
            return sum(
                1 for rec in self._records.values()
                if agent_id in rec.agent_ids
            )

    def find_collaborators(self, agent_id: str) -> List[str]:
        """Find all agents who have collaborated with the given agent.

        Returns a deduplicated list of agent IDs (excluding the queried
        agent itself).
        """
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            collaborators: set[str] = set()
            for rec in self._records.values():
                if agent_id in rec.agent_ids:
                    for aid in rec.agent_ids:
                        if aid != agent_id:
                            collaborators.add(aid)
            return sorted(collaborators)

    def list_collaborations(
        self, status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all collaborations, optionally filtered by status.

        Parameters
        ----------
        status:
            If provided, only return collaborations matching this status
            (e.g. ``"active"``, ``"completed"``, ``"cancelled"``).

        Returns
        -------
        list[dict]
            List of collaboration dicts sorted by creation time (newest first).
        """
        with self._lock:
            self._total_lookups += 1
            results = [
                self._to_dict(rec)
                for rec in self._records.values()
                if status is None or rec.status == status
            ]
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics about the store."""
        with self._lock:
            status_counts: Dict[str, int] = {}
            unique_agents: set[str] = set()

            for rec in self._records.values():
                status_counts[rec.status] = status_counts.get(rec.status, 0) + 1
                for aid in rec.agent_ids:
                    unique_agents.add(aid)

            return {
                "current_entries": len(self._records),
                "max_entries": self._max_entries,
                "status_counts": status_counts,
                "unique_agents": len(unique_agents),
                "total_started": self._total_started,
                "total_ended": self._total_ended,
                "total_cancelled": self._total_cancelled,
                "total_lookups": self._total_lookups,
                "total_evictions": self._total_evictions,
                "registered_callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all collaboration records, callbacks, and counters."""
        with self._lock:
            self._records.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_started = 0
            self._total_ended = 0
            self._total_cancelled = 0
            self._total_lookups = 0
            self._total_evictions = 0

        logger.debug("agent_collaboration_store.reset")
