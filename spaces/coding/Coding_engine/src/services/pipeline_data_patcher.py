"""Service module for applying patches to pipeline data records."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataPatcherState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataPatcher:
    """Applies patches (key/value updates) to pipeline data records."""

    PREFIX = "pdpa-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataPatcherState()
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

    def apply_patch(self, data: dict, patches: Dict[str, Any], label: str = "") -> str:
        """Apply *patches* to a deep copy of *data*, store both original and patched, return patch ID."""
        patch_id = self._generate_id()
        original_data = copy.deepcopy(data)
        patched_data = copy.deepcopy(data)
        patched_data.update(patches)
        record: Dict[str, Any] = {
            "patch_id": patch_id,
            "label": label,
            "original_data": original_data,
            "patched_data": patched_data,
            "patches": copy.deepcopy(patches),
            "keys_patched": list(patches.keys()),
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[patch_id] = record
        self._prune()
        self._fire("apply_patch", record)
        return patch_id

    def get_patch(self, patch_id: str) -> Optional[dict]:
        """Return the patch record for *patch_id*, or ``None``."""
        entry = self._state.entries.get(patch_id)
        if entry is None:
            return None
        return dict(entry)

    def get_patches(self, label: str = "", limit: int = 50) -> List[dict]:
        """Return patch records, newest first, optionally filtered by *label*."""
        results = list(self._state.entries.values())
        if label:
            results = [r for r in results if r.get("label") == label]
        results.sort(key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True)
        return [dict(r) for r in results[:limit]]

    def revert_patch(self, patch_id: str) -> Optional[dict]:
        """Return a deep copy of the original (pre-patch) data, or ``None``."""
        entry = self._state.entries.get(patch_id)
        if entry is None:
            return None
        return copy.deepcopy(entry.get("original_data"))

    def get_patch_count(self, label: str = "") -> int:
        """Return the number of patches, optionally filtered by *label*."""
        if not label:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("label") == label)

    def get_stats(self) -> dict:
        """Return summary statistics about stored patches."""
        labels = {e.get("label", "") for e in self._state.entries.values()}
        total_keys = sum(len(e.get("keys_patched", [])) for e in self._state.entries.values())
        return {
            "total_patches": len(self._state.entries),
            "unique_labels": len(labels),
            "total_keys_patched": total_keys,
        }

    def reset(self) -> None:
        """Clear all patch records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
