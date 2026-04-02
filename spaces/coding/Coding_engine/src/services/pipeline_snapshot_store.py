"""Pipeline Snapshot Store -- stores and retrieves pipeline state snapshots for recovery.

Provides an in-memory store for pipeline state snapshots that can be used
to recover pipeline state after failures.  Each snapshot captures the full
pipeline state dict, an optional label, and monotonic sequence numbers for
consistent ordering.  Snapshots are indexed by pipeline ID for fast lookup.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import copy
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
class _SnapshotEntry:
    """A single pipeline state snapshot."""

    snapshot_id: str = ""
    pipeline_id: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    label: str = ""
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Snapshot Store
# ---------------------------------------------------------------------------

class PipelineSnapshotStore:
    """Stores and retrieves pipeline state snapshots for recovery.

    Parameters
    ----------
    max_entries:
        Maximum number of snapshots to keep.  When the limit is reached the
        oldest quarter of snapshots is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, _SnapshotEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}

        # index for fast lookup by pipeline_id
        self._pipeline_index: Dict[str, List[str]] = {}  # pipeline_id -> [snapshot_id]

        # stats counters
        self._stats: Dict[str, int] = {
            "total_saved": 0,
            "total_restored": 0,
            "total_deleted": 0,
            "total_pruned": 0,
        }

        logger.debug("pipeline_snapshot_store.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        pipeline_id: str,
        state: Dict[str, Any],
        label: str = "",
    ) -> str:
        """Save a pipeline state snapshot and return its ``snapshot_id``.

        Returns an empty string when *pipeline_id* is falsy.
        """
        if not pipeline_id:
            return ""

        with self._lock:
            # prune if at capacity
            if len(self._entries) >= self._max_entries:
                self._prune()

            self._seq += 1
            now = time.time()
            raw = f"{pipeline_id}-{now}-{self._seq}"
            snapshot_id = "pss-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            entry = _SnapshotEntry(
                snapshot_id=snapshot_id,
                pipeline_id=pipeline_id,
                state=copy.deepcopy(state),
                label=label,
                created_at=now,
                seq=self._seq,
            )
            self._entries[snapshot_id] = entry

            # update pipeline index
            self._pipeline_index.setdefault(pipeline_id, []).append(snapshot_id)

            self._stats["total_saved"] += 1

        logger.debug(
            "pipeline_snapshot_store.save_snapshot snapshot_id=%s pipeline_id=%s label=%s",
            snapshot_id,
            pipeline_id,
            label,
        )
        self._fire("snapshot_saved", {
            "snapshot_id": snapshot_id,
            "pipeline_id": pipeline_id,
            "label": label,
        })
        return snapshot_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Return a single snapshot as a dict, or ``None``."""
        with self._lock:
            e = self._entries.get(snapshot_id)
            if e is None:
                return None
            return self._to_dict(e)

    def get_latest_snapshot(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent snapshot for *pipeline_id*, or ``None``.

        Sorted by ``created_at`` descending, then ``seq`` descending.
        """
        with self._lock:
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self._entries[sid] for sid in ids if sid in self._entries]
            if not entries:
                return None
            latest = max(entries, key=lambda e: (e.created_at, e.seq))
            return self._to_dict(latest)

    def get_snapshots(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Return all snapshots for *pipeline_id*, newest first.

        Sorted by ``created_at`` descending, then ``seq`` descending.
        """
        with self._lock:
            ids = self._pipeline_index.get(pipeline_id, [])
            entries = [self._entries[sid] for sid in ids if sid in self._entries]
            entries.sort(key=lambda e: (e.created_at, e.seq), reverse=True)
            return [self._to_dict(e) for e in entries]

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Return the state dict from a snapshot for restoration, or ``None``.

        Returns a deep copy of the state so the caller can mutate freely.
        """
        with self._lock:
            e = self._entries.get(snapshot_id)
            if e is None:
                return None
            self._stats["total_restored"] += 1
            pipeline_id = e.pipeline_id
            result = copy.deepcopy(e.state)

        logger.debug(
            "pipeline_snapshot_store.restore_snapshot snapshot_id=%s",
            snapshot_id,
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
        """Delete a snapshot by ID.  Returns ``False`` if not found."""
        with self._lock:
            e = self._entries.get(snapshot_id)
            if e is None:
                return False
            pipeline_id = e.pipeline_id
            self._remove_entry(snapshot_id)
            self._stats["total_deleted"] += 1

        logger.debug(
            "pipeline_snapshot_store.delete_snapshot snapshot_id=%s",
            snapshot_id,
        )
        self._fire("snapshot_deleted", {
            "snapshot_id": snapshot_id,
            "pipeline_id": pipeline_id,
        })
        return True

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return all unique pipeline IDs that have at least one snapshot."""
        with self._lock:
            return [
                pid
                for pid, ids in self._pipeline_index.items()
                if any(sid in self._entries for sid in ids)
            ]

    def get_snapshot_count(self) -> int:
        """Return the total number of snapshots in the store."""
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns ``False`` if *name* is taken."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, data)
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
                "current_entries": len(self._entries),
                "unique_pipelines": len([
                    p for p, ids in self._pipeline_index.items()
                    if any(sid in self._entries for sid in ids)
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._entries.clear()
            self._pipeline_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("pipeline_snapshot_store.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, e: _SnapshotEntry) -> Dict[str, Any]:
        """Convert a snapshot entry to a plain dict with all dataclass fields."""
        return {
            "snapshot_id": e.snapshot_id,
            "pipeline_id": e.pipeline_id,
            "state": copy.deepcopy(e.state),
            "label": e.label,
            "created_at": e.created_at,
            "seq": e.seq,
        }

    def _remove_entry(self, snapshot_id: str) -> None:
        """Remove a single entry from the store and indexes."""
        e = self._entries.pop(snapshot_id, None)
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
        entries = sorted(self._entries.values(), key=lambda e: e.seq)
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            self._remove_entry(e.snapshot_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("pipeline_snapshot_store.prune removed=%d", to_remove)
