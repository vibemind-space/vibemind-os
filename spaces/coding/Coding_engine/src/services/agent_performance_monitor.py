"""Agent performance monitor.

Tracks agent performance metrics including execution times, throughput,
resource usage, and quality scores. Provides analytics for optimization.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Metric:
    """A performance metric entry."""
    metric_id: str = ""
    agent: str = ""
    metric_type: str = ""  # latency, throughput, memory, cpu, quality
    value: float = 0.0
    unit: str = ""
    operation: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0
    seq: int = 0


@dataclass
class _Benchmark:
    """A performance benchmark."""
    benchmark_id: str = ""
    name: str = ""
    agent: str = ""
    metric_type: str = ""
    target_value: float = 0.0
    threshold_value: float = 0.0
    unit: str = ""
    tags: List[str] = field(default_factory=list)
    status: str = "active"  # active, disabled
    created_at: float = 0.0


class AgentPerformanceMonitor:
    """Monitors agent performance metrics."""

    METRIC_TYPES = ("latency", "throughput", "memory", "cpu", "quality")

    def __init__(self, max_metrics: int = 500000,
                 max_benchmarks: int = 5000):
        self._max_metrics = max_metrics
        self._max_benchmarks = max_benchmarks
        self._metrics: Dict[str, _Metric] = {}
        self._benchmarks: Dict[str, _Benchmark] = {}
        self._metric_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_metrics_recorded": 0,
            "total_benchmarks_created": 0,
            "total_threshold_violations": 0,
        }

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def record_metric(self, agent: str, metric_type: str, value: float,
                      unit: str = "", operation: str = "",
                      tags: Optional[List[str]] = None,
                      metadata: Optional[Dict] = None) -> str:
        """Record a performance metric."""
        if not agent or not metric_type:
            return ""
        if metric_type not in self.METRIC_TYPES:
            return ""
        if len(self._metrics) >= self._max_metrics:
            self._prune_metrics()

        self._metric_seq += 1
        mid = "pm-" + hashlib.md5(
            f"{agent}{metric_type}{time.time()}{self._metric_seq}".encode()
        ).hexdigest()[:12]

        self._metrics[mid] = _Metric(
            metric_id=mid,
            agent=agent,
            metric_type=metric_type,
            value=value,
            unit=unit,
            operation=operation,
            tags=tags or [],
            metadata=metadata or {},
            timestamp=time.time(),
            seq=self._metric_seq,
        )
        self._stats["total_metrics_recorded"] += 1

        # Check benchmarks
        for b in self._benchmarks.values():
            if b.status != "active":
                continue
            if b.agent and b.agent != agent:
                continue
            if b.metric_type != metric_type:
                continue
            if value > b.threshold_value:
                self._stats["total_threshold_violations"] += 1
                self._fire("threshold_violated", {
                    "metric_id": mid, "benchmark_id": b.benchmark_id,
                    "agent": agent, "value": value,
                    "threshold": b.threshold_value,
                })

        self._fire("metric_recorded", {
            "metric_id": mid, "agent": agent, "metric_type": metric_type,
        })
        return mid

    def get_metric(self, metric_id: str) -> Optional[Dict]:
        """Get metric info."""
        m = self._metrics.get(metric_id)
        if not m:
            return None
        return {
            "metric_id": m.metric_id,
            "agent": m.agent,
            "metric_type": m.metric_type,
            "value": m.value,
            "unit": m.unit,
            "operation": m.operation,
            "tags": list(m.tags),
            "seq": m.seq,
        }

    def remove_metric(self, metric_id: str) -> bool:
        """Remove a metric."""
        if metric_id not in self._metrics:
            return False
        del self._metrics[metric_id]
        return True

    # ------------------------------------------------------------------
    # Benchmarks
    # ------------------------------------------------------------------

    def create_benchmark(self, name: str, metric_type: str,
                         target_value: float, threshold_value: float,
                         agent: str = "", unit: str = "",
                         tags: Optional[List[str]] = None) -> str:
        """Create a performance benchmark."""
        if not name or not metric_type:
            return ""
        if metric_type not in self.METRIC_TYPES:
            return ""
        if len(self._benchmarks) >= self._max_benchmarks:
            return ""

        bid = "bm-" + hashlib.md5(
            f"{name}{metric_type}{time.time()}{len(self._benchmarks)}".encode()
        ).hexdigest()[:12]

        self._benchmarks[bid] = _Benchmark(
            benchmark_id=bid,
            name=name,
            agent=agent,
            metric_type=metric_type,
            target_value=target_value,
            threshold_value=threshold_value,
            unit=unit,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_benchmarks_created"] += 1
        return bid

    def get_benchmark(self, benchmark_id: str) -> Optional[Dict]:
        """Get benchmark info."""
        b = self._benchmarks.get(benchmark_id)
        if not b:
            return None
        return {
            "benchmark_id": b.benchmark_id,
            "name": b.name,
            "agent": b.agent,
            "metric_type": b.metric_type,
            "target_value": b.target_value,
            "threshold_value": b.threshold_value,
            "unit": b.unit,
            "status": b.status,
            "tags": list(b.tags),
        }

    def disable_benchmark(self, benchmark_id: str) -> bool:
        """Disable a benchmark."""
        b = self._benchmarks.get(benchmark_id)
        if not b or b.status == "disabled":
            return False
        b.status = "disabled"
        return True

    def enable_benchmark(self, benchmark_id: str) -> bool:
        """Enable a benchmark."""
        b = self._benchmarks.get(benchmark_id)
        if not b or b.status == "active":
            return False
        b.status = "active"
        return True

    def remove_benchmark(self, benchmark_id: str) -> bool:
        """Remove a benchmark."""
        if benchmark_id not in self._benchmarks:
            return False
        del self._benchmarks[benchmark_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_metrics(self, agent: Optional[str] = None,
                       metric_type: Optional[str] = None,
                       operation: Optional[str] = None,
                       tag: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """Search metrics."""
        result = []
        for m in self._metrics.values():
            if agent and m.agent != agent:
                continue
            if metric_type and m.metric_type != metric_type:
                continue
            if operation and m.operation != operation:
                continue
            if tag and tag not in m.tags:
                continue
            result.append({
                "metric_id": m.metric_id,
                "agent": m.agent,
                "metric_type": m.metric_type,
                "value": m.value,
                "unit": m.unit,
                "operation": m.operation,
                "seq": m.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_agent_summary(self, agent: str) -> Dict:
        """Get performance summary for an agent."""
        by_type: Dict[str, List[float]] = {}
        for m in self._metrics.values():
            if m.agent != agent:
                continue
            if m.metric_type not in by_type:
                by_type[m.metric_type] = []
            by_type[m.metric_type].append(m.value)

        summary = {}
        for mt, values in by_type.items():
            summary[mt] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
            }
        return {"agent": agent, "metrics": summary}

    def get_metric_averages(self, metric_type: str) -> List[Dict]:
        """Get average metric values per agent."""
        agent_values: Dict[str, List[float]] = {}
        for m in self._metrics.values():
            if m.metric_type != metric_type:
                continue
            if m.agent not in agent_values:
                agent_values[m.agent] = []
            agent_values[m.agent].append(m.value)

        result = []
        for agent, values in agent_values.items():
            result.append({
                "agent": agent,
                "avg": round(sum(values) / len(values), 2),
                "count": len(values),
            })
        result.sort(key=lambda x: x["avg"])
        return result

    def list_benchmarks(self, status: Optional[str] = None,
                        tag: Optional[str] = None) -> List[Dict]:
        """List benchmarks."""
        result = []
        for b in self._benchmarks.values():
            if status and b.status != status:
                continue
            if tag and tag not in b.tags:
                continue
            result.append({
                "benchmark_id": b.benchmark_id,
                "name": b.name,
                "metric_type": b.metric_type,
                "target_value": b.target_value,
                "threshold_value": b.threshold_value,
                "status": b.status,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_metrics(self) -> None:
        """Remove oldest metrics."""
        items = list(self._metrics.items())
        items.sort(key=lambda x: x[1].seq)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._metrics[k]

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
            "current_benchmarks": len(self._benchmarks),
            "active_benchmarks": sum(
                1 for b in self._benchmarks.values() if b.status == "active"
            ),
        }

    def reset(self) -> None:
        self._metrics.clear()
        self._benchmarks.clear()
        self._metric_seq = 0
        self._stats = {k: 0 for k in self._stats}
