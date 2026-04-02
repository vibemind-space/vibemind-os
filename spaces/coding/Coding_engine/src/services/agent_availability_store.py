"""Agent Availability Store -- tracks agent availability status.

Monitors whether agents are available, busy, or offline within the
emergent pipeline system. Supports capacity tracking, status history,
callbacks on availability changes, and thread-safe access.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


VALID_STATUSES = ("available", "busy", "offline")


@dataclass
class AvailabilityRecord:
    record_id: str
    agent_id: str
    status: str
    reason: str
    metadata: Optional[Dict[str, Any]]
    created_at: float
    updated_at: float
    seq: int


@dataclass
class CapacityRecord:
    agent_id: str
    max_tasks: int
    updated_at: float


@dataclass
class HistoryEntry:
    record_id: str
    agent_id: str
    status: str
    reason: str
    timestamp: float


class AgentAvailabilityStore:
    """Tracks agent availability, capacity, and status history."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, AvailabilityRecord] = {}
        self._agent_index: Dict[str, str] = {}  # agent_id -> record_id
        self._history: Dict[str, List[HistoryEntry]] = {}
        self._capacities: Dict[str, CapacityRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_sets = 0
        self._total_gets = 0
        self._total_capacity_sets = 0
        self._total_history_queries = 0
        self._total_evictions = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"aav-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"aav-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already registered."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name. Returns False if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        with self._lock:
            callbacks = list(self._callbacks.values())
        for cb in callbacks:
            try:
                cb(action, detail)
            except Exception:
                logger.debug("callback_error", exc_info=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Prune oldest entries when max_entries is exceeded. Caller must hold lock."""
        if len(self._entries) < self._max_entries:
            return

        sorted_ids = sorted(
            self._entries.keys(),
            key=lambda eid: self._entries[eid].seq,
        )
        to_remove = len(self._entries) - self._max_entries + 1
        for eid in sorted_ids[:to_remove]:
            entry = self._entries[eid]
            self._agent_index.pop(entry.agent_id, None)
            del self._entries[eid]
            self._total_evictions += 1
            logger.debug(
                "availability_evicted record_id=%s agent_id=%s",
                eid, entry.agent_id,
            )

    def _add_history(self, agent_id: str, record_id: str, status: str, reason: str) -> None:
        """Append a history entry for an agent. Caller must hold lock."""
        if agent_id not in self._history:
            self._history[agent_id] = []
        self._history[agent_id].append(HistoryEntry(
            record_id=record_id,
            agent_id=agent_id,
            status=status,
            reason=reason,
            timestamp=time.time(),
        ))

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set_availability(
        self,
        agent_id: str,
        status: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Set availability status for an agent. Returns record_id.

        Status must be one of: available, busy, offline.
        Returns empty string on invalid input.
        """
        if not agent_id or status not in VALID_STATUSES:
            logger.warning(
                "set_availability_invalid agent_id=%s status=%s",
                agent_id, status,
            )
            return ""

        now = time.time()

        with self._lock:
            existing_rid = self._agent_index.get(agent_id)
            if existing_rid and existing_rid in self._entries:
                entry = self._entries[existing_rid]
                old_status = entry.status
                entry.status = status
                entry.reason = reason
                entry.updated_at = now
                if metadata is not None:
                    entry.metadata = metadata
                self._seq += 1
                entry.seq = self._seq
                self._total_sets += 1
                record_id = existing_rid
                self._add_history(agent_id, record_id, status, reason)
            else:
                self._prune_if_needed()
                record_id = self._gen_id(agent_id)
                old_status = None
                entry = AvailabilityRecord(
                    record_id=record_id,
                    agent_id=agent_id,
                    status=status,
                    reason=reason,
                    metadata=metadata,
                    created_at=now,
                    updated_at=now,
                    seq=self._seq,
                )
                self._entries[record_id] = entry
                self._agent_index[agent_id] = record_id
                self._total_sets += 1
                self._add_history(agent_id, record_id, status, reason)

        logger.debug(
            "availability_set agent_id=%s status=%s record_id=%s",
            agent_id, status, record_id,
        )
        self._fire("availability_set", {
            "record_id": record_id,
            "agent_id": agent_id,
            "status": status,
            "old_status": old_status,
            "reason": reason,
            "metadata": metadata,
        })
        return record_id

    def get_availability(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get current availability for an agent. Returns None if not found."""
        if not agent_id:
            return None

        with self._lock:
            self._total_gets += 1
            rid = self._agent_index.get(agent_id)
            if not rid or rid not in self._entries:
                return None
            entry = self._entries[rid]
            return {
                "record_id": entry.record_id,
                "agent_id": entry.agent_id,
                "status": entry.status,
                "reason": entry.reason,
                "metadata": dict(entry.metadata) if entry.metadata else {},
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            }

    def is_available(self, agent_id: str) -> bool:
        """Check if an agent is available. Returns False if not found or not available."""
        with self._lock:
            rid = self._agent_index.get(agent_id)
            if not rid or rid not in self._entries:
                return False
            return self._entries[rid].status == "available"

    def get_available_agents(self) -> List[str]:
        """Get all agent IDs with status 'available'."""
        with self._lock:
            return [
                entry.agent_id
                for entry in self._entries.values()
                if entry.status == "available"
            ]

    def get_agents_by_status(self, status: str) -> List[str]:
        """Get all agent IDs with the given status."""
        with self._lock:
            return [
                entry.agent_id
                for entry in self._entries.values()
                if entry.status == status
            ]

    def get_availability_history(
        self,
        agent_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get history of status changes for an agent."""
        if not agent_id:
            return []

        with self._lock:
            self._total_history_queries += 1
            history = self._history.get(agent_id, [])
            selected = history[-limit:] if limit > 0 else history
            return [
                {
                    "record_id": h.record_id,
                    "agent_id": h.agent_id,
                    "status": h.status,
                    "reason": h.reason,
                    "timestamp": h.timestamp,
                }
                for h in selected
            ]

    # ------------------------------------------------------------------
    # Capacity management
    # ------------------------------------------------------------------

    def set_capacity(self, agent_id: str, max_tasks: int) -> bool:
        """Set max task capacity for an agent. Creates entry if needed. Returns True."""
        if not agent_id:
            return False

        now = time.time()
        with self._lock:
            self._total_capacity_sets += 1
            self._capacities[agent_id] = CapacityRecord(
                agent_id=agent_id,
                max_tasks=max_tasks,
                updated_at=now,
            )

            # Create availability entry if agent not tracked yet
            if agent_id not in self._agent_index:
                self._prune_if_needed()
                record_id = self._gen_id(agent_id)
                entry = AvailabilityRecord(
                    record_id=record_id,
                    agent_id=agent_id,
                    status="offline",
                    reason="capacity_set",
                    metadata=None,
                    created_at=now,
                    updated_at=now,
                    seq=self._seq,
                )
                self._entries[record_id] = entry
                self._agent_index[agent_id] = record_id

        logger.debug(
            "capacity_set agent_id=%s max_tasks=%d", agent_id, max_tasks,
        )
        self._fire("capacity_set", {
            "agent_id": agent_id,
            "max_tasks": max_tasks,
        })
        return True

    def get_capacity(self, agent_id: str) -> int:
        """Get max task capacity for an agent. Returns 0 if not set."""
        with self._lock:
            cap = self._capacities.get(agent_id)
            return cap.max_tasks if cap else 0

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """List all tracked agent IDs."""
        with self._lock:
            return sorted({entry.agent_id for entry in self._entries.values()})

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return store statistics."""
        with self._lock:
            available = sum(
                1 for e in self._entries.values() if e.status == "available"
            )
            busy = sum(
                1 for e in self._entries.values() if e.status == "busy"
            )
            offline = sum(
                1 for e in self._entries.values() if e.status == "offline"
            )
            return {
                "current_entries": len(self._entries),
                "available_agents": available,
                "busy_agents": busy,
                "offline_agents": offline,
                "max_entries": self._max_entries,
                "total_sets": self._total_sets,
                "total_gets": self._total_gets,
                "total_capacity_sets": self._total_capacity_sets,
                "total_history_queries": self._total_history_queries,
                "total_evictions": self._total_evictions,
                "callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state and counters."""
        with self._lock:
            self._entries.clear()
            self._agent_index.clear()
            self._history.clear()
            self._capacities.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_sets = 0
            self._total_gets = 0
            self._total_capacity_sets = 0
            self._total_history_queries = 0
            self._total_evictions = 0
        logger.debug("agent_availability_store_reset")
