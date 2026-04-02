"""Pipeline step metric — collects and reports metrics for pipeline steps.

Tracks execution count, average duration, and error rate per pipeline step.
Useful for performance monitoring, SLA tracking, and identifying bottlenecks.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepMetricState:
    """Internal state for the PipelineStepMetric service."""

    metrics: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepMetric:
    """Collects and reports metrics for pipeline steps.

    Records execution metrics (duration, success/failure) per pipeline and step,
    supporting queries for average duration, success rate, and execution count.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = PipelineStepMetricState()
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"psm-{self._state._seq}-{id(self)}"
        return "psm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

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
        """Evict oldest entries when the store exceeds max_entries."""
        total = sum(len(entries) for entries in self._state.metrics.values())
        if total <= self._max_entries:
            return
        remove_count = total - self._max_entries
        removed = 0
        for pid in list(self._state.metrics.keys()):
            if removed >= remove_count:
                break
            entries = self._state.metrics[pid]
            while entries and removed < remove_count:
                entries.pop(0)
                removed += 1
            if not entries:
                del self._state.metrics[pid]

    # ------------------------------------------------------------------
    # Record metric
    # ------------------------------------------------------------------

    def record_metric(
        self,
        pipeline_id: str,
        step_name: str,
        duration_ms: float,
        success: bool = True,
    ) -> str:
        """Record a step execution metric. Returns metric ID (psm-xxx)."""
        self._prune_if_needed()

        metric_id = self._generate_id()
        entry = {
            "id": metric_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": time.time(),
        }

        if pipeline_id not in self._state.metrics:
            self._state.metrics[pipeline_id] = []

        self._state.metrics[pipeline_id].append(entry)

        self._fire("metric_recorded", {
            "metric_id": metric_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "duration_ms": duration_ms,
            "success": success,
        })
        return metric_id

    # ------------------------------------------------------------------
    # Get metrics
    # ------------------------------------------------------------------

    def get_metrics(self, pipeline_id: str, step_name: str = "") -> List[Dict[str, Any]]:
        """Get metrics, optionally filtered by step name."""
        entries = self._state.metrics.get(pipeline_id)
        if entries is None:
            return []
        if step_name:
            return [e for e in entries if e["step_name"] == step_name]
        return list(entries)

    # ------------------------------------------------------------------
    # Get average duration
    # ------------------------------------------------------------------

    def get_average_duration(self, pipeline_id: str, step_name: str) -> float:
        """Average duration in ms. 0.0 if no data."""
        entries = self.get_metrics(pipeline_id, step_name)
        if not entries:
            return 0.0
        total = sum(e["duration_ms"] for e in entries)
        return total / len(entries)

    # ------------------------------------------------------------------
    # Get success rate
    # ------------------------------------------------------------------

    def get_success_rate(self, pipeline_id: str, step_name: str) -> float:
        """Success rate 0.0-1.0. 0.0 if no data."""
        entries = self.get_metrics(pipeline_id, step_name)
        if not entries:
            return 0.0
        successes = sum(1 for e in entries if e["success"])
        return successes / len(entries)

    # ------------------------------------------------------------------
    # Get execution count
    # ------------------------------------------------------------------

    def get_execution_count(self, pipeline_id: str, step_name: str = "") -> int:
        """Count executions, optionally filtered by step name."""
        return len(self.get_metrics(pipeline_id, step_name))

    # ------------------------------------------------------------------
    # Get metric count
    # ------------------------------------------------------------------

    def get_metric_count(self, pipeline_id: str = "") -> int:
        """Total metric entries, optionally filtered by pipeline."""
        if pipeline_id:
            entries = self._state.metrics.get(pipeline_id)
            return len(entries) if entries else 0
        return sum(len(entries) for entries in self._state.metrics.values())

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have metrics."""
        return list(self._state.metrics.keys())

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        total_metrics = sum(len(entries) for entries in self._state.metrics.values())
        total_successes = sum(
            sum(1 for e in entries if e["success"])
            for entries in self._state.metrics.values()
        )
        return {
            "total_metrics": total_metrics,
            "total_successes": total_successes,
            "total_failures": total_metrics - total_successes,
            "max_entries": self._max_entries,
            "pipelines": len(self._state.metrics),
            "registered_callbacks": len(self._state.callbacks),
        }

    # ------------------------------------------------------------------
    # Reset all
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored metrics, callbacks, and reset sequence."""
        self._state.metrics.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
