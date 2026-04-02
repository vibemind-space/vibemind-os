"""Pipeline step counter — tracks how many times pipeline steps have been executed.

Maintains per-pipeline, per-step execution counts. Useful for monitoring
pipeline usage patterns, identifying hot steps, and enforcing execution limits.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepCounterState:
    """Internal state for the PipelineStepCounter service."""

    counters: Dict[str, Dict[str, int]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepCounter:
    """Counts how many times pipeline steps have been executed.

    Tracks execution counts per pipeline and step name, supporting
    queries for totals, top-executed steps, and per-pipeline breakdowns.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepCounterState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psc2-{self._state._seq}-{id(self)}"
        return "psc2-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

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
        total = sum(len(steps) for steps in self._state.counters.values())
        if total <= self._max_entries:
            return
        remove_count = total - self._max_entries
        removed = 0
        for pid in list(self._state.counters.keys()):
            if removed >= remove_count:
                break
            steps = self._state.counters[pid]
            for step_name in list(steps.keys()):
                if removed >= remove_count:
                    break
                del steps[step_name]
                removed += 1
            if not steps:
                del self._state.counters[pid]

    # ------------------------------------------------------------------
    # Increment
    # ------------------------------------------------------------------

    def increment(self, pipeline_id: str, step_name: str, count: int = 1) -> int:
        """Increment counter for a pipeline step. Returns new total."""
        self._prune_if_needed()

        if pipeline_id not in self._state.counters:
            self._state.counters[pipeline_id] = {}

        steps = self._state.counters[pipeline_id]
        steps[step_name] = steps.get(step_name, 0) + count
        new_total = steps[step_name]

        self._fire("counter_incremented", {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "count": count,
            "new_total": new_total,
        })
        return new_total

    # ------------------------------------------------------------------
    # Get count
    # ------------------------------------------------------------------

    def get_count(self, pipeline_id: str, step_name: str) -> int:
        """Get current count for a step. Returns 0 if not tracked."""
        steps = self._state.counters.get(pipeline_id)
        if steps is None:
            return 0
        return steps.get(step_name, 0)

    # ------------------------------------------------------------------
    # Get counts
    # ------------------------------------------------------------------

    def get_counts(self, pipeline_id: str) -> Dict[str, int]:
        """Get all step counts for a pipeline as {step_name: count}."""
        steps = self._state.counters.get(pipeline_id)
        if steps is None:
            return {}
        return dict(steps)

    # ------------------------------------------------------------------
    # Reset counter
    # ------------------------------------------------------------------

    def reset_counter(self, pipeline_id: str, step_name: str) -> bool:
        """Reset a specific counter. Returns False if not found."""
        steps = self._state.counters.get(pipeline_id)
        if steps is None:
            return False
        if step_name not in steps:
            return False
        del steps[step_name]
        if not steps:
            del self._state.counters[pipeline_id]
        self._fire("counter_reset", {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
        })
        return True

    # ------------------------------------------------------------------
    # Get total
    # ------------------------------------------------------------------

    def get_total(self, pipeline_id: str = "") -> int:
        """Get total across all steps, or for a specific pipeline."""
        if pipeline_id:
            steps = self._state.counters.get(pipeline_id)
            if steps is None:
                return 0
            return sum(steps.values())
        return sum(
            sum(steps.values())
            for steps in self._state.counters.values()
        )

    # ------------------------------------------------------------------
    # Get most executed
    # ------------------------------------------------------------------

    def get_most_executed(self, pipeline_id: str, limit: int = 5) -> List[Tuple[str, int]]:
        """Get top N most executed steps as list of (step_name, count) tuples."""
        steps = self._state.counters.get(pipeline_id)
        if steps is None:
            return []
        sorted_steps = sorted(steps.items(), key=lambda x: x[1], reverse=True)
        return sorted_steps[:limit]

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have counters."""
        return list(self._state.counters.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        total_counters = sum(len(steps) for steps in self._state.counters.values())
        total_executions = sum(
            sum(steps.values()) for steps in self._state.counters.values()
        )
        return {
            "total_counters": total_counters,
            "total_executions": total_executions,
            "max_entries": self._max_entries,
            "pipelines": len(self._state.counters),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored counters, callbacks, and reset sequence."""
        self._state.counters.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
