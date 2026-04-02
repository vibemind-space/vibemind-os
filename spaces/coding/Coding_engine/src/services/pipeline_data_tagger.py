"""Service module for tagging pipeline data with categorization labels."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataTaggerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataTagger:
    """Tags pipeline data with categorization labels."""

    PREFIX = "pdtg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataTaggerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{digest}"

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, action: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def tag(self, pipeline_id: str, data: dict, tags: List[str], label: str = "") -> str:
        """Tag data with categorization labels and return the tag record ID."""
        record_id = self._generate_id()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "label": label,
            "data": copy.deepcopy(data),
            "tags": copy.deepcopy(tags),
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("tag", record)
        return record_id

    def get_tag_record(self, record_id: str) -> Optional[dict]:
        """Return the tag record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def add_tag(self, record_id: str, tag: str) -> bool:
        """Add a tag to an existing record. Returns True on success."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return False
        if tag not in entry["tags"]:
            entry["tags"].append(tag)
        self._fire("add_tag", {"record_id": record_id, "tag": tag})
        return True

    def remove_tag(self, record_id: str, tag: str) -> bool:
        """Remove a tag from an existing record. Returns True on success."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return False
        if tag not in entry["tags"]:
            return False
        entry["tags"].remove(tag)
        self._fire("remove_tag", {"record_id": record_id, "tag": tag})
        return True

    def get_tag_records(self, pipeline_id: str = "", tag: str = "", limit: int = 50) -> List[dict]:
        """Return tag records, newest first, optionally filtered by *pipeline_id* and/or *tag*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        if tag:
            results = [r for r in results if tag in r.get("tags", [])]
        results.sort(key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True)
        return [dict(r) for r in results[:limit]]

    def get_tag_count(self, pipeline_id: str = "") -> int:
        """Return the number of tag records, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        """Return summary statistics about stored tag records."""
        all_tags = set()
        all_pipelines = set()
        for e in self._state.entries.values():
            all_tags.update(e.get("tags", []))
            all_pipelines.add(e.get("pipeline_id", ""))
        return {
            "total_records": len(self._state.entries),
            "unique_tags": len(all_tags),
            "unique_pipelines": len(all_pipelines),
        }

    def reset(self) -> None:
        """Clear all tag records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
