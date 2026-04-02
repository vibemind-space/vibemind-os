"""Pipeline data counter service - counts occurrences of values in pipeline data fields."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataCounterState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataCounter:
    """Count occurrences of values in pipeline data fields."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "pdct-"

    def __init__(self):
        self._state = PipelineDataCounterState()
        self._callbacks: dict = {}
        self._created_at = time.time()
        logger.info("PipelineDataCounter initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.ID_PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        entries = self._state.entries
        if len(entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                entries.keys(),
                key=lambda k: entries[k].get("updated_at", 0),
            )
            to_remove = len(entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del entries[k]
            logger.info("Pruned %d entries", to_remove)

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        return self._callbacks.pop(cb_id, None) is not None

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    # ---- Public API ----

    def create_counter(self, pipeline_id: str, field: str) -> str:
        counter_id = self._generate_id(f"{pipeline_id}-{field}")
        self._state.entries[counter_id] = {
            "counter_id": counter_id,
            "pipeline_id": pipeline_id,
            "field": field,
            "counts": {},
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._prune()
        self._fire("counter_created", {"counter_id": counter_id, "pipeline_id": pipeline_id})
        logger.info("Created counter %s for pipeline=%s field=%s", counter_id, pipeline_id, field)
        return counter_id

    def count(self, pipeline_id: str, records: list) -> dict:
        """Count values across all counters for a pipeline."""
        counters = self.get_counters(pipeline_id)
        if not counters:
            return {}
        result = {}
        for counter in counters:
            field = counter["field"]
            counts = counter["counts"]
            for record in records:
                if isinstance(record, dict) and field in record:
                    value = str(record[field])
                    counts[value] = counts.get(value, 0) + 1
                    result[value] = counts[value]
            counter["updated_at"] = time.time()
        self._fire("count_updated", {"pipeline_id": pipeline_id, "result": result})
        return result

    def increment(self, counter_id: str, value: str, amount: int = 1) -> int:
        entry = self._state.entries.get(counter_id)
        if entry is None:
            raise KeyError(f"Counter not found: {counter_id}")
        counts = entry["counts"]
        counts[value] = counts.get(value, 0) + amount
        entry["updated_at"] = time.time()
        new_count = counts[value]
        self._fire("incremented", {"counter_id": counter_id, "value": value, "count": new_count})
        return new_count

    def get_count(self, counter_id: str, value: str) -> int:
        entry = self._state.entries.get(counter_id)
        if entry is None:
            return 0
        return entry["counts"].get(value, 0)

    def get_top(self, counter_id: str, limit: int = 10) -> list:
        entry = self._state.entries.get(counter_id)
        if entry is None:
            return []
        counts = entry["counts"]
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:limit]

    def get_counter(self, counter_id: str) -> dict | None:
        return self._state.entries.get(counter_id)

    def get_counters(self, pipeline_id: str) -> list:
        return [
            e for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        ]

    def get_counter_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return len(self.get_counters(pipeline_id))

    def list_pipelines(self) -> list:
        seen = set()
        result = []
        for e in self._state.entries.values():
            pid = e.get("pipeline_id")
            if pid and pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    def get_stats(self) -> dict:
        total_values = sum(
            len(e.get("counts", {})) for e in self._state.entries.values()
        )
        return {
            "total_counters": len(self._state.entries),
            "total_values": total_values,
            "pipelines": len(self.list_pipelines()),
            "uptime": time.time() - self._created_at,
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        self._state = PipelineDataCounterState()
        self._callbacks.clear()
        self._created_at = time.time()
        logger.info("PipelineDataCounter reset")
