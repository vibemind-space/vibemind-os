"""Agent Operation Log -- records agent operations with duration, status, and metadata.

Provides an in-memory log for tracking agent operations from start to
completion.  Each operation captures timing information (start/end),
status, and optional metadata.  Supports filtering, duration analytics,
and automatic pruning when the entry limit is reached.

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
# State
# ------------------------------------------------------------------

@dataclass
class AgentOperationLogState:
    """Internal mutable state for the operation log."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentOperationLog:
    """In-memory operation log for agents.

    Parameters
    ----------
    max_entries:
        Maximum number of operation entries to keep.  When the limit
        is reached the oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = AgentOperationLogState()
        self._callbacks: Dict[str, Callable] = {}

        self._stats: Dict[str, int] = {
            "total_started": 0,
            "total_ended": 0,
            "total_pruned": 0,
            "total_queries": 0,
        }

        logger.debug("agent_operation_log.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        """Create a collision-free operation ID using SHA-256 + _seq."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "aol-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def start_operation(
        self,
        agent_id: str,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start tracking an operation, returning its ``operation_id``."""
        with self._lock:
            if len(self._state.entries) >= self._max_entries:
                self._prune()

            now = time.time()
            operation_id = self._generate_id(f"{agent_id}-{operation}-{now}")

            entry: Dict[str, Any] = {
                "operation_id": operation_id,
                "agent_id": agent_id,
                "operation": operation,
                "metadata": metadata or {},
                "start_time": now,
                "end_time": None,
                "status": "running",
                "result": None,
                "duration_ms": None,
                "_seq_num": self._state._seq,
            }

            self._state.entries[operation_id] = entry
            self._stats["total_started"] += 1

        logger.debug(
            "agent_operation_log.start_operation op_id=%s agent=%s op=%s",
            operation_id, agent_id, operation,
        )
        self._fire("operation_started", {
            "operation_id": operation_id,
            "agent_id": agent_id,
            "operation": operation,
        })
        return operation_id

    def end_operation(
        self,
        operation_id: str,
        status: str = "success",
        result: Any = None,
    ) -> Dict[str, Any]:
        """Mark an operation as complete.

        Returns a summary dict with ``operation_id``, ``duration_ms``, and ``status``.
        """
        with self._lock:
            entry = self._state.entries.get(operation_id)
            if entry is None:
                return {"operation_id": operation_id, "duration_ms": 0.0, "status": status}

            now = time.time()
            duration_ms = (now - entry["start_time"]) * 1000.0
            entry["end_time"] = now
            entry["status"] = status
            entry["result"] = result
            entry["duration_ms"] = duration_ms
            self._stats["total_ended"] += 1

        logger.debug(
            "agent_operation_log.end_operation op_id=%s status=%s duration=%.2fms",
            operation_id, status, duration_ms,
        )
        self._fire("operation_ended", {
            "operation_id": operation_id,
            "status": status,
            "duration_ms": duration_ms,
        })
        return {
            "operation_id": operation_id,
            "duration_ms": duration_ms,
            "status": status,
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Return a single operation entry by ID, or ``None``."""
        with self._lock:
            self._stats["total_queries"] += 1
            entry = self._state.entries.get(operation_id)
            if entry is None:
                return None
            return dict(entry)

    def get_operations(
        self,
        agent_id: str,
        operation: str = "",
        status: str = "",
    ) -> List[Dict[str, Any]]:
        """Return operations for *agent_id*, optionally filtered."""
        with self._lock:
            self._stats["total_queries"] += 1
            results = [
                dict(e) for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            ]
            if operation:
                results = [e for e in results if e["operation"] == operation]
            if status:
                results = [e for e in results if e["status"] == status]
            return results

    def get_latest_operation(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent operation for *agent_id*, or ``None``.

        Uses ``_seq_num`` for tiebreaking.
        """
        with self._lock:
            self._stats["total_queries"] += 1
            agent_ops = [
                e for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            ]
            if not agent_ops:
                return None
            latest = max(agent_ops, key=lambda e: e["_seq_num"])
            return dict(latest)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_average_duration(self, agent_id: str, operation: str) -> float:
        """Return average duration in ms for completed operations matching agent+operation."""
        with self._lock:
            self._stats["total_queries"] += 1
            durations = [
                e["duration_ms"]
                for e in self._state.entries.values()
                if e["agent_id"] == agent_id
                and e["operation"] == operation
                and e["duration_ms"] is not None
            ]
            if not durations:
                return 0.0
            return sum(durations) / len(durations)

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_operation_count(self, agent_id: str = "") -> int:
        """Count operations, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return len(self._state.entries)
            return sum(
                1 for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            )

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one operation."""
        with self._lock:
            seen: set = set()
            result: List[str] = []
            for e in self._state.entries.values():
                aid = e["agent_id"]
                if aid not in seen:
                    seen.add(aid)
                    result.append(aid)
            return result

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
            if name in self._callbacks:
                del self._callbacks[name]
                return True
            return False

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
                "current_entries": len(self._state.entries),
                "unique_agents": len(set(e["agent_id"] for e in self._state.entries.values())),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.entries.clear()
            self._state._seq = 0
            self._callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_operation_log.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries_by_time = sorted(
            self._state.entries.items(),
            key=lambda kv: kv[1]["start_time"],
        )
        to_remove = max(len(entries_by_time) // 4, 1)

        for op_id, _ in entries_by_time[:to_remove]:
            del self._state.entries[op_id]

        self._stats["total_pruned"] += to_remove
        logger.debug("agent_operation_log.prune removed=%d", to_remove)
