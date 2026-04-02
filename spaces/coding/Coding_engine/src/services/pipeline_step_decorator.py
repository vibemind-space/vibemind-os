"""Pipeline step decorator — decorates pipeline steps with additional metadata/tags.

Allows attaching tags and metadata to pipeline steps for categorization,
filtering, and operational insight across pipeline executions.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineStepDecoratorState:
    """Internal state for the PipelineStepDecorator service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepDecorator:
    """Decorates pipeline steps with additional metadata and tags.

    Supports creating decoration records, querying by pipeline/step,
    adding tags after creation, and computing aggregate statistics.
    """

    PREFIX = "psdc-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepDecoratorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries.keys(),
            key=lambda k: self._state.entries[k].get("_seq", 0),
        )
        target = self.MAX_ENTRIES - 1
        remove_count = len(self._state.entries) - target
        if remove_count <= 0:
            return
        for entry_id in sorted_ids[:remove_count]:
            del self._state.entries[entry_id]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently caught."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Decorate
    # ------------------------------------------------------------------

    def decorate(
        self,
        pipeline_id: str,
        step_name: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a decoration record for a pipeline step. Returns the decoration ID."""
        self._prune()
        decoration_id = self._generate_id()
        entry = {
            "id": decoration_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "tags": list(tags) if tags else [],
            "metadata": dict(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[decoration_id] = entry
        self._fire("decoration_created", entry)
        return decoration_id

    # ------------------------------------------------------------------
    # Get decoration
    # ------------------------------------------------------------------

    def get_decoration(self, decoration_id: str) -> Optional[dict]:
        """Retrieve a single decoration by ID. Returns None if not found."""
        entry = self._state.entries.get(decoration_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get decorations
    # ------------------------------------------------------------------

    def get_decorations(
        self,
        pipeline_id: str = "",
        step_name: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return decorations filtered by pipeline/step, newest first."""
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: e.get("_seq", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Add tag
    # ------------------------------------------------------------------

    def add_tag(self, decoration_id: str, tag: str) -> bool:
        """Add a tag to an existing decoration. Returns False if not found."""
        entry = self._state.entries.get(decoration_id)
        if entry is None:
            return False
        if tag not in entry["tags"]:
            entry["tags"].append(tag)
        self._fire("tag_added", {"id": decoration_id, "tag": tag})
        return True

    # ------------------------------------------------------------------
    # Get decoration count
    # ------------------------------------------------------------------

    def get_decoration_count(self, pipeline_id: str = "") -> int:
        """Count decorations, optionally filtered by pipeline_id."""
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
        """Return aggregate statistics about stored decorations."""
        all_tags: set = set()
        all_pipelines: set = set()
        for entry in self._state.entries.values():
            all_tags.update(entry.get("tags", []))
            all_pipelines.add(entry["pipeline_id"])
        return {
            "total_decorations": len(self._state.entries),
            "unique_tags": len(all_tags),
            "unique_pipelines": len(all_pipelines),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored entries, callbacks, and reset sequence."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
        self._fire("reset", {})
