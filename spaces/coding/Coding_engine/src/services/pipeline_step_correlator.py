"""Pipeline step correlator - correlates related pipeline step executions.

Groups related pipeline step executions by correlation keys, enabling
tracking of which steps belong together across pipeline runs.
"""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepCorrelatorState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepCorrelator:
    """Correlates related pipeline step executions by grouping them.

    Creates correlation groups that track which pipeline steps
    are related, enabling cross-step analysis and monitoring.
    """

    PREFIX = "psco-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepCorrelatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepCorrelator initialized")

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
    # Correlate
    # ------------------------------------------------------------------

    def correlate(
        self,
        pipeline_id: str,
        step_names: List[str],
        correlation_key: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a correlation group for related pipeline steps.

        Args:
            pipeline_id: Identifier for the pipeline.
            step_names: List of step names to correlate.
            correlation_key: Optional key for grouping correlations.
            metadata: Optional metadata dict.

        Returns:
            Correlation ID string.
        """
        if not pipeline_id or not step_names:
            return ""
        self._prune()
        corr_id = self._generate_id(pipeline_id)
        now = time.time()
        self._state.entries[corr_id] = {
            "correlation_id": corr_id,
            "pipeline_id": pipeline_id,
            "step_names": list(step_names),
            "correlation_key": correlation_key,
            "metadata": dict(metadata) if metadata else {},
            "created_at": now,
        }
        self._fire("correlation_created", {
            "correlation_id": corr_id,
            "pipeline_id": pipeline_id,
            "step_names": list(step_names),
        })
        return corr_id

    # ------------------------------------------------------------------
    # Get correlation
    # ------------------------------------------------------------------

    def get_correlation(self, correlation_id: str) -> Optional[dict]:
        """Get a correlation group by ID.

        Returns dict with correlation info or None if not found.
        """
        entry = self._state.entries.get(correlation_id)
        if not entry:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get correlations
    # ------------------------------------------------------------------

    def get_correlations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get correlation groups, newest first.

        Args:
            pipeline_id: Optional filter by pipeline ID.
            limit: Maximum number of results.

        Returns:
            List of correlation dicts, newest first.
        """
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Add step to correlation
    # ------------------------------------------------------------------

    def add_step_to_correlation(self, correlation_id: str, step_name: str) -> bool:
        """Add a step name to an existing correlation group.

        Args:
            correlation_id: The correlation group ID.
            step_name: Step name to add.

        Returns:
            True if step was added, False otherwise.
        """
        entry = self._state.entries.get(correlation_id)
        if not entry:
            return False
        if not step_name:
            return False
        if step_name in entry["step_names"]:
            return False
        entry["step_names"].append(step_name)
        self._fire("step_added", {
            "correlation_id": correlation_id,
            "step_name": step_name,
        })
        return True

    # ------------------------------------------------------------------
    # Get correlation count
    # ------------------------------------------------------------------

    def get_correlation_count(self, pipeline_id: str = "") -> int:
        """Get count of correlation groups.

        Args:
            pipeline_id: Optional filter by pipeline ID.

        Returns:
            Number of matching correlations.
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

        Returns dict with total_correlations, total_steps_correlated,
        and unique_pipelines.
        """
        total_steps = sum(
            len(entry["step_names"]) for entry in self._state.entries.values()
        )
        unique_pipelines = len(set(
            entry["pipeline_id"] for entry in self._state.entries.values()
        ))
        return {
            "total_correlations": len(self._state.entries),
            "total_steps_correlated": total_steps,
            "unique_pipelines": unique_pipelines,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored correlations, callbacks, and reset state."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
