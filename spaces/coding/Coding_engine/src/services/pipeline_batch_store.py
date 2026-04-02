"""Pipeline Batch Store -- manages batch execution of pipelines, grouping
multiple pipeline runs together for coordinated execution and tracking.

Features:
- Create batches that group multiple pipeline runs together
- Track batch lifecycle: pending -> running -> completed/failed/cancelled
- Record individual pipeline results within a batch
- Query batch progress (total, completed, failed pipelines)
- Max-entries pruning with configurable limit
- Thread-safe access via threading.Lock
- Change callbacks for reactive integrations
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Result of a single pipeline execution within a batch."""

    pipeline_name: str = ""
    success: bool = False
    result: Optional[Any] = None
    recorded_at: float = 0.0


@dataclass
class BatchRecord:
    """Internal representation of a pipeline batch."""

    batch_id: str = ""
    name: str = ""
    pipeline_names: List[str] = field(default_factory=list)
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)
    pipeline_results: Dict[str, PipelineResult] = field(default_factory=dict)
    results: Optional[Any] = None
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Batch Store
# ---------------------------------------------------------------------------

class PipelineBatchStore:
    """Manages batch execution of pipelines with status lifecycle tracking,
    per-pipeline result recording, callback notifications, and thread-safe
    access."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._batches: Dict[str, BatchRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._seq: int = 0
        self._stats = {
            "total_created": 0,
            "total_started": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_pipeline_results": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix pbs-."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pbs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest terminal entries when at capacity.

        Caller must hold the lock.  Only terminal entries (completed,
        failed, cancelled) are eligible for pruning.  If no terminal
        entries exist the store is allowed to grow beyond max_entries
        until terminal entries become available.
        """
        if len(self._batches) < self._max_entries:
            return

        terminal = sorted(
            (b for b in self._batches.values()
             if b.status in ("completed", "failed", "cancelled")),
            key=lambda b: b.created_at,
        )

        remove_count = len(self._batches) - self._max_entries + 1
        for batch in terminal[:remove_count]:
            del self._batches[batch.batch_id]
            logger.debug("batch_pruned: %s", batch.batch_id)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _batch_to_dict(batch: BatchRecord) -> Dict[str, Any]:
        """Convert a BatchRecord to a plain dict."""
        return {
            "batch_id": batch.batch_id,
            "name": batch.name,
            "pipeline_names": list(batch.pipeline_names),
            "status": batch.status,
            "metadata": dict(batch.metadata),
            "pipeline_results": {
                name: {
                    "pipeline_name": pr.pipeline_name,
                    "success": pr.success,
                    "result": pr.result,
                    "recorded_at": pr.recorded_at,
                }
                for name, pr in batch.pipeline_results.items()
            },
            "results": batch.results,
            "error": batch.error,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*.

        If a callback with the same name already exists it is silently
        replaced.
        """
        with self._lock:
            self._callbacks[name] = callback
            logger.debug("callback_registered: %s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.  Returns False if *name* not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            logger.debug("callback_removed: %s", name)
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*.

        Exceptions inside individual callbacks are logged but do not
        propagate.
        """
        with self._lock:
            cbs = list(self._callbacks.values())

        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # create_batch
    # ------------------------------------------------------------------

    def create_batch(
        self,
        name: str,
        pipeline_names: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new pipeline batch.

        Args:
            name: Human-readable name for the batch.
            pipeline_names: List of pipeline names to execute in this batch.
            metadata: Optional arbitrary metadata dict.

        Returns:
            The new batch_id (prefixed ``pbs-``).
        """
        with self._lock:
            self._prune_if_needed()

            now = time.time()
            batch_id = self._next_id(name)

            batch = BatchRecord(
                batch_id=batch_id,
                name=name,
                pipeline_names=list(pipeline_names),
                status="pending",
                metadata=dict(metadata) if metadata else {},
                pipeline_results={},
                results=None,
                error="",
                created_at=now,
                updated_at=now,
                started_at=0.0,
                completed_at=0.0,
            )

            self._batches[batch_id] = batch
            self._stats["total_created"] += 1

        logger.info(
            "batch_created: id=%s name=%s pipelines=%d",
            batch_id,
            name,
            len(pipeline_names),
        )
        self._fire("create_batch", self._batch_to_dict(batch))
        return batch_id

    # ------------------------------------------------------------------
    # get_batch
    # ------------------------------------------------------------------

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a batch record by ID.  Returns ``None`` if not found."""
        with self._lock:
            self._stats["total_lookups"] += 1
            batch = self._batches.get(batch_id)
            if batch is None:
                return None
            return self._batch_to_dict(batch)

    # ------------------------------------------------------------------
    # start_batch
    # ------------------------------------------------------------------

    def start_batch(self, batch_id: str) -> bool:
        """Start a pending batch (pending -> running).

        Returns:
            ``True`` on success, ``False`` if the batch is not found or
            is not currently in ``pending`` status.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                logger.warning("start_batch_not_found: %s", batch_id)
                return False
            if batch.status != "pending":
                logger.warning(
                    "start_batch_invalid_status: id=%s status=%s",
                    batch_id,
                    batch.status,
                )
                return False

            now = time.time()
            batch.status = "running"
            batch.started_at = now
            batch.updated_at = now
            self._stats["total_started"] += 1

            snapshot = self._batch_to_dict(batch)

        logger.info("batch_started: %s", batch_id)
        self._fire("start_batch", snapshot)
        return True

    # ------------------------------------------------------------------
    # complete_batch
    # ------------------------------------------------------------------

    def complete_batch(
        self, batch_id: str, results: Optional[Any] = None
    ) -> bool:
        """Complete a running batch (running -> completed).

        Args:
            batch_id: The batch identifier.
            results: Optional aggregate results to attach.

        Returns:
            ``True`` on success, ``False`` if the batch is not found or
            is not currently in ``running`` status.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                logger.warning("complete_batch_not_found: %s", batch_id)
                return False
            if batch.status != "running":
                logger.warning(
                    "complete_batch_invalid_status: id=%s status=%s",
                    batch_id,
                    batch.status,
                )
                return False

            now = time.time()
            batch.status = "completed"
            batch.results = results
            batch.completed_at = now
            batch.updated_at = now
            self._stats["total_completed"] += 1

            snapshot = self._batch_to_dict(batch)

        logger.info("batch_completed: %s", batch_id)
        self._fire("complete_batch", snapshot)
        return True

    # ------------------------------------------------------------------
    # fail_batch
    # ------------------------------------------------------------------

    def fail_batch(self, batch_id: str, error: str = "") -> bool:
        """Fail a running batch (running -> failed).

        Args:
            batch_id: The batch identifier.
            error: Optional error message describing the failure.

        Returns:
            ``True`` on success, ``False`` if the batch is not found or
            is not currently in ``running`` status.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                logger.warning("fail_batch_not_found: %s", batch_id)
                return False
            if batch.status != "running":
                logger.warning(
                    "fail_batch_invalid_status: id=%s status=%s",
                    batch_id,
                    batch.status,
                )
                return False

            now = time.time()
            batch.status = "failed"
            batch.error = error
            batch.completed_at = now
            batch.updated_at = now
            self._stats["total_failed"] += 1

            snapshot = self._batch_to_dict(batch)

        logger.info("batch_failed: id=%s error=%s", batch_id, error)
        self._fire("fail_batch", snapshot)
        return True

    # ------------------------------------------------------------------
    # cancel_batch
    # ------------------------------------------------------------------

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch (pending or running -> cancelled).

        Returns:
            ``True`` on success, ``False`` if the batch is not found or
            is not in ``pending`` or ``running`` status.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                logger.warning("cancel_batch_not_found: %s", batch_id)
                return False
            if batch.status not in ("pending", "running"):
                logger.warning(
                    "cancel_batch_invalid_status: id=%s status=%s",
                    batch_id,
                    batch.status,
                )
                return False

            now = time.time()
            batch.status = "cancelled"
            batch.completed_at = now
            batch.updated_at = now
            self._stats["total_cancelled"] += 1

            snapshot = self._batch_to_dict(batch)

        logger.info("batch_cancelled: %s", batch_id)
        self._fire("cancel_batch", snapshot)
        return True

    # ------------------------------------------------------------------
    # list_batches
    # ------------------------------------------------------------------

    def list_batches(
        self, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all batches, optionally filtered by status.

        Results are sorted by created_at (ascending).
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            results: List[Dict[str, Any]] = []
            for batch in self._batches.values():
                if status is not None and batch.status != status:
                    continue
                results.append(self._batch_to_dict(batch))

        results.sort(key=lambda d: d["created_at"])
        return results

    # ------------------------------------------------------------------
    # add_pipeline_result
    # ------------------------------------------------------------------

    def add_pipeline_result(
        self,
        batch_id: str,
        pipeline_name: str,
        success: bool,
        result: Optional[Any] = None,
    ) -> bool:
        """Record the result of a single pipeline execution within a batch.

        Args:
            batch_id: The batch identifier.
            pipeline_name: Name of the pipeline that completed.
            success: Whether the pipeline succeeded.
            result: Optional result data from the pipeline.

        Returns:
            ``True`` on success, ``False`` if the batch is not found or
            is not in ``running`` status.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                logger.warning("add_pipeline_result_not_found: %s", batch_id)
                return False
            if batch.status != "running":
                logger.warning(
                    "add_pipeline_result_invalid_status: id=%s status=%s",
                    batch_id,
                    batch.status,
                )
                return False

            now = time.time()
            batch.pipeline_results[pipeline_name] = PipelineResult(
                pipeline_name=pipeline_name,
                success=success,
                result=result,
                recorded_at=now,
            )
            batch.updated_at = now
            self._stats["total_pipeline_results"] += 1

            snapshot = self._batch_to_dict(batch)

        logger.info(
            "pipeline_result_added: batch=%s pipeline=%s success=%s",
            batch_id,
            pipeline_name,
            success,
        )
        self._fire("add_pipeline_result", snapshot)
        return True

    # ------------------------------------------------------------------
    # get_batch_progress
    # ------------------------------------------------------------------

    def get_batch_progress(
        self, batch_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get progress information for a batch.

        Returns a dict with total, completed, failed, and pending
        pipeline counts, or ``None`` if the batch is not found.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            batch = self._batches.get(batch_id)
            if batch is None:
                return None

            total = len(batch.pipeline_names)
            completed = sum(
                1 for pr in batch.pipeline_results.values() if pr.success
            )
            failed = sum(
                1 for pr in batch.pipeline_results.values() if not pr.success
            )
            pending = total - completed - failed

            return {
                "batch_id": batch.batch_id,
                "name": batch.name,
                "status": batch.status,
                "total": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "percent_done": (
                    round((completed + failed) / total * 100, 1)
                    if total > 0
                    else 0.0
                ),
            }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        with self._lock:
            status_counts: Dict[str, int] = {}
            for batch in self._batches.values():
                status_counts[batch.status] = (
                    status_counts.get(batch.status, 0) + 1
                )

            return {
                **self._stats,
                "current_batches": len(self._batches),
                "current_pending": status_counts.get("pending", 0),
                "current_running": status_counts.get("running", 0),
                "current_completed": status_counts.get("completed", 0),
                "current_failed": status_counts.get("failed", 0),
                "current_cancelled": status_counts.get("cancelled", 0),
                "current_callbacks": len(self._callbacks),
                "max_entries": self._max_entries,
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all batches, callbacks, and counters."""
        with self._lock:
            self._batches.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_batch_store_reset")
