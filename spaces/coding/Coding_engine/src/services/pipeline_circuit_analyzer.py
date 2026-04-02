"""Pipeline Circuit Analyzer – analyzes circuit health across pipeline stages.

Monitors pipeline stage health, detects failure patterns, and provides
circuit-level insights like failure rates, latency percentiles, and
stage dependency analysis.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _CircuitStage:
    stage_id: str
    name: str
    status: str  # healthy, degraded, failing, open
    total_calls: int
    total_failures: int
    total_latency: float
    min_latency: float
    max_latency: float
    consecutive_failures: int
    failure_threshold: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _CircuitEvent:
    event_id: str
    stage_name: str
    action: str  # call_success, call_failure, status_changed, reset
    latency: float
    timestamp: float


class PipelineCircuitAnalyzer:
    """Analyzes circuit health across pipeline stages."""

    STATUSES = ("healthy", "degraded", "failing", "open")

    def __init__(
        self,
        max_stages: int = 5000,
        max_history: int = 100000,
        failure_threshold: int = 5,
        degraded_threshold: float = 20.0,  # failure rate %
    ):
        self._stages: Dict[str, _CircuitStage] = {}
        self._name_index: Dict[str, str] = {}  # name -> stage_id
        self._history: List[_CircuitEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_stages = max_stages
        self._max_history = max_history
        self._failure_threshold = failure_threshold
        self._degraded_threshold = degraded_threshold
        self._seq = 0

        # stats
        self._total_registered = 0
        self._total_calls = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_stage(
        self,
        name: str,
        failure_threshold: int = 0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._stages) >= self._max_stages:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        sid = "cst-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        thresh = failure_threshold if failure_threshold > 0 else self._failure_threshold

        stage = _CircuitStage(
            stage_id=sid,
            name=name,
            status="healthy",
            total_calls=0,
            total_failures=0,
            total_latency=0.0,
            min_latency=float("inf"),
            max_latency=0.0,
            consecutive_failures=0,
            failure_threshold=thresh,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._stages[sid] = stage
        self._name_index[name] = sid
        self._total_registered += 1
        self._fire("stage_registered", {"stage_id": sid, "name": name})
        return sid

    def get_stage(self, name: str) -> Optional[Dict[str, Any]]:
        sid = self._name_index.get(name)
        if not sid:
            return None
        s = self._stages[sid]
        avg_latency = (s.total_latency / s.total_calls) if s.total_calls > 0 else 0.0
        failure_rate = (s.total_failures / s.total_calls * 100) if s.total_calls > 0 else 0.0
        return {
            "stage_id": s.stage_id,
            "name": s.name,
            "status": s.status,
            "total_calls": s.total_calls,
            "total_failures": s.total_failures,
            "failure_rate_pct": failure_rate,
            "avg_latency": avg_latency,
            "min_latency": s.min_latency if s.total_calls > 0 else 0.0,
            "max_latency": s.max_latency,
            "consecutive_failures": s.consecutive_failures,
            "failure_threshold": s.failure_threshold,
            "tags": list(s.tags),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }

    def remove_stage(self, name: str) -> bool:
        sid = self._name_index.pop(name, None)
        if not sid:
            return False
        self._stages.pop(sid, None)
        return True

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_success(self, name: str, latency: float = 0.0) -> bool:
        sid = self._name_index.get(name)
        if not sid:
            return False
        s = self._stages[sid]
        s.total_calls += 1
        s.total_latency += latency
        if latency < s.min_latency:
            s.min_latency = latency
        if latency > s.max_latency:
            s.max_latency = latency
        s.consecutive_failures = 0
        s.updated_at = time.time()
        self._total_calls += 1

        # Re-evaluate status
        old_status = s.status
        s.status = self._evaluate_status(s)
        if old_status != s.status:
            self._fire("status_changed", {"name": name, "from": old_status, "to": s.status})

        self._record_event(name, "call_success", latency)
        return True

    def record_failure(self, name: str, latency: float = 0.0) -> bool:
        sid = self._name_index.get(name)
        if not sid:
            return False
        s = self._stages[sid]
        s.total_calls += 1
        s.total_failures += 1
        s.total_latency += latency
        if latency < s.min_latency:
            s.min_latency = latency
        if latency > s.max_latency:
            s.max_latency = latency
        s.consecutive_failures += 1
        s.updated_at = time.time()
        self._total_calls += 1
        self._total_failures += 1

        # Re-evaluate status
        old_status = s.status
        s.status = self._evaluate_status(s)
        if old_status != s.status:
            self._fire("status_changed", {"name": name, "from": old_status, "to": s.status})

        self._record_event(name, "call_failure", latency)
        return True

    def _evaluate_status(self, stage: _CircuitStage) -> str:
        if stage.consecutive_failures >= stage.failure_threshold:
            return "open"
        if stage.total_calls > 0:
            rate = stage.total_failures / stage.total_calls * 100
            if rate >= self._degraded_threshold:
                return "failing"
            if rate > 0:
                return "degraded"
        return "healthy"

    def reset_stage(self, name: str) -> bool:
        sid = self._name_index.get(name)
        if not sid:
            return False
        s = self._stages[sid]
        s.total_calls = 0
        s.total_failures = 0
        s.total_latency = 0.0
        s.min_latency = float("inf")
        s.max_latency = 0.0
        s.consecutive_failures = 0
        s.status = "healthy"
        s.updated_at = time.time()
        self._record_event(name, "reset", 0.0)
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_stages(self, status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for s in self._stages.values():
            if status and s.status != status:
                continue
            if tag and tag not in s.tags:
                continue
            results.append(self.get_stage(s.name))
        return results

    def get_unhealthy(self) -> List[Dict[str, Any]]:
        return [self.get_stage(s.name) for s in self._stages.values() if s.status != "healthy"]

    def get_failure_rate(self, name: str) -> float:
        sid = self._name_index.get(name)
        if not sid:
            return 0.0
        s = self._stages[sid]
        if s.total_calls == 0:
            return 0.0
        return s.total_failures / s.total_calls * 100

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        stage_name: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if stage_name and ev.stage_name != stage_name:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "stage_name": ev.stage_name,
                "action": ev.action,
                "latency": ev.latency,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, stage_name: str, action: str, latency: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{stage_name}-{action}-{now}-{self._seq}"
        evid = "cev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _CircuitEvent(
            event_id=evid, stage_name=stage_name,
            action=action, latency=latency, timestamp=now,
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
        healthy = sum(1 for s in self._stages.values() if s.status == "healthy")
        unhealthy = len(self._stages) - healthy
        return {
            "current_stages": len(self._stages),
            "healthy_stages": healthy,
            "unhealthy_stages": unhealthy,
            "total_registered": self._total_registered,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._stages.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_calls = 0
        self._total_failures = 0
