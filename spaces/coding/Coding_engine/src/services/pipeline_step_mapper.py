"""Pipeline step mapper for mapping step inputs to outputs with transformation records."""

import copy
import time
import hashlib
import dataclasses
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepMapperState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepMapper:
    """Maps step inputs to outputs with transformation records."""

    PREFIX = "psma-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepMapperState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("_seq_num", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, action: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._callbacks

    @on_change.setter
    def on_change(self, value):
        if callable(value):
            self._callbacks["default"] = value
        elif isinstance(value, dict):
            self._callbacks = value

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def create_mapping(
        self,
        pipeline_id: str,
        step_name: str,
        input_keys: List[str],
        output_keys: List[str],
        metadata: dict = None,
    ) -> str:
        mapping_id = self._generate_id(f"{pipeline_id}{step_name}{time.time()}")
        seq_num = self._state._seq
        entry = {
            "mapping_id": mapping_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "input_keys": copy.deepcopy(input_keys),
            "output_keys": copy.deepcopy(output_keys),
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "transforms": [],
            "created_at": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[mapping_id] = entry
        self._prune()
        self._fire("mapping_created", copy.deepcopy(entry))
        return mapping_id

    def get_mapping(self, mapping_id: str) -> Optional[dict]:
        entry = self._state.entries.get(mapping_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_mappings(
        self, pipeline_id: str = "", step_name: str = "", limit: int = 50
    ) -> List[dict]:
        results = [
            e
            for e in self._state.entries.values()
            if (not pipeline_id or e["pipeline_id"] == pipeline_id)
            and (not step_name or e["step_name"] == step_name)
        ]
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq_num", 0)), reverse=True)
        return [copy.deepcopy(r) for r in results[:limit]]

    def record_transform(
        self, mapping_id: str, input_data: dict, output_data: dict
    ) -> bool:
        entry = self._state.entries.get(mapping_id)
        if entry is None:
            return False
        transform = {
            "input_data": copy.deepcopy(input_data),
            "output_data": copy.deepcopy(output_data),
            "recorded_at": time.time(),
        }
        entry["transforms"].append(transform)
        self._fire(
            "transform_recorded",
            copy.deepcopy({"mapping_id": mapping_id, "transform": transform}),
        )
        return True

    def get_mapping_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        total_transforms = sum(
            len(e.get("transforms", [])) for e in self._state.entries.values()
        )
        unique_pipelines = set(
            e["pipeline_id"] for e in self._state.entries.values()
        )
        return {
            "total_mappings": len(self._state.entries),
            "total_transforms": total_transforms,
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineStepMapperState()
        self._callbacks.clear()
        self._fire("reset", {})
