"""Pipeline data joiner - joins data from multiple pipeline sources."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineDataJoiner:
    """Joins data from multiple pipeline sources.

    Supports inner join and left join on a key field.
    """

    max_entries: int = 10000
    _joins: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_joins_created: int = field(default=0)
    _total_joins_executed: int = field(default=0)
    _total_records_produced: int = field(default=0)

    def _next_id(self, pipeline_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{pipeline_id}{self._seq}".encode()).hexdigest()[:12]
        return f"pdj-{raw}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "pipeline_data_joiner.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def create_join(
        self, pipeline_id: str, join_key: str, join_type: str = "inner"
    ) -> str:
        """Create a join configuration.

        Args:
            pipeline_id: The pipeline this join belongs to.
            join_key: The field name to join on.
            join_type: "inner" or "left".

        Returns:
            The join ID (prefixed with 'pdj-').
        """
        if join_type not in ("inner", "left"):
            return ""
        if not pipeline_id or not join_key:
            return ""
        if len(self._joins) >= self.max_entries:
            return ""

        join_id = self._next_id(pipeline_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "join_id": join_id,
            "pipeline_id": pipeline_id,
            "join_key": join_key,
            "join_type": join_type,
            "created_at": now,
        }
        self._joins[join_id] = entry
        self._total_joins_created += 1
        logger.info(
            "pipeline_data_joiner.join_created",
            join_id=join_id,
            pipeline_id=pipeline_id,
            join_key=join_key,
            join_type=join_type,
        )
        self._fire("join_created", {"join_id": join_id, "pipeline_id": pipeline_id})
        return join_id

    def execute_join(
        self, join_id: str, left_records: list, right_records: list
    ) -> list:
        """Execute the join on two record lists.

        For inner join, only include records where join_key exists in both.
        For left join, include all left records, adding right fields where matched.

        Returns:
            List of merged dicts.
        """
        join_cfg = self._joins.get(join_id)
        if not join_cfg:
            return []

        join_key = join_cfg["join_key"]
        join_type = join_cfg["join_type"]

        # Index right records by join_key
        right_index: Dict[Any, Dict[str, Any]] = {}
        for rec in right_records:
            if join_key in rec:
                right_index[rec[join_key]] = rec

        results: list = []
        for left_rec in left_records:
            if join_key not in left_rec:
                if join_type == "left":
                    results.append(dict(left_rec))
                continue

            key_val = left_rec[join_key]
            if key_val in right_index:
                merged = {**left_rec, **right_index[key_val]}
                results.append(merged)
            elif join_type == "left":
                results.append(dict(left_rec))

        self._total_joins_executed += 1
        self._total_records_produced += len(results)
        logger.info(
            "pipeline_data_joiner.join_executed",
            join_id=join_id,
            join_type=join_type,
            left_count=len(left_records),
            right_count=len(right_records),
            result_count=len(results),
        )
        self._fire(
            "join_executed",
            {
                "join_id": join_id,
                "result_count": len(results),
            },
        )
        return results

    def get_join(self, join_id: str) -> Optional[Dict[str, Any]]:
        """Get a join configuration by ID."""
        entry = self._joins.get(join_id)
        if not entry:
            return None
        return dict(entry)

    def get_joins(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Get all joins for a pipeline."""
        results: List[Dict[str, Any]] = []
        for entry in self._joins.values():
            if entry["pipeline_id"] == pipeline_id:
                results.append(dict(entry))
        return results

    def get_join_count(self, pipeline_id: str = "") -> int:
        """Return the number of joins, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._joins)
        count = 0
        for entry in self._joins.values():
            if entry["pipeline_id"] == pipeline_id:
                count += 1
        return count

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline IDs that have joins."""
        seen: set[str] = set()
        result: List[str] = []
        for entry in self._joins.values():
            pid = entry["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns True if registered, False if name exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        logger.debug("pipeline_data_joiner.callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if found, False otherwise."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("pipeline_data_joiner.callback_removed", name=name)
        return True

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_joins": len(self._joins),
            "total_joins_created": self._total_joins_created,
            "total_joins_executed": self._total_joins_executed,
            "total_records_produced": self._total_records_produced,
            "max_entries": self.max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._joins.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_joins_created = 0
        self._total_joins_executed = 0
        self._total_records_produced = 0
        logger.info("pipeline_data_joiner.reset")
