"""Pipeline Resource Monitor – tracks resource usage across pipeline components.

Monitors CPU, memory, disk, and custom resource metrics per component.
Supports thresholds, alerts, and usage history for capacity planning.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Resource:
    resource_id: str
    name: str
    component: str
    resource_type: str  # cpu | memory | disk | network | custom
    current_value: float
    max_value: float
    unit: str
    threshold_warning: float
    threshold_critical: float
    status: str  # normal | warning | critical
    tags: List[str]
    created_at: float
    updated_at: float
    seq: int


@dataclass
class _Sample:
    sample_id: str
    resource_id: str
    value: float
    timestamp: float
    seq: int


class PipelineResourceMonitor:
    """Tracks resource usage with thresholds and alerts."""

    RESOURCE_TYPES = ("cpu", "memory", "disk", "network", "custom")
    STATUSES = ("normal", "warning", "critical")

    def __init__(self, max_resources: int = 5000,
                 max_samples: int = 1000000) -> None:
        self._max_resources = max_resources
        self._max_samples = max_samples
        self._resources: Dict[str, _Resource] = {}
        self._samples: Dict[str, _Sample] = {}
        self._name_index: Dict[str, str] = {}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_resources": 0,
            "total_samples": 0,
            "total_warnings": 0,
            "total_criticals": 0,
        }

    # ------------------------------------------------------------------
    # Resource CRUD
    # ------------------------------------------------------------------

    def register_resource(self, name: str, component: str = "",
                          resource_type: str = "custom",
                          max_value: float = 100.0, unit: str = "%",
                          threshold_warning: float = 80.0,
                          threshold_critical: float = 95.0,
                          tags: Optional[List[str]] = None) -> str:
        if not name:
            return ""
        if resource_type not in self.RESOURCE_TYPES:
            return ""
        if name in self._name_index:
            return ""
        if len(self._resources) >= self._max_resources:
            return ""
        self._seq += 1
        raw = f"res-{name}-{component}-{self._seq}-{len(self._resources)}"
        rid = "res-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        r = _Resource(
            resource_id=rid, name=name, component=component,
            resource_type=resource_type, current_value=0.0,
            max_value=max_value, unit=unit,
            threshold_warning=threshold_warning,
            threshold_critical=threshold_critical,
            status="normal", tags=list(tags or []),
            created_at=time.time(), updated_at=time.time(), seq=self._seq,
        )
        self._resources[rid] = r
        self._name_index[name] = rid
        self._stats["total_resources"] += 1
        self._fire("resource_registered", {"resource_id": rid, "name": name})
        return rid

    def get_resource(self, resource_id: str) -> Optional[Dict]:
        r = self._resources.get(resource_id)
        if r is None:
            return None
        return self._r_to_dict(r)

    def get_resource_by_name(self, name: str) -> Optional[Dict]:
        rid = self._name_index.get(name)
        if rid is None:
            return None
        return self.get_resource(rid)

    def remove_resource(self, resource_id: str) -> bool:
        r = self._resources.get(resource_id)
        if r is None:
            return False
        self._name_index.pop(r.name, None)
        del self._resources[resource_id]
        to_rm = [s for s in self._samples.values() if s.resource_id == resource_id]
        for s in to_rm:
            del self._samples[s.sample_id]
        return True

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_sample(self, resource_id: str, value: float) -> str:
        r = self._resources.get(resource_id)
        if r is None:
            return ""
        if len(self._samples) >= self._max_samples:
            return ""
        self._seq += 1
        raw = f"smp-{resource_id}-{self._seq}-{len(self._samples)}"
        sid = "smp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        s = _Sample(
            sample_id=sid, resource_id=resource_id, value=value,
            timestamp=time.time(), seq=self._seq,
        )
        self._samples[sid] = s
        r.current_value = value
        r.updated_at = time.time()
        self._stats["total_samples"] += 1
        # Check thresholds
        old_status = r.status
        if value >= r.threshold_critical:
            r.status = "critical"
            if old_status != "critical":
                self._stats["total_criticals"] += 1
                self._fire("resource_critical", {"resource_id": resource_id, "value": value})
        elif value >= r.threshold_warning:
            r.status = "warning"
            if old_status != "warning":
                self._stats["total_warnings"] += 1
                self._fire("resource_warning", {"resource_id": resource_id, "value": value})
        else:
            r.status = "normal"
        return sid

    def get_samples(self, resource_id: str, limit: int = 100) -> List[Dict]:
        results = []
        for s in self._samples.values():
            if s.resource_id != resource_id:
                continue
            results.append({
                "sample_id": s.sample_id,
                "resource_id": s.resource_id,
                "value": s.value,
                "timestamp": s.timestamp,
            })
        results.sort(key=lambda x: x["timestamp"])
        if limit > 0:
            results = results[-limit:]
        return results

    def get_resource_avg(self, resource_id: str) -> float:
        values = [s.value for s in self._samples.values() if s.resource_id == resource_id]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_resources(self, component: str = "", resource_type: str = "",
                       status: str = "", tag: str = "") -> List[Dict]:
        results = []
        for r in self._resources.values():
            if component and r.component != component:
                continue
            if resource_type and r.resource_type != resource_type:
                continue
            if status and r.status != status:
                continue
            if tag and tag not in r.tags:
                continue
            results.append(self._r_to_dict(r))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_component_usage(self, component: str) -> List[Dict]:
        return [self._r_to_dict(r) for r in self._resources.values()
                if r.component == component]

    def get_alerts(self) -> List[Dict]:
        return [self._r_to_dict(r) for r in self._resources.values()
                if r.status in ("warning", "critical")]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_resources": len(self._resources),
            "current_samples": len(self._samples),
            "resources_warning": sum(1 for r in self._resources.values() if r.status == "warning"),
            "resources_critical": sum(1 for r in self._resources.values() if r.status == "critical"),
        }

    def reset(self) -> None:
        self._resources.clear()
        self._samples.clear()
        self._name_index.clear()
        self._seq = 0
        self._stats = {
            "total_resources": 0,
            "total_samples": 0,
            "total_warnings": 0,
            "total_criticals": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _r_to_dict(r: _Resource) -> Dict:
        return {
            "resource_id": r.resource_id,
            "name": r.name,
            "component": r.component,
            "resource_type": r.resource_type,
            "current_value": r.current_value,
            "max_value": r.max_value,
            "unit": r.unit,
            "threshold_warning": r.threshold_warning,
            "threshold_critical": r.threshold_critical,
            "status": r.status,
            "tags": list(r.tags),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "seq": r.seq,
        }
