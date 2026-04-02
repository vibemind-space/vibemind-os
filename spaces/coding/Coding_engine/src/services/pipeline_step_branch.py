"""Pipeline step branch service for conditional branching logic."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepBranchState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepBranch:
    """Conditional branching logic for pipeline steps."""

    PREFIX = "psb-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepBranchState()
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            entries = sorted(
                self._state.entries.items(),
                key=lambda x: x[1].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key, _ in entries[:to_remove]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", to_remove)

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

    def add_branch(self, pipeline_id: str, step_name: str, condition_field: str, branches: dict) -> str:
        branch_id = self._generate_id(f"{pipeline_id}-{step_name}-{condition_field}")
        entry = {
            "branch_id": branch_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "condition_field": condition_field,
            "branches": dict(branches),
            "default_step": "default",
            "created_at": time.time(),
        }
        self._state.entries[branch_id] = entry
        self._prune()
        self._fire("add_branch", entry)
        logger.info("Added branch %s for pipeline %s step %s", branch_id, pipeline_id, step_name)
        return branch_id

    def evaluate_branch(self, pipeline_id: str, step_name: str, context: dict) -> str:
        for entry in self._state.entries.values():
            if entry["pipeline_id"] == pipeline_id and entry["step_name"] == step_name:
                field_value = context.get(entry["condition_field"])
                if field_value is not None:
                    str_value = str(field_value)
                    if str_value in entry["branches"]:
                        return entry["branches"][str_value]
                return entry.get("default_step", "default")
        return "default"

    def set_default(self, branch_id: str, default_step: str) -> bool:
        if branch_id in self._state.entries:
            self._state.entries[branch_id]["default_step"] = default_step
            self._fire("set_default", {"branch_id": branch_id, "default_step": default_step})
            return True
        return False

    def get_branch(self, branch_id: str) -> dict | None:
        entry = self._state.entries.get(branch_id)
        if entry:
            return dict(entry)
        return None

    def get_branches(self, pipeline_id: str, step_name: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] == pipeline_id:
                if step_name == "" or entry["step_name"] == step_name:
                    results.append(dict(entry))
        return results

    def remove_branch(self, branch_id: str) -> bool:
        if branch_id in self._state.entries:
            entry = self._state.entries.pop(branch_id)
            self._fire("remove_branch", {"branch_id": branch_id})
            logger.info("Removed branch %s", branch_id)
            return True
        return False

    def get_branch_count(self, pipeline_id: str = "") -> int:
        if pipeline_id == "":
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> list:
        pipelines = set()
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
        return sorted(pipelines)

    def get_stats(self) -> dict:
        return {
            "total_branches": len(self._state.entries),
            "total_pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
        }

    def reset(self):
        self._state = PipelineStepBranchState()
        self._callbacks.clear()
        logger.info("Reset pipeline step branch state")
