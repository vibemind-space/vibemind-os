"""Pipeline data pivot service for pivot/unpivot tabular data in pipeline records."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclass
class PipelineDataPivotState:
    """State container for PipelineDataPivot."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineDataPivot:
    """Pivot/unpivot tabular data in pipeline records."""

    def __init__(self) -> None:
        self._state = PipelineDataPivotState()
        self._callbacks: Dict[str, Callable] = {}
        self._created_at = time.time()

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "pdp2-" + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self) -> None:
        while len(self._state.entries) > MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]

    def on_change(self, name: str, cb: Callable) -> None:
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Any = None) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception as e:
                logger.warning("Callback %s failed: %s", name, e)

    def configure_pivot(
        self,
        pipeline_id: str,
        pivot_column: str,
        value_column: str,
        agg: str = "first",
    ) -> str:
        config_id = self._generate_id(f"config:{pipeline_id}:{pivot_column}:{value_column}")
        entry = {
            "config_id": config_id,
            "pipeline_id": pipeline_id,
            "pivot_column": pivot_column,
            "value_column": value_column,
            "agg": agg,
            "created_at": time.time(),
        }
        self._state.entries[config_id] = entry
        self._prune()
        self._fire("configure_pivot", entry)
        logger.info("Configured pivot %s for pipeline %s", config_id, pipeline_id)
        return config_id

    def get_config(self, pipeline_id: str) -> Optional[Dict]:
        for entry in self._state.entries.values():
            if entry.get("pipeline_id") == pipeline_id:
                return dict(entry)
        return None

    def remove_config(self, config_id: str) -> bool:
        if config_id in self._state.entries:
            del self._state.entries[config_id]
            self._fire("remove_config", {"config_id": config_id})
            return True
        return False

    def get_config_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def list_pipelines(self) -> List[str]:
        seen = []
        for entry in self._state.entries.values():
            pid = entry.get("pipeline_id")
            if pid and pid not in seen:
                seen.append(pid)
        return seen

    def pivot(self, pipeline_id: str, records: List[Dict]) -> List[Dict]:
        """Pivot records: group by non-pivot columns, spread pivot_column values as new columns."""
        config = self.get_config(pipeline_id)
        if config is None:
            raise ValueError(f"No pivot config for pipeline {pipeline_id}")

        pivot_col = config["pivot_column"]
        value_col = config["value_column"]
        agg = config["agg"]

        # Determine group-by columns (all columns except pivot and value)
        all_cols = set()
        for rec in records:
            all_cols.update(rec.keys())
        group_cols = sorted(all_cols - {pivot_col, value_col})

        # Group records
        groups: Dict[tuple, Dict] = {}
        group_values: Dict[tuple, Dict[str, list]] = {}

        for rec in records:
            key = tuple(rec.get(c) for c in group_cols)
            if key not in groups:
                groups[key] = {c: rec.get(c) for c in group_cols}
                group_values[key] = {}
            pv = rec.get(pivot_col)
            vv = rec.get(value_col)
            if pv is not None:
                pv_str = str(pv)
                if pv_str not in group_values[key]:
                    group_values[key][pv_str] = []
                group_values[key][pv_str].append(vv)

        result = []
        for key in groups:
            row = dict(groups[key])
            for pv_str, vals in group_values[key].items():
                if agg == "first":
                    row[pv_str] = vals[0] if vals else None
                elif agg == "sum":
                    row[pv_str] = sum(v for v in vals if v is not None)
                elif agg == "count":
                    row[pv_str] = len(vals)
                elif agg == "max":
                    row[pv_str] = max(v for v in vals if v is not None)
                elif agg == "min":
                    row[pv_str] = min(v for v in vals if v is not None)
                else:
                    row[pv_str] = vals[0] if vals else None
            result.append(row)

        self._fire("pivot", {"pipeline_id": pipeline_id, "count": len(result)})
        return result

    def unpivot(
        self,
        pipeline_id: str,
        records: List[Dict],
        columns: List[str],
        var_name: str = "variable",
        value_name: str = "value",
    ) -> List[Dict]:
        """Unpivot records: melt specified columns into variable/value rows."""
        result = []
        for rec in records:
            base = {k: v for k, v in rec.items() if k not in columns}
            for col in columns:
                if col in rec:
                    row = dict(base)
                    row[var_name] = col
                    row[value_name] = rec[col]
                    result.append(row)
        self._fire("unpivot", {"pipeline_id": pipeline_id, "count": len(result)})
        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_configs": len(self._state.entries),
            "pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
            "callbacks": len(self._callbacks),
            "uptime": time.time() - self._created_at,
        }

    def reset(self) -> None:
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("PipelineDataPivot reset")
