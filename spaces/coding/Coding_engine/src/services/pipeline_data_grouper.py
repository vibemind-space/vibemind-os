"""Pipeline Data Grouper - Group pipeline data records by specified keys."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataGrouperState:
    """State container for PipelineDataGrouper."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineDataGrouper:
    """Group pipeline data records by specified keys."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "pdg-"

    def __init__(self) -> None:
        self._state = PipelineDataGrouperState()
        self._callbacks: Dict[str, Callable] = {}
        self._configs: Dict[str, dict] = {}  # config_id -> config
        self._pipeline_configs: Dict[str, str] = {}  # pipeline_id -> config_id
        logger.info("PipelineDataGrouper initialized")

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using sha256 hash."""
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune_entries(self) -> None:
        """Prune entries if exceeding MAX_ENTRIES."""
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(self._state.entries.keys())
            excess = len(self._state.entries) - self.MAX_ENTRIES
            for key in sorted_keys[:excess]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", excess)

    # Callback system
    def on_change(self, name: str, cb: Callable) -> None:
        """Register a callback."""
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Any = None) -> None:
        """Fire all registered callbacks."""
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception as e:
                logger.error("Callback %s failed: %s", name, e)

    # API methods
    def configure(self, pipeline_id: str, group_keys: List[str],
                  agg_config: Optional[Dict[str, str]] = None) -> str:
        """Configure grouping for a pipeline.

        Args:
            pipeline_id: The pipeline identifier.
            group_keys: List of field names to group by.
            agg_config: Optional dict of {field: aggregation_type}.
                       Supported: sum, count, avg, min, max, first, last.

        Returns:
            config_id: The generated configuration ID.
        """
        config_id = self._generate_id(pipeline_id)
        config = {
            "config_id": config_id,
            "pipeline_id": pipeline_id,
            "group_keys": list(group_keys),
            "agg_config": agg_config or {},
            "created_at": time.time(),
        }
        self._configs[config_id] = config
        self._pipeline_configs[pipeline_id] = config_id
        self._state.entries[config_id] = config
        self._prune_entries()
        self._fire("configure", {"pipeline_id": pipeline_id, "config_id": config_id})
        logger.info("Configured pipeline %s with config %s", pipeline_id, config_id)
        return config_id

    def group(self, pipeline_id: str, records: List[dict]) -> Dict[tuple, List[dict]]:
        """Group records by the configured group keys.

        Args:
            pipeline_id: The pipeline identifier.
            records: List of record dicts.

        Returns:
            Dict mapping group key tuples to lists of records.
        """
        config_id = self._pipeline_configs.get(pipeline_id)
        if not config_id or config_id not in self._configs:
            raise ValueError(f"No configuration found for pipeline: {pipeline_id}")

        config = self._configs[config_id]
        group_keys = config["group_keys"]
        groups: Dict[tuple, List[dict]] = {}

        for record in records:
            key = tuple(record.get(k) for k in group_keys)
            if key not in groups:
                groups[key] = []
            groups[key].append(record)

        self._fire("group", {"pipeline_id": pipeline_id, "group_count": len(groups)})
        return groups

    def aggregate(self, pipeline_id: str, records: List[dict]) -> List[dict]:
        """Aggregate records by group keys using the configured aggregation.

        Args:
            pipeline_id: The pipeline identifier.
            records: List of record dicts.

        Returns:
            List of aggregated dicts, one per group.
        """
        config_id = self._pipeline_configs.get(pipeline_id)
        if not config_id or config_id not in self._configs:
            raise ValueError(f"No configuration found for pipeline: {pipeline_id}")

        config = self._configs[config_id]
        group_keys = config["group_keys"]
        agg_config = config["agg_config"]

        groups = self.group(pipeline_id, records)
        results = []

        for key_tuple, group_records in groups.items():
            row: dict = {}
            # Set group key values
            for i, k in enumerate(group_keys):
                row[k] = key_tuple[i]

            # Apply aggregations
            for agg_field, agg_type in agg_config.items():
                values = [r.get(agg_field) for r in group_records if r.get(agg_field) is not None]
                if agg_type == "sum":
                    row[agg_field] = sum(values) if values else 0
                elif agg_type == "count":
                    row[agg_field] = len(values)
                elif agg_type == "avg":
                    row[agg_field] = sum(values) / len(values) if values else 0
                elif agg_type == "min":
                    row[agg_field] = min(values) if values else None
                elif agg_type == "max":
                    row[agg_field] = max(values) if values else None
                elif agg_type == "first":
                    row[agg_field] = values[0] if values else None
                elif agg_type == "last":
                    row[agg_field] = values[-1] if values else None

            results.append(row)

        self._fire("aggregate", {"pipeline_id": pipeline_id, "result_count": len(results)})
        return results

    def get_config(self, pipeline_id: str) -> Optional[dict]:
        """Get the configuration for a pipeline."""
        config_id = self._pipeline_configs.get(pipeline_id)
        if config_id and config_id in self._configs:
            return dict(self._configs[config_id])
        return None

    def remove_config(self, config_id: str) -> bool:
        """Remove a configuration by config_id."""
        if config_id not in self._configs:
            return False
        config = self._configs.pop(config_id)
        pipeline_id = config["pipeline_id"]
        if self._pipeline_configs.get(pipeline_id) == config_id:
            del self._pipeline_configs[pipeline_id]
        self._state.entries.pop(config_id, None)
        self._fire("remove_config", {"config_id": config_id})
        return True

    def get_config_count(self, pipeline_id: str = "") -> int:
        """Get the number of configurations, optionally filtered by pipeline_id."""
        if pipeline_id:
            return 1 if pipeline_id in self._pipeline_configs else 0
        return len(self._configs)

    def list_pipelines(self) -> List[str]:
        """List all configured pipeline IDs."""
        return list(self._pipeline_configs.keys())

    def get_stats(self) -> dict:
        """Get statistics about the grouper."""
        return {
            "config_count": len(self._configs),
            "pipeline_count": len(self._pipeline_configs),
            "entry_count": len(self._state.entries),
            "seq": self._state._seq,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineDataGrouperState()
        self._configs.clear()
        self._pipeline_configs.clear()
        self._fire("reset", {})
        logger.info("PipelineDataGrouper reset")
