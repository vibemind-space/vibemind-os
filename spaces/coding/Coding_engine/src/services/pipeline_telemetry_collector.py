"""Pipeline Telemetry Collector – collects and aggregates telemetry metrics.

Gathers metrics (counters, gauges, histograms) from pipeline components,
aggregates them over time windows, and provides query capabilities for
dashboards and alerting.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Metric:
    metric_id: str
    name: str
    metric_type: str  # counter, gauge, histogram
    value: float
    count: int  # number of samples (for histogram)
    total: float  # sum of all samples (for histogram)
    min_val: float
    max_val: float
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _TelemetryEvent:
    event_id: str
    metric_name: str
    action: str  # recorded, reset
    value: float
    timestamp: float


class PipelineTelemetryCollector:
    """Collects and aggregates telemetry metrics."""

    METRIC_TYPES = ("counter", "gauge", "histogram")

    def __init__(self, max_metrics: int = 50000, max_history: int = 100000):
        self._metrics: Dict[str, _Metric] = {}
        self._name_index: Dict[str, str] = {}  # name -> metric_id
        self._history: List[_TelemetryEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_metrics = max_metrics
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_registered = 0
        self._total_recordings = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_metric(
        self,
        name: str,
        metric_type: str = "counter",
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if metric_type not in self.METRIC_TYPES:
            return ""
        if name in self._name_index:
            return ""
        if len(self._metrics) >= self._max_metrics:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{metric_type}-{now}-{self._seq}"
        mid = "met-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        metric = _Metric(
            metric_id=mid,
            name=name,
            metric_type=metric_type,
            value=0.0,
            count=0,
            total=0.0,
            min_val=float("inf"),
            max_val=float("-inf"),
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._metrics[mid] = metric
        self._name_index[name] = mid
        self._total_registered += 1
        self._fire("metric_registered", {"metric_id": mid, "name": name, "type": metric_type})
        return mid

    def get_metric(self, name: str) -> Optional[Dict[str, Any]]:
        mid = self._name_index.get(name)
        if not mid:
            return None
        m = self._metrics[mid]
        avg = (m.total / m.count) if m.count > 0 else 0.0
        return {
            "metric_id": m.metric_id,
            "name": m.name,
            "metric_type": m.metric_type,
            "value": m.value,
            "count": m.count,
            "total": m.total,
            "min": m.min_val if m.count > 0 else 0.0,
            "max": m.max_val if m.count > 0 else 0.0,
            "avg": avg,
            "tags": list(m.tags),
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }

    def remove_metric(self, name: str) -> bool:
        mid = self._name_index.pop(name, None)
        if not mid:
            return False
        self._metrics.pop(mid, None)
        return True

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, name: str, value: float = 1.0) -> bool:
        """Record a value for a metric.

        - counter: value is added to current value
        - gauge: value replaces current value
        - histogram: value is added as a sample
        """
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics[mid]

        if m.metric_type == "counter":
            m.value += value
        elif m.metric_type == "gauge":
            m.value = value
        elif m.metric_type == "histogram":
            m.value = value  # last recorded
            m.total += value
            m.count += 1
            if value < m.min_val:
                m.min_val = value
            if value > m.max_val:
                m.max_val = value

        m.updated_at = time.time()
        self._total_recordings += 1
        self._record_event(name, "recorded", value)
        self._fire("metric_recorded", {"name": name, "value": value, "type": m.metric_type})
        return True

    def increment(self, name: str, amount: float = 1.0) -> bool:
        """Increment a counter metric."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics[mid]
        if m.metric_type != "counter":
            return False
        return self.record(name, amount)

    def set_gauge(self, name: str, value: float) -> bool:
        """Set a gauge metric value."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics[mid]
        if m.metric_type != "gauge":
            return False
        return self.record(name, value)

    def observe(self, name: str, value: float) -> bool:
        """Record a histogram observation."""
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics[mid]
        if m.metric_type != "histogram":
            return False
        return self.record(name, value)

    def get_value(self, name: str) -> float:
        mid = self._name_index.get(name)
        if not mid:
            return 0.0
        return self._metrics[mid].value

    def reset_metric(self, name: str) -> bool:
        mid = self._name_index.get(name)
        if not mid:
            return False
        m = self._metrics[mid]
        m.value = 0.0
        m.count = 0
        m.total = 0.0
        m.min_val = float("inf")
        m.max_val = float("-inf")
        m.updated_at = time.time()
        self._record_event(name, "reset", 0.0)
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_metrics(self, metric_type: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for m in self._metrics.values():
            if metric_type and m.metric_type != metric_type:
                continue
            if tag and tag not in m.tags:
                continue
            results.append(self.get_metric(m.name))
        return results

    def search(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower()
        results = []
        for m in self._metrics.values():
            if q in m.name.lower() or any(q in t.lower() for t in m.tags):
                results.append(self.get_metric(m.name))
        return results

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        metric_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if metric_name and ev.metric_name != metric_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "metric_name": ev.metric_name,
                "action": ev.action,
                "value": ev.value,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, metric_name: str, action: str, value: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{metric_name}-{action}-{now}-{self._seq}"
        evid = "tev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _TelemetryEvent(
            event_id=evid, metric_name=metric_name,
            action=action, value=value, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        counters = sum(1 for m in self._metrics.values() if m.metric_type == "counter")
        gauges = sum(1 for m in self._metrics.values() if m.metric_type == "gauge")
        histograms = sum(1 for m in self._metrics.values() if m.metric_type == "histogram")
        return {
            "current_metrics": len(self._metrics),
            "counters": counters,
            "gauges": gauges,
            "histograms": histograms,
            "total_registered": self._total_registered,
            "total_recordings": self._total_recordings,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._metrics.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_recordings = 0
