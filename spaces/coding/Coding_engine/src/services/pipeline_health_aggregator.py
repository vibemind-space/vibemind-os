"""Pipeline Health Aggregator – aggregate health status from all pipeline components.

Provides a unified health view across the entire pipeline. Tracks component
uptime, error rates, latency, and computes an overall system health score.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _HealthComponent:
    comp_id: str
    name: str
    component_type: str
    current_status: str
    total_checks: int
    healthy_checks: int
    total_latency: float
    total_error_rate: float
    tags: List[str]
    last_check_at: float
    created_at: float


@dataclass
class _HealthReport:
    report_id: str
    component_name: str
    status: str
    latency: float
    error_rate: float
    details: Dict[str, Any]
    timestamp: float


@dataclass
class _HealthEvent:
    event_id: str
    component_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class PipelineHealthAggregator:
    """Aggregates health status from all pipeline components into a unified view."""

    VALID_STATUSES = ("healthy", "degraded", "unhealthy", "unknown")

    def __init__(self, max_components: int = 5000,
                 max_history: int = 100000) -> None:
        self._max_components = max_components
        self._max_history = max_history
        self._components: Dict[str, _HealthComponent] = {}
        self._reports: List[_HealthReport] = []
        self._history: List[_HealthEvent] = []
        self._callbacks: Dict[str, Callable[..., Any]] = {}
        self._seq = 0
        self._stats = {
            "total_components_registered": 0,
            "total_reports_received": 0,
            "total_components_removed": 0,
            "total_callbacks_fired": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        raw = f"{prefix}-{self._seq}-{time.time()}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_event(self, component_name: str, action: str,
                      data: Optional[Dict[str, Any]] = None) -> None:
        evt = _HealthEvent(
            event_id=self._next_id("phe-"),
            component_name=component_name,
            action=action,
            data=data or {},
            timestamp=time.time(),
        )
        self._history.append(evt)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def _trim_reports(self) -> None:
        if len(self._reports) > self._max_history:
            self._reports = self._reports[-self._max_history:]

    # ------------------------------------------------------------------
    # Component management
    # ------------------------------------------------------------------

    def register_component(self, name: str, component_type: str = "service",
                           tags: Optional[List[str]] = None) -> str:
        """Register a pipeline component for health tracking. Returns comp_id."""
        if name in self._components:
            return self._components[name].comp_id
        if len(self._components) >= self._max_components:
            return ""
        comp_id = self._next_id("phc-")
        now = time.time()
        comp = _HealthComponent(
            comp_id=comp_id,
            name=name,
            component_type=component_type,
            current_status="unknown",
            total_checks=0,
            healthy_checks=0,
            total_latency=0.0,
            total_error_rate=0.0,
            tags=list(tags) if tags else [],
            last_check_at=0.0,
            created_at=now,
        )
        self._components[name] = comp
        self._stats["total_components_registered"] += 1
        self._record_event(name, "register", {"comp_id": comp_id,
                                                "component_type": component_type})
        self._fire("register", {"comp_id": comp_id, "name": name})
        return comp_id

    def remove_component(self, name: str) -> bool:
        """Remove a component from health tracking."""
        if name not in self._components:
            return False
        comp = self._components.pop(name)
        self._stats["total_components_removed"] += 1
        self._record_event(name, "remove", {"comp_id": comp.comp_id})
        self._fire("remove", {"comp_id": comp.comp_id, "name": name})
        return True

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    def report_health(self, name: str, status: str = "healthy",
                      latency: float = 0.0, error_rate: float = 0.0,
                      details: Optional[Dict[str, Any]] = None) -> bool:
        """Report a health check result for a component."""
        if name not in self._components:
            return False
        if status not in self.VALID_STATUSES:
            return False
        comp = self._components[name]
        now = time.time()

        report = _HealthReport(
            report_id=self._next_id("phr-"),
            component_name=name,
            status=status,
            latency=latency,
            error_rate=error_rate,
            details=details or {},
            timestamp=now,
        )
        self._reports.append(report)
        self._trim_reports()

        prev_status = comp.current_status
        comp.current_status = status
        comp.total_checks += 1
        if status == "healthy":
            comp.healthy_checks += 1
        comp.total_latency += latency
        comp.total_error_rate += error_rate
        comp.last_check_at = now

        self._stats["total_reports_received"] += 1
        self._record_event(name, "report_health", {
            "status": status, "latency": latency, "error_rate": error_rate,
        })
        if prev_status != status:
            self._fire("status_change", {
                "name": name, "from": prev_status, "to": status,
            })
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_component(self, name: str) -> Optional[Dict[str, Any]]:
        """Return component details including computed metrics."""
        if name not in self._components:
            return None
        comp = self._components[name]
        total = comp.total_checks if comp.total_checks > 0 else 1
        return {
            "comp_id": comp.comp_id,
            "name": comp.name,
            "component_type": comp.component_type,
            "current_status": comp.current_status,
            "uptime_pct": round(comp.healthy_checks / total * 100, 2),
            "avg_latency": round(comp.total_latency / total, 4),
            "avg_error_rate": round(comp.total_error_rate / total, 4),
            "check_count": comp.total_checks,
            "last_check_at": comp.last_check_at,
            "tags": list(comp.tags),
            "created_at": comp.created_at,
        }

    def get_system_health(self) -> Dict[str, Any]:
        """Compute and return the overall system health summary."""
        total = len(self._components)
        if total == 0:
            return {
                "status": "unknown",
                "health_score": 0,
                "component_count": 0,
                "healthy_count": 0,
                "degraded_count": 0,
                "unhealthy_count": 0,
                "unknown_count": 0,
            }
        counts: Dict[str, int] = {
            "healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0,
        }
        for comp in self._components.values():
            st = comp.current_status if comp.current_status in counts else "unknown"
            counts[st] += 1

        health_score = round(
            (counts["healthy"] * 100 + counts["degraded"] * 50) / total, 2
        )

        if counts["unhealthy"] > 0:
            overall = "unhealthy"
        elif counts["degraded"] > 0:
            overall = "degraded"
        elif counts["healthy"] == total:
            overall = "healthy"
        else:
            overall = "unknown"

        return {
            "status": overall,
            "health_score": health_score,
            "component_count": total,
            "healthy_count": counts["healthy"],
            "degraded_count": counts["degraded"],
            "unhealthy_count": counts["unhealthy"],
            "unknown_count": counts["unknown"],
        }

    def get_unhealthy_components(self) -> List[Dict[str, Any]]:
        """Return all components with unhealthy status."""
        results: List[Dict[str, Any]] = []
        for name, comp in self._components.items():
            if comp.current_status == "unhealthy":
                info = self.get_component(name)
                if info is not None:
                    results.append(info)
        return results

    def get_degraded_components(self) -> List[Dict[str, Any]]:
        """Return all components with degraded status."""
        results: List[Dict[str, Any]] = []
        for name, comp in self._components.items():
            if comp.current_status == "degraded":
                info = self.get_component(name)
                if info is not None:
                    results.append(info)
        return results

    def get_health_timeline(self, name: str,
                            limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent health reports for a specific component."""
        timeline: List[Dict[str, Any]] = []
        for report in reversed(self._reports):
            if report.component_name == name:
                timeline.append({
                    "report_id": report.report_id,
                    "status": report.status,
                    "latency": report.latency,
                    "error_rate": report.error_rate,
                    "details": dict(report.details),
                    "timestamp": report.timestamp,
                })
                if len(timeline) >= limit:
                    break
        return timeline

    def list_components(self, component_type: str = "",
                        status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        """List components with optional filters."""
        results: List[Dict[str, Any]] = []
        for name, comp in self._components.items():
            if component_type and comp.component_type != component_type:
                continue
            if status and comp.current_status != status:
                continue
            if tag and tag not in comp.tags:
                continue
            info = self.get_component(name)
            if info is not None:
                results.append(info)
        return results

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent health events."""
        entries = self._history[-limit:] if limit < len(self._history) else list(self._history)
        results: List[Dict[str, Any]] = []
        for evt in reversed(entries):
            results.append({
                "event_id": evt.event_id,
                "component_name": evt.component_name,
                "action": evt.action,
                "data": dict(evt.data),
                "timestamp": evt.timestamp,
            })
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable[..., Any]) -> None:
        """Register a callback for health change events."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Fire all registered callbacks with the given event data."""
        self._stats["total_callbacks_fired"] += 1
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregator statistics."""
        return {
            "total_components_registered": self._stats["total_components_registered"],
            "total_reports_received": self._stats["total_reports_received"],
            "total_components_removed": self._stats["total_components_removed"],
            "total_callbacks_fired": self._stats["total_callbacks_fired"],
            "active_components": len(self._components),
            "total_reports_stored": len(self._reports),
            "total_history_events": len(self._history),
            "active_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state to initial empty values."""
        self._components.clear()
        self._reports.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {
            "total_components_registered": 0,
            "total_reports_received": 0,
            "total_components_removed": 0,
            "total_callbacks_fired": 0,
        }
