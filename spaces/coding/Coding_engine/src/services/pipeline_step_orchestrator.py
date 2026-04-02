"""Pipeline step orchestrator — orchestrates pipeline step execution strategies.

Manages the orchestration of pipeline steps with configurable execution
strategies (sequential, parallel, etc.) and tracks orchestration records.
"""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepOrchestratorState:
    """Internal state for the PipelineStepOrchestrator service."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepOrchestrator:
    """Orchestrates pipeline step execution with configurable strategies.

    Supports sequential, parallel, and other execution strategies for
    pipeline steps, maintaining orchestration records for tracking.
    """

    PREFIX = "psor-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepOrchestratorState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest quarter of entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # orchestrate
    # ------------------------------------------------------------------

    def orchestrate(
        self,
        pipeline_id: str,
        step_name: str,
        strategy: str = "sequential",
        metadata: Optional[dict] = None,
    ) -> str:
        """Orchestrate a pipeline step. Returns record ID or '' for empty params."""
        if not pipeline_id or not step_name:
            return ""
        self._prune()
        record_id = self._generate_id()
        now = time.time()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "strategy": strategy,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._fire("orchestrated", record_id=record_id, pipeline_id=pipeline_id,
                    step_name=step_name, strategy=strategy)
        return record_id

    # ------------------------------------------------------------------
    # get_orchestration
    # ------------------------------------------------------------------

    def get_orchestration(self, record_id: str) -> Optional[dict]:
        """Get a single orchestration by ID. Returns None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # get_orchestrations
    # ------------------------------------------------------------------

    def get_orchestrations(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Get orchestrations, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_orchestration_count
    # ------------------------------------------------------------------

    def get_orchestration_count(self, pipeline_id: str = "") -> int:
        """Count orchestrations, optionally filtering by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        entries = list(self._state.entries.values())
        total = len(entries)
        pipelines = set(e.get("pipeline_id", "") for e in entries)
        return {
            "total_orchestrations": total,
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence."""
        self._state = PipelineStepOrchestratorState()
        self._on_change = None
