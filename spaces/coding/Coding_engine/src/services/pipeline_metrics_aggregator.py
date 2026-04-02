"""
Pipeline Metrics Aggregator — collects, aggregates, and queries pipeline metrics.

Features:
- Counter, gauge, histogram, and timer metric types
- Namespace and label-based organization
- Time-windowed aggregation (min, max, avg, p50, p95, p99)
- Metric snapshots for dashboards
- Alert thresholds with callbacks
- Metric export
"""

from __future__ import annotations

import bisect
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MetricPoint:
    """A single metric data point."""
    timestamp: float
    value: float


@dataclass
class Metric:
    """A named metric with history."""
    name: str
    metric_type: str  # "counter", "gauge", "histogram", "timer"
    namespace: str
    labels: Dict[str, str]
    unit: str
    description: str
    points: List[MetricPoint]
    created_at: float
    max_points: int = 10000

    def add(self, value: float, timestamp: float = 0.0) -> None:
        ts = timestamp or time.time()
        self.points.append(MetricPoint(timestamp=ts, value=value))
        if len(self.points) > self.max_points:
            self.points = self.points[-self.max_points:]


@dataclass
class AlertRule:
    """A threshold-based alert rule."""
    rule_id: str
    metric_name: str
    namespace: str
    condition: str  # "gt", "lt", "gte", "lte", "eq"
    threshold: float
    window_seconds: float
    cooldown_seconds: float
    callback: Optional[Callable]
    last_triggered: float = 0.0
    triggered_count: int = 0
    enabled: bool = True


# ---------------------------------------------------------------------------
# Pipeline Metrics Aggregator
# ---------------------------------------------------------------------------

