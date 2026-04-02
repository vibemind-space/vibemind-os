"""Pipeline execution logger.

Logs pipeline execution events including stage transitions, agent
actions, and timing data. Provides execution history and analytics.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ExecutionLog:
    """An execution log entry."""
    log_id: str = ""
    run_id: str = ""
    stage: str = ""
    agent: str = ""
    action: str = ""
    level: str = "info"  # debug, info, warning, error
    message: str = ""
    duration_ms: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0
    seq: int = 0


@dataclass
class _ExecutionRun:
    """A pipeline execution run."""
    run_id: str = ""
    name: str = ""
    status: str = "running"  # running, completed, failed, cancelled
    start_time: float = 0.0
    end_time: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    log_count: int = 0
    seq: int = 0


class PipelineExecutionLogger:
    """Logs pipeline execution events."""

    LEVELS = ("debug", "info", "warning", "error")
    RUN_STATUSES = ("running", "completed", "failed", "cancelled")

    def __init__(self, max_logs: int = 500000,
                 max_runs: int = 50000):
        self._max_logs = max_logs
        self._max_runs = max_runs
        self._logs: Dict[str, _ExecutionLog] = {}
        self._runs: Dict[str, _ExecutionRun] = {}
        self._log_seq = 0
        self._run_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_logs_written": 0,
            "total_runs_created": 0,
            "total_runs_completed": 0,
            "total_runs_failed": 0,
        }

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def create_run(self, name: str, tags: Optional[List[str]] = None,
                   metadata: Optional[Dict] = None) -> str:
        """Create a new execution run."""
        if not name:
            return ""
        if len(self._runs) >= self._max_runs:
            self._prune_runs()

        self._run_seq += 1
        rid = "run-" + hashlib.md5(
            f"{name}{time.time()}{self._run_seq}".encode()
        ).hexdigest()[:12]

        self._runs[rid] = _ExecutionRun(
            run_id=rid,
            name=name,
            start_time=time.time(),
            tags=tags or [],
            metadata=metadata or {},
            seq=self._run_seq,
        )
        self._stats["total_runs_created"] += 1
        self._fire("run_created", {"run_id": rid, "name": name})
        return rid

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get run info."""
        r = self._runs.get(run_id)
        if not r:
            return None
        duration = (r.end_time or time.time()) - r.start_time
        return {
            "run_id": r.run_id,
            "name": r.name,
            "status": r.status,
            "duration_s": round(duration, 3),
            "log_count": r.log_count,
            "tags": list(r.tags),
            "seq": r.seq,
        }

    def complete_run(self, run_id: str) -> bool:
        """Complete a run."""
        r = self._runs.get(run_id)
        if not r or r.status != "running":
            return False
        r.status = "completed"
        r.end_time = time.time()
        self._stats["total_runs_completed"] += 1
        return True

    def fail_run(self, run_id: str) -> bool:
        """Fail a run."""
        r = self._runs.get(run_id)
        if not r or r.status != "running":
            return False
        r.status = "failed"
        r.end_time = time.time()
        self._stats["total_runs_failed"] += 1
        return True

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a run."""
        r = self._runs.get(run_id)
        if not r or r.status != "running":
            return False
        r.status = "cancelled"
        r.end_time = time.time()
        return True

    def remove_run(self, run_id: str) -> bool:
        """Remove a run and its logs."""
        if run_id not in self._runs:
            return False
        del self._runs[run_id]
        to_delete = [k for k, v in self._logs.items() if v.run_id == run_id]
        for k in to_delete:
            del self._logs[k]
        return True

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, run_id: str, message: str,
            stage: str = "", agent: str = "",
            action: str = "", level: str = "info",
            duration_ms: float = 0.0,
            tags: Optional[List[str]] = None,
            metadata: Optional[Dict] = None) -> str:
        """Write a log entry."""
        if not run_id or not message:
            return ""
        if level not in self.LEVELS:
            return ""
        if run_id not in self._runs:
            return ""
        if len(self._logs) >= self._max_logs:
            self._prune_logs()

        self._log_seq += 1
        lid = "log-" + hashlib.md5(
            f"{run_id}{message}{time.time()}{self._log_seq}".encode()
        ).hexdigest()[:12]

        self._logs[lid] = _ExecutionLog(
            log_id=lid,
            run_id=run_id,
            stage=stage,
            agent=agent,
            action=action,
            level=level,
            message=message,
            duration_ms=duration_ms,
            tags=tags or [],
            metadata=metadata or {},
            timestamp=time.time(),
            seq=self._log_seq,
        )
        self._runs[run_id].log_count += 1
        self._stats["total_logs_written"] += 1
        return lid

    def get_log(self, log_id: str) -> Optional[Dict]:
        """Get log entry."""
        l = self._logs.get(log_id)
        if not l:
            return None
        return {
            "log_id": l.log_id,
            "run_id": l.run_id,
            "stage": l.stage,
            "agent": l.agent,
            "action": l.action,
            "level": l.level,
            "message": l.message,
            "duration_ms": l.duration_ms,
            "tags": list(l.tags),
            "seq": l.seq,
        }

    def remove_log(self, log_id: str) -> bool:
        """Remove a log entry."""
        l = self._logs.get(log_id)
        if not l:
            return False
        r = self._runs.get(l.run_id)
        if r:
            r.log_count -= 1
        del self._logs[log_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_run_logs(self, run_id: str, level: Optional[str] = None,
                     stage: Optional[str] = None,
                     limit: int = 500) -> List[Dict]:
        """Get logs for a run."""
        result = []
        for l in self._logs.values():
            if l.run_id != run_id:
                continue
            if level and l.level != level:
                continue
            if stage and l.stage != stage:
                continue
            result.append({
                "log_id": l.log_id,
                "stage": l.stage,
                "agent": l.agent,
                "action": l.action,
                "level": l.level,
                "message": l.message,
                "duration_ms": l.duration_ms,
                "seq": l.seq,
            })
        result.sort(key=lambda x: x["seq"])
        return result[:limit]

    def search_logs(self, agent: Optional[str] = None,
                    level: Optional[str] = None,
                    stage: Optional[str] = None,
                    action: Optional[str] = None,
                    tag: Optional[str] = None,
                    limit: int = 100) -> List[Dict]:
        """Search all logs."""
        result = []
        for l in self._logs.values():
            if agent and l.agent != agent:
                continue
            if level and l.level != level:
                continue
            if stage and l.stage != stage:
                continue
            if action and l.action != action:
                continue
            if tag and tag not in l.tags:
                continue
            result.append({
                "log_id": l.log_id,
                "run_id": l.run_id,
                "agent": l.agent,
                "level": l.level,
                "message": l.message,
                "seq": l.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def list_runs(self, status: Optional[str] = None,
                  tag: Optional[str] = None,
                  limit: int = 100) -> List[Dict]:
        """List execution runs."""
        result = []
        for r in self._runs.values():
            if status and r.status != status:
                continue
            if tag and tag not in r.tags:
                continue
            result.append({
                "run_id": r.run_id,
                "name": r.name,
                "status": r.status,
                "log_count": r.log_count,
                "seq": r.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_level_counts(self, run_id: Optional[str] = None) -> Dict[str, int]:
        """Get log counts by level."""
        counts = {lv: 0 for lv in self.LEVELS}
        for l in self._logs.values():
            if run_id and l.run_id != run_id:
                continue
            counts[l.level] += 1
        return counts

    def get_stage_timing(self, run_id: str) -> List[Dict]:
        """Get total duration per stage in a run."""
        stage_times: Dict[str, float] = {}
        stage_counts: Dict[str, int] = {}
        for l in self._logs.values():
            if l.run_id != run_id:
                continue
            if not l.stage:
                continue
            stage_times[l.stage] = stage_times.get(l.stage, 0) + l.duration_ms
            stage_counts[l.stage] = stage_counts.get(l.stage, 0) + 1

        result = [
            {
                "stage": s,
                "total_duration_ms": round(stage_times[s], 2),
                "log_count": stage_counts[s],
            }
            for s in stage_times
        ]
        result.sort(key=lambda x: -x["total_duration_ms"])
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_logs(self) -> None:
        """Remove oldest logs from completed/failed runs."""
        prunable = []
        for k, l in self._logs.items():
            r = self._runs.get(l.run_id)
            if r and r.status in ("completed", "failed", "cancelled"):
                prunable.append((k, l))
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._logs) // 4)
        for k, _ in prunable[:to_remove]:
            del self._logs[k]

    def _prune_runs(self) -> None:
        """Remove oldest completed/failed runs."""
        prunable = [(k, v) for k, v in self._runs.items()
                    if v.status in ("completed", "failed", "cancelled")]
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._runs) // 4)
        for k, _ in prunable[:to_remove]:
            del self._runs[k]

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
            "current_logs": len(self._logs),
            "current_runs": len(self._runs),
            "running_runs": sum(
                1 for r in self._runs.values() if r.status == "running"
            ),
        }

    def reset(self) -> None:
        self._logs.clear()
        self._runs.clear()
        self._log_seq = 0
        self._run_seq = 0
        self._stats = {k: 0 for k in self._stats}
