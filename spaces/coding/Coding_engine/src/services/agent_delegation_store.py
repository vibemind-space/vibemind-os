"""Agent Delegation Store -- manages task delegation between agents.

Tracks who delegated what to whom, delegation status lifecycle
(pending -> accepted -> completed, or pending -> rejected/cancelled),
priority, metadata, and optional result payloads.

Usage::

    store = AgentDelegationStore()

    # Delegate a task
    did = store.delegate("planner", "coder", "Implement auth module")
    store.accept(did)
    store.complete(did, result={"files": ["auth.py"]})

    # Query
    pending = store.get_pending_for("coder")
    stats   = store.get_stats()
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
class DelegationRecord:
    """A single delegation between two agents."""

    delegation_id: str
    from_agent: str
    to_agent: str
    task_description: str
    priority: str
    status: str  # pending | accepted | rejected | completed | cancelled
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    reject_reason: str = ""
    seq: int = 0


# ======================================================================
# Store
# ======================================================================

class AgentDelegationStore:
    """Manages task delegation between agents with full lifecycle tracking.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # primary storage
        self._records: Dict[str, DelegationRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_delegations: int = 0
        self._total_accepts: int = 0
        self._total_rejects: int = 0
        self._total_completes: int = 0
        self._total_cancels: int = 0
        self._total_lookups: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_delegation_store.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, from_agent: str, to_agent: str, desc: str) -> str:
        """Generate a unique delegation ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{from_agent}:{to_agent}:{desc}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ads-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is reached.

        Prefers removing terminal records (completed / rejected / cancelled)
        first, falling back to the oldest overall entries if necessary.
        """
        if len(self._records) < self._max_entries:
            return

        terminal = [
            (rid, rec)
            for rid, rec in self._records.items()
            if rec.status in ("completed", "rejected", "cancelled")
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
            "agent_delegation_store.pruned removed=%d remaining=%d",
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
        logger.debug("agent_delegation_store.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("agent_delegation_store.callback_removed name=%s", name)
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
                    "agent_delegation_store.callback_error callback=%s action=%s",
                    cb_name,
                    action,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, rec: DelegationRecord) -> Dict[str, Any]:
        """Convert a DelegationRecord to a plain dict for external use."""
        return {
            "delegation_id": rec.delegation_id,
            "from_agent": rec.from_agent,
            "to_agent": rec.to_agent,
            "task_description": rec.task_description,
            "priority": rec.priority,
            "status": rec.status,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
            "metadata": dict(rec.metadata),
            "result": rec.result,
            "reject_reason": rec.reject_reason,
        }

    # ------------------------------------------------------------------
    # Core API -- delegation lifecycle
    # ------------------------------------------------------------------

    def delegate(
        self,
        from_agent: str,
        to_agent: str,
        task_description: str,
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new delegation from one agent to another.

        Parameters
        ----------
        from_agent:
            The agent issuing the delegation.
        to_agent:
            The agent expected to carry out the task.
        task_description:
            A human-readable description of the delegated task.
        priority:
            Priority level (e.g. ``"low"``, ``"normal"``, ``"high"``).
        metadata:
            Arbitrary key-value pairs attached to the delegation.

        Returns
        -------
        str
            The generated delegation ID (prefix ``"ads-"``), or an empty
            string if required arguments are missing.
        """
        if not from_agent or not to_agent or not task_description:
            logger.warning(
                "agent_delegation_store.delegate.invalid_args "
                "from_agent=%s to_agent=%s task_description=%s",
                from_agent,
                to_agent,
                task_description,
            )
            return ""

        with self._lock:
            self._prune_if_needed()

            now = time.time()
            delegation_id = self._gen_id(from_agent, to_agent, task_description)

            rec = DelegationRecord(
                delegation_id=delegation_id,
                from_agent=from_agent,
                to_agent=to_agent,
                task_description=task_description,
                priority=priority,
                status="pending",
                created_at=now,
                updated_at=now,
                metadata=dict(metadata) if metadata else {},
                seq=self._seq,
            )
            self._records[delegation_id] = rec
            self._total_delegations += 1

            detail = self._to_dict(rec)

        logger.debug(
            "agent_delegation_store.delegation_created id=%s from=%s to=%s",
            delegation_id,
            from_agent,
            to_agent,
        )
        self._fire("delegation_created", detail)
        return delegation_id

    def accept(self, delegation_id: str) -> bool:
        """Mark a pending delegation as accepted.

        Returns ``False`` if the delegation is not found or is not in
        ``"pending"`` status.
        """
        if not delegation_id:
            return False

        with self._lock:
            rec = self._records.get(delegation_id)
            if rec is None:
                logger.debug(
                    "agent_delegation_store.accept.not_found id=%s",
                    delegation_id,
                )
                return False

            if rec.status != "pending":
                logger.debug(
                    "agent_delegation_store.accept.wrong_status id=%s status=%s",
                    delegation_id,
                    rec.status,
                )
                return False

            rec.status = "accepted"
            rec.updated_at = time.time()
            self._total_accepts += 1
            detail = self._to_dict(rec)

        logger.debug(
            "agent_delegation_store.delegation_accepted id=%s", delegation_id,
        )
        self._fire("delegation_accepted", detail)
        return True

    def reject(self, delegation_id: str, reason: str = "") -> bool:
        """Reject a pending delegation with an optional reason.

        Returns ``False`` if the delegation is not found or is not in
        ``"pending"`` status.
        """
        if not delegation_id:
            return False

        with self._lock:
            rec = self._records.get(delegation_id)
            if rec is None:
                logger.debug(
                    "agent_delegation_store.reject.not_found id=%s",
                    delegation_id,
                )
                return False

            if rec.status != "pending":
                logger.debug(
                    "agent_delegation_store.reject.wrong_status id=%s status=%s",
                    delegation_id,
                    rec.status,
                )
                return False

            rec.status = "rejected"
            rec.reject_reason = reason
            rec.updated_at = time.time()
            self._total_rejects += 1
            detail = self._to_dict(rec)

        logger.debug(
            "agent_delegation_store.delegation_rejected id=%s reason=%s",
            delegation_id,
            reason,
        )
        self._fire("delegation_rejected", detail)
        return True

    def complete(self, delegation_id: str, result: Any = None) -> bool:
        """Mark an accepted delegation as completed with an optional result.

        Returns ``False`` if the delegation is not found or is not in
        ``"accepted"`` status.
        """
        if not delegation_id:
            return False

        with self._lock:
            rec = self._records.get(delegation_id)
            if rec is None:
                logger.debug(
                    "agent_delegation_store.complete.not_found id=%s",
                    delegation_id,
                )
                return False

            if rec.status != "accepted":
                logger.debug(
                    "agent_delegation_store.complete.wrong_status id=%s status=%s",
                    delegation_id,
                    rec.status,
                )
                return False

            rec.status = "completed"
            rec.result = result
            rec.updated_at = time.time()
            self._total_completes += 1
            detail = self._to_dict(rec)

        logger.debug(
            "agent_delegation_store.delegation_completed id=%s", delegation_id,
        )
        self._fire("delegation_completed", detail)
        return True

    def cancel(self, delegation_id: str) -> bool:
        """Cancel a delegation that is pending or accepted.

        Returns ``False`` if the delegation is not found or is already in
        a terminal state (``"completed"``, ``"rejected"``, ``"cancelled"``).
        """
        if not delegation_id:
            return False

        with self._lock:
            rec = self._records.get(delegation_id)
            if rec is None:
                logger.debug(
                    "agent_delegation_store.cancel.not_found id=%s",
                    delegation_id,
                )
                return False

            if rec.status not in ("pending", "accepted"):
                logger.debug(
                    "agent_delegation_store.cancel.wrong_status id=%s status=%s",
                    delegation_id,
                    rec.status,
                )
                return False

            rec.status = "cancelled"
            rec.updated_at = time.time()
            self._total_cancels += 1
            detail = self._to_dict(rec)

        logger.debug(
            "agent_delegation_store.delegation_cancelled id=%s", delegation_id,
        )
        self._fire("delegation_cancelled", detail)
        return True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_delegation(self, delegation_id: str) -> Optional[Dict[str, Any]]:
        """Return a delegation record as a dict, or ``None`` if not found."""
        with self._lock:
            self._total_lookups += 1
            rec = self._records.get(delegation_id)
            if rec is None:
                return None
            return self._to_dict(rec)

    def get_delegations_from(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all delegations originating FROM the given agent."""
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            return [
                self._to_dict(rec)
                for rec in self._records.values()
                if rec.from_agent == agent_id
            ]

    def get_delegations_to(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all delegations targeting TO the given agent."""
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            return [
                self._to_dict(rec)
                for rec in self._records.values()
                if rec.to_agent == agent_id
            ]

    def get_pending_for(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return pending delegations assigned to *agent_id*."""
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            return [
                self._to_dict(rec)
                for rec in self._records.values()
                if rec.to_agent == agent_id and rec.status == "pending"
            ]

    def list_delegations(
        self, status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all delegations, optionally filtered by status.

        Parameters
        ----------
        status:
            If provided, only return delegations matching this status
            (e.g. ``"pending"``, ``"accepted"``, ``"completed"``).

        Returns
        -------
        list[dict]
            List of delegation dicts sorted by creation time (newest first).
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
            unique_from: set[str] = set()
            unique_to: set[str] = set()
            priority_counts: Dict[str, int] = {}

            for rec in self._records.values():
                status_counts[rec.status] = status_counts.get(rec.status, 0) + 1
                unique_from.add(rec.from_agent)
                unique_to.add(rec.to_agent)
                priority_counts[rec.priority] = (
                    priority_counts.get(rec.priority, 0) + 1
                )

            return {
                "current_entries": len(self._records),
                "max_entries": self._max_entries,
                "status_counts": status_counts,
                "priority_counts": priority_counts,
                "unique_from_agents": len(unique_from),
                "unique_to_agents": len(unique_to),
                "total_delegations": self._total_delegations,
                "total_accepts": self._total_accepts,
                "total_rejects": self._total_rejects,
                "total_completes": self._total_completes,
                "total_cancels": self._total_cancels,
                "total_lookups": self._total_lookups,
                "total_evictions": self._total_evictions,
                "registered_callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all delegation records, callbacks, and counters."""
        with self._lock:
            self._records.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_delegations = 0
            self._total_accepts = 0
            self._total_rejects = 0
            self._total_completes = 0
            self._total_cancels = 0
            self._total_lookups = 0
            self._total_evictions = 0

        logger.debug("agent_delegation_store.reset")
