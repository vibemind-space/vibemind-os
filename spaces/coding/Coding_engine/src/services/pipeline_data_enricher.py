"""Service module for emergent autonomous pipeline data enrichment system."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

MAX_ENTRIES = 10000


@dataclass
class _State:
    enrichers: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataEnricher:
    """Autonomous pipeline data enrichment service."""

    def __init__(self) -> None:
        self._state = _State()

    # ── ID generation ──────────────────────────────────────────────

    def _next_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pde-{digest}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.enrichers) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.enrichers,
                key=lambda k: self._state.enrichers[k].get("created_at", 0),
            )
            to_remove = len(self._state.enrichers) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.enrichers[k]
            logger.info("pruned_enrichers", removed=to_remove)

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

    def register_enricher(
        self,
        pipeline_id: str,
        field_name: str,
        default_value: Any = None,
        transform: str = "none",
    ) -> str:
        """Register an enrichment rule and return its enricher_id."""
        enricher_id = self._next_id(pipeline_id)
        record = {
            "enricher_id": enricher_id,
            "pipeline_id": pipeline_id,
            "field_name": field_name,
            "default_value": default_value,
            "transform": transform,
            "created_at": time.time(),
            "apply_count": 0,
        }
        self._state.enrichers[enricher_id] = record
        self._prune()
        self._fire("register_enricher", enricher_id=enricher_id, pipeline_id=pipeline_id)
        logger.info("enricher_registered", enricher_id=enricher_id, pipeline_id=pipeline_id)
        return enricher_id

    def enrich(self, pipeline_id: str, data: dict) -> dict:
        """Apply all registered enrichments for *pipeline_id* to *data*."""
        result = dict(data)
        for rec in self._state.enrichers.values():
            if rec["pipeline_id"] != pipeline_id:
                continue
            fname = rec["field_name"]
            if fname not in result:
                result[fname] = rec["default_value"]
            if rec["transform"] == "upper" and isinstance(result.get(fname), str):
                result[fname] = result[fname].upper()
            rec["apply_count"] += 1
        self._fire("enrich", pipeline_id=pipeline_id)
        return result

    def get_enricher(self, enricher_id: str) -> Optional[dict]:
        """Return enricher record or None."""
        return self._state.enrichers.get(enricher_id)

    def get_enrichers(self, pipeline_id: str) -> List[dict]:
        """Return all enrichers for a pipeline."""
        return [
            r for r in self._state.enrichers.values()
            if r["pipeline_id"] == pipeline_id
        ]

    def get_enricher_count(self, pipeline_id: str = "") -> int:
        """Return count of enrichers, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.enrichers)
        return sum(
            1 for r in self._state.enrichers.values()
            if r["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> list:
        """Return sorted list of unique pipeline IDs."""
        return sorted({r["pipeline_id"] for r in self._state.enrichers.values()})

    def get_stats(self) -> dict:
        """Return summary statistics."""
        pipelines = self.list_pipelines()
        total_applies = sum(r["apply_count"] for r in self._state.enrichers.values())
        return {
            "total_enrichers": len(self._state.enrichers),
            "total_pipelines": len(pipelines),
            "total_applies": total_applies,
            "pipelines": pipelines,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.enrichers.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        self._fire("reset")
        logger.info("pipeline_data_enricher_reset")
