"""Pipeline anomaly detector.

Detects anomalies in pipeline metrics using statistical methods.
Supports threshold-based, z-score, and moving average detection.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Metric:
    """Internal metric series."""
    metric_id: str = ""
    name: str = ""
    source: str = ""
    detection_method: str = "threshold"
    threshold_high: Optional[float] = None
    threshold_low: Optional[float] = None
    z_score_limit: float = 3.0
    window_size: int = 30
    values: List[float] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0


@dataclass
class _Anomaly:
    """Internal anomaly record."""
    anomaly_id: str = ""
    metric_id: str = ""
    metric_name: str = ""
    value: float = 0.0
    expected_range: str = ""
    severity: str = "warning"  # info, warning, critical
    detection_method: str = ""
    acknowledged: bool = False
    timestamp: float = 0.0


class PipelineAnomalyDetector:
    """Detects anomalies in pipeline metrics."""

    DETECTION_METHODS = ("threshold", "z_score", "moving_average", "rate_of_change")
    SEVERITIES = ("info", "warning", "critical")

    def __init__(self, max_metrics: int = 5000, max_values_per_metric: int = 1000,
                 max_anomalies: int = 10000):
        self._max_metrics = max_metrics
        self._max_values = max_values_per_metric
        self._max_anomalies = max_anomalies
        self._metrics: Dict[str, _Metric] = {}
        self._anomalies: List[_Anomaly] = []
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_metrics": 0,
            "total_values_recorded": 0,
            "total_anomalies_detected": 0,
            "total_acknowledged": 0,
        }

    # ------------------------------------------------------------------
    # Metric registration
    # ------------------------------------------------------------------

    def register_metric(self, name: str, source: str = "",
                        detection_method: str = "threshold",
                        threshold_high: Optional[float] = None,
                        threshold_low: Optional[float] = None,
                        z_score_limit: float = 3.0,
                        window_size: int = 30,
                        tags: Optional[List[str]] = None) -> str:
        """Register a metric to monitor."""
        if not name:
            return ""
        if detection_method not in self.DETECTION_METHODS:
            return ""
        if len(self._metrics) >= self._max_metrics:
            return ""

        mid = "metric-" + hashlib.md5(f"{name}{source}{time.time()}".encode()).hexdigest()[:12]
        self._metrics[mid] = _Metric(
            metric_id=mid,
            name=name,
            source=source,
            detection_method=detection_method,
            threshold_high=threshold_high,
            threshold_low=threshold_low,
            z_score_limit=z_score_limit,
            window_size=window_size,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_metrics"] += 1
        return mid

    def get_metric(self, metric_id: str) -> Optional[Dict]:
        """Get metric info."""
        m = self._metrics.get(metric_id)
        if not m:
            return None
        return {
            "metric_id": m.metric_id,
            "name": m.name,
            "source": m.source,
            "detection_method": m.detection_method,
            "threshold_high": m.threshold_high,
            "threshold_low": m.threshold_low,
            "z_score_limit": m.z_score_limit,
            "window_size": m.window_size,
            "value_count": len(m.values),
            "tags": list(m.tags),
        }

    def remove_metric(self, metric_id: str) -> bool:
        """Remove a metric."""
        if metric_id not in self._metrics:
            return False
        del self._metrics[metric_id]
        return True

    # ------------------------------------------------------------------
    # Value recording and anomaly detection
    # ------------------------------------------------------------------

    def record_value(self, metric_id: str, value: float) -> Optional[Dict]:
        """Record a value and check for anomalies. Returns anomaly dict if detected."""
        m = self._metrics.get(metric_id)
        if not m:
            return None

        now = time.time()
        m.values.append(value)
        m.timestamps.append(now)
        self._stats["total_values_recorded"] += 1

        # Prune old values
        if len(m.values) > self._max_values:
            excess = len(m.values) - self._max_values
            m.values = m.values[excess:]
            m.timestamps = m.timestamps[excess:]

        # Check for anomaly
        anomaly = self._detect(m, value)
        if anomaly:
            if len(self._anomalies) >= self._max_anomalies:
                self._anomalies = self._anomalies[self._max_anomalies // 2:]
            self._anomalies.append(anomaly)
            self._stats["total_anomalies_detected"] += 1
            self._fire("anomaly_detected", {
                "anomaly_id": anomaly.anomaly_id,
                "metric_name": m.name,
                "value": value,
                "severity": anomaly.severity,
            })
            return {
                "anomaly_id": anomaly.anomaly_id,
                "metric_id": metric_id,
                "metric_name": m.name,
                "value": value,
                "expected_range": anomaly.expected_range,
                "severity": anomaly.severity,
                "detection_method": anomaly.detection_method,
            }
        return None

    def _detect(self, m: _Metric, value: float) -> Optional[_Anomaly]:
        """Run anomaly detection based on configured method."""
        if m.detection_method == "threshold":
            return self._detect_threshold(m, value)
        elif m.detection_method == "z_score":
            return self._detect_z_score(m, value)
        elif m.detection_method == "moving_average":
            return self._detect_moving_avg(m, value)
        elif m.detection_method == "rate_of_change":
            return self._detect_rate_change(m, value)
        return None

    def _detect_threshold(self, m: _Metric, value: float) -> Optional[_Anomaly]:
        """Threshold-based detection."""
        is_anomaly = False
        expected = ""

        if m.threshold_high is not None and value > m.threshold_high:
            is_anomaly = True
            expected = f"<= {m.threshold_high}"
        elif m.threshold_low is not None and value < m.threshold_low:
            is_anomaly = True
            expected = f">= {m.threshold_low}"

        if not is_anomaly:
            return None

        severity = "warning"
        if m.threshold_high is not None and value > m.threshold_high * 1.5:
            severity = "critical"
        elif m.threshold_low is not None and m.threshold_low != 0 and value < m.threshold_low * 0.5:
            severity = "critical"

        return _Anomaly(
            anomaly_id="anom-" + hashlib.md5(
                f"{m.metric_id}{value}{time.time()}".encode()
            ).hexdigest()[:12],
            metric_id=m.metric_id,
            metric_name=m.name,
            value=value,
            expected_range=expected,
            severity=severity,
            detection_method="threshold",
            timestamp=time.time(),
        )

    def _detect_z_score(self, m: _Metric, value: float) -> Optional[_Anomaly]:
        """Z-score based detection."""
        if len(m.values) < 10:
            return None

        window = m.values[-m.window_size:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(variance) if variance > 0 else 0

        if std == 0:
            return None

        z = abs(value - mean) / std
        if z <= m.z_score_limit:
            return None

        severity = "warning"
        if z > m.z_score_limit * 2:
            severity = "critical"

        return _Anomaly(
            anomaly_id="anom-" + hashlib.md5(
                f"{m.metric_id}{value}{time.time()}".encode()
            ).hexdigest()[:12],
            metric_id=m.metric_id,
            metric_name=m.name,
            value=value,
            expected_range=f"{round(mean - m.z_score_limit * std, 2)} to {round(mean + m.z_score_limit * std, 2)}",
            severity=severity,
            detection_method="z_score",
            timestamp=time.time(),
        )

    def _detect_moving_avg(self, m: _Metric, value: float) -> Optional[_Anomaly]:
        """Moving average deviation detection."""
        if len(m.values) < m.window_size:
            return None

        window = m.values[-m.window_size - 1:-1]  # Exclude current
        mean = sum(window) / len(window)
        deviation = abs(value - mean) / mean if mean != 0 else 0

        if deviation <= 0.5:  # >50% deviation
            return None

        severity = "warning"
        if deviation > 1.0:
            severity = "critical"

        return _Anomaly(
            anomaly_id="anom-" + hashlib.md5(
                f"{m.metric_id}{value}{time.time()}".encode()
            ).hexdigest()[:12],
            metric_id=m.metric_id,
            metric_name=m.name,
            value=value,
            expected_range=f"within 50% of {round(mean, 2)}",
            severity=severity,
            detection_method="moving_average",
            timestamp=time.time(),
        )

    def _detect_rate_change(self, m: _Metric, value: float) -> Optional[_Anomaly]:
        """Rate of change detection."""
        if len(m.values) < 2:
            return None

        prev = m.values[-2]
        if prev == 0:
            return None

        rate = abs(value - prev) / abs(prev)
        if rate <= 0.5:  # >50% change
            return None

        severity = "warning"
        if rate > 1.0:
            severity = "critical"

        return _Anomaly(
            anomaly_id="anom-" + hashlib.md5(
                f"{m.metric_id}{value}{time.time()}".encode()
            ).hexdigest()[:12],
            metric_id=m.metric_id,
            metric_name=m.name,
            value=value,
            expected_range=f"within 50% of {prev}",
            severity=severity,
            detection_method="rate_of_change",
            timestamp=time.time(),
        )

    # ------------------------------------------------------------------
    # Anomaly queries
    # ------------------------------------------------------------------

    def get_anomalies(self, metric_id: Optional[str] = None,
                      severity: Optional[str] = None,
                      acknowledged: Optional[bool] = None,
                      limit: int = 50) -> List[Dict]:
        """Get anomalies with optional filters."""
        result = []
        for a in reversed(self._anomalies):  # Most recent first
            if metric_id and a.metric_id != metric_id:
                continue
            if severity and a.severity != severity:
                continue
            if acknowledged is not None and a.acknowledged != acknowledged:
                continue
            result.append({
                "anomaly_id": a.anomaly_id,
                "metric_id": a.metric_id,
                "metric_name": a.metric_name,
                "value": a.value,
                "expected_range": a.expected_range,
                "severity": a.severity,
                "detection_method": a.detection_method,
                "acknowledged": a.acknowledged,
                "timestamp": a.timestamp,
            })
            if len(result) >= limit:
                break
        return result

    def acknowledge_anomaly(self, anomaly_id: str) -> bool:
        """Acknowledge an anomaly."""
        for a in self._anomalies:
            if a.anomaly_id == anomaly_id:
                if a.acknowledged:
                    return False
                a.acknowledged = True
                self._stats["total_acknowledged"] += 1
                return True
        return False

    def get_metric_health(self, metric_id: str) -> Dict:
        """Get health summary for a metric."""
        m = self._metrics.get(metric_id)
        if not m:
            return {}

        recent_anomalies = sum(
            1 for a in self._anomalies
            if a.metric_id == metric_id and time.time() - a.timestamp < 3600
        )
        total_anomalies = sum(
            1 for a in self._anomalies if a.metric_id == metric_id
        )

        status = "healthy"
        if recent_anomalies > 5:
            status = "critical"
        elif recent_anomalies > 0:
            status = "degraded"

        stats_data: Dict[str, Any] = {}
        if m.values:
            stats_data["min"] = min(m.values)
            stats_data["max"] = max(m.values)
            stats_data["mean"] = round(sum(m.values) / len(m.values), 4)
            stats_data["latest"] = m.values[-1]
            stats_data["count"] = len(m.values)

        return {
            "metric_id": metric_id,
            "name": m.name,
            "status": status,
            "recent_anomalies": recent_anomalies,
            "total_anomalies": total_anomalies,
            "statistics": stats_data,
        }

    def get_severity_summary(self) -> Dict[str, int]:
        """Get count of anomalies by severity."""
        summary: Dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
        for a in self._anomalies:
            if a.severity in summary:
                summary[a.severity] += 1
        return summary

    def list_metrics(self, source: Optional[str] = None,
                     tag: Optional[str] = None) -> List[Dict]:
        """List registered metrics."""
        result = []
        for m in self._metrics.values():
            if source and m.source != source:
                continue
            if tag and tag not in m.tags:
                continue
            result.append({
                "metric_id": m.metric_id,
                "name": m.name,
                "source": m.source,
                "detection_method": m.detection_method,
                "value_count": len(m.values),
                "tags": list(m.tags),
            })
        return result

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_metrics": len(self._metrics),
            "current_anomalies": len(self._anomalies),
        }

    def reset(self) -> None:
        self._metrics.clear()
        self._anomalies.clear()
        self._stats = {k: 0 for k in self._stats}
