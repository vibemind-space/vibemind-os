"""Pipeline notification queue.

Queues notifications for pipeline events with priority-based ordering,
per-pipeline queues, and change notification callbacks.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _Notification:
    """A queued notification entry."""
    notif_id: str = ""
    pipeline_id: str = ""
    notification_type: str = ""
    message: str = ""
    priority: int = 0
    created_at: float = 0.0
    seq: int = 0


class PipelineNotificationQueue:
    """Queues notifications for pipeline events."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._queues: Dict[str, List[_Notification]] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_enqueued": 0,
            "total_dequeued": 0,
            "total_peeked": 0,
        }

    # ------------------------------------------------------------------
    # ID Generation
    # ------------------------------------------------------------------

    def _make_id(self, pipeline_id: str, notification_type: str) -> str:
        raw = hashlib.sha256(
            f"{pipeline_id}{notification_type}{self._seq}".encode()
        ).hexdigest()[:12]
        return f"pnq-{raw}"

    # ------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------

    def enqueue(self, pipeline_id: str, notification_type: str,
                message: str, priority: int = 0) -> str:
        """Enqueue a notification for a pipeline. Returns notif_id."""
        if not pipeline_id or not notification_type:
            return ""

        # Prune if at capacity
        if self._total_entries() >= self._max_entries:
            self._prune_oldest()

        self._seq += 1
        notif_id = self._make_id(pipeline_id, notification_type)
        now = time.time()

        notif = _Notification(
            notif_id=notif_id,
            pipeline_id=pipeline_id,
            notification_type=notification_type,
            message=message,
            priority=priority,
            created_at=now,
            seq=self._seq,
        )

        if pipeline_id not in self._queues:
            self._queues[pipeline_id] = []
        self._queues[pipeline_id].append(notif)
        self._stats["total_enqueued"] += 1

        logger.info("notification_enqueued", notif_id=notif_id,
                     pipeline_id=pipeline_id, notification_type=notification_type)
        self._fire("enqueued", self._notif_to_dict(notif))
        return notif_id

    def dequeue(self, pipeline_id: str) -> Optional[Dict]:
        """Dequeue highest-priority notification for a pipeline. Returns dict or None."""
        queue = self._queues.get(pipeline_id)
        if not queue:
            return None

        # Find highest priority (ties broken by earliest seq)
        best_idx = 0
        for i in range(1, len(queue)):
            if (queue[i].priority > queue[best_idx].priority or
                    (queue[i].priority == queue[best_idx].priority and
                     queue[i].seq < queue[best_idx].seq)):
                best_idx = i

        notif = queue.pop(best_idx)
        if not queue:
            del self._queues[pipeline_id]

        self._stats["total_dequeued"] += 1

        logger.info("notification_dequeued", notif_id=notif.notif_id,
                     pipeline_id=pipeline_id)
        result = self._notif_to_dict(notif)
        self._fire("dequeued", result)
        return result

    def peek(self, pipeline_id: str) -> Optional[Dict]:
        """Peek at highest-priority notification without removing. Returns dict or None."""
        queue = self._queues.get(pipeline_id)
        if not queue:
            return None

        best = queue[0]
        for notif in queue[1:]:
            if (notif.priority > best.priority or
                    (notif.priority == best.priority and
                     notif.seq < best.seq)):
                best = notif

        self._stats["total_peeked"] += 1
        return self._notif_to_dict(best)

    def get_queue_length(self, pipeline_id: str) -> int:
        """Get the number of queued notifications for a pipeline."""
        queue = self._queues.get(pipeline_id)
        if not queue:
            return 0
        return len(queue)

    def get_total_queued(self) -> int:
        """Get total number of queued notifications across all pipelines."""
        return self._total_entries()

    def list_pipelines(self) -> List[str]:
        """List pipeline IDs that have queued notifications."""
        return sorted(self._queues.keys())

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _total_entries(self) -> int:
        return sum(len(q) for q in self._queues.values())

    def _prune_oldest(self) -> None:
        """Remove the oldest entry by seq to make room."""
        oldest_notif = None
        oldest_pid = None
        oldest_idx = None

        for pid, queue in self._queues.items():
            for i, notif in enumerate(queue):
                if oldest_notif is None or notif.seq < oldest_notif.seq:
                    oldest_notif = notif
                    oldest_pid = pid
                    oldest_idx = i

        if oldest_pid is not None and oldest_idx is not None:
            self._queues[oldest_pid].pop(oldest_idx)
            if not self._queues[oldest_pid]:
                del self._queues[oldest_pid]

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

    def _fire(self, event: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_entries": self._total_entries(),
            "pipeline_count": len(self._queues),
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        self._queues.clear()
        self._seq = 0
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _notif_to_dict(self, notif: _Notification) -> Dict:
        return {
            "notif_id": notif.notif_id,
            "pipeline_id": notif.pipeline_id,
            "notification_type": notif.notification_type,
            "message": notif.message,
            "priority": notif.priority,
            "created_at": notif.created_at,
            "seq": notif.seq,
        }
