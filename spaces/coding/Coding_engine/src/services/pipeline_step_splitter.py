"""Pipeline Step Splitter - splits pipeline steps into sub-steps for parallel or sequential execution."""

import hashlib
import time
from dataclasses import dataclass, field


@dataclass
class PipelineStepSplitterState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineStepSplitter:
    PREFIX = "pss2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepSplitterState()
        self._callbacks = {}
        self._on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + h[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                self._state.entries.pop(sorted_keys.pop(0))

    def _fire(self, event, data):
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                pass
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                pass

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, value):
        self._on_change = value

    def remove_callback(self, name) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def register_split(self, step_name: str, sub_steps: list, mode: str = "sequential") -> str:
        split_id = self._generate_id(step_name)
        self._state.entries[split_id] = {
            "split_id": split_id,
            "step_name": step_name,
            "sub_steps": list(sub_steps),
            "mode": mode,
            "created_at": time.time(),
            "execution_count": 0,
        }
        self._prune()
        self._fire("register_split", {"split_id": split_id, "step_name": step_name})
        return split_id

    def execute_split(self, split_id: str, context: dict) -> dict:
        entry = self._state.entries.get(split_id)
        if entry is None:
            raise KeyError(f"Split not found: {split_id}")
        entry["execution_count"] += 1
        sub_results = []
        for sub_step in entry["sub_steps"]:
            sub_results.append({
                "sub_step": sub_step,
                "status": "success",
                "context": dict(context),
            })
        result = {
            "split_id": split_id,
            "step_name": entry["step_name"],
            "sub_results": sub_results,
            "mode": entry["mode"],
            "total_sub_steps": len(entry["sub_steps"]),
        }
        self._fire("execute_split", result)
        return result

    def get_split(self, split_id: str) -> dict:
        entry = self._state.entries.get(split_id)
        if entry is None:
            raise KeyError(f"Split not found: {split_id}")
        return dict(entry)

    def get_splits(self, step_name: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if step_name == "" or entry["step_name"] == step_name:
                results.append(dict(entry))
        return results

    def add_sub_step(self, split_id: str, sub_step_name: str) -> bool:
        entry = self._state.entries.get(split_id)
        if entry is None:
            return False
        entry["sub_steps"].append(sub_step_name)
        self._fire("add_sub_step", {"split_id": split_id, "sub_step_name": sub_step_name})
        return True

    def remove_sub_step(self, split_id: str, sub_step_name: str) -> bool:
        entry = self._state.entries.get(split_id)
        if entry is None:
            return False
        if sub_step_name not in entry["sub_steps"]:
            return False
        entry["sub_steps"].remove(sub_step_name)
        self._fire("remove_sub_step", {"split_id": split_id, "sub_step_name": sub_step_name})
        return True

    def get_split_count(self) -> int:
        return len(self._state.entries)

    def remove_split(self, split_id: str) -> bool:
        if split_id in self._state.entries:
            del self._state.entries[split_id]
            self._fire("remove_split", {"split_id": split_id})
            return True
        return False

    def get_stats(self) -> dict:
        total_splits = len(self._state.entries)
        total_executions = sum(e["execution_count"] for e in self._state.entries.values())
        total_sub_steps = sum(len(e["sub_steps"]) for e in self._state.entries.values())
        return {
            "total_splits": total_splits,
            "total_executions": total_executions,
            "total_sub_steps": total_sub_steps,
        }

    def reset(self):
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
