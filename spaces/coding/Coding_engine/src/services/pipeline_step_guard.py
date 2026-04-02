"""Pipeline step guard service.

Guards pipeline steps with preconditions that must be met before execution.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepGuardState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepGuard:
    """Guard pipeline steps with preconditions that must be met before execution."""

    PREFIX = "psg-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self.state = PipelineStepGuardState()
        self.callbacks = {}
        self.on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self.state._seq}"
        self.state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _fire(self, event: str, data: dict):
        if self.on_change:
            try:
                self.on_change(event, data)
            except Exception as e:
                logger.error("on_change callback error: %s", e)
        for cb in list(self.callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def _prune(self):
        entries = self.state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(entries.keys(), key=lambda k: entries[k].get("created_at", 0))
        while len(entries) > self.MAX_ENTRIES:
            oldest = sorted_keys.pop(0)
            del entries[oldest]

    def add_guard(self, pipeline_id: str, step_name: str, guard_type: str = "field_present", config: dict = None) -> str:
        guard_id = self._generate_id(f"{pipeline_id}:{step_name}:{guard_type}")
        entry = {
            "guard_id": guard_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "guard_type": guard_type,
            "config": config or {},
            "created_at": time.time(),
        }
        self.state.entries[guard_id] = entry
        self._prune()
        self._fire("guard_added", entry)
        return guard_id

    def check_guards(self, pipeline_id: str, step_name: str, context: dict) -> dict:
        guards = self.get_guards(pipeline_id, step_name)
        failed_guards = []
        for g in guards:
            if not self._evaluate_guard(g, context):
                failed_guards.append(g)
        passed = len(failed_guards) == 0
        return {"passed": passed, "failed_guards": failed_guards}

    def _evaluate_guard(self, guard: dict, context: dict) -> bool:
        guard_type = guard.get("guard_type", "")
        config = guard.get("config", {})
        if guard_type == "field_present":
            field = config.get("field", "")
            return field in context
        elif guard_type == "field_value":
            field = config.get("field", "")
            value = config.get("value")
            return context.get(field) == value
        elif guard_type == "custom":
            fn = config.get("fn")
            if callable(fn):
                try:
                    return bool(fn(context))
                except Exception as e:
                    logger.error("Custom guard error: %s", e)
                    return False
            return False
        return False

    def remove_guard(self, guard_id: str) -> bool:
        if guard_id in self.state.entries:
            entry = self.state.entries.pop(guard_id)
            self._fire("guard_removed", entry)
            return True
        return False

    def get_guards(self, pipeline_id: str, step_name: str = "") -> list:
        results = []
        for entry in self.state.entries.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            results.append(entry)
        return results

    def get_guard(self, guard_id: str) -> dict:
        return self.state.entries.get(guard_id)

    def get_guard_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self.state.entries)
        return sum(1 for e in self.state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> list:
        return list({e["pipeline_id"] for e in self.state.entries.values()})

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self.callbacks:
            del self.callbacks[callback_id]
            return True
        return False

    def get_stats(self) -> dict:
        pipelines = self.list_pipelines()
        return {
            "total_guards": len(self.state.entries),
            "total_pipelines": len(pipelines),
            "pipelines": pipelines,
            "seq": self.state._seq,
        }

    def reset(self):
        self.state = PipelineStepGuardState()
        self.callbacks = {}
        self.on_change = None
        self._fire("reset", {})
