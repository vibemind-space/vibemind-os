"""Pipeline step inspector -- inspects and records step execution details.

Records inspection data for pipeline steps including input/output data,
duration, and status. Supports filtering, statistics, and change callbacks.
"""

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepInspectorState:
    """Internal state for the PipelineStepInspector service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepInspector:
    """Inspects and records step execution details for pipelines."""

    PREFIX = "psin-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepInspectorState()
        self._callbacks: dict = {}

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Inspection operations
    # ------------------------------------------------------------------

    def inspect_step(
        self,
        pipeline_id: str,
        step_name: str,
        input_data: dict = None,
        output_data: dict = None,
        duration: float = 0.0,
        status: str = "ok",
    ) -> str:
        """Record an inspection of a pipeline step execution. Returns inspection ID."""
        inspection_id = self._generate_id(
            f"{pipeline_id}{step_name}{time.time()}"
        )
        seq_num = self._state._seq
        entry = {
            "inspection_id": inspection_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "input_data": copy.deepcopy(input_data) if input_data else {},
            "output_data": copy.deepcopy(output_data) if output_data else {},
            "duration": duration,
            "status": status,
            "created_at": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[inspection_id] = entry
        self._prune()
        self._fire("inspection_created", copy.deepcopy(entry))
        return inspection_id

    def get_inspection(self, inspection_id: str) -> Optional[dict]:
        """Get a single inspection by ID."""
        entry = self._state.entries.get(inspection_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_inspections(
        self,
        pipeline_id: str = "",
        step_name: str = "",
        status: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """List inspections, newest first. Optionally filter by pipeline_id, step_name, status."""
        results = []
        for e in self._state.entries.values():
            if pipeline_id and e["pipeline_id"] != pipeline_id:
                continue
            if step_name and e["step_name"] != step_name:
                continue
            if status and e["status"] != status:
                continue
            results.append(e)
        results.sort(
            key=lambda x: (x.get("created_at", 0), x.get("_seq_num", 0)),
            reverse=True,
        )
        return [copy.deepcopy(r) for r in results[:limit]]

    def get_inspection_count(
        self, pipeline_id: str = "", status: str = ""
    ) -> int:
        """Count inspections, optionally filtered by pipeline_id and/or status."""
        if not pipeline_id and not status:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if pipeline_id and e["pipeline_id"] != pipeline_id:
                continue
            if status and e["status"] != status:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._state.entries)
        by_status: Dict[str, int] = {}
        total_duration = 0.0
        unique_pipelines: set = set()

        for e in self._state.entries.values():
            s = e.get("status", "ok")
            by_status[s] = by_status.get(s, 0) + 1
            total_duration += e.get("duration", 0.0)
            unique_pipelines.add(e["pipeline_id"])

        return {
            "total_inspections": total,
            "by_status": by_status,
            "avg_duration": total_duration / total if total > 0 else 0.0,
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Reset all state and callbacks."""
        self._state = PipelineStepInspectorState()
        self._callbacks.clear()
        self._fire("reset", {})
