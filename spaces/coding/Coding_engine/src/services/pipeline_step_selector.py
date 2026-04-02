"""Pipeline step selector - selects which pipeline steps to execute.

Selects which pipeline steps to execute based on conditions and
criteria such as all, first, or random selection strategies.
"""

import random
import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepSelectorState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepSelector:
    """Selects which pipeline steps to execute based on conditions.

    Supports criteria-based selection: all steps, first step only,
    or random step selection from a given list of step names.
    """

    PREFIX = "psse-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepSelectorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepSelector initialized")

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
    # Create selector
    # ------------------------------------------------------------------

    def create_selector(
        self,
        pipeline_id: str,
        step_names: List[str],
        criteria: str = "all",
    ) -> str:
        """Create a selection rule for pipeline steps.

        Args:
            pipeline_id: Identifier for the pipeline.
            step_names: List of step names to select from.
            criteria: Selection criteria - "all", "first", or "random".

        Returns:
            Selector ID string, or empty string on invalid input.
        """
        if not pipeline_id or not step_names:
            return ""
        if criteria not in ("all", "first", "random"):
            return ""
        self._prune()
        selector_id = self._generate_id(pipeline_id)
        now = time.time()
        self._state.entries[selector_id] = {
            "selector_id": selector_id,
            "pipeline_id": pipeline_id,
            "step_names": list(step_names),
            "criteria": criteria,
            "created_at": now,
            "_seq": self._state._seq,
            "total_selections": 0,
        }
        self._fire("selector_created", {
            "selector_id": selector_id,
            "pipeline_id": pipeline_id,
            "criteria": criteria,
        })
        return selector_id

    # ------------------------------------------------------------------
    # Get selector
    # ------------------------------------------------------------------

    def get_selector(self, selector_id: str) -> Optional[dict]:
        """Get a selector entry by ID.

        Returns dict with selector info or None if not found.
        """
        entry = self._state.entries.get(selector_id)
        if not entry:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Select
    # ------------------------------------------------------------------

    def select(self, selector_id: str) -> List[str]:
        """Apply selector criteria and return selected step names.

        Args:
            selector_id: The selector ID.

        Returns:
            List of selected step name strings, or empty list if not found.
        """
        entry = self._state.entries.get(selector_id)
        if not entry:
            return []
        criteria = entry["criteria"]
        step_names = entry["step_names"]
        if criteria == "all":
            selected = list(step_names)
        elif criteria == "first":
            selected = [step_names[0]] if step_names else []
        elif criteria == "random":
            selected = [random.choice(step_names)] if step_names else []
        else:
            selected = []
        entry["total_selections"] += 1
        self._fire("selection_applied", {
            "selector_id": selector_id,
            "criteria": criteria,
            "selected": selected,
        })
        return selected

    # ------------------------------------------------------------------
    # Get selectors
    # ------------------------------------------------------------------

    def get_selectors(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get selector entries, newest first.

        Args:
            pipeline_id: Optional filter by pipeline ID.
            limit: Maximum number of results.

        Returns:
            List of selector dicts, newest first (sorted by created_at and _seq).
        """
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq", 0)), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Get selector count
    # ------------------------------------------------------------------

    def get_selector_count(self, pipeline_id: str = "") -> int:
        """Get count of selector entries.

        Args:
            pipeline_id: Optional filter by pipeline ID.

        Returns:
            Number of matching selectors.
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

        Returns dict with total_selectors, unique_pipelines,
        and total_selections.
        """
        unique_pipelines = len(set(
            entry["pipeline_id"] for entry in self._state.entries.values()
        ))
        total_selections = sum(
            entry["total_selections"] for entry in self._state.entries.values()
        )
        return {
            "total_selectors": len(self._state.entries),
            "unique_pipelines": unique_pipelines,
            "total_selections": total_selections,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored selectors, callbacks, and reset state."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
