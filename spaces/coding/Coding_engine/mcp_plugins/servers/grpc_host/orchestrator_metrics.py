#!/usr/bin/env python3
"""
Orchestrator Metrics - Iteration 5

Metriken-Sammlung und Export für Dashboard und Monitoring.

Features:
- Echtzeit-Metriken (Counters, Gauges, Histogramme)
- Dashboard-Export
- Performance-Tracking
- Alerting-Thresholds
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
from threading import Lock
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Ein einzelner Metrik-Datenpunkt"""
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Ein monoton steigender Counter"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0
        self._lock = Lock()

    def inc(self, amount: int = 1):
        """Erhöht den Counter"""
        with self._lock:
            self._value += amount

    @property
    def value(self) -> int:
        return self._value


class Gauge:
    """Eine Gauge-Metrik (kann steigen und fallen)"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = Lock()

    def set(self, value: float):
        """Setzt den Wert"""
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0):
        """Erhöht den Wert"""
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0):
        """Verringert den Wert"""
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class Histogram:
    """Ein Histogram für Latenz/Dauer-Verteilung"""

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: List[float] = None
    ):
        self.name = name
        self.description = description
        self.buckets = buckets or [10, 50, 100, 250, 500, 1000, 2500, 5000, 10000]

        self._counts: Dict[float, int] = {b: 0 for b in self.buckets}
        self._counts[float('inf')] = 0
        self._sum = 0.0
        self._count = 0
        self._lock = Lock()

    def observe(self, value: float):
        """Fügt eine Beobachtung hinzu"""
        with self._lock:
            self._sum += value
            self._count += 1

            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[bucket] += 1
                    break
            else:
                self._counts[float('inf')] += 1

    @property
    def avg(self) -> float:
        return self._sum / self._count if self._count > 0 else 0.0

    def percentile(self, p: float) -> float:
        """Berechnet approximatives Perzentil"""
        if self._count == 0:
            return 0.0

        target = self._count * p / 100

        cumulative = 0
        prev_bucket = 0
        for bucket in sorted(self._counts.keys()):
            cumulative += self._counts[bucket]
            if cumulative >= target:
                return bucket
            prev_bucket = bucket

        return self.buckets[-1] if self.buckets else 0


class RollingWindow:
    """Rolling Window für Zeitreihen"""

    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        self._points: deque = deque()
        self._lock = Lock()

    def add(self, value: float, timestamp: Optional[float] = None):
        """Fügt einen Datenpunkt hinzu"""
        ts = timestamp or time.time()

        with self._lock:
            self._points.append((ts, value))
            self._cleanup()

    def _cleanup(self):
        """Entfernt alte Punkte"""
        cutoff = time.time() - self.window_seconds
        while self._points and self._points[0][0] < cutoff:
            self._points.popleft()

    def avg(self) -> float:
        """Durchschnitt im Window"""
        with self._lock:
            self._cleanup()
            if not self._points:
                return 0.0
            return sum(v for _, v in self._points) / len(self._points)

    def rate(self) -> float:
        """Rate pro Sekunde im Window"""
        with self._lock:
            self._cleanup()
            if len(self._points) < 2:
                return 0.0
            duration = self._points[-1][0] - self._points[0][0]
            if duration <= 0:
                return 0.0
            return len(self._points) / duration


class OrchestratorMetrics:
    """
    Zentrale Metrik-Sammlung für den Orchestrator.

    Sammelt und exportiert Metriken für Dashboard.
    """

    def __init__(self):
        # Counters
        self.tasks_total = Counter("tasks_total", "Total tasks executed")
        self.tasks_success = Counter("tasks_success", "Successful tasks")
        self.tasks_failed = Counter("tasks_failed", "Failed tasks")
        self.tool_calls_total = Counter("tool_calls_total", "Total tool calls")
        self.tool_calls_success = Counter("tool_calls_success", "Successful tool calls")
        self.tool_calls_failed = Counter("tool_calls_failed", "Failed tool calls")
        self.cache_hits = Counter("cache_hits", "Cache hits")
        self.cache_misses = Counter("cache_misses", "Cache misses")
        self.circuit_opens = Counter("circuit_opens", "Circuit breaker opens")
        self.recoveries_attempted = Counter("recoveries_attempted", "Recovery attempts")
        self.recoveries_success = Counter("recoveries_success", "Successful recoveries")

        # Gauges
        self.active_tasks = Gauge("active_tasks", "Currently running tasks")
        self.active_tools = Gauge("active_tools", "Tools currently loaded")
        self.circuits_open = Gauge("circuits_open", "Open circuit breakers")
        self.memory_usage_mb = Gauge("memory_usage_mb", "Memory usage in MB")

        # Histograms
        self.task_duration = Histogram("task_duration_ms", "Task duration in ms")
        self.tool_call_duration = Histogram("tool_call_duration_ms", "Tool call duration in ms")

        # Rolling Windows
        self.success_rate_window = RollingWindow(300)  # 5 min
        self.throughput_window = RollingWindow(60)     # 1 min

        # Start time
        self._start_time = time.time()

        logger.info("OrchestratorMetrics initialized")

    def record_task_started(self):
        """Markiert Start eines Tasks"""
        self.active_tasks.inc()
        self.throughput_window.add(1)

    def record_task_completed(self, success: bool, duration_ms: int):
        """Markiert Ende eines Tasks"""
        self.tasks_total.inc()
        self.active_tasks.dec()
        self.task_duration.observe(duration_ms)
        self.success_rate_window.add(1 if success else 0)

        if success:
            self.tasks_success.inc()
        else:
            self.tasks_failed.inc()

    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_ms: int,
        from_cache: bool = False
    ):
        """Markiert einen Tool-Call"""
        self.tool_calls_total.inc()
        self.tool_call_duration.observe(duration_ms)

        if success:
            self.tool_calls_success.inc()
        else:
            self.tool_calls_failed.inc()

        if from_cache:
            self.cache_hits.inc()
        else:
            self.cache_misses.inc()

    def record_recovery_attempt(self, success: bool):
        """Markiert einen Recovery-Versuch"""
        self.recoveries_attempted.inc()
        if success:
            self.recoveries_success.inc()

    def record_circuit_open(self):
        """Markiert das Öffnen eines Circuit Breakers"""
        self.circuit_opens.inc()
        self.circuits_open.inc()

    def record_circuit_close(self):
        """Markiert das Schließen eines Circuit Breakers"""
        self.circuits_open.dec()

    def update_memory_usage(self):
        """Aktualisiert Memory-Usage"""
        try:
            import psutil
            process = psutil.Process()
            self.memory_usage_mb.set(process.memory_info().rss / 1024 / 1024)
        except ImportError:
            pass

    def export_for_dashboard(self) -> Dict[str, Any]:
        """
        Exportiert alle Metriken für das Dashboard.

        Returns:
            Dict mit allen Metriken
        """
        uptime_seconds = time.time() - self._start_time

        # Success Rates berechnen
        task_success_rate = 0.0
        if self.tasks_total.value > 0:
            task_success_rate = self.tasks_success.value / self.tasks_total.value * 100

        tool_success_rate = 0.0
        if self.tool_calls_total.value > 0:
            tool_success_rate = self.tool_calls_success.value / self.tool_calls_total.value * 100

        cache_hit_rate = 0.0
        total_cache = self.cache_hits.value + self.cache_misses.value
        if total_cache > 0:
            cache_hit_rate = self.cache_hits.value / total_cache * 100

        recovery_success_rate = 0.0
        if self.recoveries_attempted.value > 0:
            recovery_success_rate = self.recoveries_success.value / self.recoveries_attempted.value * 100

        return {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": int(uptime_seconds),
            "uptime_human": str(timedelta(seconds=int(uptime_seconds))),

            # Counters
            "counters": {
                "tasks_total": self.tasks_total.value,
                "tasks_success": self.tasks_success.value,
                "tasks_failed": self.tasks_failed.value,
                "tool_calls_total": self.tool_calls_total.value,
                "tool_calls_success": self.tool_calls_success.value,
                "tool_calls_failed": self.tool_calls_failed.value,
                "cache_hits": self.cache_hits.value,
                "cache_misses": self.cache_misses.value,
                "circuit_opens": self.circuit_opens.value,
                "recoveries_attempted": self.recoveries_attempted.value,
                "recoveries_success": self.recoveries_success.value,
            },

            # Gauges
            "gauges": {
                "active_tasks": self.active_tasks.value,
                "active_tools": self.active_tools.value,
                "circuits_open": self.circuits_open.value,
                "memory_usage_mb": f"{self.memory_usage_mb.value:.1f}",
            },

            # Rates
            "rates": {
                "task_success_rate": f"{task_success_rate:.1f}%",
                "tool_success_rate": f"{tool_success_rate:.1f}%",
                "cache_hit_rate": f"{cache_hit_rate:.1f}%",
                "recovery_success_rate": f"{recovery_success_rate:.1f}%",
                "rolling_success_rate": f"{self.success_rate_window.avg() * 100:.1f}%",
                "throughput_per_sec": f"{self.throughput_window.rate():.2f}",
            },

            # Latencies
            "latencies": {
                "task_avg_ms": f"{self.task_duration.avg:.1f}",
                "task_p50_ms": f"{self.task_duration.percentile(50):.1f}",
                "task_p95_ms": f"{self.task_duration.percentile(95):.1f}",
                "tool_avg_ms": f"{self.tool_call_duration.avg:.1f}",
                "tool_p50_ms": f"{self.tool_call_duration.percentile(50):.1f}",
                "tool_p95_ms": f"{self.tool_call_duration.percentile(95):.1f}",
            },
        }

    def export_prometheus(self) -> str:
        """
        Exportiert Metriken im Prometheus-Format.

        Returns:
            String im Prometheus Text-Format
        """
        lines = []

        # Counters
        counters = [
            ("orchestrator_tasks_total", self.tasks_total.value),
            ("orchestrator_tasks_success_total", self.tasks_success.value),
            ("orchestrator_tasks_failed_total", self.tasks_failed.value),
            ("orchestrator_tool_calls_total", self.tool_calls_total.value),
            ("orchestrator_cache_hits_total", self.cache_hits.value),
        ]

        for name, value in counters:
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")

        # Gauges
        gauges = [
            ("orchestrator_active_tasks", self.active_tasks.value),
            ("orchestrator_circuits_open", self.circuits_open.value),
        ]

        for name, value in gauges:
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {value}")

        return "\n".join(lines)

    def reset(self):
        """Setzt alle Metriken zurück (für Tests)"""
        self.__init__()

    def get_alerts(self) -> List[Dict[str, Any]]:
        """
        Prüft Alert-Conditions.

        Returns:
            Liste von aktiven Alerts
        """
        alerts = []

        # Alert: Niedrige Erfolgsrate
        if self.tasks_total.value >= 10:
            rate = self.tasks_success.value / self.tasks_total.value * 100
            if rate < 70:
                alerts.append({
                    "level": "warning",
                    "metric": "task_success_rate",
                    "value": f"{rate:.1f}%",
                    "threshold": "70%",
                    "message": f"Task success rate below 70%: {rate:.1f}%"
                })

        # Alert: Viele offene Circuits
        if self.circuits_open.value >= 3:
            alerts.append({
                "level": "warning",
                "metric": "circuits_open",
                "value": self.circuits_open.value,
                "threshold": 3,
                "message": f"{int(self.circuits_open.value)} circuit breakers are open"
            })

        # Alert: Hohe Latenz
        if self.task_duration._count >= 5 and self.task_duration.avg > 30000:
            alerts.append({
                "level": "warning",
                "metric": "task_avg_duration",
                "value": f"{self.task_duration.avg:.0f}ms",
                "threshold": "30000ms",
                "message": f"Average task duration is high: {self.task_duration.avg:.0f}ms"
            })

        return alerts


# Globale Instanz
_metrics: Optional[OrchestratorMetrics] = None


def get_metrics() -> OrchestratorMetrics:
    """Gibt die globale Metrik-Instanz zurück"""
    global _metrics
    if _metrics is None:
        _metrics = OrchestratorMetrics()
    return _metrics


# =============================================================================
# Test
# =============================================================================

def test_metrics():
    """Test der OrchestratorMetrics"""
    print("=== Orchestrator Metrics Test ===\n")

    metrics = OrchestratorMetrics()

    # Simuliere einige Tasks
    print("1. Simulating tasks:")
    for i in range(10):
        metrics.record_task_started()
        success = i % 3 != 0  # 7/10 erfolgreich
        duration = 100 + i * 50
        metrics.record_task_completed(success, duration)
        print(f"   Task {i+1}: success={success}, duration={duration}ms")

    # Simuliere Tool Calls
    print("\n2. Simulating tool calls:")
    for i in range(20):
        success = i % 4 != 0
        cached = i % 5 == 0
        metrics.record_tool_call(f"tool_{i}", success, 50 + i * 10, cached)

    # Ein paar Recoveries
    metrics.record_recovery_attempt(True)
    metrics.record_recovery_attempt(False)
    metrics.record_recovery_attempt(True)

    # Circuit öffnen
    metrics.record_circuit_open()

    # Export
    print("\n3. Dashboard export:")
    export = metrics.export_for_dashboard()
    print(json.dumps(export, indent=2))

    # Alerts
    print("\n4. Alerts:")
    alerts = metrics.get_alerts()
    for alert in alerts:
        print(f"   [{alert['level']}] {alert['message']}")

    # Prometheus
    print("\n5. Prometheus format:")
    print(metrics.export_prometheus()[:500] + "...")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_metrics()
