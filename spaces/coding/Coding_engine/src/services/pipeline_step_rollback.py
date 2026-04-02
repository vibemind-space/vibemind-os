"""Pipeline step rollback service.

Save and restore pipeline step state for rollback on failure.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepRollbackState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepRollback:
    """Save and restore pipeline step state for rollback on failure."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "psrb-"

    def __init__(self):
        self._state = PipelineStepRollbackState()
        self._callbacks = {}
        self._on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_entries = sorted(
                self._state.entries.items(),
                key=lambda x: x[1].get("timestamp", 0)
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key, _ in sorted_entries[:to_remove]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", to_remove)

    def _fire(self, event: str, data=None):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change callback error: %s", e)
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback %s error: %s", cb_id, e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def add_callback(self, callback_id: str, callback) -> None:
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def save_checkpoint(self, pipeline_id: str, step_name: str, state_data: dict) -> str:
        """Save a checkpoint for a pipeline step. Returns checkpoint_id."""
        checkpoint_id = self._generate_id(f"{pipeline_id}:{step_name}")
        entry = {
            "checkpoint_id": checkpoint_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "state_data": state_data,
            "timestamp": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[checkpoint_id] = entry
        self._prune()
        self._fire("save_checkpoint", entry)
        logger.debug("Saved checkpoint %s for %s/%s", checkpoint_id, pipeline_id, step_name)
        return checkpoint_id

    def rollback(self, pipeline_id: str, step_name: str):
        """Rollback to the latest checkpoint for a pipeline step. Returns state_data or None."""
        checkpoints = self.get_checkpoints(pipeline_id, step_name)
        if not checkpoints:
            return None
        latest = max(checkpoints, key=lambda c: c.get("_order", 0))
        self._fire("rollback", latest)
        logger.info("Rolling back %s/%s to checkpoint %s", pipeline_id, step_name, latest["checkpoint_id"])
        return latest.get("state_data")

    def get_checkpoint(self, checkpoint_id: str):
        """Get a checkpoint by ID. Returns dict or None."""
        entry = self._state.entries.get(checkpoint_id)
        if entry:
            return dict(entry)
        return None

    def get_checkpoints(self, pipeline_id: str, step_name: str = "") -> list:
        """Get all checkpoints for a pipeline, optionally filtered by step_name."""
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            results.append(dict(entry))
        results.sort(key=lambda c: c.get("timestamp", 0))
        return results

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID. Returns True if deleted."""
        if checkpoint_id in self._state.entries:
            del self._state.entries[checkpoint_id]
            self._fire("delete_checkpoint", {"checkpoint_id": checkpoint_id})
            return True
        return False

    def get_checkpoint_count(self, pipeline_id: str = "") -> int:
        """Get count of checkpoints, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> list:
        """List all unique pipeline IDs."""
        pipelines = set()
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
        return sorted(pipelines)

    def get_stats(self) -> dict:
        """Get statistics about the rollback store."""
        pipelines = self.list_pipelines()
        return {
            "total_checkpoints": len(self._state.entries),
            "total_pipelines": len(pipelines),
            "pipelines": pipelines,
            "max_entries": self.MAX_ENTRIES,
            "seq": self._state._seq,
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        """Reset all state."""
        self._state = PipelineStepRollbackState()
        self._callbacks.clear()
        self._on_change = None
        self._fire("reset", None)
        logger.info("PipelineStepRollback reset")
