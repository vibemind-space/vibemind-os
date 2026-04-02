"""Pipeline checkpoint manager – manages execution checkpoints for pipeline recovery/restart.

Provides checkpoint creation, retrieval, and lifecycle management so that
pipelines can be resumed from a known-good state after failures or restarts.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _CheckpointEntry:
    """Internal record for a single pipeline checkpoint."""

    checkpoint_id: str = ""
    pipeline_id: str = ""
    step_name: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    label: str = ""
    seq: int = 0
    created_at: float = field(default_factory=time.time)


class PipelineCheckpointManager:
    """Manages execution checkpoints for pipeline recovery/restart."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._checkpoints: Dict[str, _CheckpointEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4().hex}{self._seq}"
        return "pcpm-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Checkpoint CRUD
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        pipeline_id: str,
        step_name: str,
        state: Dict,
        label: str = "",
    ) -> str:
        """Save a checkpoint and return its ID."""
        if not pipeline_id or not step_name:
            logger.warning("create_checkpoint.invalid_args", pipeline_id=pipeline_id, step_name=step_name)
            return ""
        if len(self._checkpoints) >= self._max_entries:
            logger.warning("create_checkpoint.capacity_reached", max_entries=self._max_entries)
            return ""

        cid = self._generate_id(pipeline_id + step_name)
        entry = _CheckpointEntry(
            checkpoint_id=cid,
            pipeline_id=pipeline_id,
            step_name=step_name,
            state=dict(state),
            label=label,
            seq=self._seq,
            created_at=time.time(),
        )
        self._checkpoints[cid] = entry
        logger.info("checkpoint.created", checkpoint_id=cid, pipeline_id=pipeline_id, step_name=step_name)
        self._fire("checkpoint_created", {
            "checkpoint_id": cid,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "label": label,
        })
        return cid

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """Retrieve a checkpoint by its ID."""
        entry = self._checkpoints.get(checkpoint_id)
        if entry is None:
            return None
        return {
            "checkpoint_id": entry.checkpoint_id,
            "pipeline_id": entry.pipeline_id,
            "step_name": entry.step_name,
            "state": dict(entry.state),
            "label": entry.label,
            "seq": entry.seq,
            "created_at": entry.created_at,
        }

    def get_latest_checkpoint(self, pipeline_id: str) -> Optional[Dict]:
        """Return the most recent checkpoint for a given pipeline."""
        latest: Optional[_CheckpointEntry] = None
        for entry in self._checkpoints.values():
            if entry.pipeline_id != pipeline_id:
                continue
            if latest is None or (entry.created_at, entry.seq) > (latest.created_at, latest.seq):
                latest = entry
        if latest is None:
            return None
        return self.get_checkpoint(latest.checkpoint_id)

    def get_checkpoints(self, pipeline_id: str) -> List[Dict]:
        """Return all checkpoints for a pipeline, sorted by creation time."""
        results: List[Dict] = []
        for entry in self._checkpoints.values():
            if entry.pipeline_id != pipeline_id:
                continue
            results.append({
                "checkpoint_id": entry.checkpoint_id,
                "pipeline_id": entry.pipeline_id,
                "step_name": entry.step_name,
                "state": dict(entry.state),
                "label": entry.label,
                "seq": entry.seq,
                "created_at": entry.created_at,
            })
        results.sort(key=lambda r: (r["created_at"], r["seq"]))
        return results

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint. Returns True if it existed."""
        if checkpoint_id not in self._checkpoints:
            return False
        del self._checkpoints[checkpoint_id]
        logger.info("checkpoint.deleted", checkpoint_id=checkpoint_id)
        self._fire("checkpoint_deleted", {"checkpoint_id": checkpoint_id})
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return all pipeline IDs that have at least one checkpoint."""
        seen: Dict[str, None] = {}
        for entry in self._checkpoints.values():
            seen.setdefault(entry.pipeline_id, None)
        return list(seen.keys())

    def get_checkpoint_count(self) -> int:
        """Return the total number of stored checkpoints."""
        return len(self._checkpoints)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback to be invoked on checkpoint changes."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Unregister a callback by name. Returns True if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return summary statistics about stored checkpoints."""
        pipeline_ids = set()
        for entry in self._checkpoints.values():
            pipeline_ids.add(entry.pipeline_id)
        return {
            "total_checkpoints": len(self._checkpoints),
            "total_pipelines": len(pipeline_ids),
            "max_entries": self._max_entries,
            "seq": self._seq,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all checkpoints, callbacks, and reset internal counters."""
        self._checkpoints.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("checkpoint_manager.reset")
        self._fire("reset", {})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback.error", action=action)
