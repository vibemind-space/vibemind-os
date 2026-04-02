"""Agent Status Reporter -- reports agent status and health state.

Provides a central, in-memory store for agent status reports.  Agents
report their current status (idle, busy, error, offline) along with
optional details.  The reporter supports querying by agent, filtering
by status, history retrieval, and automatic pruning when the entry
limit is reached.

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
# State
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the status reporter."""

    statuses: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentStatusReporter:
    """In-memory status reporter for agents.

    Parameters
    ----------
    max_entries:
        Maximum total number of status reports to keep.  When the limit
        is reached the oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _State()

        # stats counters
        self._stats: Dict[str, int] = {
            "total_reported": 0,
            "total_pruned": 0,
            "total_queries": 0,
        }

        logger.debug("agent_status_reporter.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, status: str, now: float) -> str:
        """Create a collision-free report ID using SHA-256 + _seq."""
        raw = f"{agent_id}-{status}-{now}-{self._state._seq}"
        return "asr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Total entry count (internal)
    # ------------------------------------------------------------------

    def _total_entries(self) -> int:
        """Return the total number of status reports across all agents."""
        return sum(len(v) for v in self._state.statuses.values())

    # ------------------------------------------------------------------
    # Reporting status
    # ------------------------------------------------------------------

    def report_status(
        self,
        agent_id: str,
        status: str,
        details: dict = None,
    ) -> str:
        """Report current status for an agent and return its ``report_id``.

        Parameters
        ----------
        agent_id:
            The identifier of the agent reporting status.
        status:
            One of ``"idle"``, ``"busy"``, ``"error"``, ``"offline"``.
        details:
            Optional dictionary with additional status details.

        Returns the generated ``asr-...`` identifier for the new report.
        """
        with self._lock:
            # prune if at capacity
            if self._total_entries() >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            report_id = self._generate_id(agent_id, status, now)

            entry: Dict[str, Any] = {
                "report_id": report_id,
                "agent_id": agent_id,
                "status": status,
                "details": details or {},
                "timestamp": now,
            }

            self._state.statuses.setdefault(agent_id, []).append(entry)
            self._stats["total_reported"] += 1

        logger.debug(
            "agent_status_reporter.report_status",
            report_id=report_id,
            agent_id=agent_id,
            status=status,
        )
        self._fire("status_reported", {
            "report_id": report_id,
            "agent_id": agent_id,
            "status": status,
            "details": details or {},
        })
        return report_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the latest status for *agent_id*, or ``None``."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = self._state.statuses.get(agent_id, [])
            if not entries:
                return None
            return dict(entries[-1])

    def get_status_history(
        self,
        agent_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return recent status reports for *agent_id*."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = list(self._state.statuses.get(agent_id, []))
            return entries[-limit:]

    def get_agents_by_status(self, status: str) -> List[str]:
        """Return agent IDs whose latest status matches *status*."""
        with self._lock:
            self._stats["total_queries"] += 1
            result: List[str] = []
            for aid, entries in self._state.statuses.items():
                if entries and entries[-1]["status"] == status:
                    result.append(aid)
            return result

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_report_count(self, agent_id: str = "") -> int:
        """Count reports, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return self._total_entries()
            return len(self._state.statuses.get(agent_id, []))

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one status report."""
        with self._lock:
            return [
                aid
                for aid, entries in self._state.statuses.items()
                if entries
            ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._state.callbacks:
                del self._state.callbacks[name]
                return True
            else:
                return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
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
                "current_entries": self._total_entries(),
                "unique_agents": len([
                    aid for aid, entries in self._state.statuses.items()
                    if entries
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.statuses.clear()
            self._state._seq = 0
            self._state.callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_status_reporter.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        all_entries: List[tuple] = []
        for aid, entries in self._state.statuses.items():
            for entry in entries:
                all_entries.append((aid, entry))

        all_entries.sort(key=lambda x: x[1]["timestamp"])
        to_remove = max(len(all_entries) // 4, 1)

        for aid, entry in all_entries[:to_remove]:
            agent_list = self._state.statuses.get(aid, [])
            try:
                agent_list.remove(entry)
            except ValueError:
                pass

        self._stats["total_pruned"] += to_remove
        logger.debug("agent_status_reporter.prune", removed=to_remove)
