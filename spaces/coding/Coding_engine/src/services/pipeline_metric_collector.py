"""Pipeline Metric Collector – collects counter, gauge, and histogram metrics.

Provides a unified interface for registering and recording pipeline metrics
across three types: counters (monotonic increment), gauges (point-in-time
values), and histograms (observation distributions with percentile support).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _MetricEntry:
    metric_id: str
    name: str
    metric_type: str  # "counter" | "gauge" | "histogram"
    unit: str
    tags: List[str]
    value: float  # current value for counter/gauge
    observations: List[float]  # histogram observations
    created_at: float
    updated_at: float


class PipelineMetricCollector:
    """Collects counter, gauge, and histogram metrics for pipelines."""

    VALID_TYPES = ("counter", "gauge", "histogram")

    def __init__(self, max_entries: int = 10000, max_history: int = 50000):
        self._metrics: Dict[str, _MetricEntry] = {}
        self._name_index: Dict[str, str] = {}  # name -> metric_id
        self._callbacks: Dict[str, Callable] = {}
        self._history: List[Dict[str, Any]] = []
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_registered = 0
        self._total_increments = 0
        self._total_gauge_sets = 0
        self._total_recordings = 0
        self._total_removals = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pmc-{digest}"

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        entry = {
            "action": action,
            "detail": detail,
            "timestamp": time.time(),
        }
        self._history.append(entry)
        if len(self._history) > self._max_history:
            trim = self._max_history // 10
            self._history = self._history[trim:]

    def get_history(
        self,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return recent history entries, optionally filtered by action."""
        if action:
            filtered = [h for h in self._history if h["action"] == action]
        else:
            filtered = list(self._history)
        return filtered[-limit:]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when collection exceeds max_entries."""
        if len(self._metrics) <= self._max_entries:
            return
        overage = len(self._metrics) - self._max_entries
        sorted_ids = sorted(
            self._metrics,
            key=lambda mid: self._metrics[mid].created_at,
        )
        for mid in sorted_ids[:overage]:
            m = self._metrics.pop(mid)
            self._name_index.pop(m.name, None)

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    def register_metric(
        self,
        name: str,
        metric_type: str = "counter",
        unit: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a new metric. Returns metric ID or '' on duplicate/invalid."""
        if not name:
            return ""
        if metric_type not in self.VALID_TYPES:
            return ""
        if name in self._name_index:
            return ""

        mid = self._generate_id(name)
        now = time.time()

        entry = _MetricEntry(
            metric_id=mid,
            name=name,
            metric_type=metric_type,
            unit=unit,
            tags=tags or [],
            value=0.0,
            observations=[],
            created_at=now,
            updated_at=now,
        )
        self._metrics[mid] = entry
        self._name_index[name] = mid
        self._total_registered += 1
        self._prune_if_needed()

        detail = {"metric_id": mid, "name": name, "metric_type": metric_type}
        self._record_history("metric_registered", detail)
        self._fire("metric_registered", detail)
        return mid

    # ------------------------------------------------------------------
    # Counter operations
    # ------------------------------------------------------------------

    def increment(self, name: str, value: float = 1.0) -> bool:
        """Increment a counter metric by value."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics.get(mid)
        if not m or m.metric_type != "counter":
            return False

        m.value += value
        m.updated_at = time.time()
        self._total_increments += 1

        detail = {"name": name, "value": value, "new_total": m.value}
        self._record_history("counter_incremented", detail)
        self._fire("counter_incremented", detail)
        return True

    # ------------------------------------------------------------------
    # Gauge operations
    # ------------------------------------------------------------------

    def set_gauge(self, name: str, value: float) -> bool:
        """Set the current value of a gauge metric."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics.get(mid)
        if not m or m.metric_type != "gauge":
            return False

        m.value = value
        m.updated_at = time.time()
        self._total_gauge_sets += 1

        detail = {"name": name, "value": value}
        self._record_history("gauge_set", detail)
        self._fire("gauge_set", detail)
        return True

    # ------------------------------------------------------------------
    # Histogram operations
    # ------------------------------------------------------------------

    def record(self, name: str, value: float) -> bool:
        """Record an observation for a histogram metric."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics.get(mid)
        if not m or m.metric_type != "histogram":
            return False

        m.observations.append(value)
        m.updated_at = time.time()
        self._total_recordings += 1

        detail = {"name": name, "value": value, "count": len(m.observations)}
        self._record_history("observation_recorded", detail)
        self._fire("observation_recorded", detail)
        return True

    def get_percentile(self, name: str, percentile: float) -> float:
        """Get a percentile value for a histogram metric.

        Returns 0.0 if the metric is not found, not a histogram, or has
        no observations. Percentile should be 0-100 (e.g. 95 for p95).
        """
        mid = self._name_index.get(name)
        if not mid:
            return 0.0
        m = self._metrics.get(mid)
        if not m or m.metric_type != "histogram" or not m.observations:
            return 0.0

        sorted_obs = sorted(m.observations)
        n = len(sorted_obs)
        if n == 1:
            return sorted_obs[0]

        # clamp percentile
        p = max(0.0, min(100.0, percentile))
        rank = (p / 100.0) * (n - 1)
        lower = int(rank)
        upper = min(lower + 1, n - 1)
        frac = rank - lower
        return sorted_obs[lower] + frac * (sorted_obs[upper] - sorted_obs[lower])

    def get_summary(self, name: str) -> Dict[str, Any]:
        """Get summary statistics for a histogram metric.

        Returns dict with min, max, avg, count, sum, p50, p95, p99.
        Returns empty dict if metric not found or not a histogram.
        """
        mid = self._name_index.get(name)
        if not mid:
            return {}
        m = self._metrics.get(mid)
        if not m or m.metric_type != "histogram" or not m.observations:
            return {}

        obs = m.observations
        total = sum(obs)
        count = len(obs)
        return {
            "name": name,
            "count": count,
            "sum": total,
            "min": min(obs),
            "max": max(obs),
            "avg": total / count,
            "p50": self.get_percentile(name, 50),
            "p95": self.get_percentile(name, 95),
            "p99": self.get_percentile(name, 99),
        }

    # ------------------------------------------------------------------
    # Get / List / Remove
    # ------------------------------------------------------------------

    def get_metric(self, name: str) -> Optional[Dict[str, Any]]:
        """Get the current state of a metric by name."""
        mid = self._name_index.get(name)
        if not mid:
            return None
        m = self._metrics.get(mid)
        if not m:
            return None

        result: Dict[str, Any] = {
            "metric_id": m.metric_id,
            "name": m.name,
            "metric_type": m.metric_type,
            "unit": m.unit,
            "tags": list(m.tags),
            "value": m.value,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }
        if m.metric_type == "histogram":
            result["observation_count"] = len(m.observations)
        return result

    def list_metrics(
        self,
        metric_type: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List metrics, optionally filtered by type or tag."""
        results: List[Dict[str, Any]] = []
        for m in self._metrics.values():
            if metric_type and m.metric_type != metric_type:
                continue
            if tag and tag not in m.tags:
                continue
            info = self.get_metric(m.name)
            if info:
                results.append(info)
        return results

    def remove_metric(self, name: str) -> bool:
        """Remove a metric by name."""
        mid = self._name_index.pop(name, None)
        if not mid:
            return False
        m = self._metrics.pop(mid, None)
        if not m:
            return False

        self._total_removals += 1
        detail = {"metric_id": mid, "name": name}
        self._record_history("metric_removed", detail)
        self._fire("metric_removed", detail)
        return True

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Return a full snapshot of all metrics."""
        metrics: List[Dict[str, Any]] = []
        for m in self._metrics.values():
            entry: Dict[str, Any] = {
                "metric_id": m.metric_id,
                "name": m.name,
                "metric_type": m.metric_type,
                "unit": m.unit,
                "tags": list(m.tags),
                "value": m.value,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            }
            if m.metric_type == "histogram":
                entry["observation_count"] = len(m.observations)
                if m.observations:
                    entry["summary"] = self.get_summary(m.name)
            metrics.append(entry)

        return {
            "total_metrics": len(self._metrics),
            "metrics": metrics,
            "stats": self.get_stats(),
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        return {
            "current_metrics": len(self._metrics),
            "total_registered": self._total_registered,
            "total_increments": self._total_increments,
            "total_gauge_sets": self._total_gauge_sets,
            "total_recordings": self._total_recordings,
            "total_removals": self._total_removals,
            "history_size": len(self._history),
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._metrics.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._history.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_increments = 0
        self._total_gauge_sets = 0
        self._total_recordings = 0
        self._total_removals = 0
