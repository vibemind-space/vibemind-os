"""Pipeline step scheduler — manages when pipeline steps should run.

Schedules pipeline step execution with support for immediate, delayed,
and priority-based scheduling. Tracks schedule status through pending,
running, and completed states.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepSchedulerState:
    """Internal state for the PipelineStepScheduler service."""

    schedules: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepScheduler:
    """Schedules pipeline step execution — manages when steps should run.

    Supports immediate, delayed, and priority-based scheduling with
    status tracking through pending, running, and completed states.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepSchedulerState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"pss2-{self._state._seq}-{id(self)}"
        return "pss2-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named change-notification callback."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict entries when the store exceeds max_entries."""
        if len(self._state.schedules) <= self._max_entries:
            return
        remove_count = len(self._state.schedules) - self._max_entries
        removed = 0
        for sched_id in list(self._state.schedules.keys()):
            if removed >= remove_count:
                break
            del self._state.schedules[sched_id]
            removed += 1

    # ------------------------------------------------------------------
    # Schedule step
    # ------------------------------------------------------------------

    def schedule_step(
        self,
        pipeline_id: str,
        step_name: str,
        delay_seconds: float = 0.0,
        priority: int = 0,
    ) -> str:
        """Schedule a step for execution.

        Returns a schedule ID (pss2-xxx). The schedule is stored with
        status='pending'.
        """
        self._prune_if_needed()

        sched_id = self._generate_id()
        now = time.time()
        self._state.schedules[sched_id] = {
            "schedule_id": sched_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "delay_seconds": delay_seconds,
            "priority": priority,
            "status": "pending",
            "scheduled_at": now,
            "run_at": now + delay_seconds,
        }

        self._fire("step_scheduled", {
            "schedule_id": sched_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
        })
        return sched_id

    # ------------------------------------------------------------------
    # Get schedule
    # ------------------------------------------------------------------

    def get_schedule(self, schedule_id: str) -> Optional[Dict]:
        """Get a schedule by ID. Returns dict or None."""
        sched = self._state.schedules.get(schedule_id)
        if not sched:
            return None
        return dict(sched)

    # ------------------------------------------------------------------
    # Get pending
    # ------------------------------------------------------------------

    def get_pending(self, pipeline_id: str) -> List[Dict]:
        """Get pending schedules for a pipeline, sorted by priority (highest first)."""
        result: List[Dict] = []
        for sched in self._state.schedules.values():
            if sched["pipeline_id"] == pipeline_id and sched["status"] == "pending":
                result.append(dict(sched))
        result.sort(key=lambda s: s["priority"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Mark running
    # ------------------------------------------------------------------

    def mark_running(self, schedule_id: str) -> bool:
        """Set schedule status to 'running'. Returns True if updated."""
        sched = self._state.schedules.get(schedule_id)
        if not sched or sched["status"] != "pending":
            return False
        sched["status"] = "running"
        self._fire("step_running", {
            "schedule_id": schedule_id,
            "pipeline_id": sched["pipeline_id"],
            "step_name": sched["step_name"],
        })
        return True

    # ------------------------------------------------------------------
    # Mark completed
    # ------------------------------------------------------------------

    def mark_completed(self, schedule_id: str) -> bool:
        """Set schedule status to 'completed'. Returns True if updated."""
        sched = self._state.schedules.get(schedule_id)
        if not sched or sched["status"] != "running":
            return False
        sched["status"] = "completed"
        self._fire("step_completed", {
            "schedule_id": schedule_id,
            "pipeline_id": sched["pipeline_id"],
            "step_name": sched["step_name"],
        })
        return True

    # ------------------------------------------------------------------
    # Cancel schedule
    # ------------------------------------------------------------------

    def cancel_schedule(self, schedule_id: str) -> bool:
        """Remove a schedule. Returns True if removed."""
        if schedule_id not in self._state.schedules:
            return False
        info = self._state.schedules.pop(schedule_id)
        self._fire("step_cancelled", {
            "schedule_id": schedule_id,
            "pipeline_id": info["pipeline_id"],
            "step_name": info["step_name"],
        })
        return True

    # ------------------------------------------------------------------
    # Get schedule count
    # ------------------------------------------------------------------

    def get_schedule_count(self, pipeline_id: str = "") -> int:
        """Get total schedule count, optionally filtered by pipeline."""
        if pipeline_id:
            return sum(
                1 for s in self._state.schedules.values()
                if s["pipeline_id"] == pipeline_id
            )
        return len(self._state.schedules)

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have schedules."""
        seen: set = set()
        result: List[str] = []
        for sched in self._state.schedules.values():
            pid = sched["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the scheduler."""
        pipelines = set(s["pipeline_id"] for s in self._state.schedules.values())
        statuses: Dict[str, int] = {}
        for s in self._state.schedules.values():
            statuses[s["status"]] = statuses.get(s["status"], 0) + 1
        return {
            "total_schedules": len(self._state.schedules),
            "max_entries": self._max_entries,
            "pipelines": len(pipelines),
            "registered_callbacks": len(self._state.callbacks),
            "statuses": statuses,
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored schedules, callbacks, and reset sequence."""
        self._state.schedules.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
