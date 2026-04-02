"""Pipeline Queue Store -- manages a pipeline execution queue for ordered,
priority-aware execution of pipeline runs.

Features:
- Enqueue pipeline runs with configurable priority (1-10, lower = higher)
- Dequeue next item by highest priority then FIFO ordering
- Track entry lifecycle: queued -> processing -> completed/failed
- Cancel queued entries or requeue failed ones
- Position tracking within the queue
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
class QueueEntry:
    """Internal representation of a queued pipeline execution."""

    entry_id: str = ""
    pipeline_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    status: str = "queued"
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Queue Store
# ---------------------------------------------------------------------------

class PipelineQueueStore:
    """Manages a pipeline execution queue with priority-aware ordering,
    status lifecycle tracking, callback notifications, and thread-safe
    access."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, QueueEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._seq: int = 0
        self._stats = {
            "total_enqueued": 0,
            "total_dequeued": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_requeued": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix pqs-."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pqs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest completed/failed entries when at capacity.

        Caller must hold the lock.  Only terminal entries (completed,
        failed, cancelled) are eligible for pruning.  If no terminal
        entries exist the store is allowed to grow beyond max_entries
        until terminal entries become available.
        """
        if len(self._entries) < self._max_entries:
            return

        terminal = sorted(
            (e for e in self._entries.values()
             if e.status in ("completed", "failed", "cancelled")),
            key=lambda e: e.created_at,
        )

        remove_count = len(self._entries) - self._max_entries + 1
        for entry in terminal[:remove_count]:
            del self._entries[entry.entry_id]
            logger.debug("queue_entry_pruned: %s", entry.entry_id)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry: QueueEntry) -> Dict[str, Any]:
        """Convert a QueueEntry to a plain dict."""
        return {
            "entry_id": entry.entry_id,
            "pipeline_name": entry.pipeline_name,
            "params": dict(entry.params),
            "priority": entry.priority,
            "status": entry.status,
            "metadata": dict(entry.metadata),
            "result": entry.result,
            "error": entry.error,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
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
    # enqueue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        pipeline_name: str,
        params: Optional[Dict[str, Any]] = None,
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a pipeline run to the queue.

        Args:
            pipeline_name: Name of the pipeline to execute.
            params: Optional parameters to pass to the pipeline.
            priority: Execution priority (1-10, lower number = higher
                priority).  Defaults to 5.
            metadata: Optional arbitrary metadata dict.

        Returns:
            The new entry_id (prefixed ``pqs-``).
        """
        priority = max(1, min(10, int(priority)))

        with self._lock:
            self._prune_if_needed()

            now = time.time()
            entry_id = self._next_id(pipeline_name)

            entry = QueueEntry(
                entry_id=entry_id,
                pipeline_name=pipeline_name,
                params=dict(params) if params else {},
                priority=priority,
                status="queued",
                metadata=dict(metadata) if metadata else {},
                result=None,
                error="",
                created_at=now,
                updated_at=now,
            )

            self._entries[entry_id] = entry
            self._stats["total_enqueued"] += 1

        logger.info(
            "entry_enqueued: id=%s pipeline=%s priority=%d",
            entry_id,
            pipeline_name,
            priority,
        )
        self._fire("enqueue", self._entry_to_dict(entry))
        return entry_id

    # ------------------------------------------------------------------
    # dequeue
    # ------------------------------------------------------------------

    def dequeue(self) -> Optional[Dict[str, Any]]:
        """Get the next item from the queue for processing.

        Selection order: highest priority (lowest number) first, then
        FIFO (earliest ``created_at``) among equal priorities.

        The entry's status is changed from ``queued`` to ``processing``.
        Returns ``None`` if no queued entries are available.
        """
        with self._lock:
            candidates = [
                e for e in self._entries.values()
                if e.status == "queued"
            ]

            if not candidates:
                return None

            candidates.sort(key=lambda e: (e.priority, e.created_at))
            chosen = candidates[0]

            chosen.status = "processing"
            chosen.updated_at = time.time()
            self._stats["total_dequeued"] += 1

            snapshot = self._entry_to_dict(chosen)

        logger.info(
            "entry_dequeued: id=%s pipeline=%s priority=%d",
            chosen.entry_id,
            chosen.pipeline_name,
            chosen.priority,
        )
        self._fire("dequeue", snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # complete
    # ------------------------------------------------------------------

    def complete(self, entry_id: str, result: Optional[Any] = None) -> bool:
        """Mark a processing entry as completed.

        Args:
            entry_id: The queue entry identifier.
            result: Optional result data to attach.

        Returns:
            ``True`` on success, ``False`` if the entry is not found or
            is not currently in ``processing`` status.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                logger.warning("complete_not_found: %s", entry_id)
                return False
            if entry.status != "processing":
                logger.warning(
                    "complete_invalid_status: id=%s status=%s",
                    entry_id,
                    entry.status,
                )
                return False

            entry.status = "completed"
            entry.result = result
            entry.updated_at = time.time()
            self._stats["total_completed"] += 1

            snapshot = self._entry_to_dict(entry)

        logger.info("entry_completed: %s", entry_id)
        self._fire("complete", snapshot)
        return True

    # ------------------------------------------------------------------
    # fail
    # ------------------------------------------------------------------

    def fail(self, entry_id: str, error: str = "") -> bool:
        """Mark a processing entry as failed.

        Args:
            entry_id: The queue entry identifier.
            error: Optional error message describing the failure.

        Returns:
            ``True`` on success, ``False`` if the entry is not found or
            is not currently in ``processing`` status.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                logger.warning("fail_not_found: %s", entry_id)
                return False
            if entry.status != "processing":
                logger.warning(
                    "fail_invalid_status: id=%s status=%s",
                    entry_id,
                    entry.status,
                )
                return False

            entry.status = "failed"
            entry.error = error
            entry.updated_at = time.time()
            self._stats["total_failed"] += 1

            snapshot = self._entry_to_dict(entry)

        logger.info("entry_failed: id=%s error=%s", entry_id, error)
        self._fire("fail", snapshot)
        return True

    # ------------------------------------------------------------------
    # cancel
    # ------------------------------------------------------------------

    def cancel(self, entry_id: str) -> bool:
        """Cancel a queued entry.

        Only entries with status ``queued`` can be cancelled.

        Returns:
            ``True`` on success, ``False`` if the entry is not found or
            is not in ``queued`` status.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                logger.warning("cancel_not_found: %s", entry_id)
                return False
            if entry.status != "queued":
                logger.warning(
                    "cancel_invalid_status: id=%s status=%s",
                    entry_id,
                    entry.status,
                )
                return False

            entry.status = "cancelled"
            entry.updated_at = time.time()
            self._stats["total_cancelled"] += 1

            snapshot = self._entry_to_dict(entry)

        logger.info("entry_cancelled: %s", entry_id)
        self._fire("cancel", snapshot)
        return True

    # ------------------------------------------------------------------
    # get_entry
    # ------------------------------------------------------------------

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a queue entry by ID.  Returns ``None`` if not found."""
        with self._lock:
            self._stats["total_lookups"] += 1
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # get_queue_size
    # ------------------------------------------------------------------

    def get_queue_size(self) -> int:
        """Return the number of entries with status ``queued``."""
        with self._lock:
            return sum(
                1 for e in self._entries.values()
                if e.status == "queued"
            )

    # ------------------------------------------------------------------
    # list_entries
    # ------------------------------------------------------------------

    def list_entries(
        self, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all entries, optionally filtered by status.

        Results are sorted by priority (ascending) then created_at
        (ascending).
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            results: List[Dict[str, Any]] = []
            for entry in self._entries.values():
                if status is not None and entry.status != status:
                    continue
                results.append(self._entry_to_dict(entry))

        results.sort(key=lambda d: (d["priority"], d["created_at"]))
        return results

    # ------------------------------------------------------------------
    # get_position
    # ------------------------------------------------------------------

    def get_position(self, entry_id: str) -> int:
        """Get the 1-based position of an entry in the queue.

        Position is determined by priority (ascending) then FIFO order
        among entries with status ``queued``.

        Returns:
            The 1-based position, or ``-1`` if the entry is not found
            or is not in ``queued`` status.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None or entry.status != "queued":
                return -1

            queued = sorted(
                (e for e in self._entries.values() if e.status == "queued"),
                key=lambda e: (e.priority, e.created_at),
            )

            for idx, e in enumerate(queued, start=1):
                if e.entry_id == entry_id:
                    return idx

        return -1  # pragma: no cover

    # ------------------------------------------------------------------
    # requeue
    # ------------------------------------------------------------------

    def requeue(self, entry_id: str) -> bool:
        """Move a failed entry back to queued status.

        Only entries with status ``failed`` can be requeued.

        Returns:
            ``True`` on success, ``False`` if the entry is not found or
            is not in ``failed`` status.
        """
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                logger.warning("requeue_not_found: %s", entry_id)
                return False
            if entry.status != "failed":
                logger.warning(
                    "requeue_invalid_status: id=%s status=%s",
                    entry_id,
                    entry.status,
                )
                return False

            entry.status = "queued"
            entry.error = ""
            entry.result = None
            entry.updated_at = time.time()
            self._stats["total_requeued"] += 1

            snapshot = self._entry_to_dict(entry)

        logger.info("entry_requeued: %s", entry_id)
        self._fire("requeue", snapshot)
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        with self._lock:
            status_counts: Dict[str, int] = {}
            for entry in self._entries.values():
                status_counts[entry.status] = (
                    status_counts.get(entry.status, 0) + 1
                )

            return {
                **self._stats,
                "current_entries": len(self._entries),
                "current_queued": status_counts.get("queued", 0),
                "current_processing": status_counts.get("processing", 0),
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
        """Clear all entries, callbacks, and counters."""
        with self._lock:
            self._entries.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_queue_store_reset")
