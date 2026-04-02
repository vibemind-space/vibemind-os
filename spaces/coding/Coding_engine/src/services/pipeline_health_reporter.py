"""Pipeline Health Reporter – generates health reports for pipeline components.

Collects health status from registered components, generates periodic
reports, tracks health history, and supports alerting on degraded states.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _HealthRecord:
    record_id: str
    component: str
    status: str  # healthy, degraded, unhealthy, unknown
    message: str
    metrics: Dict[str, float]
    timestamp: float


@dataclass
class _ComponentReg:
    component: str
    check_fn: Optional[Callable]
    current_status: str
    last_check_at: float
    total_checks: int
    total_healthy: int
    total_degraded: int
    total_unhealthy: int
    tags: List[str]
    created_at: float


class PipelineHealthReporter:
    """Generates health reports for pipeline components."""

    STATUSES = ("healthy", "degraded", "unhealthy", "unknown")

    def __init__(self, max_components: int = 1000, max_history: int = 100000):
        self._components: Dict[str, _ComponentReg] = {}
        self._history: List[_HealthRecord] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_components = max_components
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_reports = 0
        self._total_checks = 0

    # ------------------------------------------------------------------
    # Component registration
    # ------------------------------------------------------------------

    def register(
        self,
        component: str,
        check_fn: Optional[Callable] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        if not component:
            return False
        if component in self._components:
            return False
        if len(self._components) >= self._max_components:
            return False

        now = time.time()
        self._components[component] = _ComponentReg(
            component=component,
            check_fn=check_fn,
            current_status="unknown",
            last_check_at=0.0,
            total_checks=0,
            total_healthy=0,
            total_degraded=0,
            total_unhealthy=0,
            tags=tags or [],
            created_at=now,
        )
        self._fire("component_registered", {"component": component})
        return True

    def unregister(self, component: str) -> bool:
        return self._components.pop(component, None) is not None

    def get_component(self, component: str) -> Optional[Dict[str, Any]]:
        c = self._components.get(component)
        if not c:
            return None
        return {
            "component": c.component,
            "current_status": c.current_status,
            "last_check_at": c.last_check_at,
            "total_checks": c.total_checks,
            "total_healthy": c.total_healthy,
            "total_degraded": c.total_degraded,
            "total_unhealthy": c.total_unhealthy,
            "tags": list(c.tags),
            "created_at": c.created_at,
        }

    # ------------------------------------------------------------------
    # Health checking
    # ------------------------------------------------------------------

    def check(self, component: str) -> Optional[str]:
        """Run health check for a component. Returns status or None."""
        c = self._components.get(component)
        if not c:
            return None

        status = "healthy"
        message = ""
        metrics: Dict[str, float] = {}

        if c.check_fn:
            try:
                result = c.check_fn()
                if isinstance(result, dict):
                    status = result.get("status", "healthy")
                    message = result.get("message", "")
                    metrics = result.get("metrics", {})
                elif isinstance(result, str):
                    status = result
                elif isinstance(result, bool):
                    status = "healthy" if result else "unhealthy"
            except Exception as exc:
                status = "unhealthy"
                message = str(exc)

        if status not in self.STATUSES:
            status = "unknown"

        c.current_status = status
        c.last_check_at = time.time()
        c.total_checks += 1
        self._total_checks += 1

        if status == "healthy":
            c.total_healthy += 1
        elif status == "degraded":
            c.total_degraded += 1
        elif status == "unhealthy":
            c.total_unhealthy += 1

        # record history
        self._seq += 1
        raw = f"{component}-{time.time()}-{self._seq}"
        rid = "hrc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        record = _HealthRecord(
            record_id=rid,
            component=component,
            status=status,
            message=message,
            metrics=metrics,
            timestamp=c.last_check_at,
        )

        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(record)

        if status != "healthy":
            self._fire("health_degraded", {
                "component": component, "status": status, "message": message,
            })

        return status

    def check_all(self) -> Dict[str, str]:
        """Check all components. Returns component->status mapping."""
        results = {}
        for comp in list(self._components.keys()):
            results[comp] = self.check(comp) or "unknown"
        return results

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self) -> Dict[str, Any]:
        """Generate a full health report."""
        self._total_reports += 1
        components = {}
        for name, c in self._components.items():
            components[name] = {
                "status": c.current_status,
                "last_check_at": c.last_check_at,
                "total_checks": c.total_checks,
            }

        total = len(self._components)
        healthy = sum(1 for c in self._components.values() if c.current_status == "healthy")
        degraded = sum(1 for c in self._components.values() if c.current_status == "degraded")
        unhealthy = sum(1 for c in self._components.values() if c.current_status == "unhealthy")

        overall = "healthy"
        if unhealthy > 0:
            overall = "unhealthy"
        elif degraded > 0:
            overall = "degraded"
        elif healthy < total:
            overall = "unknown"

        return {
            "overall": overall,
            "total_components": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "components": components,
            "generated_at": time.time(),
        }

    def get_history(
        self,
        component: str = "",
        status: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for r in reversed(self._history):
            if component and r.component != component:
                continue
            if status and r.status != status:
                continue
            results.append({
                "record_id": r.record_id,
                "component": r.component,
                "status": r.status,
                "message": r.message,
                "metrics": dict(r.metrics),
                "timestamp": r.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_components(
        self,
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for c in self._components.values():
            if status and c.current_status != status:
                continue
            if tag and tag not in c.tags:
                continue
            results.append(self.get_component(c.component))
        return results

    def get_unhealthy(self) -> List[str]:
        return [c.component for c in self._components.values()
                if c.current_status in ("unhealthy", "degraded")]

    def is_all_healthy(self) -> bool:
        return all(c.current_status == "healthy" for c in self._components.values())

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
            "current_components": len(self._components),
            "total_reports": self._total_reports,
            "total_checks": self._total_checks,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._components.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_reports = 0
        self._total_checks = 0
