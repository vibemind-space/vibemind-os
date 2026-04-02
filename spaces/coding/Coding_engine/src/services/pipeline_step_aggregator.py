"""Pipeline step aggregator - aggregates results from multiple pipeline step executions.

Collects, merges, or sums results from related pipeline steps,
enabling unified views of distributed step outputs.
"""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepAggregatorState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepAggregator:
    """Aggregates results from multiple pipeline step executions.

    Supports collect, merge, and sum strategies for combining
    step outputs into unified aggregation groups.
    """

    PREFIX = "psag-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepAggregatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepAggregator initialized")

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
    # Create aggregation
    # ------------------------------------------------------------------

    def create_aggregation(
        self,
        pipeline_id: str,
        step_names: List[str],
        strategy: str = "collect",
    ) -> str:
        """Create an aggregation group for pipeline step results.

        Args:
            pipeline_id: Identifier for the pipeline.
            step_names: List of step names to aggregate.
            strategy: Aggregation strategy - "collect", "merge", or "sum".

        Returns:
            Aggregation ID string, or empty string on invalid input.
        """
        if not pipeline_id or not step_names:
            return ""
        if strategy not in ("collect", "merge", "sum"):
            return ""
        self._prune()
        agg_id = self._generate_id(pipeline_id)
        now = time.time()
        self._state.entries[agg_id] = {
            "aggregation_id": agg_id,
            "pipeline_id": pipeline_id,
            "step_names": list(step_names),
            "strategy": strategy,
            "results": {},
            "created_at": now,
        }
        self._fire("aggregation_created", {
            "aggregation_id": agg_id,
            "pipeline_id": pipeline_id,
            "step_names": list(step_names),
            "strategy": strategy,
        })
        return agg_id

    # ------------------------------------------------------------------
    # Add result
    # ------------------------------------------------------------------

    def add_result(self, aggregation_id: str, step_name: str, result: Any) -> bool:
        """Add a step result to an aggregation group.

        Args:
            aggregation_id: The aggregation group ID.
            step_name: Name of the step producing the result.
            result: The result data to add.

        Returns:
            True if the result was added, False otherwise.
        """
        entry = self._state.entries.get(aggregation_id)
        if not entry:
            return False
        if not step_name:
            return False
        strategy = entry["strategy"]
        if strategy == "collect":
            if step_name not in entry["results"]:
                entry["results"][step_name] = []
            entry["results"][step_name].append(result)
        elif strategy == "merge":
            if step_name not in entry["results"]:
                entry["results"][step_name] = {}
            if isinstance(result, dict):
                entry["results"][step_name].update(result)
            else:
                entry["results"][step_name] = result
        elif strategy == "sum":
            if step_name not in entry["results"]:
                entry["results"][step_name] = 0
            if isinstance(result, (int, float)):
                entry["results"][step_name] += result
            else:
                entry["results"][step_name] = result
        self._fire("result_added", {
            "aggregation_id": aggregation_id,
            "step_name": step_name,
        })
        return True

    # ------------------------------------------------------------------
    # Get aggregation
    # ------------------------------------------------------------------

    def get_aggregation(self, aggregation_id: str) -> Optional[dict]:
        """Get an aggregation group by ID.

        Returns dict with aggregation info or None if not found.
        """
        entry = self._state.entries.get(aggregation_id)
        if not entry:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get aggregations
    # ------------------------------------------------------------------

    def get_aggregations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get aggregation groups, newest first.

        Args:
            pipeline_id: Optional filter by pipeline ID.
            limit: Maximum number of results.

        Returns:
            List of aggregation dicts, newest first.
        """
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Get aggregation count
    # ------------------------------------------------------------------

    def get_aggregation_count(self, pipeline_id: str = "") -> int:
        """Get count of aggregation groups.

        Args:
            pipeline_id: Optional filter by pipeline ID.

        Returns:
            Number of matching aggregations.
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

        Returns dict with total_aggregations, total_results,
        and unique_pipelines.
        """
        total_results = 0
        for entry in self._state.entries.values():
            for step_data in entry["results"].values():
                if isinstance(step_data, list):
                    total_results += len(step_data)
                else:
                    total_results += 1
        unique_pipelines = len(set(
            entry["pipeline_id"] for entry in self._state.entries.values()
        ))
        return {
            "total_aggregations": len(self._state.entries),
            "total_results": total_results,
            "unique_pipelines": unique_pipelines,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored aggregations, callbacks, and reset state."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
