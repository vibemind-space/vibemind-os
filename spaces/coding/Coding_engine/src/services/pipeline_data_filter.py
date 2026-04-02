"""Service module for emergent autonomous pipeline data filtering system."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

MAX_ENTRIES = 10000

VALID_OPERATORS = ("eq", "neq", "gt", "lt", "contains")


@dataclass
class _State:
    filters: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataFilter:
    """Autonomous pipeline data filtering service."""

    def __init__(self) -> None:
        self._state = _State()

    # ── ID generation ──────────────────────────────────────────────

    def _next_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdf2-{digest}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.filters) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.filters,
                key=lambda k: self._state.filters[k].get("created_at", 0),
            )
            to_remove = len(self._state.filters) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.filters[k]
            logger.info("pruned_filters", removed=to_remove)

    # ── Callbacks ──────────────────────────────────────────────────

    def on_change(self, name: str, cb: Callable) -> None:
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ── API ────────────────────────────────────────────────────────

    def add_filter(
        self,
        pipeline_id: str,
        field: str,
        operator: str,
        value: Any,
    ) -> str:
        """Add a filter rule and return its filter_id."""
        if operator not in VALID_OPERATORS:
            raise ValueError(f"Invalid operator '{operator}', must be one of {VALID_OPERATORS}")
        filter_id = self._next_id(pipeline_id)
        record = {
            "filter_id": filter_id,
            "pipeline_id": pipeline_id,
            "field": field,
            "operator": operator,
            "value": value,
            "created_at": time.time(),
            "apply_count": 0,
        }
        self._state.filters[filter_id] = record
        self._prune()
        logger.info("filter_added", filter_id=filter_id, pipeline_id=pipeline_id)
        self._fire("add_filter", filter_id=filter_id, pipeline_id=pipeline_id)
        return filter_id

    def _match(self, record: dict, filt: dict) -> bool:
        """Check whether a single record matches a single filter."""
        fld = filt["field"]
        if fld not in record:
            return False
        val = record[fld]
        op = filt["operator"]
        target = filt["value"]
        if op == "eq":
            return val == target
        if op == "neq":
            return val != target
        if op == "gt":
            return val > target
        if op == "lt":
            return val < target
        if op == "contains":
            return target in val
        return False

    def apply_filters(self, pipeline_id: str, records: List[dict]) -> List[dict]:
        """Apply all filters for *pipeline_id* to *records*, returning matching ones."""
        pipeline_filters = [
            f for f in self._state.filters.values() if f["pipeline_id"] == pipeline_id
        ]
        if not pipeline_filters:
            return list(records)
        result: List[dict] = []
        for rec in records:
            if all(self._match(rec, f) for f in pipeline_filters):
                result.append(rec)
        for f in pipeline_filters:
            f["apply_count"] += 1
        logger.info(
            "filters_applied",
            pipeline_id=pipeline_id,
            input_count=len(records),
            output_count=len(result),
        )
        self._fire("apply_filters", pipeline_id=pipeline_id, matched=len(result))
        return result

    def get_filters(self, pipeline_id: str) -> List[dict]:
        """Return all filter records for the given pipeline."""
        return [
            dict(f) for f in self._state.filters.values() if f["pipeline_id"] == pipeline_id
        ]

    def remove_filter(self, filter_id: str) -> bool:
        """Remove a filter by its id. Returns True if found and removed."""
        if filter_id in self._state.filters:
            removed = self._state.filters.pop(filter_id)
            logger.info("filter_removed", filter_id=filter_id)
            self._fire("remove_filter", filter_id=filter_id, pipeline_id=removed["pipeline_id"])
            return True
        return False

    def get_filter_count(self, pipeline_id: str = "") -> int:
        """Return the number of filters, optionally scoped to a pipeline."""
        if not pipeline_id:
            return len(self._state.filters)
        return sum(1 for f in self._state.filters.values() if f["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of unique pipeline IDs that have filters."""
        return sorted({f["pipeline_id"] for f in self._state.filters.values()})

    def get_stats(self) -> dict:
        """Return summary statistics about current filter state."""
        pipelines = self.list_pipelines()
        total_applies = sum(f["apply_count"] for f in self._state.filters.values())
        return {
            "total_filters": len(self._state.filters),
            "total_pipelines": len(pipelines),
            "total_apply_count": total_applies,
            "callbacks_registered": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all filters, reset sequence counter, and remove callbacks."""
        self._state.filters.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")
