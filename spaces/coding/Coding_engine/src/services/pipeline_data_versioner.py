"""Pipeline Data Versioner -- versions pipeline data records with version numbers.

Creates and manages versioned pipeline data records, supporting version numbering,
labels, querying by pipeline, and retrieving the latest version.
Uses SHA-256-based IDs with a ``pdve-`` prefix.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataVersionerState:
    """Internal store for versioned pipeline data entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataVersioner:
    """Versions pipeline data records with version numbers.

    Supports creating versioned records, querying by pipeline, retrieving
    the latest version, and collecting statistics.
    """

    PREFIX = "pdve-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataVersionerState()
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict the oldest entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(), key=lambda kv: kv[1].get("created_at", 0)
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
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

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Create version
    # ------------------------------------------------------------------

    def create_version(
        self,
        pipeline_id: str,
        data: dict,
        version: int = 1,
        label: str = "",
    ) -> str:
        """Create a versioned pipeline data record.

        Returns the version ID (``pdve-`` prefix).
        """
        self._prune()
        version_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "version_id": version_id,
            "pipeline_id": pipeline_id,
            "data": copy.deepcopy(data),
            "version": version,
            "label": label,
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[version_id] = entry
        self._fire("version_created", copy.deepcopy(entry))
        logger.debug(
            "Version created: %s for pipeline=%s version=%d label=%s",
            version_id, pipeline_id, version, label,
        )
        return version_id

    # ------------------------------------------------------------------
    # Get version by ID
    # ------------------------------------------------------------------

    def get_version(self, version_id: str) -> Optional[dict]:
        """Get a version record by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(version_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    # ------------------------------------------------------------------
    # Get versions for a pipeline
    # ------------------------------------------------------------------

    def get_versions(self, pipeline_id: str, limit: int = 50) -> List[dict]:
        """Query versions for a pipeline, newest first.

        Sorted by created_at and _seq descending.  Capped by *limit*.
        """
        candidates = [
            e for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [copy.deepcopy(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get latest version
    # ------------------------------------------------------------------

    def get_latest_version(self, pipeline_id: str) -> Optional[dict]:
        """Get the version record with the highest version number for a pipeline.

        Returns ``None`` if no versions exist for the pipeline.
        """
        candidates = [
            e for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda e: e["version"])
        return copy.deepcopy(best)

    # ------------------------------------------------------------------
    # Get version count
    # ------------------------------------------------------------------

    def get_version_count(self, pipeline_id: str = "") -> int:
        """Return the number of versions, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the versioner."""
        pipelines = set()
        max_version = 0
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
            if entry["version"] > max_version:
                max_version = entry["version"]
        return {
            "total_versions": len(self._state.entries),
            "unique_pipelines": len(pipelines),
            "max_version_number": max_version,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored versions, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
