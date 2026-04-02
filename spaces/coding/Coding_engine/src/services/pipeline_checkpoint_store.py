"""Pipeline checkpoint store.

Saves and restores pipeline execution checkpoints for resumability.
Checkpoints capture pipeline step state so that interrupted or failed
pipelines can be resumed from the last successful step.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CheckpointEntry:
    """A single pipeline checkpoint record."""
    checkpoint_id: str = ""
    pipeline_name: str = ""
    execution_id: str = ""
    step_name: str = ""
    state: Any = None
    created_at: float = 0.0
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline Checkpoint Store
# ---------------------------------------------------------------------------

class PipelineCheckpointStore:
    """Saves and restores pipeline execution checkpoints for resumability."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._checkpoints: Dict[str, CheckpointEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_saved": 0,
            "total_restored": 0,
            "total_deleted": 0,
            "total_purged": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'pcs-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pcs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._checkpoints) < self._max_entries:
            return
        sorted_entries = sorted(
            self._checkpoints.values(), key=lambda c: c.created_at
        )
        remove_count = len(self._checkpoints) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            del self._checkpoints[entry.checkpoint_id]
            logger.debug("checkpoint_pruned", checkpoint_id=entry.checkpoint_id)

    # ------------------------------------------------------------------
    # Save checkpoint
    # ------------------------------------------------------------------

    def save_checkpoint(
        self,
        pipeline_name: str,
        execution_id: str,
        step_name: str,
        state: Any,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Save a checkpoint for a pipeline execution step.

        Returns the checkpoint_id. Returns empty string on invalid input.
        """
        if not pipeline_name or not execution_id or not step_name:
            logger.warning(
                "save_checkpoint_invalid_input",
                pipeline_name=pipeline_name,
                execution_id=execution_id,
                step_name=step_name,
            )
            return ""

        self._prune_if_needed()

        checkpoint_id = self._next_id(
            f"{pipeline_name}:{execution_id}:{step_name}"
        )
        now = time.time()

        entry = CheckpointEntry(
            checkpoint_id=checkpoint_id,
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            step_name=step_name,
            state=state,
            created_at=now,
            tags=list(tags) if tags else [],
        )

        self._checkpoints[checkpoint_id] = entry
        self._stats["total_saved"] += 1

        logger.info(
            "checkpoint_saved",
            checkpoint_id=checkpoint_id,
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            step_name=step_name,
        )
        self._fire("checkpoint_saved", self._entry_to_dict(entry))
        return checkpoint_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """Get a single checkpoint by ID. Returns None if not found."""
        self._stats["total_lookups"] += 1
        entry = self._checkpoints.get(checkpoint_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def get_latest_checkpoint(
        self,
        pipeline_name: str,
        execution_id: str,
    ) -> Optional[Dict]:
        """Get the most recent checkpoint for a pipeline execution.

        Returns None if no matching checkpoint exists.
        """
        self._stats["total_lookups"] += 1
        candidates = [
            e for e in self._checkpoints.values()
            if e.pipeline_name == pipeline_name
            and e.execution_id == execution_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda c: c.created_at)
        return self._entry_to_dict(latest)

    def list_checkpoints(
        self,
        pipeline_name: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> List[Dict]:
        """List checkpoints, optionally filtered by pipeline and execution.

        Returns checkpoints sorted by created_at descending (newest first).
        """
        self._stats["total_lookups"] += 1
        results = []
        for entry in self._checkpoints.values():
            if pipeline_name and entry.pipeline_name != pipeline_name:
                continue
            if execution_id and entry.execution_id != execution_id:
                continue
            results.append(self._entry_to_dict(entry))
        results.sort(key=lambda x: -x["created_at"])
        return results

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """Restore a checkpoint by ID, returning only the saved state.

        Returns None if the checkpoint does not exist. Fires a
        'checkpoint_restored' callback on success.
        """
        self._stats["total_lookups"] += 1
        entry = self._checkpoints.get(checkpoint_id)
        if not entry:
            logger.warning(
                "restore_checkpoint_not_found",
                checkpoint_id=checkpoint_id,
            )
            return None

        self._stats["total_restored"] += 1
        logger.info(
            "checkpoint_restored",
            checkpoint_id=checkpoint_id,
            pipeline_name=entry.pipeline_name,
            execution_id=entry.execution_id,
            step_name=entry.step_name,
        )
        self._fire("checkpoint_restored", self._entry_to_dict(entry))
        return entry.state

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID. Returns True on success."""
        entry = self._checkpoints.get(checkpoint_id)
        if not entry:
            logger.warning(
                "delete_checkpoint_not_found",
                checkpoint_id=checkpoint_id,
            )
            return False

        del self._checkpoints[checkpoint_id]
        self._stats["total_deleted"] += 1

        logger.info("checkpoint_deleted", checkpoint_id=checkpoint_id)
        self._fire("checkpoint_deleted", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Purge checkpoints. If *before_timestamp* is given, only purge
        checkpoints created before that time. Returns count removed."""
        to_remove: List[str] = []
        for checkpoint_id, entry in self._checkpoints.items():
            if before_timestamp is not None and entry.created_at >= before_timestamp:
                continue
            to_remove.append(checkpoint_id)

        for checkpoint_id in to_remove:
            del self._checkpoints[checkpoint_id]

        removed = len(to_remove)
        self._stats["total_purged"] += removed

        if removed:
            logger.info("checkpoints_purged", count=removed)
            self._fire("checkpoints_purged", {"count": removed})
        return removed

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
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: CheckpointEntry) -> Dict:
        """Convert a CheckpointEntry to a plain dict."""
        return {
            "checkpoint_id": entry.checkpoint_id,
            "pipeline_name": entry.pipeline_name,
            "execution_id": entry.execution_id,
            "step_name": entry.step_name,
            "state": entry.state,
            "created_at": entry.created_at,
            "tags": list(entry.tags),
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        return {
            **self._stats,
            "current_checkpoints": len(self._checkpoints),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._checkpoints.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")
