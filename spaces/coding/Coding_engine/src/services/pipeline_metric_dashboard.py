"""Pipeline Metric Dashboard – aggregates and summarizes pipeline performance metrics.

Provides recording, retrieval, aggregation, and dashboard summaries of numeric
metrics keyed by pipeline name and metric name.  Supports per-pipeline
summaries, min/max/average queries, purging, and configurable entry limits
with automatic pruning.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricEntry:
    """A single recorded pipeline metric data point."""

    metric_id: str
    pipeline_name: str
    metric_name: str
    value: float
    tags: List[str]
    metadata: Dict[str, Any]
    timestamp: float


@dataclass
class _DashboardState:
    """Internal mutable state for the metric dashboard."""

    entries: Dict[str, MetricEntry] = field(default_factory=dict)
    # pipeline_name -> metric_name -> list of metric_ids (chronological)
    pipeline_index: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    seq: int = 0
    total_recorded: int = 0
    total_pruned: int = 0


class PipelineMetricDashboard:
    """Aggregates and summarizes pipeline performance metrics."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _DashboardState()
        logger.info("pipeline_metric_dashboard.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, pipeline_name: str, metric_name: str) -> str:
        self._state.seq += 1
        now = time.time()
        raw = f"{pipeline_name}-{metric_name}-{now}-{self._state.seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pmd-{digest}"

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_metric(
        self,
        pipeline_name: str,
        metric_name: str,
        value: float,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a metric value for a pipeline.  Returns the metric_id."""
        if not pipeline_name or not metric_name:
            logger.warning("pipeline_metric_dashboard.record_metric.invalid_args")
            return ""

        with self._lock:
            # Prune if at capacity
            if len(self._state.entries) >= self._max_entries:
                self._prune_oldest()

            mid = self._generate_id(pipeline_name, metric_name)
            now = time.time()

            entry = MetricEntry(
                metric_id=mid,
                pipeline_name=pipeline_name,
                metric_name=metric_name,
                value=float(value),
                tags=list(tags) if tags else [],
                metadata=dict(metadata) if metadata else {},
                timestamp=now,
            )
            self._state.entries[mid] = entry

            # Update pipeline index
            if pipeline_name not in self._state.pipeline_index:
                self._state.pipeline_index[pipeline_name] = {}
            pipeline_metrics = self._state.pipeline_index[pipeline_name]
            if metric_name not in pipeline_metrics:
                pipeline_metrics[metric_name] = []
            pipeline_metrics[metric_name].append(mid)

            self._state.total_recorded += 1

        logger.debug(
            "pipeline_metric_dashboard.recorded metric_id=%s pipeline=%s metric=%s value=%s",
            mid,
            pipeline_name,
            metric_name,
            value,
        )
        self._fire("recorded", {
            "metric_id": mid,
            "pipeline_name": pipeline_name,
            "metric_name": metric_name,
            "value": value,
        })
        return mid

    def _prune_oldest(self) -> None:
        """Remove the oldest 10%% of entries when at capacity.

        Caller must hold ``self._lock``.
        """
        count = max(1, self._max_entries // 10)
        sorted_ids = sorted(
            self._state.entries.keys(),
            key=lambda k: self._state.entries[k].timestamp,
        )
        for mid in sorted_ids[:count]:
            self._remove_entry(mid)
            self._state.total_pruned += 1

    def _remove_entry(self, metric_id: str) -> None:
        """Remove a single entry from entries and the pipeline index.

        Caller must hold ``self._lock``.
        """
        entry = self._state.entries.pop(metric_id, None)
        if not entry:
            return
        pipeline_metrics = self._state.pipeline_index.get(entry.pipeline_name, {})
        name_list = pipeline_metrics.get(entry.metric_name, [])
        if metric_id in name_list:
            name_list.remove(metric_id)
        # Clean up empty structures
        if not name_list and entry.metric_name in pipeline_metrics:
            del pipeline_metrics[entry.metric_name]
        if not pipeline_metrics and entry.pipeline_name in self._state.pipeline_index:
            del self._state.pipeline_index[entry.pipeline_name]

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: MetricEntry) -> Dict[str, Any]:
        """Convert a metric entry to a plain dict."""
        return {
            "metric_id": entry.metric_id,
            "pipeline_name": entry.pipeline_name,
            "metric_name": entry.metric_name,
            "value": entry.value,
            "tags": list(entry.tags),
            "metadata": dict(entry.metadata),
            "timestamp": entry.timestamp,
        }

    def get_metric(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """Return a single metric entry by ID, or ``None``."""
        with self._lock:
            entry = self._state.entries.get(metric_id)
            if not entry:
                return None
            return self._entry_to_dict(entry)

    def get_pipeline_metrics(
        self,
        pipeline_name: str,
        metric_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return metrics for a pipeline, optionally filtered by metric name."""
        with self._lock:
            pipeline_metrics = self._state.pipeline_index.get(pipeline_name, {})
            if metric_name is not None:
                id_list = pipeline_metrics.get(metric_name, [])
            else:
                id_list = []
                for ids in pipeline_metrics.values():
                    id_list.extend(ids)

            results: List[Dict[str, Any]] = []
            for mid in id_list:
                entry = self._state.entries.get(mid)
                if entry:
                    results.append(self._entry_to_dict(entry))
            return results

    def get_latest_metric(
        self,
        pipeline_name: str,
        metric_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent metric value for a pipeline + metric name."""
        with self._lock:
            pipeline_metrics = self._state.pipeline_index.get(pipeline_name, {})
            id_list = pipeline_metrics.get(metric_name, [])
            if not id_list:
                return None
            latest_id = id_list[-1]
            entry = self._state.entries.get(latest_id)
            if not entry:
                return None
            return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_average(self, pipeline_name: str, metric_name: str) -> float:
        """Return the average value for a pipeline + metric name, or ``0.0``."""
        with self._lock:
            pipeline_metrics = self._state.pipeline_index.get(pipeline_name, {})
            id_list = pipeline_metrics.get(metric_name, [])
            if not id_list:
                return 0.0
            total = 0.0
            count = 0
            for mid in id_list:
                entry = self._state.entries.get(mid)
                if entry:
                    total += entry.value
                    count += 1
            return total / count if count > 0 else 0.0

    def get_min_max(self, pipeline_name: str, metric_name: str) -> Dict[str, float]:
        """Return ``{"min": …, "max": …}`` for a pipeline + metric name.

        Returns ``{"min": 0.0, "max": 0.0}`` when no data is present.
        """
        with self._lock:
            pipeline_metrics = self._state.pipeline_index.get(pipeline_name, {})
            id_list = pipeline_metrics.get(metric_name, [])
            if not id_list:
                return {"min": 0.0, "max": 0.0}
            values: List[float] = []
            for mid in id_list:
                entry = self._state.entries.get(mid)
                if entry:
                    values.append(entry.value)
            if not values:
                return {"min": 0.0, "max": 0.0}
            return {"min": min(values), "max": max(values)}

    # ------------------------------------------------------------------
    # Dashboard summary
    # ------------------------------------------------------------------

    def get_dashboard_summary(
        self,
        pipeline_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a summary of all metrics, optionally scoped to one pipeline.

        Structure::

            {
                "pipelines": {
                    "<pipeline>": {
                        "<metric>": {
                            "count": int,
                            "avg": float,
                            "min": float,
                            "max": float,
                            "latest": float,
                        },
                        ...
                    },
                    ...
                },
                "total_entries": int,
            }
        """
        with self._lock:
            if pipeline_name is not None:
                pipelines_to_scan = {pipeline_name: self._state.pipeline_index.get(pipeline_name, {})}
            else:
                pipelines_to_scan = dict(self._state.pipeline_index)

            pipelines_summary: Dict[str, Dict[str, Any]] = {}
            for pname, metrics_map in pipelines_to_scan.items():
                metric_summaries: Dict[str, Any] = {}
                for mname, id_list in metrics_map.items():
                    values: List[float] = []
                    for mid in id_list:
                        entry = self._state.entries.get(mid)
                        if entry:
                            values.append(entry.value)
                    if not values:
                        continue
                    metric_summaries[mname] = {
                        "count": len(values),
                        "avg": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "latest": values[-1],
                    }
                pipelines_summary[pname] = metric_summaries

            return {
                "pipelines": pipelines_summary,
                "total_entries": len(self._state.entries),
            }

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_metric_names(
        self,
        pipeline_name: Optional[str] = None,
    ) -> List[str]:
        """Return unique metric names, optionally filtered by pipeline."""
        with self._lock:
            if pipeline_name is not None:
                pipeline_metrics = self._state.pipeline_index.get(pipeline_name, {})
                return sorted(pipeline_metrics.keys())
            names: set[str] = set()
            for pipeline_metrics in self._state.pipeline_index.values():
                names.update(pipeline_metrics.keys())
            return sorted(names)

    # ------------------------------------------------------------------
    # Purging
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove entries recorded before *before_timestamp*.

        If *before_timestamp* is ``None`` all entries are removed.
        Returns the number of entries purged.
        """
        with self._lock:
            to_remove: List[str] = []
            for mid, entry in self._state.entries.items():
                if before_timestamp is not None and entry.timestamp >= before_timestamp:
                    continue
                to_remove.append(mid)

            for mid in to_remove:
                self._remove_entry(mid)

            removed = len(to_remove)
            if removed:
                self._state.total_pruned += removed

        if removed:
            logger.info(
                "pipeline_metric_dashboard.purged count=%d before=%s",
                removed,
                before_timestamp,
            )
            self._fire("purged", {"count": removed, "before_timestamp": before_timestamp})
        return removed

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns ``False`` if *name* is taken."""
        with self._lock:
            if name in self._state.callbacks:
                return False
            self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``True`` if it existed."""
        with self._lock:
            return self._state.callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                logger.exception("pipeline_metric_dashboard.callback_error action=%s", action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics about the dashboard."""
        with self._lock:
            unique_pipelines = len(self._state.pipeline_index)
            unique_metrics: set[str] = set()
            for pipeline_metrics in self._state.pipeline_index.values():
                unique_metrics.update(pipeline_metrics.keys())

            return {
                "current_entries": len(self._state.entries),
                "max_entries": self._max_entries,
                "total_recorded": self._state.total_recorded,
                "total_pruned": self._state.total_pruned,
                "unique_pipelines": unique_pipelines,
                "unique_metrics": len(unique_metrics),
                "callbacks": len(self._state.callbacks),
            }

    def reset(self) -> None:
        """Clear all data and reset counters."""
        with self._lock:
            self._state = _DashboardState()
        logger.info("pipeline_metric_dashboard.reset")
