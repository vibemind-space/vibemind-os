"""Pipeline Resource Limiter – enforces resource limits across pipeline components.

Defines per-component resource limits (rate, concurrency, memory, custom),
tracks consumption, and rejects requests when limits are exceeded.
Supports burst allowances and automatic reset windows.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _LimitEntry:
    entry_id: str
    component: str
    resource: str
    max_value: float
    current_value: float
    burst_max: float
    window_seconds: float
    window_start: float
    total_requests: int
    total_rejected: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _LimitEvent:
    event_id: str
    entry_id: str
    component: str
    resource: str
    action: str
    amount: float
    timestamp: float


class PipelineResourceLimiter:
    """Enforces resource limits across pipeline components."""

    RESOURCES = ("rate", "concurrency", "memory", "tokens", "custom")

    def __init__(self, max_entries: int = 5000, max_history: int = 100000):
        self._entries: Dict[str, _LimitEntry] = {}
        self._comp_res_index: Dict[str, str] = {}  # "comp:resource" -> entry_id
        self._component_index: Dict[str, List[str]] = {}
        self._history: List[_LimitEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_requests = 0
        self._total_allowed = 0
        self._total_rejected = 0

    # ------------------------------------------------------------------
    # Limit management
    # ------------------------------------------------------------------

    def add_limit(
        self,
        component: str,
        resource: str = "custom",
        max_value: float = 100.0,
        burst_max: float = 0.0,
        window_seconds: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not component or resource not in self.RESOURCES:
            return ""
        key = f"{component}:{resource}"
        if key in self._comp_res_index:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""
        if max_value <= 0:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{component}-{resource}-{now}-{self._seq}"
        eid = "lmt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _LimitEntry(
            entry_id=eid,
            component=component,
            resource=resource,
            max_value=max_value,
            current_value=0.0,
            burst_max=burst_max,
            window_seconds=window_seconds,
            window_start=now,
            total_requests=0,
            total_rejected=0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._entries[eid] = entry
        self._comp_res_index[key] = eid
        self._component_index.setdefault(component, []).append(eid)
        self._total_created += 1
        self._fire("limit_added", {"entry_id": eid, "component": component, "resource": resource})
        return eid

    def get_limit(self, entry_id: str) -> Optional[Dict[str, Any]]:
        e = self._entries.get(entry_id)
        if not e:
            return None
        effective_max = e.max_value + e.burst_max
        usage_pct = (e.current_value / e.max_value * 100.0) if e.max_value > 0 else 0.0
        return {
            "entry_id": e.entry_id,
            "component": e.component,
            "resource": e.resource,
            "max_value": e.max_value,
            "burst_max": e.burst_max,
            "effective_max": effective_max,
            "current_value": e.current_value,
            "usage_pct": usage_pct,
            "window_seconds": e.window_seconds,
            "total_requests": e.total_requests,
            "total_rejected": e.total_rejected,
            "tags": list(e.tags),
            "created_at": e.created_at,
        }

    def get_limit_by_component(self, component: str, resource: str) -> Optional[Dict[str, Any]]:
        key = f"{component}:{resource}"
        eid = self._comp_res_index.get(key)
        if not eid:
            return None
        return self.get_limit(eid)

    def remove_limit(self, entry_id: str) -> bool:
        e = self._entries.pop(entry_id, None)
        if not e:
            return False
        key = f"{e.component}:{e.resource}"
        self._comp_res_index.pop(key, None)
        comp_list = self._component_index.get(e.component, [])
        if entry_id in comp_list:
            comp_list.remove(entry_id)
        return True

    def update_limit(self, entry_id: str, max_value: float = 0.0, burst_max: float = -1.0) -> bool:
        e = self._entries.get(entry_id)
        if not e:
            return False
        if max_value > 0:
            e.max_value = max_value
        if burst_max >= 0:
            e.burst_max = burst_max
        e.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Acquire / Release
    # ------------------------------------------------------------------

    def acquire(self, entry_id: str, amount: float = 1.0) -> bool:
        """Try to acquire resource. Returns True if allowed, False if rejected."""
        e = self._entries.get(entry_id)
        if not e or amount <= 0:
            return False

        self._maybe_reset_window(e)

        e.total_requests += 1
        self._total_requests += 1

        effective_max = e.max_value + e.burst_max
        if e.current_value + amount > effective_max:
            e.total_rejected += 1
            self._total_rejected += 1
            self._record_event(e, "rejected", amount)
            self._fire("limit_exceeded", {
                "entry_id": entry_id, "component": e.component,
                "resource": e.resource, "current": e.current_value,
                "requested": amount, "max": effective_max,
            })
            return False

        e.current_value += amount
        e.updated_at = time.time()
        self._total_allowed += 1
        self._record_event(e, "acquired", amount)
        return True

    def acquire_by_component(self, component: str, resource: str, amount: float = 1.0) -> bool:
        key = f"{component}:{resource}"
        eid = self._comp_res_index.get(key)
        if not eid:
            return False
        return self.acquire(eid, amount)

    def release(self, entry_id: str, amount: float = 1.0) -> bool:
        """Release previously acquired resource."""
        e = self._entries.get(entry_id)
        if not e or amount <= 0:
            return False

        e.current_value = max(0.0, e.current_value - amount)
        e.updated_at = time.time()
        self._record_event(e, "released", amount)
        return True

    def release_by_component(self, component: str, resource: str, amount: float = 1.0) -> bool:
        key = f"{component}:{resource}"
        eid = self._comp_res_index.get(key)
        if not eid:
            return False
        return self.release(eid, amount)

    def reset_usage(self, entry_id: str) -> bool:
        e = self._entries.get(entry_id)
        if not e:
            return False
        e.current_value = 0.0
        e.window_start = time.time()
        e.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def _maybe_reset_window(self, entry: _LimitEntry) -> None:
        if entry.window_seconds <= 0:
            return
        now = time.time()
        if now - entry.window_start >= entry.window_seconds:
            entry.current_value = 0.0
            entry.window_start = now

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_component_limits(self, component: str) -> List[Dict[str, Any]]:
        eids = self._component_index.get(component, [])
        results = []
        for eid in eids:
            info = self.get_limit(eid)
            if info:
                results.append(info)
        return results

    def get_exceeded(self) -> List[Dict[str, Any]]:
        results = []
        for e in self._entries.values():
            if e.current_value > e.max_value:
                results.append(self.get_limit(e.entry_id))
        return results

    def list_limits(
        self,
        component: str = "",
        resource: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._entries.values():
            if component and e.component != component:
                continue
            if resource and e.resource != resource:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_limit(e.entry_id))
        return results

    def get_history(self, component: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if component and ev.component != component:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "entry_id": ev.entry_id,
                "component": ev.component,
                "resource": ev.resource,
                "action": ev.action,
                "amount": ev.amount,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_event(self, entry: _LimitEntry, action: str, amount: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{entry.component}-{action}-{now}-{self._seq}"
        evid = "lev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _LimitEvent(
            event_id=evid,
            entry_id=entry.entry_id,
            component=entry.component,
            resource=entry.resource,
            action=action,
            amount=amount,
            timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_limits": len(self._entries),
            "total_created": self._total_created,
            "total_requests": self._total_requests,
            "total_allowed": self._total_allowed,
            "total_rejected": self._total_rejected,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._comp_res_index.clear()
        self._component_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_requests = 0
        self._total_allowed = 0
        self._total_rejected = 0
