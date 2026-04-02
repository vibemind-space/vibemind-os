"""Pipeline metric aggregator.

Aggregates metrics from multiple pipelines into summaries.
Supports recording metric values per pipeline and metric name,
and provides aggregation queries (average, min, max, count, sum).
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MetricEntry:
    """A single recorded metric value."""
    entry_id: str = ""
    pipeline_id: str = ""
    metric_name: str = ""
    value: float = 0.0
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Metric Aggregator
# ---------------------------------------------------------------------------

class PipelineMetricAggregator:
    """Aggregates metrics from multiple pipelines into summaries."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: Dict[str, MetricEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._stats = {
            "total_recorded": 0,
            "total_lookups": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'pma-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pma-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._entries) < self._max_entries:
            return
        sorted_entries = sorted(
            self._entries.values(), key=lambda e: e.created_at
        )
        remove_count = len(self._entries) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            del self._entries[entry.entry_id]
            self._stats["total_pruned"] += 1
            logger.debug("metric_entry_pruned", entry_id=entry.entry_id)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_metric(
        self,
        pipeline_id: str,
        metric_name: str,
        value: float,
    ) -> str:
        """Record a metric value. Returns the entry ID.

        Creates an entry associating a float value with a pipeline
        and metric name for later aggregation queries.
        """
        if not pipeline_id or not metric_name:
            logger.warning(
                "record_metric_invalid_input",
                pipeline_id=pipeline_id,
                metric_name=metric_name,
            )
            return ""

        self._prune_if_needed()

        entry_id = self._next_id(f"{pipeline_id}:{metric_name}")
        now = time.time()

        entry = MetricEntry(
            entry_id=entry_id,
            pipeline_id=pipeline_id,
            metric_name=metric_name,
            value=value,
            created_at=now,
            seq=self._seq,
        )

        self._entries[entry_id] = entry
        self._stats["total_recorded"] += 1

        logger.info(
            "metric_recorded",
            entry_id=entry_id,
            pipeline_id=pipeline_id,
            metric_name=metric_name,
            value=value,
        )
        self._fire("metric_recorded", self._entry_to_dict(entry))
        return entry_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_metric(self, entry_id: str) -> Optional[Dict]:
        """Get a metric entry by ID. Returns None if not found."""
        self._stats["total_lookups"] += 1
        entry = self._entries.get(entry_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def _values_for(self, pipeline_id: str, metric_name: str) -> List[float]:
        """Collect all recorded values for a pipeline/metric pair."""
        return [
            e.value
            for e in self._entries.values()
            if e.pipeline_id == pipeline_id and e.metric_name == metric_name
        ]

    def get_average(self, pipeline_id: str, metric_name: str) -> float:
        """Get the average of all recorded values for a pipeline/metric."""
        values = self._values_for(pipeline_id, metric_name)
        if not values:
            return 0.0
        return sum(values) / len(values)

    def get_min(self, pipeline_id: str, metric_name: str) -> float:
        """Get the minimum recorded value for a pipeline/metric."""
        values = self._values_for(pipeline_id, metric_name)
        if not values:
            return 0.0
        return min(values)

    def get_max(self, pipeline_id: str, metric_name: str) -> float:
        """Get the maximum recorded value for a pipeline/metric."""
        values = self._values_for(pipeline_id, metric_name)
        if not values:
            return 0.0
        return max(values)

    def get_count(self, pipeline_id: str, metric_name: str) -> int:
        """Get the count of recorded values for a pipeline/metric."""
        return len(self._values_for(pipeline_id, metric_name))

    def get_summary(self, pipeline_id: str, metric_name: str) -> Dict:
        """Get full summary (avg, min, max, count, sum) for a pipeline/metric."""
        values = self._values_for(pipeline_id, metric_name)
        if not values:
            return {
                "avg": 0.0,
                "min": 0.0,
                "max": 0.0,
                "count": 0,
                "sum": 0.0,
            }
        return {
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
            "sum": sum(values),
        }

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all pipeline IDs that have recorded metrics."""
        pipelines = set()
        for entry in self._entries.values():
            pipelines.add(entry.pipeline_id)
        return sorted(pipelines)

    def list_metrics(self, pipeline_id: str) -> List[str]:
        """List all metric names for a given pipeline."""
        metrics = set()
        for entry in self._entries.values():
            if entry.pipeline_id == pipeline_id:
                metrics.add(entry.metric_name)
        return sorted(metrics)

    def get_entry_count(self) -> int:
        """Return the total number of metric entries."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: MetricEntry) -> Dict:
        """Convert a MetricEntry to a plain dict."""
        return {
            "entry_id": entry.entry_id,
            "pipeline_id": entry.pipeline_id,
            "metric_name": entry.metric_name,
            "value": entry.value,
            "created_at": entry.created_at,
            "seq": entry.seq,
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return aggregator statistics."""
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "max_entries": self._max_entries,
            "pipelines": len(set(e.pipeline_id for e in self._entries.values())),
            "metrics": len(
                set(
                    (e.pipeline_id, e.metric_name)
                    for e in self._entries.values()
                )
            ),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("aggregator_reset")
