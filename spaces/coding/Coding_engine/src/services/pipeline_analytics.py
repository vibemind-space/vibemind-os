"""
Pipeline Analytics Data Layer — collects, aggregates, and reports
pipeline execution metrics for dashboards and trend analysis.

Features:
- Pipeline run tracking (start/end/duration/status)
- Phase-level timing and success rates
- Agent performance aggregation
- Trend analysis (throughput, failure rates over time)
- Custom metric recording
- Time-bucketed aggregation for charts
- Export capabilities
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineRun:
    """Record of a single pipeline execution."""
    run_id: str
    project: str
    started_at: float
    status: RunStatus = RunStatus.RUNNING
    ended_at: float = 0.0
    phases: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    agent_times: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    tags: set = field(default_factory=set)


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Analytics Engine
# ---------------------------------------------------------------------------

class PipelineAnalytics:
    """Collects and reports pipeline execution analytics."""

    def __init__(self, max_runs: int = 500, max_metrics: int = 10000):
        self._max_runs = max_runs
        self._max_metrics = max_metrics

        # Run records: run_id → PipelineRun
        self._runs: Dict[str, PipelineRun] = {}

        # Custom metric time-series
        self._metrics: List[MetricPoint] = []

        # Aggregate counters
        self._counters: Dict[str, int] = defaultdict(int)

        # Stats
        self._stats = {
            "total_runs_started": 0,
            "total_runs_completed": 0,
            "total_runs_failed": 0,
            "total_metrics_recorded": 0,
        }

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def start_run(
        self,
        project: str,
        tags: Optional[set] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Start tracking a pipeline run. Returns run_id."""
        rid = f"run-{uuid.uuid4().hex[:8]}"
        self._runs[rid] = PipelineRun(
            run_id=rid,
            project=project,
            started_at=time.time(),
            metrics=metadata or {},
            tags=tags or set(),
        )
        self._stats["total_runs_started"] += 1
        self._prune_runs()
        return rid

    def end_run(
        self,
        run_id: str,
        status: str = "completed",
        error: str = "",
    ) -> bool:
        """End a pipeline run."""
        run = self._runs.get(run_id)
        if not run or run.status != RunStatus.RUNNING:
            return False
        run.status = RunStatus(status)
        run.ended_at = time.time()
        run.error = error
        if status == "completed":
            self._stats["total_runs_completed"] += 1
        elif status == "failed":
            self._stats["total_runs_failed"] += 1
        return True

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get run details."""
        run = self._runs.get(run_id)
        if not run:
            return None
        return self._run_to_dict(run)

    def list_runs(
        self,
        project: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List runs with filters."""
        results = []
        for run in sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True):
            if project and run.project != project:
                continue
            if status and run.status.value != status:
                continue
            results.append(self._run_to_dict(run))
            if len(results) >= limit:
                break
        return results

    def _run_to_dict(self, run: PipelineRun) -> Dict:
        duration = (run.ended_at or time.time()) - run.started_at
        return {
            "run_id": run.run_id,
            "project": run.project,
            "status": run.status.value,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "duration_seconds": round(duration, 2),
            "phases": dict(run.phases),
            "agent_times": dict(run.agent_times),
            "metrics": run.metrics,
            "error": run.error,
            "tags": sorted(run.tags),
        }

    # ------------------------------------------------------------------
    # Phase tracking
    # ------------------------------------------------------------------

    def record_phase(
        self,
        run_id: str,
        phase: str,
        duration_seconds: float,
        status: str = "completed",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Record a phase completion within a run."""
        run = self._runs.get(run_id)
        if not run:
            return False
        run.phases[phase] = {
            "duration_seconds": round(duration_seconds, 3),
            "status": status,
            "metadata": metadata or {},
            "recorded_at": time.time(),
        }
        return True

    def record_agent_time(
        self,
        run_id: str,
        agent_name: str,
        duration_seconds: float,
    ) -> bool:
        """Record an agent's contribution time within a run."""
        run = self._runs.get(run_id)
        if not run:
            return False
        run.agent_times[agent_name] = run.agent_times.get(agent_name, 0) + duration_seconds
        return True

    # ------------------------------------------------------------------
    # Custom metrics
    # ------------------------------------------------------------------

    def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        timestamp: float = 0.0,
    ) -> None:
        """Record a custom metric data point."""
        self._metrics.append(MetricPoint(
            name=name,
            value=value,
            timestamp=timestamp or time.time(),
            labels=labels or {},
        ))
        self._stats["total_metrics_recorded"] += 1
        self._prune_metrics()

    def get_metric_series(
        self,
        name: str,
        since: float = 0.0,
        labels: Optional[Dict[str, str]] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get time series data for a metric."""
        results = []
        for m in reversed(self._metrics):
            if m.name != name:
                continue
            if since and m.timestamp < since:
                continue
            if labels:
                if not all(m.labels.get(k) == v for k, v in labels.items()):
                    continue
            results.append({
                "name": m.name,
                "value": m.value,
                "timestamp": m.timestamp,
                "labels": m.labels,
            })
            if len(results) >= limit:
                break
        return list(reversed(results))

    def increment_counter(self, name: str, amount: int = 1) -> int:
        """Increment a counter. Returns new value."""
        self._counters[name] += amount
        return self._counters[name]

    def get_counter(self, name: str) -> int:
        """Get counter value."""
        return self._counters.get(name, 0)

    def list_counters(self) -> Dict[str, int]:
        """List all counters."""
        return dict(self._counters)

    # ------------------------------------------------------------------
    # Aggregation & analysis
    # ------------------------------------------------------------------

    def get_project_summary(self, project: str) -> Dict:
        """Get aggregate analytics for a project."""
        runs = [r for r in self._runs.values() if r.project == project]
        if not runs:
            return {"project": project, "total_runs": 0}

        completed = [r for r in runs if r.status == RunStatus.COMPLETED]
        failed = [r for r in runs if r.status == RunStatus.FAILED]

        durations = [(r.ended_at - r.started_at) for r in completed if r.ended_at > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0

        success_rate = len(completed) / len(runs) * 100 if runs else 0

        return {
            "project": project,
            "total_runs": len(runs),
            "completed": len(completed),
            "failed": len(failed),
            "success_rate": round(success_rate, 1),
            "avg_duration_seconds": round(avg_duration, 2),
            "min_duration_seconds": round(min(durations), 2) if durations else 0,
            "max_duration_seconds": round(max(durations), 2) if durations else 0,
        }

    def get_agent_performance(self, limit: int = 20) -> List[Dict]:
        """Get aggregate performance across all agents."""
        agent_totals: Dict[str, Dict] = defaultdict(lambda: {"total_time": 0, "run_count": 0})

        for run in self._runs.values():
            for agent, time_spent in run.agent_times.items():
                agent_totals[agent]["total_time"] += time_spent
                agent_totals[agent]["run_count"] += 1

        results = []
        for agent, data in agent_totals.items():
            avg = data["total_time"] / data["run_count"] if data["run_count"] > 0 else 0
            results.append({
                "agent_name": agent,
                "total_time_seconds": round(data["total_time"], 2),
                "run_count": data["run_count"],
                "avg_time_seconds": round(avg, 2),
            })

        results.sort(key=lambda x: x["total_time_seconds"], reverse=True)
        return results[:limit]

    def get_phase_performance(self) -> List[Dict]:
        """Get aggregate performance across all phases."""
        phase_data: Dict[str, Dict] = defaultdict(
            lambda: {"total_time": 0, "count": 0, "failures": 0})

        for run in self._runs.values():
            for phase, info in run.phases.items():
                phase_data[phase]["total_time"] += info.get("duration_seconds", 0)
                phase_data[phase]["count"] += 1
                if info.get("status") == "failed":
                    phase_data[phase]["failures"] += 1

        results = []
        for phase, data in phase_data.items():
            avg = data["total_time"] / data["count"] if data["count"] > 0 else 0
            fail_rate = data["failures"] / data["count"] * 100 if data["count"] > 0 else 0
            results.append({
                "phase": phase,
                "total_time_seconds": round(data["total_time"], 2),
                "count": data["count"],
                "avg_time_seconds": round(avg, 2),
                "failure_rate": round(fail_rate, 1),
            })

        return sorted(results, key=lambda x: x["total_time_seconds"], reverse=True)

    def get_throughput(self, window_seconds: float = 3600.0) -> Dict:
        """Get pipeline throughput within a time window."""
        cutoff = time.time() - window_seconds
        recent = [r for r in self._runs.values() if r.started_at >= cutoff]
        completed = [r for r in recent if r.status == RunStatus.COMPLETED]
        failed = [r for r in recent if r.status == RunStatus.FAILED]

        return {
            "window_seconds": window_seconds,
            "total_runs": len(recent),
            "completed": len(completed),
            "failed": len(failed),
            "runs_per_hour": round(len(recent) / (window_seconds / 3600), 2),
            "success_rate": round(len(completed) / len(recent) * 100, 1) if recent else 0,
        }

    def get_trend(
        self,
        metric_name: str,
        bucket_seconds: float = 3600.0,
        num_buckets: int = 24,
    ) -> List[Dict]:
        """Get metric trend over time buckets."""
        now = time.time()
        buckets = []

        for i in range(num_buckets):
            end = now - (i * bucket_seconds)
            start = end - bucket_seconds
            points = [m.value for m in self._metrics
                       if m.name == metric_name and start <= m.timestamp < end]

            bucket = {
                "bucket_start": start,
                "bucket_end": end,
                "count": len(points),
                "sum": round(sum(points), 4) if points else 0,
                "avg": round(sum(points) / len(points), 4) if points else 0,
                "min": round(min(points), 4) if points else 0,
                "max": round(max(points), 4) if points else 0,
            }
            buckets.append(bucket)

        return list(reversed(buckets))

    def list_projects(self) -> List[str]:
        """List all projects that have run data."""
        return sorted(set(r.project for r in self._runs.values()))

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_runs(self) -> None:
        if len(self._runs) <= self._max_runs:
            return
        # Remove oldest completed runs
        sorted_runs = sorted(self._runs.values(), key=lambda r: r.started_at)
        to_remove = len(self._runs) - self._max_runs
        removed = 0
        for run in sorted_runs:
            if run.status != RunStatus.RUNNING and removed < to_remove:
                del self._runs[run.run_id]
                removed += 1

    def _prune_metrics(self) -> None:
        if len(self._metrics) <= self._max_metrics:
            return
        keep = self._max_metrics // 2
        self._metrics = self._metrics[-keep:]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_runs": len(self._runs),
            "active_runs": sum(1 for r in self._runs.values()
                               if r.status == RunStatus.RUNNING),
            "total_metrics": len(self._metrics),
            "total_counters": len(self._counters),
            "total_projects": len(self.list_projects()),
        }

    def reset(self) -> None:
        self._runs.clear()
        self._metrics.clear()
        self._counters.clear()
        self._stats = {k: 0 for k in self._stats}
