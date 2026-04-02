"""Pipeline batch processor.

Processes items in configurable batches with progress tracking,
error handling, and throughput monitoring.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Batch:
    """A processing batch."""
    batch_id: str = ""
    name: str = ""
    total_items: int = 0
    batch_size: int = 100
    status: str = "pending"  # pending, processing, completed, failed, cancelled
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    processed_count: int = 0
    success_count: int = 0
    error_count: int = 0
    current_batch_num: int = 0
    total_batches: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _BatchResult:
    """Result from a batch chunk."""
    result_id: str = ""
    batch_id: str = ""
    batch_num: int = 0
    items_processed: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    created_at: float = 0.0
    seq: int = 0


class PipelineBatchProcessor:
    """Manages batch processing operations."""

    STATUSES = ("pending", "processing", "completed", "failed", "cancelled")

    def __init__(self, max_batches: int = 10000,
                 max_results: int = 500000):
        self._max_batches = max_batches
        self._max_results = max_results
        self._batches: Dict[str, _Batch] = {}
        self._results: Dict[str, _BatchResult] = {}
        self._batch_seq = 0
        self._result_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_batches_created": 0,
            "total_items_processed": 0,
            "total_items_succeeded": 0,
            "total_items_failed": 0,
            "total_completed": 0,
            "total_failed": 0,
        }

    # ------------------------------------------------------------------
    # Batch Lifecycle
    # ------------------------------------------------------------------

    def create_batch(self, name: str, total_items: int,
                     batch_size: int = 100,
                     tags: Optional[List[str]] = None,
                     metadata: Optional[Dict] = None) -> str:
        """Create a new batch job."""
        if not name or total_items <= 0:
            return ""
        if batch_size <= 0:
            return ""
        if len(self._batches) >= self._max_batches:
            return ""

        self._batch_seq += 1
        bid = "batch-" + hashlib.md5(
            f"{name}{time.time()}{self._batch_seq}{len(self._batches)}".encode()
        ).hexdigest()[:12]

        total_batches = (total_items + batch_size - 1) // batch_size

        self._batches[bid] = _Batch(
            batch_id=bid,
            name=name,
            total_items=total_items,
            batch_size=batch_size,
            total_batches=total_batches,
            tags=tags or [],
            metadata=metadata or {},
            created_at=time.time(),
            seq=self._batch_seq,
        )
        self._stats["total_batches_created"] += 1
        self._fire("batch_created", {"batch_id": bid, "name": name})
        return bid

    def get_batch(self, batch_id: str) -> Optional[Dict]:
        """Get batch info."""
        b = self._batches.get(batch_id)
        if not b:
            return None
        progress = round((b.processed_count / b.total_items) * 100.0, 1) \
            if b.total_items > 0 else 0.0
        return {
            "batch_id": b.batch_id,
            "name": b.name,
            "total_items": b.total_items,
            "batch_size": b.batch_size,
            "status": b.status,
            "tags": list(b.tags),
            "processed_count": b.processed_count,
            "success_count": b.success_count,
            "error_count": b.error_count,
            "current_batch_num": b.current_batch_num,
            "total_batches": b.total_batches,
            "progress_pct": progress,
            "seq": b.seq,
        }

    def start_batch(self, batch_id: str) -> bool:
        """Start processing a batch."""
        b = self._batches.get(batch_id)
        if not b or b.status != "pending":
            return False
        b.status = "processing"
        b.started_at = time.time()
        return True

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch."""
        b = self._batches.get(batch_id)
        if not b or b.status in ("completed", "failed", "cancelled"):
            return False
        b.status = "cancelled"
        b.completed_at = time.time()
        return True

    def remove_batch(self, batch_id: str) -> bool:
        """Remove a batch and its results."""
        if batch_id not in self._batches:
            return False
        del self._batches[batch_id]
        to_remove = [rid for rid, r in self._results.items()
                     if r.batch_id == batch_id]
        for rid in to_remove:
            del self._results[rid]
        return True

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def record_chunk(self, batch_id: str, items_processed: int,
                     items_succeeded: int = 0, items_failed: int = 0,
                     duration_ms: float = 0.0,
                     errors: Optional[List[str]] = None) -> str:
        """Record processing of a batch chunk."""
        b = self._batches.get(batch_id)
        if not b or b.status != "processing":
            return ""
        if len(self._results) >= self._max_results:
            return ""

        if items_succeeded == 0 and items_failed == 0:
            items_succeeded = items_processed

        self._result_seq += 1
        rid = "bres-" + hashlib.md5(
            f"{batch_id}{time.time()}{self._result_seq}{len(self._results)}".encode()
        ).hexdigest()[:12]

        b.current_batch_num += 1
        b.processed_count += items_processed
        b.success_count += items_succeeded
        b.error_count += items_failed

        self._results[rid] = _BatchResult(
            result_id=rid,
            batch_id=batch_id,
            batch_num=b.current_batch_num,
            items_processed=items_processed,
            items_succeeded=items_succeeded,
            items_failed=items_failed,
            duration_ms=duration_ms,
            errors=errors or [],
            created_at=time.time(),
            seq=self._result_seq,
        )

        self._stats["total_items_processed"] += items_processed
        self._stats["total_items_succeeded"] += items_succeeded
        self._stats["total_items_failed"] += items_failed

        # Auto-complete if all items processed
        if b.processed_count >= b.total_items:
            if b.error_count > 0 and b.success_count == 0:
                b.status = "failed"
                b.completed_at = time.time()
                self._stats["total_failed"] += 1
            else:
                b.status = "completed"
                b.completed_at = time.time()
                self._stats["total_completed"] += 1
            self._fire("batch_completed", {
                "batch_id": batch_id, "status": b.status,
            })

        return rid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_batches(self, status: Optional[str] = None,
                       tag: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """Search batches."""
        result = []
        for b in self._batches.values():
            if status and b.status != status:
                continue
            if tag and tag not in b.tags:
                continue
            progress = round((b.processed_count / b.total_items) * 100.0, 1) \
                if b.total_items > 0 else 0.0
            result.append({
                "batch_id": b.batch_id,
                "name": b.name,
                "status": b.status,
                "total_items": b.total_items,
                "processed_count": b.processed_count,
                "progress_pct": progress,
                "seq": b.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_batch_results(self, batch_id: str,
                          limit: int = 100) -> List[Dict]:
        """Get results for a batch."""
        result = []
        for r in self._results.values():
            if r.batch_id != batch_id:
                continue
            result.append({
                "result_id": r.result_id,
                "batch_num": r.batch_num,
                "items_processed": r.items_processed,
                "items_succeeded": r.items_succeeded,
                "items_failed": r.items_failed,
                "duration_ms": r.duration_ms,
                "seq": r.seq,
            })
        result.sort(key=lambda x: x["batch_num"])
        return result[:limit]

    def get_batch_throughput(self, batch_id: str) -> Dict:
        """Get throughput stats for a batch."""
        b = self._batches.get(batch_id)
        if not b:
            return {}
        results = [r for r in self._results.values()
                   if r.batch_id == batch_id]
        total_duration = sum(r.duration_ms for r in results)
        return {
            "batch_id": batch_id,
            "chunks_processed": len(results),
            "total_items": b.processed_count,
            "total_duration_ms": total_duration,
            "items_per_ms": b.processed_count / total_duration if total_duration else 0.0,
            "avg_chunk_duration_ms": total_duration / len(results) if results else 0.0,
        }

    def get_active_batches(self) -> List[Dict]:
        """Get currently processing batches."""
        return self.search_batches(status="processing")

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
            "current_batches": len(self._batches),
            "active_batches": sum(1 for b in self._batches.values()
                                  if b.status == "processing"),
            "current_results": len(self._results),
        }

    def reset(self) -> None:
        self._batches.clear()
        self._results.clear()
        self._batch_seq = 0
        self._result_seq = 0
        self._stats = {k: 0 for k in self._stats}
