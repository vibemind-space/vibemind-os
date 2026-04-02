"""Pipeline step interceptor service.

Intercept pipeline step execution to modify input/output or add logging.
Supports before, after, and around intercept types for flexible step wrapping.
"""

import time
import hashlib
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepInterceptorState:
    entries: dict
    _seq: int = 0


class PipelineStepInterceptor:
    MAX_ENTRIES = 10000
    ID_PREFIX = "psi-"

    def __init__(self):
        self._state = PipelineStepInterceptorState(entries={})
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        hash_part = hashlib.sha256(f"{data}{self._state._seq}".encode()).hexdigest()[:16]
        self._state._seq += 1
        return f"{self.ID_PREFIX}{hash_part}"

    def on_change(self, name: str, cb) -> None:
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail_dict: dict) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail_dict)
            except Exception as e:
                logger.error(f"Callback '{name}' failed for action '{action}': {e}")

    def _prune_if_needed(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]
            logger.info(f"Pruned {to_remove} interceptor entries")

    def register_interceptor(
        self,
        pipeline_id: str,
        step_name: str,
        intercept_type: str = "before",
        interceptor_fn=None,
        label: str = "",
    ) -> str:
        if intercept_type not in ("before", "after", "around"):
            raise ValueError(f"Invalid intercept_type: {intercept_type}. Must be 'before', 'after', or 'around'.")

        interceptor_id = self._generate_id(f"{pipeline_id}:{step_name}:{intercept_type}")
        entry = {
            "interceptor_id": interceptor_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "intercept_type": intercept_type,
            "interceptor_fn": interceptor_fn,
            "label": label,
            "created_at": time.time(),
        }
        self._state.entries[interceptor_id] = entry
        self._prune_if_needed()
        logger.debug(f"Registered interceptor {interceptor_id} for {pipeline_id}/{step_name} ({intercept_type})")
        self._fire("register", {"interceptor_id": interceptor_id, "pipeline_id": pipeline_id, "step_name": step_name})
        return interceptor_id

    def execute_interceptors(
        self,
        pipeline_id: str,
        step_name: str,
        intercept_type: str,
        context: dict = None,
    ) -> dict:
        if context is None:
            context = {}
        result = dict(context)

        matching = [
            entry for entry in self._state.entries.values()
            if entry["pipeline_id"] == pipeline_id
            and entry["step_name"] == step_name
            and entry["intercept_type"] == intercept_type
        ]
        matching.sort(key=lambda e: e["created_at"])

        for entry in matching:
            fn = entry.get("interceptor_fn")
            if fn is not None:
                try:
                    modified = fn(result)
                    if isinstance(modified, dict):
                        result = modified
                except Exception as e:
                    logger.error(f"Interceptor {entry['interceptor_id']} failed: {e}")

        self._fire("execute", {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "intercept_type": intercept_type,
            "interceptor_count": len(matching),
        })
        return result

    def remove_interceptor(self, interceptor_id: str) -> bool:
        if interceptor_id in self._state.entries:
            entry = self._state.entries.pop(interceptor_id)
            logger.debug(f"Removed interceptor {interceptor_id}")
            self._fire("remove", {"interceptor_id": interceptor_id, "pipeline_id": entry["pipeline_id"]})
            return True
        return False

    def get_interceptors(
        self,
        pipeline_id: str,
        step_name: str = "",
        intercept_type: str = "",
    ) -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            if intercept_type and entry["intercept_type"] != intercept_type:
                continue
            results.append({
                "interceptor_id": entry["interceptor_id"],
                "pipeline_id": entry["pipeline_id"],
                "step_name": entry["step_name"],
                "intercept_type": entry["intercept_type"],
                "label": entry["label"],
                "created_at": entry["created_at"],
            })
        return results

    def get_interceptor_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> list:
        pipeline_ids = set()
        for entry in self._state.entries.values():
            pipeline_ids.add(entry["pipeline_id"])
        return sorted(pipeline_ids)

    def get_stats(self) -> dict:
        by_type = {}
        by_pipeline = {}
        for entry in self._state.entries.values():
            t = entry["intercept_type"]
            p = entry["pipeline_id"]
            by_type[t] = by_type.get(t, 0) + 1
            by_pipeline[p] = by_pipeline.get(p, 0) + 1
        return {
            "total_interceptors": len(self._state.entries),
            "by_type": by_type,
            "by_pipeline": by_pipeline,
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        logger.info("PipelineStepInterceptor reset")
        self._fire("reset", {})
