"""Pipeline data sorter - sorts pipeline data records by configurable fields and directions."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineDataSorter:
    """Sorts pipeline data records by configurable fields and directions.

    Supports per-pipeline sort configuration with ascending/descending order.
    Records missing the sort field are placed last.
    """

    max_entries: int = 10000
    _configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_configs_created: int = field(default=0)
    _total_sorts_executed: int = field(default=0)
    _total_records_sorted: int = field(default=0)

    def _next_id(self, pipeline_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{pipeline_id}{self._seq}".encode()).hexdigest()[:12]
        return f"pdso-{raw}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "pipeline_data_sorter.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def configure_sort(
        self, pipeline_id: str, sort_field: str, ascending: bool = True
    ) -> str:
        """Configure sort for a pipeline.

        Args:
            pipeline_id: The pipeline this sort belongs to.
            sort_field: The field name to sort on.
            ascending: True for ascending, False for descending.

        Returns:
            The config ID (prefixed with 'pdso-').
        """
        if not pipeline_id or not sort_field:
            return ""
        if len(self._configs) >= self.max_entries:
            return ""

        config_id = self._next_id(pipeline_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "config_id": config_id,
            "pipeline_id": pipeline_id,
            "sort_field": sort_field,
            "ascending": ascending,
            "created_at": now,
        }
        self._configs[config_id] = entry
        self._total_configs_created += 1
        logger.info(
            "pipeline_data_sorter.sort_configured",
            config_id=config_id,
            pipeline_id=pipeline_id,
            sort_field=sort_field,
            ascending=ascending,
        )
        self._fire("sort_configured", {"config_id": config_id, "pipeline_id": pipeline_id})
        return config_id

    def sort_records(self, pipeline_id: str, records: list) -> list:
        """Sort records by the configured field for the given pipeline.

        Uses the most recently created config for the pipeline.
        Records missing the sort field are placed last.

        Returns:
            Sorted list of records.
        """
        # Find the latest config for this pipeline
        cfg = None
        for entry in self._configs.values():
            if entry["pipeline_id"] == pipeline_id:
                if cfg is None or entry["created_at"] > cfg["created_at"]:
                    cfg = entry

        if cfg is None:
            return list(records)

        sort_field = cfg["sort_field"]
        ascending = cfg["ascending"]

        def sort_key(record: Dict[str, Any]):
            val = record.get(sort_field)
            if val is None:
                return (1, "")  # sort last
            return (0, val)

        result = sorted(records, key=sort_key, reverse=not ascending)
        self._total_sorts_executed += 1
        self._total_records_sorted += len(result)
        logger.info(
            "pipeline_data_sorter.records_sorted",
            pipeline_id=pipeline_id,
            sort_field=sort_field,
            ascending=ascending,
            record_count=len(result),
        )
        self._fire(
            "records_sorted",
            {
                "pipeline_id": pipeline_id,
                "record_count": len(result),
            },
        )
        return result

    def get_config(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest sort configuration for a pipeline."""
        cfg = None
        for entry in self._configs.values():
            if entry["pipeline_id"] == pipeline_id:
                if cfg is None or entry["created_at"] > cfg["created_at"]:
                    cfg = entry
        if cfg is None:
            return None
        return dict(cfg)

    def remove_config(self, config_id: str) -> bool:
        """Remove a sort configuration by config ID. Returns True if found."""
        entry = self._configs.pop(config_id, None)
        if entry is None:
            return False
        logger.info(
            "pipeline_data_sorter.config_removed",
            config_id=config_id,
            pipeline_id=entry["pipeline_id"],
        )
        self._fire("config_removed", {"config_id": config_id, "pipeline_id": entry["pipeline_id"]})
        return True

    def get_config_count(self, pipeline_id: str = "") -> int:
        """Return the number of configs, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._configs)
        count = 0
        for entry in self._configs.values():
            if entry["pipeline_id"] == pipeline_id:
                count += 1
        return count

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline IDs that have sort configs."""
        seen: set[str] = set()
        result: List[str] = []
        for entry in self._configs.values():
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
        logger.debug("pipeline_data_sorter.callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if found, False otherwise."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("pipeline_data_sorter.callback_removed", name=name)
        return True

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_configs": len(self._configs),
            "total_configs_created": self._total_configs_created,
            "total_sorts_executed": self._total_sorts_executed,
            "total_records_sorted": self._total_records_sorted,
            "max_entries": self.max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._configs.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_configs_created = 0
        self._total_sorts_executed = 0
        self._total_records_sorted = 0
        logger.info("pipeline_data_sorter.reset")
