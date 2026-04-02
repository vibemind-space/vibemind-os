"""Pipeline execution record store.

Records and queries pipeline execution history with timing, results,
and metadata. Tracks per-pipeline statistics and supports purging
old records.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _ExecutionRecord:
    """A single pipeline execution record."""
    execution_id: str = ""
    pipeline_name: str = ""
    status: str = "running"  # running, succeeded, failed
    context: Dict = field(default_factory=dict)
    result: Dict = field(default_factory=dict)
    error: str = ""
    tags: List[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    seq: int = 0


class PipelineExecutionRecord:
    """Records and queries pipeline execution history."""

    STATUSES = ("running", "succeeded", "failed")

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._records: Dict[str, _ExecutionRecord] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_started": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_purged": 0,
        }

    # ------------------------------------------------------------------
    # Execution lifecycle
    # ------------------------------------------------------------------

    def start_execution(self, pipeline_name: str,
                        context: Optional[Dict] = None,
                        tags: Optional[List[str]] = None) -> str:
        """Start recording a new pipeline execution.

        Returns the execution_id string.
        """
        if not pipeline_name:
            return ""
        if len(self._records) >= self._max_entries:
            self._prune()

        self._seq += 1
        execution_id = "per-" + hashlib.sha256(
            f"{pipeline_name}{time.time()}{self._seq}".encode()
        ).hexdigest()[:16]

        now = time.time()
        self._records[execution_id] = _ExecutionRecord(
            execution_id=execution_id,
            pipeline_name=pipeline_name,
            status="running",
            context=context or {},
            tags=tags or [],
            start_time=now,
            seq=self._seq,
        )
        self._stats["total_started"] += 1
        logger.debug("execution_started", execution_id=execution_id,
                      pipeline=pipeline_name)
        self._fire("execution_started", {
            "execution_id": execution_id,
            "pipeline_name": pipeline_name,
        })
        return execution_id

    def complete_execution(self, execution_id: str,
                           result: Optional[Dict] = None) -> bool:
        """Mark an execution as successfully completed.

        Records end time and stores the result dict.
        """
        rec = self._records.get(execution_id)
        if not rec or rec.status != "running":
            return False
        rec.status = "succeeded"
        rec.end_time = time.time()
        rec.result = result or {}
        self._stats["total_completed"] += 1
        logger.debug("execution_completed", execution_id=execution_id,
                      pipeline=rec.pipeline_name)
        self._fire("execution_completed", {
            "execution_id": execution_id,
            "pipeline_name": rec.pipeline_name,
            "duration_s": round(rec.end_time - rec.start_time, 4),
        })
        return True

    def fail_execution(self, execution_id: str, error: str = "") -> bool:
        """Mark an execution as failed.

        Records end time and the error message.
        """
        rec = self._records.get(execution_id)
        if not rec or rec.status != "running":
            return False
        rec.status = "failed"
        rec.end_time = time.time()
        rec.error = error
        self._stats["total_failed"] += 1
        logger.debug("execution_failed", execution_id=execution_id,
                      pipeline=rec.pipeline_name, error=error)
        self._fire("execution_failed", {
            "execution_id": execution_id,
            "pipeline_name": rec.pipeline_name,
            "error": error,
        })
        return True

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_execution(self, execution_id: str) -> Optional[Dict]:
        """Get a single execution record by ID."""
        rec = self._records.get(execution_id)
        if not rec:
            return None
        return self._to_dict(rec)

    def get_history(self, pipeline_name: str,
                    limit: int = 100) -> List[Dict]:
        """Get execution history for a specific pipeline.

        Returns most recent first, up to *limit* entries.
        """
        results = []
        for rec in self._records.values():
            if rec.pipeline_name != pipeline_name:
                continue
            results.append(self._to_dict(rec))
        results.sort(key=lambda x: -x["seq"])
        return results[:limit]

    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get the most recent executions across all pipelines."""
        results = [self._to_dict(rec) for rec in self._records.values()]
        results.sort(key=lambda x: -x["seq"])
        return results[:limit]

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of unique pipeline names.

        Iterates all stored records and collects the distinct
        pipeline_name values seen across all executions.
        """
        names = set()
        for rec in self._records.values():
            names.add(rec.pipeline_name)
        return sorted(names)

    def get_by_status(self, status: str,
                      limit: int = 100) -> List[Dict]:
        """Get executions filtered by status.

        Valid statuses are: running, succeeded, failed.
        Returns most recent first, up to *limit* entries.
        """
        if status not in self.STATUSES:
            return []
        results = []
        for rec in self._records.values():
            if rec.status != status:
                continue
            results.append(self._to_dict(rec))
        results.sort(key=lambda x: -x["seq"])
        return results[:limit]

    def get_by_tag(self, tag: str,
                   limit: int = 100) -> List[Dict]:
        """Get executions that contain the given tag.

        Returns most recent first, up to *limit* entries.
        """
        if not tag:
            return []
        results = []
        for rec in self._records.values():
            if tag not in rec.tags:
                continue
            results.append(self._to_dict(rec))
        results.sort(key=lambda x: -x["seq"])
        return results[:limit]

    def count_by_pipeline(self) -> Dict[str, int]:
        """Return a dict mapping each pipeline name to its execution count."""
        counts: Dict[str, int] = {}
        for rec in self._records.values():
            counts[rec.pipeline_name] = counts.get(rec.pipeline_name, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Summary / analytics
    # ------------------------------------------------------------------

    def get_summary(self, pipeline_name: Optional[str] = None) -> Dict:
        """Get an aggregate summary of executions.

        If *pipeline_name* is provided, the summary is scoped to
        that pipeline only. Otherwise summarises all pipelines.

        Returns a dict containing:
            total      - total number of executions
            succeeded  - count of successful executions
            failed     - count of failed executions
            avg_duration - average duration in seconds (finished only)
        """
        total = 0
        succeeded = 0
        failed = 0
        total_duration = 0.0
        finished_count = 0

        for rec in self._records.values():
            if pipeline_name and rec.pipeline_name != pipeline_name:
                continue
            total += 1
            if rec.status == "succeeded":
                succeeded += 1
            elif rec.status == "failed":
                failed += 1
            if rec.end_time > 0:
                total_duration += rec.end_time - rec.start_time
                finished_count += 1

        avg_duration = 0.0
        if finished_count > 0:
            avg_duration = round(total_duration / finished_count, 4)

        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "avg_duration": avg_duration,
        }

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Purge completed/failed records.

        If *before_timestamp* is given, only purge records that ended
        before that time. Returns the number of records purged.
        """
        to_remove = []
        for eid, rec in self._records.items():
            if rec.status == "running":
                continue
            if before_timestamp is not None:
                if rec.end_time <= 0 or rec.end_time >= before_timestamp:
                    continue
            to_remove.append(eid)

        for eid in to_remove:
            del self._records[eid]

        count = len(to_remove)
        if count > 0:
            self._stats["total_purged"] += count
            logger.debug("records_purged", count=count)
            self._fire("records_purged", {"count": count})
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, rec: _ExecutionRecord) -> Dict:
        """Convert a record dataclass to a plain dict."""
        duration = 0.0
        if rec.end_time > 0:
            duration = round(rec.end_time - rec.start_time, 4)
        elif rec.start_time > 0:
            duration = round(time.time() - rec.start_time, 4)

        return {
            "execution_id": rec.execution_id,
            "pipeline_name": rec.pipeline_name,
            "status": rec.status,
            "context": dict(rec.context),
            "result": dict(rec.result),
            "error": rec.error,
            "tags": list(rec.tags),
            "start_time": rec.start_time,
            "end_time": rec.end_time,
            "duration_s": duration,
            "seq": rec.seq,
        }

    def _prune(self) -> None:
        """Remove oldest finished records when at capacity."""
        prunable = []
        for eid, rec in self._records.items():
            if rec.status in ("succeeded", "failed"):
                prunable.append((eid, rec))
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._records) // 4)
        removed = 0
        for eid, _ in prunable[:to_remove]:
            del self._records[eid]
            removed += 1
        if removed > 0:
            self._stats["total_purged"] += removed

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        running = sum(
            1 for r in self._records.values() if r.status == "running"
        )
        return {
            **self._stats,
            "current_records": len(self._records),
            "current_running": running,
            "unique_pipelines": len(self.list_pipelines()),
        }

    def reset(self) -> None:
        """Clear all records, counters, and callbacks.

        Restores the store to its initial empty state. The sequence
        counter is reset to zero, all callbacks are removed, and
        all stat counters are zeroed out.
        """
        self._records.clear()
        self._seq = 0
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
        logger.debug("execution_record_reset")