class PipelineMetricsAggregator:
    """Collects, aggregates, and queries pipeline metrics."""

    def __init__(
        self,
        max_metrics: int = 5000,
        default_max_points: int = 10000,
    ):
        self._max_metrics = max_metrics
        self._default_max_points = default_max_points
        self._metrics: Dict[str, Metric] = {}  # key = "namespace:name"
        self._alerts: Dict[str, AlertRule] = {}

        self._stats = {
            "total_recorded": 0,
            "total_alerts_triggered": 0,
        }

    # ------------------------------------------------------------------
    # Metric key helpers
    # ------------------------------------------------------------------

    def _key(self, name: str, namespace: str = "default") -> str:
        return f"{namespace}:{name}"

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        metric_type: str = "gauge",
        namespace: str = "default",
        labels: Optional[Dict[str, str]] = None,
        unit: str = "",
        description: str = "",
        max_points: int = 0,
    ) -> bool:
        """Register a new metric. Returns False if already exists."""
        key = self._key(name, namespace)
        if key in self._metrics:
            return False
        self._metrics[key] = Metric(
            name=name,
            metric_type=metric_type,
            namespace=namespace,
            labels=labels or {},
            unit=unit,
            description=description,
            points=[],
            created_at=time.time(),
            max_points=max_points or self._default_max_points,
        )
        return True

    def unregister(self, name: str, namespace: str = "default") -> bool:
        """Remove a metric."""
        key = self._key(name, namespace)
        if key not in self._metrics:
            return False
        del self._metrics[key]
        return True

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        name: str,
        value: float,
        namespace: str = "default",
        timestamp: float = 0.0,
    ) -> bool:
        """Record a value for a metric. Auto-registers gauges."""
        key = self._key(name, namespace)
        m = self._metrics.get(key)
        if not m:
            # Auto-register as gauge
            self.register(name, metric_type="gauge", namespace=namespace)
            m = self._metrics[key]

        if m.metric_type == "counter":
            # Counters only increase
            if value < 0:
                return False
            last_val = m.points[-1].value if m.points else 0.0
            m.add(last_val + value, timestamp)
        else:
            m.add(value, timestamp)

        self._stats["total_recorded"] += 1
        self._check_alerts(name, namespace)
        return True

    def increment(
        self,
        name: str,
        amount: float = 1.0,
        namespace: str = "default",
    ) -> bool:
        """Increment a counter metric."""
        key = self._key(name, namespace)
        m = self._metrics.get(key)
        if not m:
            self.register(name, metric_type="counter", namespace=namespace)
            m = self._metrics[key]
        if m.metric_type != "counter":
            return False
        last_val = m.points[-1].value if m.points else 0.0
        m.add(last_val + amount)
        self._stats["total_recorded"] += 1
        self._check_alerts(name, namespace)
        return True

    def time_start(self, name: str, namespace: str = "default") -> str:
        """Start a timer. Returns timer_id."""
        key = self._key(name, namespace)
        if key not in self._metrics:
            self.register(name, metric_type="timer", namespace=namespace, unit="seconds")
        timer_id = f"tmr-{uuid.uuid4().hex[:8]}"
        # Store start time in a transient way using metric metadata
        if not hasattr(self, "_timers"):
            self._timers: Dict[str, Tuple[str, str, float]] = {}
        self._timers[timer_id] = (name, namespace, time.time())
        return timer_id

    def time_stop(self, timer_id: str) -> Optional[float]:
        """Stop a timer and record duration. Returns duration in seconds."""
        if not hasattr(self, "_timers"):
            return None
        entry = self._timers.pop(timer_id, None)
        if not entry:
            return None
        name, namespace, start = entry
        duration = time.time() - start
        self.record(name, duration, namespace=namespace)
        return duration

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_current(self, name: str, namespace: str = "default") -> Optional[float]:
        """Get the latest value of a metric."""
        key = self._key(name, namespace)
        m = self._metrics.get(key)
        if not m or not m.points:
            return None
        return m.points[-1].value

    def get_metric(self, name: str, namespace: str = "default") -> Optional[Dict]:
        """Get metric info."""
        key = self._key(name, namespace)
        m = self._metrics.get(key)
        if not m:
            return None
        return self._metric_to_dict(m)

    def get_history(
        self,
        name: str,
        namespace: str = "default",
        since: float = 0.0,
        limit: int = 100,
    ) -> List[Dict]:
        """Get metric history."""
        key = self._key(name, namespace)
        m = self._metrics.get(key)
        if not m:
            return []
        points = m.points
        if since > 0:
            points = [p for p in points if p.timestamp >= since]
        points = points[-limit:]
        return [{"timestamp": p.timestamp, "value": p.value} for p in points]

    def aggregate(
        self,
        name: str,
        namespace: str = "default",
        window_seconds: float = 300.0,
    ) -> Optional[Dict]:
        """Aggregate metric over a time window."""
        key = self._key(name, namespace)
        m = self._metrics.get(key)
        if not m or not m.points:
            return None

        cutoff = time.time() - window_seconds
        values = [p.value for p in m.points if p.timestamp >= cutoff]
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "sum": 0,
                    "p50": 0, "p95": 0, "p99": 0}

        values.sort()
        count = len(values)
        return {
            "count": count,
            "min": round(values[0], 4),
            "max": round(values[-1], 4),
            "avg": round(sum(values) / count, 4),
            "sum": round(sum(values), 4),
            "p50": round(self._percentile(values, 50), 4),
            "p95": round(self._percentile(values, 95), 4),
            "p99": round(self._percentile(values, 99), 4),
        }

    def list_metrics(
        self,
        namespace: Optional[str] = None,
        metric_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """List metrics with optional filters."""
        results = []
        for m in self._metrics.values():
            if namespace and m.namespace != namespace:
                continue
            if metric_type and m.metric_type != metric_type:
                continue
            results.append(self._metric_to_dict(m))
            if len(results) >= limit:
                break
        return results

    def list_namespaces(self) -> Dict[str, int]:
        """List namespaces with metric counts."""
        counts: Dict[str, int] = defaultdict(int)
        for m in self._metrics.values():
            counts[m.namespace] += 1
        return dict(sorted(counts.items()))

    def snapshot(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Get a snapshot of all current metric values."""
        result: Dict[str, Any] = {}
        for key, m in self._metrics.items():
            if namespace and m.namespace != namespace:
                continue
            if m.points:
                result[key] = {
                    "value": m.points[-1].value,
                    "type": m.metric_type,
                    "unit": m.unit,
                    "points_count": len(m.points),
                }
        return result

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def add_alert(
        self,
        metric_name: str,
        condition: str,
        threshold: float,
        namespace: str = "default",
        window_seconds: float = 60.0,
        cooldown_seconds: float = 300.0,
        callback: Optional[Callable] = None,
    ) -> str:
        """Add an alert rule. Returns rule_id."""
        rule_id = f"alrt-{uuid.uuid4().hex[:8]}"
        self._alerts[rule_id] = AlertRule(
            rule_id=rule_id,
            metric_name=metric_name,
            namespace=namespace,
            condition=condition,
            threshold=threshold,
            window_seconds=window_seconds,
            cooldown_seconds=cooldown_seconds,
            callback=callback,
        )
        return rule_id

    def remove_alert(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        if rule_id not in self._alerts:
            return False
        del self._alerts[rule_id]
        return True

    def list_alerts(self) -> List[Dict]:
        """List all alert rules."""
        return [
            {
                "rule_id": r.rule_id,
                "metric_name": r.metric_name,
                "namespace": r.namespace,
                "condition": r.condition,
                "threshold": r.threshold,
                "window_seconds": r.window_seconds,
                "cooldown_seconds": r.cooldown_seconds,
                "triggered_count": r.triggered_count,
                "enabled": r.enabled,
            }
            for r in self._alerts.values()
        ]

    def enable_alert(self, rule_id: str) -> bool:
        r = self._alerts.get(rule_id)
        if not r:
            return False
        r.enabled = True
        return True

    def disable_alert(self, rule_id: str) -> bool:
        r = self._alerts.get(rule_id)
        if not r:
            return False
        r.enabled = False
        return True

    def _check_alerts(self, name: str, namespace: str) -> None:
        """Check alert rules for a metric."""
        now = time.time()
        for r in self._alerts.values():
            if not r.enabled:
                continue
            if r.metric_name != name or r.namespace != namespace:
                continue
            if now - r.last_triggered < r.cooldown_seconds:
                continue

            agg = self.aggregate(name, namespace, r.window_seconds)
            if not agg or agg["count"] == 0:
                continue

            avg = agg["avg"]
            triggered = False
            if r.condition == "gt" and avg > r.threshold:
                triggered = True
            elif r.condition == "lt" and avg < r.threshold:
                triggered = True
            elif r.condition == "gte" and avg >= r.threshold:
                triggered = True
            elif r.condition == "lte" and avg <= r.threshold:
                triggered = True
            elif r.condition == "eq" and avg == r.threshold:
                triggered = True

            if triggered:
                r.last_triggered = now
                r.triggered_count += 1
                self._stats["total_alerts_triggered"] += 1
                if r.callback:
                    try:
                        r.callback(r.rule_id, name, namespace, avg)
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _percentile(self, sorted_values: List[float], p: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_values[int(k)]
        return sorted_values[int(f)] * (c - k) + sorted_values[int(c)] * (k - f)

    def _metric_to_dict(self, m: Metric) -> Dict:
        current = m.points[-1].value if m.points else None
        return {
            "name": m.name,
            "metric_type": m.metric_type,
            "namespace": m.namespace,
            "labels": m.labels,
            "unit": m.unit,
            "description": m.description,
            "current_value": current,
            "points_count": len(m.points),
            "created_at": m.created_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_metrics": len(self._metrics),
            "total_alerts": len(self._alerts),
            "total_namespaces": len(set(m.namespace for m in self._metrics.values())),
        }

    def reset(self) -> None:
        self._metrics.clear()
        self._alerts.clear()
        if hasattr(self, "_timers"):
            self._timers.clear()
        self._stats = {k: 0 for k in self._stats}
