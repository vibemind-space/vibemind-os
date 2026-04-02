"""Pipeline step composer for composing ordered step sequences for pipeline execution."""

import copy
import time
import hashlib
import dataclasses
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepComposerState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepComposer:
    """Composes ordered step sequences for pipeline execution."""

    PREFIX = "pscp-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepComposerState()
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

    def compose(
        self,
        pipeline_id: str,
        steps: List[str],
        label: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a composition of ordered steps for a pipeline. Returns composition ID."""
        composition_id = self._generate_id(f"{pipeline_id}{steps}{time.time()}")
        seq_num = self._state._seq
        entry = {
            "composition_id": composition_id,
            "pipeline_id": pipeline_id,
            "steps": copy.deepcopy(steps),
            "label": label,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[composition_id] = entry
        self._prune()
        self._fire("composition_created", copy.deepcopy(entry))
        return composition_id

    def get_composition(self, composition_id: str) -> Optional[dict]:
        """Get a single composition by ID."""
        entry = self._state.entries.get(composition_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def append_step(self, composition_id: str, step_name: str) -> bool:
        """Append a step to an existing composition."""
        entry = self._state.entries.get(composition_id)
        if entry is None:
            return False
        entry["steps"].append(step_name)
        self._fire(
            "step_appended",
            copy.deepcopy({"composition_id": composition_id, "step_name": step_name}),
        )
        return True

    def get_compositions(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """List compositions, newest first. Optionally filter by pipeline_id."""
        results = [
            e
            for e in self._state.entries.values()
            if not pipeline_id or e["pipeline_id"] == pipeline_id
        ]
        results.sort(
            key=lambda x: (x.get("created_at", 0), x.get("_seq_num", 0)),
            reverse=True,
        )
        return [copy.deepcopy(r) for r in results[:limit]]

    def get_composition_count(self, pipeline_id: str = "") -> int:
        """Count compositions, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total_steps = sum(
            len(e.get("steps", [])) for e in self._state.entries.values()
        )
        unique_pipelines = set(
            e["pipeline_id"] for e in self._state.entries.values()
        )
        return {
            "total_compositions": len(self._state.entries),
            "total_steps": total_steps,
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Reset all state and callbacks."""
        self._state = PipelineStepComposerState()
        self._callbacks.clear()
        self._fire("reset", {})
