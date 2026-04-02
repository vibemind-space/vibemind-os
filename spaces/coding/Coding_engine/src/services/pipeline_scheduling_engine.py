"""Pipeline scheduling engine.

Schedules pipeline jobs with cron-like scheduling, priority queuing,
and execution windows. Manages job lifecycle and tracks execution history.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Job:
    """A scheduled job."""
    job_id: str = ""
    name: str = ""
    pipeline: str = ""
    schedule: str = ""  # cron-like expression or "once"
    priority: int = 5  # 1 (highest) .. 10 (lowest)
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: str = "pending"  # pending, scheduled, running, completed, failed, cancelled, paused
    max_retries: int = 0
    retry_count: int = 0
    last_run_at: float = 0.0
    next_run_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _Execution:
    """A job execution record."""
    execution_id: str = ""
    job_id: str = ""
    status: str = "running"  # running, completed, failed, cancelled
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0
    result: str = ""
    error: str = ""
    seq: int = 0


class PipelineSchedulingEngine:
    """Schedules and manages pipeline job execution."""

    JOB_STATUSES = ("pending", "scheduled", "running", "completed",
                    "failed", "cancelled", "paused")
    EXEC_STATUSES = ("running", "completed", "failed", "cancelled")

    def __init__(self, max_jobs: int = 50000,
                 max_executions: int = 500000):
        self._max_jobs = max_jobs
        self._max_executions = max_executions
        self._jobs: Dict[str, _Job] = {}
        self._executions: Dict[str, _Execution] = {}
        self._job_seq = 0
        self._exec_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_jobs_created": 0,
            "total_executions": 0,
            "total_completed": 0,
            "total_failed": 0,
        }

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def create_job(self, name: str, pipeline: str = "",
                   schedule: str = "once", priority: int = 5,
                   max_retries: int = 0,
                   tags: Optional[List[str]] = None,
                   metadata: Optional[Dict] = None) -> str:
        if not name or not name.strip():
            return ""
        if len(self._jobs) >= self._max_jobs:
            return ""

        priority = max(1, min(10, priority))
        self._job_seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._job_seq}-{len(self._jobs)}"
        jid = "job-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._jobs[jid] = _Job(
            job_id=jid,
            name=name,
            pipeline=pipeline,
            schedule=schedule,
            priority=priority,
            max_retries=max_retries,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            status="pending",
            created_at=now,
            seq=self._job_seq,
        )
        self._stats["total_jobs_created"] += 1
        self._fire("job_created", {"job_id": jid, "name": name})
        return jid

    def get_job(self, job_id: str) -> Optional[Dict]:
        j = self._jobs.get(job_id)
        if not j:
            return None
        return {
            "job_id": j.job_id, "name": j.name,
            "pipeline": j.pipeline, "schedule": j.schedule,
            "priority": j.priority, "tags": list(j.tags),
            "metadata": dict(j.metadata), "status": j.status,
            "max_retries": j.max_retries, "retry_count": j.retry_count,
            "last_run_at": j.last_run_at, "next_run_at": j.next_run_at,
            "created_at": j.created_at,
        }

    def remove_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        # Remove associated executions
        to_del = [eid for eid, e in self._executions.items()
                  if e.job_id == job_id]
        for eid in to_del:
            del self._executions[eid]
        del self._jobs[job_id]
        return True

    def schedule_job(self, job_id: str, next_run_at: float = 0.0) -> bool:
        j = self._jobs.get(job_id)
        if not j or j.status not in ("pending", "completed", "failed"):
            return False
        j.status = "scheduled"
        j.next_run_at = next_run_at or time.time()
        return True

    def pause_job(self, job_id: str) -> bool:
        j = self._jobs.get(job_id)
        if not j or j.status in ("paused", "cancelled", "running"):
            return False
        j.status = "paused"
        return True

    def resume_job(self, job_id: str) -> bool:
        j = self._jobs.get(job_id)
        if not j or j.status != "paused":
            return False
        j.status = "scheduled"
        return True

    def cancel_job(self, job_id: str) -> bool:
        j = self._jobs.get(job_id)
        if not j or j.status in ("cancelled", "completed"):
            return False
        j.status = "cancelled"
        return True

    # ------------------------------------------------------------------
    # Executions
    # ------------------------------------------------------------------

    def start_execution(self, job_id: str) -> str:
        j = self._jobs.get(job_id)
        if not j:
            return ""
        if j.status not in ("pending", "scheduled"):
            return ""
        if len(self._executions) >= self._max_executions:
            return ""

        self._exec_seq += 1
        now = time.time()
        raw = f"{job_id}-{now}-{self._exec_seq}-{len(self._executions)}"
        eid = "exec-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._executions[eid] = _Execution(
            execution_id=eid,
            job_id=job_id,
            status="running",
            started_at=now,
            seq=self._exec_seq,
        )
        j.status = "running"
        j.last_run_at = now
        self._stats["total_executions"] += 1
        self._fire("execution_started", {"execution_id": eid, "job_id": job_id})
        return eid

    def complete_execution(self, execution_id: str,
                           result: str = "",
                           duration_ms: float = 0.0) -> bool:
        ex = self._executions.get(execution_id)
        if not ex or ex.status != "running":
            return False
        ex.status = "completed"
        ex.completed_at = time.time()
        ex.duration_ms = duration_ms
        ex.result = result
        j = self._jobs.get(ex.job_id)
        if j:
            j.status = "completed"
        self._stats["total_completed"] += 1
        return True

    def fail_execution(self, execution_id: str,
                       error: str = "",
                       duration_ms: float = 0.0) -> bool:
        ex = self._executions.get(execution_id)
        if not ex or ex.status != "running":
            return False
        ex.status = "failed"
        ex.completed_at = time.time()
        ex.duration_ms = duration_ms
        ex.error = error
        j = self._jobs.get(ex.job_id)
        if j:
            j.retry_count += 1
            j.status = "failed"
        self._stats["total_failed"] += 1
        return True

    def cancel_execution(self, execution_id: str) -> bool:
        ex = self._executions.get(execution_id)
        if not ex or ex.status != "running":
            return False
        ex.status = "cancelled"
        ex.completed_at = time.time()
        j = self._jobs.get(ex.job_id)
        if j:
            j.status = "cancelled"
        return True

    def get_execution(self, execution_id: str) -> Optional[Dict]:
        ex = self._executions.get(execution_id)
        if not ex:
            return None
        return {
            "execution_id": ex.execution_id,
            "job_id": ex.job_id, "status": ex.status,
            "started_at": ex.started_at,
            "completed_at": ex.completed_at,
            "duration_ms": ex.duration_ms,
            "result": ex.result, "error": ex.error,
        }

    def remove_execution(self, execution_id: str) -> bool:
        if execution_id not in self._executions:
            return False
        del self._executions[execution_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_job_executions(self, job_id: str,
                           limit: int = 50) -> List[Dict]:
        results = []
        for ex in self._executions.values():
            if ex.job_id == job_id:
                results.append(self.get_execution(ex.execution_id))
        results.sort(key=lambda x: x["started_at"], reverse=True)
        return results[:limit]

    def list_jobs(self, status: str = "", pipeline: str = "",
                  tag: str = "", limit: int = 100) -> List[Dict]:
        results = []
        for j in self._jobs.values():
            if status and j.status != status:
                continue
            if pipeline and j.pipeline != pipeline:
                continue
            if tag and tag not in j.tags:
                continue
            results.append(self.get_job(j.job_id))
        results.sort(key=lambda x: (x["priority"], x["created_at"]))
        return results[:limit]

    def search_executions(self, job_id: str = "",
                          status: str = "",
                          limit: int = 100) -> List[Dict]:
        results = []
        for ex in self._executions.values():
            if job_id and ex.job_id != job_id:
                continue
            if status and ex.status != status:
                continue
            results.append(self.get_execution(ex.execution_id))
        results.sort(key=lambda x: x["started_at"], reverse=True)
        return results[:limit]

    def get_queue(self, limit: int = 50) -> List[Dict]:
        """Get jobs in the queue sorted by priority."""
        results = []
        for j in self._jobs.values():
            if j.status in ("pending", "scheduled"):
                results.append(self.get_job(j.job_id))
        results.sort(key=lambda x: (x["priority"], x["created_at"]))
        return results[:limit]

    def get_job_success_rate(self, job_id: str = "") -> Dict:
        """Get success rate for a job or all jobs."""
        completed = 0
        failed = 0
        for ex in self._executions.values():
            if job_id and ex.job_id != job_id:
                continue
            if ex.status == "completed":
                completed += 1
            elif ex.status == "failed":
                failed += 1
        total = completed + failed
        rate = (completed / total * 100.0) if total > 0 else 0.0
        return {
            "completed": completed,
            "failed": failed,
            "total": total,
            "success_rate": round(rate, 1),
        }

    def get_avg_duration(self, job_id: str = "") -> Dict:
        """Get average execution duration."""
        durations = []
        for ex in self._executions.values():
            if job_id and ex.job_id != job_id:
                continue
            if ex.status in ("completed", "failed") and ex.duration_ms > 0:
                durations.append(ex.duration_ms)
        if not durations:
            return {"count": 0, "avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
        return {
            "count": len(durations),
            "avg_ms": round(sum(durations) / len(durations), 1),
            "min_ms": min(durations),
            "max_ms": max(durations),
        }

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
        running = sum(1 for j in self._jobs.values()
                      if j.status == "running")
        queued = sum(1 for j in self._jobs.values()
                     if j.status in ("pending", "scheduled"))
        return {
            **self._stats,
            "current_jobs": len(self._jobs),
            "current_executions": len(self._executions),
            "running_jobs": running,
            "queued_jobs": queued,
        }

    def reset(self) -> None:
        self._jobs.clear()
        self._executions.clear()
        self._job_seq = 0
        self._exec_seq = 0
        self._stats = {k: 0 for k in self._stats}
