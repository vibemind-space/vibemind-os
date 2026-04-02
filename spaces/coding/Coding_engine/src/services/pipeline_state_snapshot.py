"""Pipeline State Snapshot -- takes and restores snapshots of pipeline state.

Provides an in-memory snapshot service that allows rollback to previous
pipeline states.  Each snapshot captures pipeline state data (deep copy),
an optional label, and monotonic sequence numbers for deterministic ordering.
Snapshots are indexed by pipeline ID for fast lookup.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import copy
import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _SnapshotEntry:
    """A single pipeline state snapshot."""

    snapshot_id: str = ""
    pipeline_id: str = ""
    state_data: Dict[str, Any] = field(default_factory=dict)
    label: str = ""
    timestamp: float = 0.0
    _seq_num: int = 0


# ---------------------------------------------------------------------------
# Pipeline State Snapshot
# ---------------------------------------------------------------------------

@dataclass
class PipelineStateSnapshot:
    """Takes and restores snapshots of pipeline state for rollback.

    Parameters
    ----------
    max_entries:
        Maximum number of snapshots to keep.  When the limit is reached the
        oldest quarter of snapshots is pruned automatically.
    """

    snapshots: Dict[str, _SnapshotEntry] = field(default_factory=dict)
    _seq: int = 0

    def __post_init__(self) -> None:
        self._max_entries: int = 10000
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}

        # index for fast lookup by pipeline_id
        self._pipeline_index: Dict[str, List[str]] = {}  # pipeline_id -> [snapshot_id]

        # stats counters
        self._stats: Dict[str, int] = {
            "total_taken": 0,
            "total_restored": 0,
            "total_deleted": 0,
            "total_pruned": 0,
        }

        logger.debug("pipeline_state_snapshot.init", max_entries=self._max_entries)

    # ------------------------------------------------------------------
    # Take snapshot
    # ------------------------------------------------------------------

    def take_snapshot(
        self,
        pipeline_id: str,
        state_data: Dict[str, Any],
        label: str = "",
    ) -> str:
        """Take a snapshot of pipeline state and return its ``snapshot_id``.

        Returns an empty string when *pipeline_id* is falsy.
        """
        if not pipeline_id:
            return ""

        with self._lock:
            # prune if at capacity
            if len(self.snapshots) >= self._max_entries:
                self._prune()

            self._seq += 1
            now = time.time()
            raw = f"{pipeline_id}-{now}-{self._seq}"
            snapshot_id = "pss-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            entry = _SnapshotEntry(
                snapshot_id=snapshot_id,
                pipeline_id=pipeline_id,
                state_data=copy.deepcopy(state_data),
                label=label,
                timestamp=now,
                _seq_num=self._seq,
            )
            self.snapshots[snapshot_id] = entry

            # update pipeline index
            self._pipeline_index.setdefault(pipeline_id, []).append(snapshot_id)

            self._stats["total_taken"] += 1

        logger.debug(
            "pipeline_state_snapshot.take_snapshot",
            snapshot_id=snapshot_id,
            pipeline_id=pipeline_id,
            label=label,
        )
        self._fire("snapshot_taken", {
            "snapshot_id": snapshot_id,
            "pipeline_id": pipeline_id,
            "label": label,
        })
        return snapshot_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific snapshot by ID.  Returns ``None`` if not found."""
        with self._lock:
            e = self.snapshots.get(snapshot_id)
            if e is None:
                return None
            return self._to_dict(e)

    def get_snapshots(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Get all snapshots for a pipeline, ordered by timestamp.

        Sorted by ``timestamp`` ascending, then ``_seq_num`` ascending.
        """
        with self._lock:
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self.snapshots[sid] for sid in ids if sid in self.snapshots]
            entries.sort(key=lambda e: (e.timestamp, e._seq_num))
            return [self._to_dict(e) for e in entries]

    def get_latest_snapshot(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent snapshot for *pipeline_id*, or ``None``.

        Uses ``_seq_num`` as tiebreaker for deterministic ordering.
        """
        with self._lock:
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self.snapshots[sid] for sid in ids if sid in self.snapshots]
            if not entries:
                return None
            latest = max(entries, key=lambda e: (e.timestamp, e._seq_num))
            return self._to_dict(latest)

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Get the state_data from a snapshot for restoring.

        Returns a deep copy of the state_data so the caller can mutate freely,
        or ``None`` if not found.
        """
        with self._lock:
            e = self.snapshots.get(snapshot_id)
            if e is None:
                return None
            self._stats["total_restored"] += 1
            pipeline_id = e.pipeline_id
            result = copy.deepcopy(e.state_data)

        logger.debug(
            "pipeline_state_snapshot.restore_snapshot",
            snapshot_id=snapshot_id,
        )
        self._fire("snapshot_restored", {
            "snapshot_id": snapshot_id,
            "pipeline_id": pipeline_id,
        })
        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot.  Returns ``False`` if not found."""
        with self._lock:
            e = self.snapshots.get(snapshot_id)
            if e is None:
                return False
            pipeline_id = e.pipeline_id
            self._remove_entry(snapshot_id)
            self._stats["total_deleted"] += 1

        logger.debug(
            "pipeline_state_snapshot.delete_snapshot",
            snapshot_id=snapshot_id,
        )
        self._fire("snapshot_deleted", {
            "snapshot_id": snapshot_id,
            "pipeline_id": pipeline_id,
        })
        return True

    # ------------------------------------------------------------------
    # Counting / Listing
    # ------------------------------------------------------------------

    def get_snapshot_count(self, pipeline_id: str = "") -> int:
        """Count snapshots.  If *pipeline_id* is given, count only that pipeline."""
        with self._lock:
            if pipeline_id:
                ids = self._pipeline_index.get(pipeline_id, [])
                return sum(1 for sid in ids if sid in self.snapshots)
            return len(self.snapshots)

    def list_pipelines(self) -> List[str]:
        """List all pipeline IDs that have at least one snapshot."""
        with self._lock:
            return [
                pid
                for pid, ids in self._pipeline_index.items()
                if any(sid in self.snapshots for sid in ids)
            ]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._callbacks:
                del self._callbacks[name]
                return True
            return False

    def _fire(self, action: str, detail_dict: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail_dict)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_snapshots": len(self.snapshots),
                "unique_pipelines": len([
                    p for p, ids in self._pipeline_index.items()
                    if any(sid in self.snapshots for sid in ids)
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self.snapshots.clear()
            self._pipeline_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("pipeline_state_snapshot.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, e: _SnapshotEntry) -> Dict[str, Any]:
        """Convert a snapshot entry to a plain dict."""
        return {
            "snapshot_id": e.snapshot_id,
            "pipeline_id": e.pipeline_id,
            "state_data": copy.deepcopy(e.state_data),
            "label": e.label,
            "timestamp": e.timestamp,
            "_seq_num": e._seq_num,
        }

    def _remove_entry(self, snapshot_id: str) -> None:
        """Remove a single entry from the store and indexes."""
        e = self.snapshots.pop(snapshot_id, None)
        if e is None:
            return

        # clean pipeline index
        ids = self._pipeline_index.get(e.pipeline_id)
        if ids:
            try:
                ids.remove(snapshot_id)
            except ValueError:
                pass

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(self.snapshots.values(), key=lambda e: e._seq_num)
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            self._remove_entry(e.snapshot_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("pipeline_state_snapshot.prune", removed=to_remove)
