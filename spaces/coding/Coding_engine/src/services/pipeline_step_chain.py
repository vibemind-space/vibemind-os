"""Pipeline step chain service for defining and executing chains of pipeline steps with data passing."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclass
class PipelineStepChainState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineStepChain:
    """Define and execute chains of pipeline steps with data passing."""

    ID_PREFIX = "psc3-"

    def __init__(self):
        self._state = PipelineStepChainState()
        self._callbacks: Dict[str, Callable] = {}
        self._created_at = time.time()

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        entries = self._state.entries
        if len(entries) > MAX_ENTRIES:
            sorted_keys = sorted(
                entries.keys(),
                key=lambda k: entries[k].get("created_at", 0)
            )
            to_remove = len(entries) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del entries[k]
            logger.info("Pruned %d entries", to_remove)

    def on_change(self, name: str, cb: Callable):
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Any = None):
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception as e:
                logger.error("Callback %s error: %s", name, e)

    def create_chain(self, pipeline_id: str, chain_name: str) -> str:
        chain_id = self._generate_id(f"{pipeline_id}:{chain_name}")
        self._state.entries[chain_id] = {
            "type": "chain",
            "chain_id": chain_id,
            "pipeline_id": pipeline_id,
            "chain_name": chain_name,
            "steps": [],
            "created_at": time.time(),
        }
        self._prune()
        self._fire("create_chain", {"chain_id": chain_id, "pipeline_id": pipeline_id})
        return chain_id

    def add_step(self, chain_id: str, step_name: str, step_fn: Optional[Callable] = None, order: int = 0) -> str:
        chain = self._state.entries.get(chain_id)
        if not chain or chain.get("type") != "chain":
            raise ValueError(f"Chain not found: {chain_id}")
        step_id = self._generate_id(f"{chain_id}:{step_name}")
        step_entry = {
            "step_id": step_id,
            "step_name": step_name,
            "step_fn": step_fn,
            "order": order,
            "created_at": time.time(),
        }
        chain["steps"].append(step_entry)
        self._state.entries[step_id] = {
            "type": "step",
            "chain_id": chain_id,
            **step_entry,
        }
        self._prune()
        self._fire("add_step", {"chain_id": chain_id, "step_id": step_id})
        return step_id

    def execute_chain(self, chain_id: str, initial_data: Any = None) -> dict:
        chain = self._state.entries.get(chain_id)
        if not chain or chain.get("type") != "chain":
            return {
                "chain_id": chain_id,
                "success": False,
                "steps_executed": 0,
                "result": None,
                "errors": [f"Chain not found: {chain_id}"],
            }

        steps = sorted(chain["steps"], key=lambda s: s["order"])
        result = initial_data
        errors: List[str] = []
        steps_executed = 0

        for step in steps:
            step_fn = step.get("step_fn")
            try:
                if step_fn is not None:
                    result = step_fn(result)
                steps_executed += 1
            except Exception as e:
                errors.append(f"Step '{step['step_name']}' failed: {str(e)}")
                logger.error("Step %s failed: %s", step["step_name"], e)
                break

        success = len(errors) == 0
        execution_result = {
            "chain_id": chain_id,
            "success": success,
            "steps_executed": steps_executed,
            "result": result,
            "errors": errors,
        }
        self._fire("execute_chain", execution_result)
        return execution_result

    def get_chain(self, chain_id: str) -> Optional[dict]:
        entry = self._state.entries.get(chain_id)
        if entry and entry.get("type") == "chain":
            return dict(entry)
        return None

    def get_chains(self, pipeline_id: str) -> list:
        return [
            dict(v) for v in self._state.entries.values()
            if v.get("type") == "chain" and v.get("pipeline_id") == pipeline_id
        ]

    def remove_chain(self, chain_id: str) -> bool:
        chain = self._state.entries.get(chain_id)
        if not chain or chain.get("type") != "chain":
            return False
        # Remove associated steps
        step_ids = [s["step_id"] for s in chain.get("steps", [])]
        for sid in step_ids:
            self._state.entries.pop(sid, None)
        del self._state.entries[chain_id]
        self._fire("remove_chain", {"chain_id": chain_id})
        return True

    def get_chain_count(self, pipeline_id: str = "") -> int:
        if pipeline_id:
            return sum(
                1 for v in self._state.entries.values()
                if v.get("type") == "chain" and v.get("pipeline_id") == pipeline_id
            )
        return sum(
            1 for v in self._state.entries.values()
            if v.get("type") == "chain"
        )

    def list_pipelines(self) -> list:
        pipeline_ids = set()
        for v in self._state.entries.values():
            if v.get("type") == "chain":
                pipeline_ids.add(v["pipeline_id"])
        return sorted(pipeline_ids)

    def get_stats(self) -> dict:
        chains = [v for v in self._state.entries.values() if v.get("type") == "chain"]
        steps = [v for v in self._state.entries.values() if v.get("type") == "step"]
        return {
            "total_entries": len(self._state.entries),
            "total_chains": len(chains),
            "total_steps": len(steps),
            "total_callbacks": len(self._callbacks),
            "uptime": time.time() - self._created_at,
        }

    def reset(self):
        self._state = PipelineStepChainState()
        self._callbacks.clear()
        self._fire("reset", {})
