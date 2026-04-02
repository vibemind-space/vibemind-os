"""Pipeline data aggregator.

Defines and applies field-level aggregation rules (sum, avg, count, min, max)
over records flowing through pipelines.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

VALID_OPERATIONS = ("sum", "avg", "count", "min", "max")


@dataclass
class _State:
    """Internal state for PipelineDataAggregator."""
    aggregations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataAggregator:
    """Applies field-level aggregation rules to pipeline records."""

    MAX_AGGREGATIONS = 10000

    def __init__(self) -> None:
        self._state = _State()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pda-{digest}"

    # ------------------------------------------------------------------
    # Aggregation CRUD
    # ------------------------------------------------------------------

    def create_aggregation(
        self,
        pipeline_id: str,
        field: str,
        operation: str = "sum",
    ) -> str:
        """Create an aggregation rule and return its id (pda-...)."""
        if not pipeline_id or not field:
            logger.warning("create_aggregation.invalid_args",
                           pipeline_id=pipeline_id, field=field)
            return ""
        if operation not in VALID_OPERATIONS:
            logger.warning("create_aggregation.bad_operation",
                           operation=operation)
            return ""
        if len(self._state.aggregations) >= self.MAX_AGGREGATIONS:
            logger.warning("create_aggregation.limit_reached")
            return ""

        agg_id = self._next_id()
        self._state.aggregations[agg_id] = {
            "agg_id": agg_id,
            "pipeline_id": pipeline_id,
            "field": field,
            "operation": operation,
            "created_at": time.time(),
            "apply_count": 0,
        }
        logger.info("aggregation_created", agg_id=agg_id,
                     pipeline_id=pipeline_id, field=field,
                     operation=operation)
        self._fire("aggregation_created", {"agg_id": agg_id,
                                           "pipeline_id": pipeline_id})
        return agg_id

    def get_aggregation(self, agg_id: str) -> Optional[Dict]:
        """Return aggregation dict or None."""
        agg = self._state.aggregations.get(agg_id)
        if agg is None:
            return None
        return dict(agg)

    def get_aggregations(self, pipeline_id: str) -> List[Dict]:
        """Return all aggregations for a given pipeline."""
        return [
            dict(a) for a in self._state.aggregations.values()
            if a["pipeline_id"] == pipeline_id
        ]

    def get_aggregation_count(self, pipeline_id: str = "") -> int:
        """Return count of aggregations, optionally filtered by pipeline."""
        if not pipeline_id:
            return len(self._state.aggregations)
        return sum(
            1 for a in self._state.aggregations.values()
            if a["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> List[str]:
        """Return sorted list of distinct pipeline ids."""
        pids = {a["pipeline_id"] for a in self._state.aggregations.values()}
        return sorted(pids)

    # ------------------------------------------------------------------
    # Aggregation execution
    # ------------------------------------------------------------------

    def aggregate(self, agg_id: str, records: List[Dict]) -> Dict:
        """Apply the aggregation rule to *records* and return result dict."""
        agg = self._state.aggregations.get(agg_id)
        if agg is None:
            logger.warning("aggregate.unknown_agg", agg_id=agg_id)
            return {}

        f = agg["field"]
        op = agg["operation"]

        values = [r[f] for r in records if f in r]

        if op == "count":
            result = len(values)
        elif not values:
            result = 0
        elif op == "sum":
            result = sum(values)
        elif op == "avg":
            result = sum(values) / len(values)
        elif op == "min":
            result = min(values)
        elif op == "max":
            result = max(values)
        else:
            result = 0

        agg["apply_count"] += 1
        self._fire("aggregation_applied", {"agg_id": agg_id, "result": result})
        return {
            "agg_id": agg_id,
            "field": f,
            "operation": op,
            "result": result,
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return summary statistics."""
        total_applies = sum(
            a["apply_count"] for a in self._state.aggregations.values()
        )
        return {
            "total_aggregations": len(self._state.aggregations),
            "total_pipelines": len(self.list_pipelines()),
            "total_applies": total_applies,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.aggregations.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("pipeline_data_aggregator_reset")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
