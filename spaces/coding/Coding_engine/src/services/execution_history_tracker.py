"""
Execution History Tracker — records and queries pipeline execution history.

Features:
- Full execution run tracking with start/end timestamps
- Step-level tracking within runs
- Outcome recording (success, failure, timeout, cancelled)
- Duration analytics and trend analysis
- Run comparison and diff
- Searchable execution logs
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExecutionStep:
    """A step within an execution run."""
    step_id: str
    name: str
    status: str  # "pending", "running", "completed", "failed", "skipped"
    started_at: float
    completed_at: float
    duration: float
    output: Any
    error: str
    metadata: Dict[str, Any]


@dataclass
class ExecutionRun:
    """A complete execution run."""
    run_id: str
    name: str
    status: str  # "running", "completed", "failed", "timeout", "cancelled"
    started_at: float
    completed_at: float
    duration: float
    steps: List[ExecutionStep]
    trigger: str  # what started this run
    category: str
    tags: Set[str]
    metadata: Dict[str, Any]
    error: str


# ---------------------------------------------------------------------------
# Execution History Tracker
# ---------------------------------------------------------------------------

class ExecutionHistoryTracker:
    """Records and queries pipeline execution history."""

    def __init__(
        self,
        max_runs: int = 10000,
        max_steps_per_run: int = 500,
    ):
        self._max_runs = max_runs
        self._max_steps = max_steps_per_run
        self._runs: Dict[str, ExecutionRun] = {}

        self._stats = {
            "total_runs": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_steps": 0,
        }

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def start_run(
        self,
        name: str,
        trigger: str = "manual",
        category: str = "general",
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Start a new execution run. Returns run_id."""
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        self._runs[run_id] = ExecutionRun(
            run_id=run_id,
            name=name,
            status="running",
            started_at=time.time(),
            completed_at=0.0,
            duration=0.0,
            steps=[],
            trigger=trigger,
            category=category,
            tags=tags or set(),
            metadata=metadata or {},
            error="",
        )
        self._stats["total_runs"] += 1

        if len(self._runs) > self._max_runs:
            self._prune()

        return run_id

    def complete_run(self, run_id: str, metadata: Optional[Dict] = None) -> bool:
        """Mark run as completed."""
        run = self._runs.get(run_id)
        if not run or run.status != "running":
            return False
        now = time.time()
        run.status = "completed"
        run.completed_at = now
        run.duration = round(now - run.started_at, 4)
        if metadata:
            run.metadata.update(metadata)
        self._stats["total_completed"] += 1
        return True

    def fail_run(self, run_id: str, error: str = "") -> bool:
        """Mark run as failed."""
        run = self._runs.get(run_id)
        if not run or run.status != "running":
            return False
        now = time.time()
        run.status = "failed"
        run.completed_at = now
        run.duration = round(now - run.started_at, 4)
        run.error = error
        self._stats["total_failed"] += 1
        return True

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running run."""
        run = self._runs.get(run_id)
        if not run or run.status != "running":
            return False
        now = time.time()
        run.status = "cancelled"
        run.completed_at = now
        run.duration = round(now - run.started_at, 4)
        self._stats["total_cancelled"] += 1
        return True

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def add_step(
        self,
        run_id: str,
        name: str,
        status: str = "completed",
        duration: float = 0.0,
        output: Any = None,
        error: str = "",
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Add a step to a run."""
        run = self._runs.get(run_id)
        if not run:
            return None
        if len(run.steps) >= self._max_steps:
            return None

        step_id = f"step-{uuid.uuid4().hex[:8]}"
        now = time.time()
        step = ExecutionStep(
            step_id=step_id,
            name=name,
            status=status,
            started_at=now - duration,
            completed_at=now,
            duration=round(duration, 4),
            output=output,
            error=error,
            metadata=metadata or {},
        )
        run.steps.append(step)
        self._stats["total_steps"] += 1
        return step_id

    def get_steps(self, run_id: str) -> List[Dict]:
        """Get all steps for a run."""
        run = self._runs.get(run_id)
        if not run:
            return []
        return [self._step_to_dict(s) for s in run.steps]

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get run info."""
        run = self._runs.get(run_id)
        if not run:
            return None
        return self._run_to_dict(run)

    def list_runs(
        self,
        name: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        trigger: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List runs with filters."""
        results = []
        for run in sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True):
            if name and run.name != name:
                continue
            if status and run.status != status:
                continue
            if category and run.category != category:
                continue
            if trigger and run.trigger != trigger:
                continue
            if tag and tag not in run.tags:
                continue
            results.append(self._run_to_dict(run))
            if len(results) >= limit:
                break
        return results

    def get_latest(self, name: Optional[str] = None) -> Optional[Dict]:
        """Get the most recent run."""
        runs = sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)
        for run in runs:
            if name and run.name != name:
                continue
            return self._run_to_dict(run)
        return None

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Search runs by name or error."""
        q = query.lower()
        results = []
        for run in self._runs.values():
            if q in run.name.lower() or q in run.error.lower() or q in run.trigger.lower():
                results.append(self._run_to_dict(run))
                if len(results) >= limit:
                    break
        return results

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_duration_stats(self, name: Optional[str] = None, limit: int = 100) -> Dict:
        """Get duration statistics for runs."""
        durations = []
        for run in self._runs.values():
            if run.status not in ("completed", "failed"):
                continue
            if name and run.name != name:
                continue
            durations.append(run.duration)
            if len(durations) >= limit:
                break

        if not durations:
            return {"count": 0, "min": 0, "max": 0, "avg": 0}

        durations.sort()
        return {
            "count": len(durations),
            "min": round(min(durations), 4),
            "max": round(max(durations), 4),
            "avg": round(sum(durations) / len(durations), 4),
        }

    def get_success_rate(self, name: Optional[str] = None, limit: int = 100) -> Dict:
        """Get success rate for runs."""
        completed = 0
        failed = 0
        for run in sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True):
            if name and run.name != name:
                continue
            if run.status == "completed":
                completed += 1
            elif run.status == "failed":
                failed += 1
            if completed + failed >= limit:
                break

        total = completed + failed
        return {
            "completed": completed,
            "failed": failed,
            "total": total,
            "success_rate": round(completed / total * 100, 1) if total > 0 else 0.0,
        }

    def compare_runs(self, run_id_a: str, run_id_b: str) -> Optional[Dict]:
        """Compare two runs."""
        a = self._runs.get(run_id_a)
        b = self._runs.get(run_id_b)
        if not a or not b:
            return None

        return {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "duration_diff": round(b.duration - a.duration, 4),
            "status_a": a.status,
            "status_b": b.status,
            "steps_a": len(a.steps),
            "steps_b": len(b.steps),
            "step_diff": len(b.steps) - len(a.steps),
        }

    # ------------------------------------------------------------------
    # Categories & tags
    # ------------------------------------------------------------------

    def list_categories(self) -> Dict[str, int]:
        """List categories with run counts."""
        counts: Dict[str, int] = defaultdict(int)
        for run in self._runs.values():
            counts[run.category] += 1
        return dict(sorted(counts.items()))

    def list_tags(self) -> Dict[str, int]:
        """List tags with counts."""
        counts: Dict[str, int] = defaultdict(int)
        for run in self._runs.values():
            for tag in run.tags:
                counts[tag] += 1
        return dict(sorted(counts.items()))

    def list_triggers(self) -> Dict[str, int]:
        """List triggers with counts."""
        counts: Dict[str, int] = defaultdict(int)
        for run in self._runs.values():
            counts[run.trigger] += 1
        return dict(sorted(counts.items()))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def delete_run(self, run_id: str) -> bool:
        """Delete a run."""
        if run_id not in self._runs:
            return False
        del self._runs[run_id]
        return True

    def cleanup(self, max_age_seconds: float = 0.0, status: Optional[str] = None) -> int:
        """Remove old or finished runs."""
        now = time.time()
        to_remove = []
        for run_id, run in self._runs.items():
            if status and run.status != status:
                continue
            if max_age_seconds > 0 and run.completed_at > 0:
                if now - run.completed_at >= max_age_seconds:
                    to_remove.append(run_id)
            elif status and run.status in ("completed", "failed", "cancelled"):
                to_remove.append(run_id)
        for rid in to_remove:
            del self._runs[rid]
        return len(to_remove)

    def _prune(self) -> None:
        """Remove oldest finished runs."""
        finished = [
            (rid, r) for rid, r in self._runs.items()
            if r.status in ("completed", "failed", "cancelled")
        ]
        finished.sort(key=lambda x: x[1].completed_at)
        to_remove = len(self._runs) - self._max_runs
        for rid, _ in finished[:to_remove]:
            del self._runs[rid]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_to_dict(self, run: ExecutionRun) -> Dict:
        return {
            "run_id": run.run_id,
            "name": run.name,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "duration": run.duration,
            "step_count": len(run.steps),
            "trigger": run.trigger,
            "category": run.category,
            "tags": list(run.tags),
            "metadata": run.metadata,
            "error": run.error,
        }

    def _step_to_dict(self, step: ExecutionStep) -> Dict:
        return {
            "step_id": step.step_id,
            "name": step.name,
            "status": step.status,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "duration": step.duration,
            "output": step.output,
            "error": step.error,
            "metadata": step.metadata,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        active = sum(1 for r in self._runs.values() if r.status == "running")
        return {
            **self._stats,
            "active_runs": active,
            "stored_runs": len(self._runs),
        }

    def reset(self) -> None:
        self._runs.clear()
        self._stats = {k: 0 for k in self._stats}
