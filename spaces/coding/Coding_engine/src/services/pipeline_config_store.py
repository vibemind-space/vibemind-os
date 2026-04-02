"""Pipeline Config Store – stores and manages pipeline configurations.

Provides per-pipeline key-value configuration storage with change
callbacks, pruning, and statistics tracking.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ConfigEntry:
    config_id: str
    pipeline_id: str
    key: str
    value: Any
    created_at: float
    updated_at: float


class PipelineConfigStore:
    """Stores and manages pipeline configurations."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._configs: Dict[str, ConfigEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._max_entries = max_entries

        # lookup: "pipeline_id:key" -> config_id
        self._lookup: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"pcs-{self._seq}-{id(self)}"
        return "pcs-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._configs) < self._max_entries:
            return
        sorted_entries = sorted(
            self._configs.values(),
            key=lambda e: e.created_at,
        )
        to_remove = len(self._configs) - self._max_entries + 1
        for entry in sorted_entries[:to_remove]:
            lk = f"{entry.pipeline_id}:{entry.key}"
            self._lookup.pop(lk, None)
            del self._configs[entry.config_id]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set_config(self, pipeline_id: str, key: str, value: Any) -> str:
        """Set a config value. Creates if new, updates if exists. Returns config_id."""
        if not pipeline_id or not key:
            return ""

        lk = f"{pipeline_id}:{key}"
        now = time.time()

        existing_cid = self._lookup.get(lk)
        if existing_cid and existing_cid in self._configs:
            entry = self._configs[existing_cid]
            old_value = entry.value
            entry.value = value
            entry.updated_at = now
            self._fire("config_updated", {
                "config_id": existing_cid,
                "pipeline_id": pipeline_id,
                "key": key,
                "old_value": old_value,
                "new_value": value,
            })
            return existing_cid

        self._prune_if_needed()
        cid = self._generate_id()
        entry = ConfigEntry(
            config_id=cid,
            pipeline_id=pipeline_id,
            key=key,
            value=value,
            created_at=now,
            updated_at=now,
        )
        self._configs[cid] = entry
        self._lookup[lk] = cid
        self._fire("config_created", {
            "config_id": cid,
            "pipeline_id": pipeline_id,
            "key": key,
            "value": value,
        })
        return cid

    def get_config(self, pipeline_id: str, key: str) -> Optional[Any]:
        """Get a config value by pipeline_id and key. Returns value or None."""
        if not pipeline_id or not key:
            return None
        lk = f"{pipeline_id}:{key}"
        cid = self._lookup.get(lk)
        if not cid or cid not in self._configs:
            return None
        return self._configs[cid].value

    def get_all_config(self, pipeline_id: str) -> Dict[str, Any]:
        """Get all config key-value pairs for a pipeline."""
        if not pipeline_id:
            return {}
        result: Dict[str, Any] = {}
        for entry in self._configs.values():
            if entry.pipeline_id == pipeline_id:
                result[entry.key] = entry.value
        return result

    def delete_config(self, pipeline_id: str, key: str) -> bool:
        """Delete a config entry. Returns True if deleted, False if not found."""
        if not pipeline_id or not key:
            return False
        lk = f"{pipeline_id}:{key}"
        cid = self._lookup.get(lk)
        if not cid or cid not in self._configs:
            return False
        del self._configs[cid]
        del self._lookup[lk]
        self._fire("config_deleted", {
            "config_id": cid,
            "pipeline_id": pipeline_id,
            "key": key,
        })
        return True

    def has_config(self, pipeline_id: str, key: str) -> bool:
        """Check if a config entry exists."""
        if not pipeline_id or not key:
            return False
        lk = f"{pipeline_id}:{key}"
        cid = self._lookup.get(lk)
        return cid is not None and cid in self._configs

    def list_pipelines(self) -> List[str]:
        """List all pipeline_ids that have configurations stored."""
        pipelines: set[str] = set()
        for entry in self._configs.values():
            pipelines.add(entry.pipeline_id)
        return sorted(pipelines)

    def get_config_count(self) -> int:
        """Return total number of config entries."""
        return len(self._configs)

    def clear_pipeline(self, pipeline_id: str) -> int:
        """Remove all config entries for a pipeline. Returns count deleted."""
        if not pipeline_id:
            return 0
        to_delete: List[str] = []
        for entry in self._configs.values():
            if entry.pipeline_id == pipeline_id:
                to_delete.append(entry.config_id)
        for cid in to_delete:
            entry = self._configs[cid]
            lk = f"{entry.pipeline_id}:{entry.key}"
            self._lookup.pop(lk, None)
            del self._configs[cid]
        if to_delete:
            self._fire("pipeline_cleared", {
                "pipeline_id": pipeline_id,
                "count": len(to_delete),
            })
        return len(to_delete)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_configs": len(self._configs),
            "total_pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        self._configs.clear()
        self._lookup.clear()
        self._callbacks.clear()
        self._seq = 0
