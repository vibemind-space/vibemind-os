"""Service module for projecting/selecting specific fields from pipeline data records."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataProjectorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataProjector:
    """Projects/selects specific fields from pipeline data records (like SQL SELECT)."""

    PREFIX = "pdpr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataProjectorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
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

    def _fire(self, event: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.error("on_change callback error for event %s", event)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.error("callback %s error for event %s", name, event)

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

    def register_projection(
        self, name: str, fields: List[str], rename: Optional[Dict[str, str]] = None
    ) -> str:
        """Register a projection definition. Returns the projection ID."""
        proj_id = self._generate_id(name)
        self._state.entries[proj_id] = {
            "name": name,
            "fields": list(fields),
            "rename": dict(rename) if rename else {},
            "created_at": time.time(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("register", {"projection_id": proj_id, "name": name})
        logger.info("registered projection %s as %s", name, proj_id)
        return proj_id

    def project(self, projection_id: str, record: dict) -> dict:
        """Apply a projection to a single record. Returns projected dict."""
        entry = self._state.entries.get(projection_id)
        if entry is None:
            logger.warning("projection %s not found", projection_id)
            return {}
        fields = entry["fields"]
        rename = entry["rename"]
        result: Dict[str, Any] = {}
        for f in fields:
            if f in record:
                out_key = rename.get(f, f)
                result[out_key] = record[f]
        entry["usage_count"] += 1
        self._fire("project", {"projection_id": projection_id})
        return result

    def project_batch(self, projection_id: str, records: List[dict]) -> List[dict]:
        """Apply a projection to a list of records."""
        return [self.project(projection_id, r) for r in records]

    def get_projection(self, projection_id: str) -> dict:
        """Return a projection entry by ID, or empty dict if not found."""
        entry = self._state.entries.get(projection_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_projections(self) -> List[dict]:
        """Return all registered projections."""
        result = []
        for pid, entry in self._state.entries.items():
            item = dict(entry)
            item["projection_id"] = pid
            result.append(item)
        return result

    def get_projection_count(self) -> int:
        """Return the number of registered projections."""
        return len(self._state.entries)

    def remove_projection(self, projection_id: str) -> bool:
        """Remove a projection by ID. Returns True if removed."""
        if projection_id in self._state.entries:
            del self._state.entries[projection_id]
            self._fire("remove", {"projection_id": projection_id})
            return True
        return False

    def get_stats(self) -> dict:
        """Return statistics about projections."""
        total_ops = sum(
            e.get("usage_count", 0) for e in self._state.entries.values()
        )
        return {
            "total_projections": len(self._state.entries),
            "total_operations": total_ops,
        }

    def reset(self) -> None:
        """Clear all projections and reset state."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
        logger.info("projector state reset")
