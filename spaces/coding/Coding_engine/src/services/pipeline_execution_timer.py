"""Pipeline execution timer - track and analyze execution times."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class TimerEntry:
    """A single timer entry."""
    timer_id: str = ""
    name: str = ""
    category: str = ""
    owner: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    duration_ms: float = 0.0
    status: str = "running"  # running, completed, failed, cancelled
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class PipelineExecutionTimer:
    """Track execution times for pipeline operations."""

    CATEGORIES = (
        "pipeline", "task", "agent", "build", "test",
        "deploy", "validate", "transform", "custom",
    )

    def __init__(self, max_timers: int = 100000, slow_threshold_ms: float = 5000.0):
        self._max_timers = max(1, max_timers)
        self._slow_threshold = slow_threshold_ms
        self._timers: Dict[str, TimerEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_started": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_slow": 0,
        }

    # --- Timer Operations ---

    def start_timer(
        self,
        name: str,
        category: str = "custom",
        owner: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Start a timer. Returns timer_id."""
        if not name:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if len(self._timers) >= self._max_timers:
            return ""

        tid = f"timer-{uuid.uuid4().hex[:12]}"
        self._timers[tid] = TimerEntry(
            timer_id=tid,
            name=name,
            category=category,
            owner=owner,
            started_at=time.time(),
            status="running",
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )
        self._stats["total_started"] += 1
        return tid

    def stop_timer(self, timer_id: str, status: str = "completed") -> float:
        """Stop a timer. Returns duration_ms or -1 on failure."""
        t = self._timers.get(timer_id)
        if not t or t.status != "running":
            return -1.0
        if status not in ("completed", "failed", "cancelled"):
            return -1.0

        t.ended_at = time.time()
        t.duration_ms = (t.ended_at - t.started_at) * 1000.0
        t.status = status

        if status == "completed":
            self._stats["total_completed"] += 1
        elif status == "failed":
            self._stats["total_failed"] += 1

        if t.duration_ms >= self._slow_threshold:
            self._stats["total_slow"] += 1
            self._fire("slow_execution", {"timer_id": timer_id, "duration_ms": t.duration_ms})

        self._fire("timer_stopped", {"timer_id": timer_id, "duration_ms": t.duration_ms})
        return t.duration_ms

    def get_timer(self, timer_id: str) -> Optional[Dict]:
        """Get timer details."""
        t = self._timers.get(timer_id)
        if not t:
            return None
        duration = t.duration_ms
        if t.status == "running":
            duration = (time.time() - t.started_at) * 1000.0
        return {
            "timer_id": t.timer_id,
            "name": t.name,
            "category": t.category,
            "owner": t.owner,
            "status": t.status,
            "started_at": t.started_at,
            "ended_at": t.ended_at,
            "duration_ms": round(duration, 2),
            "tags": list(t.tags),
        }

    def remove_timer(self, timer_id: str) -> bool:
        """Remove a timer."""
        if timer_id not in self._timers:
            return False
        del self._timers[timer_id]
        return True

    # --- Queries ---

    def list_timers(
        self,
        status: str = "",
        category: str = "",
        owner: str = "",
        tag: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """List timers with filters."""
        results = []
        for t in self._timers.values():
            if status and t.status != status:
                continue
            if category and t.category != category:
                continue
            if owner and t.owner != owner:
                continue
            if tag and tag not in t.tags:
                continue
            duration = t.duration_ms
            if t.status == "running":
                duration = (time.time() - t.started_at) * 1000.0
            results.append({
                "timer_id": t.timer_id,
                "name": t.name,
                "category": t.category,
                "owner": t.owner,
                "status": t.status,
                "duration_ms": round(duration, 2),
            })
        results.sort(key=lambda x: -x["duration_ms"])
        return results[:limit]

    def get_running_timers(self) -> List[Dict]:
        """Get all currently running timers."""
        return self.list_timers(status="running")

    def get_slow_executions(self, threshold_ms: float = 0.0) -> List[Dict]:
        """Get completed timers exceeding threshold."""
        thresh = threshold_ms if threshold_ms > 0 else self._slow_threshold
        results = []
        for t in self._timers.values():
            if t.status != "completed":
                continue
            if t.duration_ms >= thresh:
                results.append({
                    "timer_id": t.timer_id,
                    "name": t.name,
                    "category": t.category,
                    "owner": t.owner,
                    "duration_ms": round(t.duration_ms, 2),
                })
        results.sort(key=lambda x: -x["duration_ms"])
        return results

    # --- Analytics ---

    def get_average_duration(self, category: str = "", owner: str = "") -> float:
        """Get average duration in ms for completed timers."""
        durations = []
        for t in self._timers.values():
            if t.status != "completed":
                continue
            if category and t.category != category:
                continue
            if owner and t.owner != owner:
                continue
            durations.append(t.duration_ms)
        if not durations:
            return 0.0
        return round(sum(durations) / len(durations), 2)

    def get_percentiles(self, category: str = "") -> Dict:
        """Get p50, p90, p99 durations for completed timers."""
        durations = []
        for t in self._timers.values():
            if t.status != "completed":
                continue
            if category and t.category != category:
                continue
            durations.append(t.duration_ms)
        if not durations:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0, "count": 0}
        durations.sort()
        n = len(durations)
        return {
            "p50": round(durations[int(n * 0.5)], 2),
            "p90": round(durations[min(int(n * 0.9), n - 1)], 2),
            "p99": round(durations[min(int(n * 0.99), n - 1)], 2),
            "count": n,
        }

    def get_category_summary(self) -> List[Dict]:
        """Get timing summary per category."""
        cats: Dict[str, List[float]] = {}
        for t in self._timers.values():
            if t.status != "completed":
                continue
            cats.setdefault(t.category, []).append(t.duration_ms)
        results = []
        for cat, durations in cats.items():
            results.append({
                "category": cat,
                "count": len(durations),
                "avg_ms": round(sum(durations) / len(durations), 2),
                "min_ms": round(min(durations), 2),
                "max_ms": round(max(durations), 2),
                "total_ms": round(sum(durations), 2),
            })
        results.sort(key=lambda x: -x["total_ms"])
        return results

    def get_owner_summary(self, owner: str) -> Dict:
        """Get timing summary for an owner."""
        timers = [t for t in self._timers.values() if t.owner == owner and t.status == "completed"]
        if not timers:
            return {}
        durations = [t.duration_ms for t in timers]
        return {
            "owner": owner,
            "count": len(timers),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "total_ms": round(sum(durations), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
        }

    # --- Callbacks ---

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

    # --- Stats ---

    def get_stats(self) -> Dict:
        running = sum(1 for t in self._timers.values() if t.status == "running")
        return {
            **self._stats,
            "current_timers": len(self._timers),
            "running_timers": running,
        }

    def reset(self) -> None:
        self._timers.clear()
        self._callbacks.clear()
        self._stats = {
            "total_started": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_slow": 0,
        }

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
