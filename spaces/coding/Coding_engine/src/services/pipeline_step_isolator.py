"""Pipeline step isolator - isolates step execution contexts.

Prevents cross-contamination between pipeline step executions by
maintaining isolated contexts for each step, ensuring one step's
state changes do not affect another.
"""

import copy
import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepIsolatorState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepIsolator:
    """Isolates step execution contexts to prevent cross-contamination.

    Each pipeline step gets its own isolated context that can be
    created, read, and updated independently without affecting
    other steps in the same or different pipelines.
    """

    PREFIX = "psis-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepIsolatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepIsolator initialized")

    def _generate_id(self, data: str = "") -> str:
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
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

    def _fire(self, action: str, data: dict):
        if self._on_change:
            try:
                self._on_change(action, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
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

    # ------------------------------------------------------------------
    # Create isolation
    # ------------------------------------------------------------------

    def create_isolation(
        self,
        pipeline_id: str,
        step_name: str,
        context: dict = None,
    ) -> str:
        """Create an isolated context for a pipeline step.

        Args:
            pipeline_id: Identifier for the pipeline.
            step_name: Name of the step to isolate.
            context: Optional initial context dict (deep copied).

        Returns:
            Isolation ID string, or empty string on invalid input.
        """
        if not pipeline_id or not step_name:
            return ""
        self._prune()
        isolation_id = self._generate_id(pipeline_id)
        now = time.time()
        self._state.entries[isolation_id] = {
            "isolation_id": isolation_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "context": copy.deepcopy(context) if context else {},
            "created_at": now,
            "updated_at": now,
        }
        self._fire("isolation_created", {
            "isolation_id": isolation_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
        })
        return isolation_id

    # ------------------------------------------------------------------
    # Get isolation
    # ------------------------------------------------------------------

    def get_isolation(self, isolation_id: str) -> Optional[dict]:
        """Get an isolation entry by ID.

        Returns dict with isolation info or None if not found.
        """
        entry = self._state.entries.get(isolation_id)
        if not entry:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get context (deep copy)
    # ------------------------------------------------------------------

    def get_context(self, isolation_id: str) -> Optional[dict]:
        """Get a deep copy of the isolated context.

        Args:
            isolation_id: The isolation ID.

        Returns:
            Deep copy of the context dict, or None if not found.
        """
        entry = self._state.entries.get(isolation_id)
        if not entry:
            return None
        return copy.deepcopy(entry["context"])

    # ------------------------------------------------------------------
    # Update context
    # ------------------------------------------------------------------

    def update_context(self, isolation_id: str, updates: dict) -> bool:
        """Merge updates into the isolated context.

        Args:
            isolation_id: The isolation ID.
            updates: Dict of key-value pairs to merge into context.

        Returns:
            True if updated, False if isolation not found.
        """
        entry = self._state.entries.get(isolation_id)
        if not entry:
            return False
        entry["context"].update(copy.deepcopy(updates))
        entry["updated_at"] = time.time()
        self._fire("context_updated", {
            "isolation_id": isolation_id,
            "updated_keys": list(updates.keys()),
        })
        return True

    # ------------------------------------------------------------------
    # Get isolations
    # ------------------------------------------------------------------

    def get_isolations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get isolation entries, newest first.

        Args:
            pipeline_id: Optional filter by pipeline ID.
            limit: Maximum number of results.

        Returns:
            List of isolation dicts, newest first.
        """
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Get isolation count
    # ------------------------------------------------------------------

    def get_isolation_count(self, pipeline_id: str = "") -> int:
        """Get count of isolation entries.

        Args:
            pipeline_id: Optional filter by pipeline ID.

        Returns:
            Number of matching isolations.
        """
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for entry in self._state.entries.values()
            if entry["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics.

        Returns dict with total_isolations, unique_pipelines,
        and unique_steps.
        """
        unique_pipelines = len(set(
            entry["pipeline_id"] for entry in self._state.entries.values()
        ))
        unique_steps = len(set(
            entry["step_name"] for entry in self._state.entries.values()
        ))
        return {
            "total_isolations": len(self._state.entries),
            "unique_pipelines": unique_pipelines,
            "unique_steps": unique_steps,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored isolations, callbacks, and reset state."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
