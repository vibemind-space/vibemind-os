"""Pipeline step throttle - throttle pipeline step execution rate."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepThrottleState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepThrottle:
    """Throttle pipeline step execution rate."""

    PREFIX = "psth-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepThrottleState()
        self._callbacks = {}
        logger.info("PipelineStepThrottle initialized")

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

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def _make_key(self, pipeline_id: str, step_name: str) -> str:
        return f"{pipeline_id}::{step_name}"

    def set_throttle(self, pipeline_id: str, step_name: str, max_per_second: float = 10.0) -> str:
        key = self._make_key(pipeline_id, step_name)
        throttle_id = self._generate_id(key)
        now = time.time()
        entry = {
            "throttle_id": throttle_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "max_per_second": max_per_second,
            "executions": [],
            "throttled_count": 0,
            "created_at": now,
        }
        self._state.entries[throttle_id] = entry
        self._prune()
        self._fire("throttle_set", entry)
        logger.info("Throttle set: %s for %s/%s at %.1f/s", throttle_id, pipeline_id, step_name, max_per_second)
        return throttle_id

    def _find_entry(self, pipeline_id: str, step_name: str) -> dict | None:
        key = self._make_key(pipeline_id, step_name)
        for entry in self._state.entries.values():
            if self._make_key(entry["pipeline_id"], entry["step_name"]) == key:
                return entry
        return None

    def _current_rate(self, entry: dict) -> float:
        now = time.time()
        window = 1.0
        recent = [t for t in entry["executions"] if t > now - window]
        entry["executions"] = recent
        return float(len(recent))

    def can_execute(self, pipeline_id: str, step_name: str) -> bool:
        entry = self._find_entry(pipeline_id, step_name)
        if entry is None:
            return True
        rate = self._current_rate(entry)
        return rate < entry["max_per_second"]

    def record_execution(self, pipeline_id: str, step_name: str) -> bool:
        entry = self._find_entry(pipeline_id, step_name)
        if entry is None:
            return True
        rate = self._current_rate(entry)
        if rate >= entry["max_per_second"]:
            entry["throttled_count"] += 1
            self._fire("throttled", {"pipeline_id": pipeline_id, "step_name": step_name})
            return False
        entry["executions"].append(time.time())
        self._fire("execution_recorded", {"pipeline_id": pipeline_id, "step_name": step_name})
        return True

    def get_throttle_info(self, pipeline_id: str, step_name: str) -> dict:
        entry = self._find_entry(pipeline_id, step_name)
        if entry is None:
            return {"max_per_second": 0.0, "current_rate": 0.0, "throttled_count": 0}
        rate = self._current_rate(entry)
        return {
            "max_per_second": entry["max_per_second"],
            "current_rate": rate,
            "throttled_count": entry["throttled_count"],
        }

    def get_throttle(self, throttle_id: str) -> dict | None:
        entry = self._state.entries.get(throttle_id)
        if entry is None:
            return None
        return dict(entry)

    def remove_throttle(self, throttle_id: str) -> bool:
        if throttle_id in self._state.entries:
            entry = self._state.entries.pop(throttle_id)
            self._fire("throttle_removed", entry)
            return True
        return False

    def get_throttle_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> list:
        pipelines = set()
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
        return sorted(pipelines)

    def get_stats(self) -> dict:
        total_throttled = sum(e["throttled_count"] for e in self._state.entries.values())
        return {
            "total_throttles": len(self._state.entries),
            "total_throttled_count": total_throttled,
            "pipelines": len(self.list_pipelines()),
        }

    def reset(self):
        self._state = PipelineStepThrottleState()
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("PipelineStepThrottle reset")
