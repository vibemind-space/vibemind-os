"""Pipeline Resource Tracker – tracks resource allocation and utilization.

Monitors CPU, memory, disk, and custom resources across pipeline stages.
Provides utilization metrics and alerts when thresholds are breached.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Resource:
    resource_id: str
    name: str
    resource_type: str  # cpu, memory, disk, custom
    capacity: float
    allocated: float
    used: float
    unit: str
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _ResourceEvent:
    event_id: str
    resource_name: str
    action: str  # allocated, released, usage_updated, threshold_breached
    amount: float
    timestamp: float


class PipelineResourceTracker:
    """Tracks resource allocation and utilization."""

    RESOURCE_TYPES = ("cpu", "memory", "disk", "custom")

    def __init__(self, max_resources: int = 5000, max_history: int = 100000, threshold_pct: float = 80.0):
        self._resources: Dict[str, _Resource] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[_ResourceEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_resources = max_resources
        self._max_history = max_history
        self._threshold_pct = threshold_pct
        self._seq = 0
        self._total_registered = 0
        self._total_allocations = 0
        self._total_breaches = 0

    def register_resource(self, name: str, resource_type: str = "custom", capacity: float = 100.0, unit: str = "", tags: Optional[List[str]] = None) -> str:
        if not name or resource_type not in self.RESOURCE_TYPES:
            return ""
        if name in self._name_index or len(self._resources) >= self._max_resources:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        rid = "res-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        r = _Resource(resource_id=rid, name=name, resource_type=resource_type, capacity=capacity, allocated=0.0, used=0.0, unit=unit, tags=tags or [], created_at=now, updated_at=now)
        self._resources[rid] = r
        self._name_index[name] = rid
        self._total_registered += 1
        self._fire("resource_registered", {"resource_id": rid, "name": name})
        return rid

    def get_resource(self, name: str) -> Optional[Dict[str, Any]]:
        rid = self._name_index.get(name)
        if not rid:
            return None
        r = self._resources[rid]
        util = (r.used / r.capacity * 100) if r.capacity > 0 else 0.0
        return {"resource_id": r.resource_id, "name": r.name, "resource_type": r.resource_type, "capacity": r.capacity, "allocated": r.allocated, "used": r.used, "utilization_pct": util, "unit": r.unit, "tags": list(r.tags), "created_at": r.created_at, "updated_at": r.updated_at}

    def remove_resource(self, name: str) -> bool:
        rid = self._name_index.pop(name, None)
        if not rid:
            return False
        self._resources.pop(rid, None)
        return True

    def allocate(self, name: str, amount: float) -> bool:
        rid = self._name_index.get(name)
        if not rid or amount <= 0:
            return False
        r = self._resources[rid]
        if r.allocated + amount > r.capacity:
            return False
        r.allocated += amount
        r.updated_at = time.time()
        self._total_allocations += 1
        self._record_event(name, "allocated", amount)
        self._fire("resource_allocated", {"name": name, "amount": amount})
        return True

    def release(self, name: str, amount: float) -> bool:
        rid = self._name_index.get(name)
        if not rid or amount <= 0:
            return False
        r = self._resources[rid]
        r.allocated = max(0.0, r.allocated - amount)
        r.updated_at = time.time()
        self._record_event(name, "released", amount)
        return True

    def update_usage(self, name: str, used: float) -> bool:
        rid = self._name_index.get(name)
        if not rid:
            return False
        r = self._resources[rid]
        r.used = max(0.0, min(r.capacity, used))
        r.updated_at = time.time()
        self._record_event(name, "usage_updated", used)
        util = (r.used / r.capacity * 100) if r.capacity > 0 else 0.0
        if util >= self._threshold_pct:
            self._total_breaches += 1
            self._record_event(name, "threshold_breached", util)
            self._fire("threshold_breached", {"name": name, "utilization_pct": util})
        return True

    def get_utilization(self, name: str) -> float:
        rid = self._name_index.get(name)
        if not rid:
            return 0.0
        r = self._resources[rid]
        return (r.used / r.capacity * 100) if r.capacity > 0 else 0.0

    def get_over_threshold(self) -> List[Dict[str, Any]]:
        return [self.get_resource(r.name) for r in self._resources.values() if r.capacity > 0 and (r.used / r.capacity * 100) >= self._threshold_pct]

    def list_resources(self, resource_type: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for r in self._resources.values():
            if resource_type and r.resource_type != resource_type:
                continue
            if tag and tag not in r.tags:
                continue
            results.append(self.get_resource(r.name))
        return results

    def get_history(self, resource_name: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if resource_name and ev.resource_name != resource_name:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "resource_name": ev.resource_name, "action": ev.action, "amount": ev.amount, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, resource_name: str, action: str, amount: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{resource_name}-{action}-{now}-{self._seq}"
        evid = "rev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _ResourceEvent(event_id=evid, resource_name=resource_name, action=action, amount=amount, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        return {"current_resources": len(self._resources), "total_registered": self._total_registered, "total_allocations": self._total_allocations, "total_breaches": self._total_breaches, "history_size": len(self._history)}

    def reset(self) -> None:
        self._resources.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_allocations = 0
        self._total_breaches = 0
