"""Pipeline capacity planner.

Tracks and manages capacity planning for pipeline resources.
Supports setting capacity per pipeline/resource pair, recording load,
computing headroom and utilization, and triggering scaling decisions.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CapacityRecord:
    """A single capacity plan entry."""

    plan_id: str = ""
    pipeline_id: str = ""
    resource_type: str = ""
    current_capacity: float = 0.0
    max_capacity: float = 0.0
    current_load: float = 0.0
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Capacity Planner
# ---------------------------------------------------------------------------


class PipelineCapacityPlanner:
    """Plan and manage capacity for pipeline resources."""

    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str], CapacityRecord] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_set": 0,
            "total_removed": 0,
            "total_loads_recorded": 0,
            "total_scale_ups": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix ``pcp-``."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pcp-{digest}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_dict(self, rec: CapacityRecord) -> Dict:
        """Convert a CapacityRecord to a dict."""
        return {
            "plan_id": rec.plan_id,
            "pipeline_id": rec.pipeline_id,
            "resource_type": rec.resource_type,
            "current_capacity": rec.current_capacity,
            "max_capacity": rec.max_capacity,
            "current_load": rec.current_load,
            "created_at": rec.created_at,
        }

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.warning("callback_error", action=action)

    # ------------------------------------------------------------------
    # Capacity management
    # ------------------------------------------------------------------

    def set_capacity(
        self,
        pipeline_id: str,
        resource_type: str,
        current_capacity: float,
        max_capacity: float,
    ) -> str:
        """Set or update capacity for a pipeline/resource pair.

        Returns plan_id. If the combo already exists, updates and returns
        the existing plan_id.
        """
        key = (pipeline_id, resource_type)
        existing = self._records.get(key)

        if existing is not None:
            existing.current_capacity = current_capacity
            existing.max_capacity = max_capacity
            logger.info(
                "capacity_updated",
                plan_id=existing.plan_id,
                pipeline_id=pipeline_id,
                resource_type=resource_type,
            )
            self._fire("capacity_updated", self._to_dict(existing))
            return existing.plan_id

        plan_id = self._generate_id(f"{pipeline_id}:{resource_type}")
        rec = CapacityRecord(
            plan_id=plan_id,
            pipeline_id=pipeline_id,
            resource_type=resource_type,
            current_capacity=current_capacity,
            max_capacity=max_capacity,
            current_load=0.0,
            created_at=time.time(),
        )
        self._records[key] = rec
        self._stats["total_set"] += 1
        logger.info(
            "capacity_set",
            plan_id=plan_id,
            pipeline_id=pipeline_id,
            resource_type=resource_type,
        )
        self._fire("capacity_set", self._to_dict(rec))
        return plan_id

    def get_capacity(
        self, pipeline_id: str, resource_type: str
    ) -> Optional[Dict]:
        """Return capacity dict or None if not found."""
        self._stats["total_lookups"] += 1
        rec = self._records.get((pipeline_id, resource_type))
        if rec is None:
            return None
        return self._to_dict(rec)

    def record_load(
        self, pipeline_id: str, resource_type: str, load: float
    ) -> bool:
        """Record current load for a capacity entry.

        Returns True if recorded, False if capacity not found.
        """
        rec = self._records.get((pipeline_id, resource_type))
        if rec is None:
            return False
        rec.current_load = load
        self._stats["total_loads_recorded"] += 1
        logger.info(
            "load_recorded",
            plan_id=rec.plan_id,
            pipeline_id=pipeline_id,
            resource_type=resource_type,
            load=load,
        )
        self._fire("load_recorded", self._to_dict(rec))
        return True

    def get_headroom(self, pipeline_id: str, resource_type: str) -> float:
        """Return current_capacity - current_load. 0.0 if not found."""
        rec = self._records.get((pipeline_id, resource_type))
        if rec is None:
            return 0.0
        return rec.current_capacity - rec.current_load

    def needs_scaling(
        self, pipeline_id: str, resource_type: str, threshold: float = 0.8
    ) -> bool:
        """Return True if current_load / current_capacity >= threshold.

        Returns False if not found or current_capacity is zero.
        """
        rec = self._records.get((pipeline_id, resource_type))
        if rec is None:
            return False
        if rec.current_capacity <= 0:
            return False
        return (rec.current_load / rec.current_capacity) >= threshold

    def scale_up(
        self, pipeline_id: str, resource_type: str, amount: float
    ) -> bool:
        """Increase current_capacity by amount, up to max_capacity.

        Returns True if scaled, False if not found or already at max.
        """
        rec = self._records.get((pipeline_id, resource_type))
        if rec is None:
            return False
        if rec.current_capacity >= rec.max_capacity:
            return False

        new_capacity = min(rec.current_capacity + amount, rec.max_capacity)
        if new_capacity == rec.current_capacity:
            return False

        rec.current_capacity = new_capacity
        self._stats["total_scale_ups"] += 1
        logger.info(
            "scaled_up",
            plan_id=rec.plan_id,
            pipeline_id=pipeline_id,
            resource_type=resource_type,
            new_capacity=new_capacity,
        )
        self._fire("scaled_up", self._to_dict(rec))
        return True

    def get_utilization(self, pipeline_id: str, resource_type: str) -> float:
        """Return current_load / current_capacity. 0.0 if not found."""
        rec = self._records.get((pipeline_id, resource_type))
        if rec is None:
            return 0.0
        if rec.current_capacity <= 0:
            return 0.0
        return rec.current_load / rec.current_capacity

    def remove_capacity(self, pipeline_id: str, resource_type: str) -> bool:
        """Remove a capacity entry. Returns True if removed."""
        key = (pipeline_id, resource_type)
        rec = self._records.get(key)
        if rec is None:
            return False
        data = self._to_dict(rec)
        del self._records[key]
        self._stats["total_removed"] += 1
        logger.info(
            "capacity_removed",
            plan_id=rec.plan_id,
            pipeline_id=pipeline_id,
            resource_type=resource_type,
        )
        self._fire("capacity_removed", data)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return list of unique pipeline_ids."""
        seen: Dict[str, bool] = {}
        result: List[str] = []
        for pipeline_id, _ in self._records:
            if pipeline_id not in seen:
                seen[pipeline_id] = True
                result.append(pipeline_id)
        return result

    def get_pipeline_capacities(self, pipeline_id: str) -> List[Dict]:
        """Return list of capacity dicts for a given pipeline."""
        results: List[Dict] = []
        for (pid, _), rec in self._records.items():
            if pid == pipeline_id:
                results.append(self._to_dict(rec))
        return results

    def get_plan_count(self) -> int:
        """Return total number of capacity plans."""
        return len(self._records)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_plans": len(self._records),
            "current_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._records.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {
            "total_set": 0,
            "total_removed": 0,
            "total_loads_recorded": 0,
            "total_scale_ups": 0,
            "total_lookups": 0,
        }
        logger.info("capacity_planner_reset")
