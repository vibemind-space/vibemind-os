"""Service module for emergent autonomous pipeline data field mapping system."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)

MAX_ENTRIES = 10000

VALID_TRANSFORMS = ("copy", "uppercase", "lowercase")


@dataclass
class _State:
    mappings: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataMapper:
    """Autonomous pipeline data field mapping and transformation service."""

    def __init__(self) -> None:
        self._state = _State()

    # ── ID generation ──────────────────────────────────────────────

    def _next_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdma-{digest}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.mappings) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.mappings,
                key=lambda k: self._state.mappings[k].get("created_at", 0),
            )
            to_remove = len(self._state.mappings) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.mappings[k]
            logger.info("pruned_mappings", removed=to_remove)

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

    def add_mapping(
        self,
        pipeline_id: str,
        source_field: str,
        target_field: str,
        transform: str = "copy",
    ) -> str:
        """Add a field mapping and return its mapping_id."""
        if transform not in VALID_TRANSFORMS:
            raise ValueError(f"Invalid transform '{transform}', must be one of {VALID_TRANSFORMS}")
        mapping_id = self._next_id(pipeline_id)
        record = {
            "mapping_id": mapping_id,
            "pipeline_id": pipeline_id,
            "source_field": source_field,
            "target_field": target_field,
            "transform": transform,
            "created_at": time.time(),
            "apply_count": 0,
        }
        self._state.mappings[mapping_id] = record
        self._prune()
        logger.info("mapping_added", mapping_id=mapping_id, pipeline_id=pipeline_id)
        self._fire("add_mapping", mapping_id=mapping_id, pipeline_id=pipeline_id)
        return mapping_id

    def _apply_transform(self, value: Any, transform: str) -> Any:
        """Apply a single transform to a value."""
        if transform == "copy":
            return value
        if transform == "uppercase":
            return value.upper() if isinstance(value, str) else value
        if transform == "lowercase":
            return value.lower() if isinstance(value, str) else value
        return value

    def apply_mappings(self, pipeline_id: str, record: dict) -> dict:
        """Apply all mappings for *pipeline_id* to *record*, returning a new dict with target fields."""
        pipeline_mappings = [
            m for m in self._state.mappings.values() if m["pipeline_id"] == pipeline_id
        ]
        result: Dict[str, Any] = {}
        for mapping in pipeline_mappings:
            src = mapping["source_field"]
            tgt = mapping["target_field"]
            if src in record:
                result[tgt] = self._apply_transform(record[src], mapping["transform"])
            mapping["apply_count"] += 1
        logger.info("mappings_applied", pipeline_id=pipeline_id, mapping_count=len(pipeline_mappings))
        self._fire("apply_mappings", pipeline_id=pipeline_id, mapping_count=len(pipeline_mappings))
        return result

    def remove_mapping(self, mapping_id: str) -> bool:
        """Remove a mapping by its id. Returns True if found and removed."""
        if mapping_id in self._state.mappings:
            removed = self._state.mappings.pop(mapping_id)
            logger.info("mapping_removed", mapping_id=mapping_id)
            self._fire("remove_mapping", mapping_id=mapping_id, pipeline_id=removed["pipeline_id"])
            return True
        return False

    def get_mappings(self, pipeline_id: str) -> List[dict]:
        """Return all mapping records for the given pipeline."""
        return [
            dict(m) for m in self._state.mappings.values() if m["pipeline_id"] == pipeline_id
        ]

    def get_mapping_count(self, pipeline_id: str = "") -> int:
        """Return the number of mappings, optionally scoped to a pipeline."""
        if not pipeline_id:
            return len(self._state.mappings)
        return sum(1 for m in self._state.mappings.values() if m["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of unique pipeline IDs that have mappings."""
        return sorted({m["pipeline_id"] for m in self._state.mappings.values()})

    def get_stats(self) -> dict:
        """Return summary statistics about current mapping state."""
        pipelines = self.list_pipelines()
        total_applies = sum(m["apply_count"] for m in self._state.mappings.values())
        return {
            "total_mappings": len(self._state.mappings),
            "total_pipelines": len(pipelines),
            "total_apply_count": total_applies,
            "callbacks_registered": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all mappings, reset sequence counter, and remove callbacks."""
        self._state.mappings.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")
