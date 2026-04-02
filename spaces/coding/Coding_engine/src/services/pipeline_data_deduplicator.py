"""Service module for pipeline data deduplication based on configurable keys."""

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
    configs: Dict[str, dict] = field(default_factory=dict)
    seen: Dict[str, set] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataDeduplicator:
    """Deduplicate pipeline data records based on configurable keys."""

    def __init__(self) -> None:
        self._state = _State()

    # -- ID generation -------------------------------------------------------

    def _next_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdd-{digest}"

    # -- Callbacks -----------------------------------------------------------

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

    # -- API -----------------------------------------------------------------

    def configure(self, pipeline_id: str, dedup_key: str) -> str:
        """Set the field to deduplicate on for a pipeline. Returns config ID."""
        if not pipeline_id or not dedup_key:
            return ""
        config_id = self._next_id(pipeline_id)
        self._state.configs[pipeline_id] = {
            "config_id": config_id,
            "pipeline_id": pipeline_id,
            "dedup_key": dedup_key,
            "created_at": time.time(),
        }
        if pipeline_id not in self._state.seen:
            self._state.seen[pipeline_id] = set()
        logger.info("configured", config_id=config_id, pipeline_id=pipeline_id, dedup_key=dedup_key)
        self._fire("configure", config_id=config_id, pipeline_id=pipeline_id)
        return config_id

    def deduplicate(self, pipeline_id: str, records: list) -> list:
        """Remove duplicates from records based on configured key.

        Returns unique records (first occurrence wins).
        If no config exists for pipeline_id, returns records unchanged.
        """
        config = self._state.configs.get(pipeline_id)
        if not config:
            return list(records)

        dedup_key = config["dedup_key"]
        if pipeline_id not in self._state.seen:
            self._state.seen[pipeline_id] = set()

        seen = self._state.seen[pipeline_id]
        unique: List[dict] = []
        for record in records:
            value = record.get(dedup_key)
            if value is None:
                unique.append(record)
                continue
            hashable = str(value)
            if hashable not in seen:
                if len(seen) < MAX_ENTRIES:
                    seen.add(hashable)
                unique.append(record)

        removed = len(records) - len(unique)
        logger.info("deduplicated", pipeline_id=pipeline_id, input=len(records),
                     output=len(unique), removed=removed)
        if removed > 0:
            self._fire("deduplicate", pipeline_id=pipeline_id, removed=removed)
        return unique

    def get_config(self, pipeline_id: str) -> Optional[dict]:
        """Get the dedup configuration for a pipeline, or None."""
        config = self._state.configs.get(pipeline_id)
        if not config:
            return None
        return dict(config)

    def get_seen_count(self, pipeline_id: str) -> int:
        """How many unique values have been seen for a pipeline."""
        return len(self._state.seen.get(pipeline_id, set()))

    def clear_seen(self, pipeline_id: str) -> int:
        """Clear seen values for a pipeline. Returns count cleared."""
        seen = self._state.seen.get(pipeline_id)
        if not seen:
            return 0
        count = len(seen)
        seen.clear()
        logger.info("seen_cleared", pipeline_id=pipeline_id, cleared=count)
        self._fire("clear_seen", pipeline_id=pipeline_id, cleared=count)
        return count

    def get_config_count(self, pipeline_id: str = "") -> int:
        """Return the number of configs, optionally scoped to a pipeline."""
        if not pipeline_id:
            return len(self._state.configs)
        return 1 if pipeline_id in self._state.configs else 0

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of unique pipeline IDs that have configs."""
        return sorted(self._state.configs.keys())

    # -- Stats ---------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total_seen = sum(len(s) for s in self._state.seen.values())
        return {
            "total_configs": len(self._state.configs),
            "total_pipelines": len(self._state.configs),
            "total_seen_values": total_seen,
            "callbacks_registered": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Clear all configs, seen values, reset sequence counter, and remove callbacks."""
        self._state.configs.clear()
        self._state.seen.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")
