"""Pipeline step batcher - groups multiple items into batches before processing."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepBatcherState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepBatcher:
    """Batches pipeline step executions by grouping items into batches before processing."""

    PREFIX = "psba-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepBatcherState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepBatcher initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def register_batcher(self, step_name: str, batch_size: int = 10) -> str:
        batcher_id = self._generate_id(step_name)
        now = time.time()
        entry = {
            "batcher_id": batcher_id,
            "step_name": step_name,
            "batch_size": batch_size,
            "buffer": [],
            "total_batches": 0,
            "total_items": 0,
            "created_at": now,
        }
        self._state.entries[batcher_id] = entry
        self._prune()
        self._fire("batcher_registered", entry)
        logger.info("Batcher registered: %s for step '%s' with batch_size %d", batcher_id, step_name, batch_size)
        return batcher_id

    def add_item(self, batcher_id: str, item) -> dict:
        entry = self._state.entries.get(batcher_id)
        if entry is None:
            return {}
        entry["buffer"].append(item)
        entry["total_items"] += 1
        if len(entry["buffer"]) >= entry["batch_size"]:
            batch = list(entry["buffer"])
            entry["buffer"] = []
            entry["total_batches"] += 1
            result = {"flushed": True, "batch": batch, "batch_number": entry["total_batches"]}
            self._fire("batch_flushed", {"batcher_id": batcher_id, **result})
            return result
        return {"flushed": False, "buffer_size": len(entry["buffer"])}

    def flush(self, batcher_id: str) -> dict:
        entry = self._state.entries.get(batcher_id)
        if entry is None:
            return {}
        batch = list(entry["buffer"])
        entry["buffer"] = []
        entry["total_batches"] += 1
        result = {"batch": batch, "batch_number": entry["total_batches"], "size": len(batch)}
        self._fire("batch_force_flushed", {"batcher_id": batcher_id, **result})
        return result

    def get_batcher(self, batcher_id: str) -> dict:
        entry = self._state.entries.get(batcher_id)
        if entry is None:
            return {}
        info = dict(entry)
        info["buffer_size"] = len(entry["buffer"])
        return info

    def get_batchers(self, step_name: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if step_name and entry["step_name"] != step_name:
                continue
            info = dict(entry)
            info["buffer_size"] = len(entry["buffer"])
            results.append(info)
        return results

    def get_batcher_count(self) -> int:
        return len(self._state.entries)

    def remove_batcher(self, batcher_id: str) -> bool:
        if batcher_id in self._state.entries:
            entry = self._state.entries.pop(batcher_id)
            self._fire("batcher_removed", entry)
            logger.info("Batcher removed: %s", batcher_id)
            return True
        return False

    def get_stats(self) -> dict:
        total_batches = sum(e["total_batches"] for e in self._state.entries.values())
        total_items = sum(e["total_items"] for e in self._state.entries.values())
        return {
            "total_batchers": len(self._state.entries),
            "total_batches_flushed": total_batches,
            "total_items_processed": total_items,
        }

    def reset(self):
        self._state = PipelineStepBatcherState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepBatcher reset")
