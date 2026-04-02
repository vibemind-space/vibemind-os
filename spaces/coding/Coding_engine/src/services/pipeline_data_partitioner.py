"""Pipeline data partitioner service.

Partitions pipeline data into chunks for parallel processing.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _PartitionEntry:
    """A partition plan for a pipeline."""
    partition_id: str = ""
    pipeline_id: str = ""
    total_items: int = 0
    partition_count: int = 4
    partitions: List[Dict] = field(default_factory=list)
    completed: List[bool] = field(default_factory=list)
    created_at: float = 0.0
    seq: int = 0


class PipelineDataPartitioner:
    """Partitions pipeline data into chunks for parallel processing."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max(1, max_entries)
        self._partitions: Dict[str, _PartitionEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

    # ------------------------------------------------------------------
    # Partition Management
    # ------------------------------------------------------------------

    def create_partition(
        self,
        pipeline_id: str,
        total_items: int,
        partition_count: int = 4,
    ) -> str:
        """Create a partition plan, splitting total_items into partition_count ranges.

        Returns the partition ID or empty string on failure.
        """
        if not pipeline_id or total_items <= 0 or partition_count <= 0:
            return ""
        if len(self._partitions) >= self._max_entries:
            logger.warning("max_entries_reached", max_entries=self._max_entries)
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{pipeline_id}{total_items}{partition_count}{now}{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        pid = f"pdp-{digest}"

        # Compute partition ranges
        base_size = total_items // partition_count
        remainder = total_items % partition_count
        partitions: List[Dict] = []
        offset = 0
        for i in range(partition_count):
            size = base_size + (1 if i < remainder else 0)
            partitions.append({
                "start": offset,
                "end": offset + size,
                "size": size,
            })
            offset += size

        completed = [False] * partition_count

        self._partitions[pid] = _PartitionEntry(
            partition_id=pid,
            pipeline_id=pipeline_id,
            total_items=total_items,
            partition_count=partition_count,
            partitions=partitions,
            completed=completed,
            created_at=now,
            seq=self._seq,
        )

        logger.info(
            "partition_created",
            partition_id=pid,
            pipeline_id=pipeline_id,
            total_items=total_items,
            partition_count=partition_count,
        )
        self._fire("partition_created", {
            "partition_id": pid,
            "pipeline_id": pipeline_id,
        })
        return pid

    def get_partition(self, partition_id: str) -> Optional[Dict]:
        """Return partition details or None if not found.

        Returns {pipeline_id, total_items, partition_count, partitions: [{start, end, size}]}.
        """
        entry = self._partitions.get(partition_id)
        if not entry:
            return None
        return {
            "pipeline_id": entry.pipeline_id,
            "total_items": entry.total_items,
            "partition_count": entry.partition_count,
            "partitions": [dict(p) for p in entry.partitions],
        }

    def get_partition_ranges(self, partition_id: str) -> List[Dict]:
        """Return list of {start, end, size} ranges for a partition."""
        entry = self._partitions.get(partition_id)
        if not entry:
            return []
        return [dict(p) for p in entry.partitions]

    # ------------------------------------------------------------------
    # Completion Tracking
    # ------------------------------------------------------------------

    def mark_partition_complete(
        self, partition_id: str, partition_index: int
    ) -> bool:
        """Mark a specific partition index as complete. Returns True on success."""
        entry = self._partitions.get(partition_id)
        if not entry:
            return False
        if partition_index < 0 or partition_index >= entry.partition_count:
            return False
        if entry.completed[partition_index]:
            return False

        entry.completed[partition_index] = True
        logger.info(
            "partition_index_completed",
            partition_id=partition_id,
            partition_index=partition_index,
        )
        self._fire("partition_completed", {
            "partition_id": partition_id,
            "partition_index": partition_index,
        })
        return True

    def get_completion_status(self, partition_id: str) -> Dict:
        """Return completion status {total, completed, percentage}."""
        entry = self._partitions.get(partition_id)
        if not entry:
            return {"total": 0, "completed": 0, "percentage": 0.0}
        total = entry.partition_count
        completed = sum(1 for c in entry.completed if c)
        percentage = round((completed / total) * 100.0, 1) if total > 0 else 0.0
        return {
            "total": total,
            "completed": completed,
            "percentage": percentage,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a deduplicated list of pipeline IDs that have partitions."""
        seen: Dict[str, bool] = {}
        result: List[str] = []
        for entry in self._partitions.values():
            if entry.pipeline_id not in seen:
                seen[entry.pipeline_id] = True
                result.append(entry.pipeline_id)
        return result

    def get_partition_count(self) -> int:
        """Return the total number of partition plans stored."""
        return len(self._partitions)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns False if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return service statistics."""
        total_completed = 0
        total_partitions_tracked = 0
        for entry in self._partitions.values():
            total_partitions_tracked += entry.partition_count
            total_completed += sum(1 for c in entry.completed if c)
        return {
            "partition_plans": len(self._partitions),
            "total_partitions_tracked": total_partitions_tracked,
            "total_completed": total_completed,
            "callbacks": len(self._callbacks),
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._partitions.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("partitioner_reset")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str, data: Dict) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)
