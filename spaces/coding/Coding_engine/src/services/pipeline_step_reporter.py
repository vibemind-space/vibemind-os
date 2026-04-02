"""Pipeline step reporter — generates reports about pipeline step executions.

Aggregates metrics and produces summaries for pipeline step executions,
including per-step breakdowns, success/error counts, and duration statistics.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepReporterState:
    """Internal state for the PipelineStepReporter service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepReporter:
    """Generates reports about pipeline step executions.

    Records step executions with duration and status, then produces
    aggregated reports with averages, counts, and per-step breakdowns.
    """

    PREFIX = "psrp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepReporterState()
        self._callbacks: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries.keys(),
            key=lambda eid: self._state.entries[eid].get("created_at", 0),
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for eid in sorted_ids[:remove_count]:
            del self._state.entries[eid]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error action=%s", action)

    @property
    def on_change(self) -> Optional[Callable]:
        """Return the first callback or None (property accessor)."""
        if self._callbacks:
            return next(iter(self._callbacks.values()))
        return None

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set a default change callback."""
        if callback is None:
            self._callbacks.pop("__default__", None)
        else:
            self._callbacks["__default__"] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Record execution
    # ------------------------------------------------------------------

    def record_execution(
        self,
        pipeline_id: str,
        step_name: str,
        duration_ms: float,
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a step execution. Returns the execution ID."""
        self._prune()

        exec_id = self._generate_id()
        entry = {
            "execution_id": exec_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "duration_ms": duration_ms,
            "status": status,
            "metadata": metadata or {},
            "created_at": time.time(),
        }
        self._state.entries[exec_id] = entry

        self._fire("execution_recorded", {
            "execution_id": exec_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
        })
        return exec_id

    # ------------------------------------------------------------------
    # Get report
    # ------------------------------------------------------------------

    def get_report(self, pipeline_id: str) -> Dict[str, Any]:
        """Generate an aggregated report for a pipeline."""
        matching = [
            e for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        ]

        total_executions = len(matching)
        if total_executions == 0:
            return {
                "pipeline_id": pipeline_id,
                "total_executions": 0,
                "avg_duration_ms": 0.0,
                "success_count": 0,
                "error_count": 0,
                "steps": {},
            }

        total_duration = sum(e["duration_ms"] for e in matching)
        success_count = sum(1 for e in matching if e["status"] == "success")
        error_count = sum(1 for e in matching if e["status"] != "success")

        steps: Dict[str, Dict[str, Any]] = {}
        for e in matching:
            sn = e["step_name"]
            if sn not in steps:
                steps[sn] = {"count": 0, "total_duration": 0.0}
            steps[sn]["count"] += 1
            steps[sn]["total_duration"] += e["duration_ms"]

        steps_report = {}
        for sn, data in steps.items():
            steps_report[sn] = {
                "count": data["count"],
                "avg_duration_ms": data["total_duration"] / data["count"],
            }

        return {
            "pipeline_id": pipeline_id,
            "total_executions": total_executions,
            "avg_duration_ms": total_duration / total_executions,
            "success_count": success_count,
            "error_count": error_count,
            "steps": steps_report,
        }

    # ------------------------------------------------------------------
    # Get execution
    # ------------------------------------------------------------------

    def get_execution(self, execution_id: str) -> Dict[str, Any]:
        """Get a single execution record by ID. Returns empty dict if not found."""
        entry = self._state.entries.get(execution_id)
        if entry is None:
            return {}
        return dict(entry)

    # ------------------------------------------------------------------
    # Get executions
    # ------------------------------------------------------------------

    def get_executions(
        self,
        pipeline_id: str,
        step_name: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get executions for a pipeline, optionally filtered by step name."""
        matching = [
            e for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
            and (not step_name or e["step_name"] == step_name)
        ]
        matching.sort(key=lambda e: e["created_at"], reverse=True)
        return [dict(e) for e in matching[:limit]]

    # ------------------------------------------------------------------
    # Get execution count
    # ------------------------------------------------------------------

    def get_execution_count(self, pipeline_id: str = "") -> int:
        """Get count of executions, optionally filtered by pipeline ID."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Clear executions
    # ------------------------------------------------------------------

    def clear_executions(self, pipeline_id: str) -> int:
        """Remove all executions for a pipeline. Returns number removed."""
        to_remove = [
            eid for eid, e in self._state.entries.items()
            if e["pipeline_id"] == pipeline_id
        ]
        for eid in to_remove:
            del self._state.entries[eid]

        if to_remove:
            self._fire("executions_cleared", {
                "pipeline_id": pipeline_id,
                "count": len(to_remove),
            })
        return len(to_remove)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        entries = list(self._state.entries.values())
        unique_pipelines = len(set(e["pipeline_id"] for e in entries)) if entries else 0
        total_duration = sum(e["duration_ms"] for e in entries)
        return {
            "total_executions": len(entries),
            "unique_pipelines": unique_pipelines,
            "total_duration_ms": total_duration,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored entries, callbacks, and reset sequence."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._state._seq = 0
