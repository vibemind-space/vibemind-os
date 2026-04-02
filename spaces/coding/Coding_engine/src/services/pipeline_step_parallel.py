"""Pipeline step parallel execution groups.

Define groups of pipeline steps that can execute in parallel.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepParallelState:
    """State container for parallel step groups."""
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepParallel:
    """Manage groups of pipeline steps for parallel execution."""

    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepParallelState()
        self._callbacks = {}
        self._created_at = time.time()

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "psp-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

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
        return self._callbacks.pop(cb_id, None) is not None

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def create_group(self, pipeline_id: str, group_name: str, steps=None) -> str:
        """Create a parallel step group."""
        group_id = self._generate_id(f"{pipeline_id}-{group_name}")
        entry = {
            "group_id": group_id,
            "pipeline_id": pipeline_id,
            "group_name": group_name,
            "steps": list(steps) if steps else [],
            "created_at": time.time(),
        }
        self._state.entries[group_id] = entry
        self._prune()
        self._fire("group_created", entry)
        logger.info("Created group %s for pipeline %s", group_id, pipeline_id)
        return group_id

    def add_step(self, group_id: str, step_name: str) -> bool:
        """Add a step to a group."""
        entry = self._state.entries.get(group_id)
        if not entry:
            return False
        if step_name in entry["steps"]:
            return False
        entry["steps"].append(step_name)
        self._fire("step_added", {"group_id": group_id, "step_name": step_name})
        return True

    def remove_step(self, group_id: str, step_name: str) -> bool:
        """Remove a step from a group."""
        entry = self._state.entries.get(group_id)
        if not entry or step_name not in entry["steps"]:
            return False
        entry["steps"].remove(step_name)
        self._fire("step_removed", {"group_id": group_id, "step_name": step_name})
        return True

    def execute_group(self, group_id: str, context=None, step_fns=None) -> dict:
        """Execute all steps in a group.

        step_fns is a dict of {step_name: callable}. Each callable receives context.
        Steps are executed sequentially but represent logically parallel work.
        """
        entry = self._state.entries.get(group_id)
        if not entry:
            return {"group_id": group_id, "results": {}, "success": False, "errors": ["Group not found"]}

        results = {}
        errors = []
        fns = step_fns or {}

        for step_name in entry["steps"]:
            fn = fns.get(step_name)
            if fn is None:
                errors.append(f"No function for step: {step_name}")
                results[step_name] = None
                continue
            try:
                results[step_name] = fn(context)
            except Exception as e:
                errors.append(f"Step {step_name} failed: {e}")
                results[step_name] = None

        success = len(errors) == 0
        result = {
            "group_id": group_id,
            "results": results,
            "success": success,
            "errors": errors,
        }
        self._fire("group_executed", result)
        return result

    def get_group(self, group_id: str):
        """Get a group by ID."""
        entry = self._state.entries.get(group_id)
        if entry is None:
            return None
        return dict(entry)

    def get_groups(self, pipeline_id: str) -> list:
        """Get all groups for a pipeline."""
        return [
            dict(e) for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        ]

    def get_group_count(self, pipeline_id: str = "") -> int:
        """Get the count of groups, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def list_pipelines(self) -> list:
        """List all unique pipeline IDs."""
        return list({
            e["pipeline_id"] for e in self._state.entries.values()
            if "pipeline_id" in e
        })

    def get_stats(self) -> dict:
        """Get statistics about the parallel step groups."""
        return {
            "total_groups": len(self._state.entries),
            "total_callbacks": len(self._callbacks),
            "seq": self._state._seq,
            "uptime": time.time() - self._created_at,
        }

    def reset(self):
        """Reset all state."""
        self._state = PipelineStepParallelState()
        self._callbacks.clear()
        logger.info("Reset pipeline step parallel state")
