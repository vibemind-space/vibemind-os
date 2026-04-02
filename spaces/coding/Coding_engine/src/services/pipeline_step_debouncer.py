"""Pipeline step debouncer - prevent rapid repeated pipeline step executions."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepDebouncerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepDebouncer:
    """Debounce pipeline step executions within a configurable time window."""

    PREFIX = "psdb-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepDebouncerState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepDebouncer initialized")

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

    def register_debounce(self, step_name: str, window_seconds: float = 1.0) -> str:
        debounce_id = self._generate_id(step_name)
        now = time.time()
        entry = {
            "debounce_id": debounce_id,
            "step_name": step_name,
            "window_seconds": window_seconds,
            "last_execution_at": 0,
            "total_calls": 0,
            "total_debounced": 0,
            "created_at": now,
        }
        self._state.entries[debounce_id] = entry
        self._prune()
        self._fire("debounce_registered", entry)
        logger.info("Debounce registered: %s for step '%s' with window %.2fs", debounce_id, step_name, window_seconds)
        return debounce_id

    def should_execute(self, debounce_id: str) -> bool:
        entry = self._state.entries.get(debounce_id)
        if entry is None:
            return False
        now = time.time()
        elapsed = now - entry["last_execution_at"]
        if elapsed >= entry["window_seconds"]:
            entry["last_execution_at"] = now
            entry["total_calls"] += 1
            self._fire("debounce_executed", entry)
            return True
        else:
            entry["total_debounced"] += 1
            self._fire("debounce_suppressed", entry)
            return False

    def force_execute(self, debounce_id: str) -> bool:
        entry = self._state.entries.get(debounce_id)
        if entry is None:
            return False
        now = time.time()
        entry["last_execution_at"] = now
        entry["total_calls"] += 1
        self._fire("debounce_force_executed", entry)
        logger.info("Force execute: %s", debounce_id)
        return True

    def get_debounce(self, debounce_id: str) -> dict:
        entry = self._state.entries.get(debounce_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_debounces(self, step_name: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if step_name and entry["step_name"] != step_name:
                continue
            results.append(dict(entry))
        return results

    def get_debounce_count(self) -> int:
        return len(self._state.entries)

    def remove_debounce(self, debounce_id: str) -> bool:
        if debounce_id in self._state.entries:
            entry = self._state.entries.pop(debounce_id)
            self._fire("debounce_removed", entry)
            logger.info("Debounce removed: %s", debounce_id)
            return True
        return False

    def get_stats(self) -> dict:
        total_calls = sum(e["total_calls"] for e in self._state.entries.values())
        total_debounced = sum(e["total_debounced"] for e in self._state.entries.values())
        return {
            "total_debounces": len(self._state.entries),
            "total_calls": total_calls,
            "total_debounced": total_debounced,
            "hit_rate": total_debounced / total_calls if total_calls > 0 else 0,
        }

    def reset(self):
        self._state = PipelineStepDebouncerState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepDebouncer reset")
