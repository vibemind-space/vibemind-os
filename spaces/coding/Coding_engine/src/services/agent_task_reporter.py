"""Agent Task Reporter -- generates progress reports for agent tasks.

Tracks task progress with status, completion percentage, and summary
information. Supports querying, filtering, updating, and statistics.

Usage::

    reporter = AgentTaskReporter()

    # Create a report
    report_id = reporter.create_report("task-1", "agent-1", status="in_progress")

    # Update progress
    reporter.update_report(report_id, progress=0.5, summary="Halfway done")

    # Query
    report = reporter.get_report(report_id)
    reports = reporter.get_reports(agent_id="agent-1")
    stats = reporter.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskReporterState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskReporter:
    """Generates progress reports for agent tasks."""

    PREFIX = "atrp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskReporterState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Report operations
    # ------------------------------------------------------------------

    def create_report(
        self,
        task_id: str,
        agent_id: str,
        status: str = "in_progress",
        progress: float = 0.0,
        summary: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a progress report for an agent task.

        Returns the report ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        report_id = self._generate_id()
        self._state.entries[report_id] = {
            "report_id": report_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "status": status,
            "progress": progress,
            "summary": summary,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._fire("report_created", self._state.entries[report_id])
        logger.debug(
            "Report created: %s (task=%s, agent=%s)",
            report_id,
            task_id,
            agent_id,
        )
        return report_id

    def get_report(self, report_id: str) -> Optional[dict]:
        """Return the report entry or None."""
        entry = self._state.entries.get(report_id)
        return dict(entry) if entry else None

    def get_reports(
        self,
        agent_id: str = "",
        task_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query reports, newest first.

        Optionally filter by agent_id, task_id, and/or status.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if task_id and entry["task_id"] != task_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def update_report(
        self,
        report_id: str,
        status: str = "",
        progress: float = None,
        summary: str = "",
    ) -> bool:
        """Update an existing report.

        Returns True if the report was found and updated, False otherwise.
        """
        entry = self._state.entries.get(report_id)
        if entry is None:
            return False

        if status:
            entry["status"] = status
        if progress is not None:
            entry["progress"] = progress
        if summary:
            entry["summary"] = summary
        entry["updated_at"] = time.time()

        self._fire("report_updated", entry)
        logger.debug("Report updated: %s", report_id)
        return True

    def get_report_count(self, agent_id: str = "", status: str = "") -> int:
        """Return the number of reports, optionally filtered."""
        if not agent_id and not status:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if agent_id and e["agent_id"] != agent_id:
                continue
            if status and e["status"] != status:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        by_status: Dict[str, int] = {}
        total_progress = 0.0
        for entry in self._state.entries.values():
            s = entry["status"]
            by_status[s] = by_status.get(s, 0) + 1
            total_progress += entry["progress"]
        total = len(self._state.entries)
        return {
            "total_reports": total,
            "by_status": by_status,
            "avg_progress": total_progress / total if total > 0 else 0.0,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskReporterState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskReporter reset")
