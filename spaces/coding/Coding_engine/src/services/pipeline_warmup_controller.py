"""Pipeline Warmup Controller – manages component warmup sequences.

Controls the warmup phase of pipeline components, tracking readiness
and ensuring components are fully initialized before processing.
Supports ordered warmup with dependencies and health checks.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _WarmupEntry:
    entry_id: str
    component: str
    status: str  # pending, warming, ready, failed
    order: int
    depends_on: List[str]  # entry_ids
    warmup_fn: Optional[Callable]
    health_fn: Optional[Callable]
    total_warmups: int
    last_warmup_at: float
    tags: List[str]
    created_at: float
    updated_at: float


class PipelineWarmupController:
    """Controls component warmup sequences."""

    STATUSES = ("pending", "warming", "ready", "failed")

    def __init__(self, max_entries: int = 5000):
        self._entries: Dict[str, _WarmupEntry] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # stats
        self._total_registered = 0
        self._total_warmups = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_component(
        self,
        component: str,
        order: int = 0,
        depends_on: Optional[List[str]] = None,
        warmup_fn: Optional[Callable] = None,
        health_fn: Optional[Callable] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not component:
            return ""
        if component in self._name_index:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""
        # validate dependencies exist
        if depends_on:
            for dep in depends_on:
                if dep not in self._entries:
                    return ""

        self._seq += 1
        now = time.time()
        raw = f"{component}-{now}-{self._seq}"
        eid = "wrm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _WarmupEntry(
            entry_id=eid,
            component=component,
            status="pending",
            order=order,
            depends_on=depends_on or [],
            warmup_fn=warmup_fn,
            health_fn=health_fn,
            total_warmups=0,
            last_warmup_at=0.0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._entries[eid] = entry
        self._name_index[component] = eid
        self._total_registered += 1
        self._fire("component_registered", {"entry_id": eid, "component": component})
        return eid

    def get_component(self, entry_id: str) -> Optional[Dict[str, Any]]:
        e = self._entries.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id,
            "component": e.component,
            "status": e.status,
            "order": e.order,
            "depends_on": list(e.depends_on),
            "total_warmups": e.total_warmups,
            "last_warmup_at": e.last_warmup_at,
            "tags": list(e.tags),
            "created_at": e.created_at,
        }

    def get_by_name(self, component: str) -> Optional[Dict[str, Any]]:
        eid = self._name_index.get(component)
        if not eid:
            return None
        return self.get_component(eid)

    def remove_component(self, entry_id: str) -> bool:
        e = self._entries.pop(entry_id, None)
        if not e:
            return False
        self._name_index.pop(e.component, None)
        return True

    # ------------------------------------------------------------------
    # Warmup operations
    # ------------------------------------------------------------------

    def warmup(self, entry_id: str) -> bool:
        """Start warmup for a component."""
        e = self._entries.get(entry_id)
        if not e or e.status == "ready":
            return False

        # check dependencies are ready
        for dep_id in e.depends_on:
            dep = self._entries.get(dep_id)
            if not dep or dep.status != "ready":
                return False

        e.status = "warming"
        e.updated_at = time.time()

        # run warmup function if provided
        if e.warmup_fn:
            try:
                e.warmup_fn()
            except Exception:
                e.status = "failed"
                e.updated_at = time.time()
                self._total_failures += 1
                self._fire("warmup_failed", {"entry_id": entry_id})
                return False

        e.status = "ready"
        now = time.time()
        e.last_warmup_at = now
        e.updated_at = now
        e.total_warmups += 1
        self._total_warmups += 1
        self._fire("warmup_complete", {"entry_id": entry_id, "component": e.component})
        return True

    def warmup_by_name(self, component: str) -> bool:
        eid = self._name_index.get(component)
        if not eid:
            return False
        return self.warmup(eid)

    def warmup_all(self) -> Dict[str, bool]:
        """Warmup all components in order. Returns results per entry_id."""
        results = {}
        # Sort by order
        sorted_entries = sorted(self._entries.values(), key=lambda e: e.order)
        for e in sorted_entries:
            if e.status == "ready":
                results[e.entry_id] = True
                continue
            results[e.entry_id] = self.warmup(e.entry_id)
        return results

    def check_health(self, entry_id: str) -> bool:
        """Run health check for a component."""
        e = self._entries.get(entry_id)
        if not e or not e.health_fn:
            return False
        try:
            return bool(e.health_fn())
        except Exception:
            return False

    def is_all_ready(self) -> bool:
        return all(e.status == "ready" for e in self._entries.values())

    def get_not_ready(self) -> List[str]:
        return [e.component for e in self._entries.values() if e.status != "ready"]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_components(
        self,
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._entries.values():
            if status and e.status != status:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_component(e.entry_id))
        return results

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
            "current_components": len(self._entries),
            "total_registered": self._total_registered,
            "total_warmups": self._total_warmups,
            "total_failures": self._total_failures,
            "ready_count": sum(1 for e in self._entries.values() if e.status == "ready"),
            "pending_count": sum(1 for e in self._entries.values() if e.status == "pending"),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_warmups = 0
        self._total_failures = 0
