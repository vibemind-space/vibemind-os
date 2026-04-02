"""Pipeline data accumulator service.

Accumulate pipeline data over time with configurable flush thresholds.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataAccumulatorState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataAccumulator:
    """Accumulate pipeline data with configurable flush size and interval."""

    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataAccumulatorState()
        self._callbacks: dict = {}

    # ---- ID generation ----

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pda2-{h}"

    # ---- Callbacks ----

    def on_change(self, name: str, callback) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, event: str, data=None) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.warning("Callback error: %s", exc)

    # ---- Pruning ----

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            keys = sorted(self._state.entries.keys(), key=lambda k: self._state.entries[k].get("created_at", 0))
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in keys[:to_remove]:
                del self._state.entries[k]
            logger.info("Pruned %d entries", to_remove)

    # ---- Core API ----

    def create_accumulator(self, pipeline_id: str, flush_size: int = 100, flush_interval_seconds: float = 0.0) -> str:
        acc_id = self._generate_id(pipeline_id)
        self._state.entries[acc_id] = {
            "acc_id": acc_id,
            "pipeline_id": pipeline_id,
            "flush_size": flush_size,
            "flush_interval_seconds": flush_interval_seconds,
            "records": [],
            "created_at": time.time(),
            "last_flush_at": time.time(),
        }
        self._prune()
        self._fire("created", {"acc_id": acc_id, "pipeline_id": pipeline_id})
        logger.debug("Created accumulator %s for pipeline %s", acc_id, pipeline_id)
        return acc_id

    def add(self, acc_id: str, record) -> list:
        entry = self._state.entries.get(acc_id)
        if entry is None:
            raise KeyError(f"Accumulator {acc_id} not found")
        entry["records"].append(record)
        self._fire("record_added", {"acc_id": acc_id, "record": record})

        should_flush = False
        if len(entry["records"]) >= entry["flush_size"]:
            should_flush = True
        if entry["flush_interval_seconds"] > 0:
            elapsed = time.time() - entry["last_flush_at"]
            if elapsed >= entry["flush_interval_seconds"]:
                should_flush = True

        if should_flush:
            return self.flush(acc_id)
        return []

    def flush(self, acc_id: str) -> list:
        entry = self._state.entries.get(acc_id)
        if entry is None:
            raise KeyError(f"Accumulator {acc_id} not found")
        flushed = list(entry["records"])
        entry["records"] = []
        entry["last_flush_at"] = time.time()
        self._fire("flushed", {"acc_id": acc_id, "count": len(flushed)})
        logger.debug("Flushed %d records from %s", len(flushed), acc_id)
        return flushed

    def get_current(self, acc_id: str) -> list:
        entry = self._state.entries.get(acc_id)
        if entry is None:
            raise KeyError(f"Accumulator {acc_id} not found")
        return list(entry["records"])

    def get_accumulator(self, acc_id: str):
        entry = self._state.entries.get(acc_id)
        if entry is None:
            return None
        return dict(entry)

    def get_accumulators(self, pipeline_id: str) -> list:
        return [
            dict(e) for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        ]

    def get_accumulator_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> list:
        seen = set()
        result = []
        for e in self._state.entries.values():
            pid = e["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # ---- Stats / Reset ----

    def get_stats(self) -> dict:
        total_records = sum(len(e["records"]) for e in self._state.entries.values())
        return {
            "total_accumulators": len(self._state.entries),
            "total_buffered_records": total_records,
            "pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state = PipelineDataAccumulatorState()
        self._callbacks.clear()
        self._fire("reset", None)
        logger.info("PipelineDataAccumulator reset")
