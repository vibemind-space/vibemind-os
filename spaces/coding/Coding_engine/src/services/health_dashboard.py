"""
Health Dashboard — Aggregated health monitoring data for the pipeline system.

Provides:
- Agent health status tracking (healthy/degraded/unhealthy/unknown)
- Service health checks with customizable probes
- Health history and uptime calculation
- System-wide health overview
- Alerts and thresholds
- Health trend analysis

Usage:
    dashboard = HealthDashboard()

    # Register components
    dashboard.register_component("Builder", component_type="agent")
    dashboard.register_component("EventBus", component_type="service")

    # Report health
    dashboard.report_health("Builder", "healthy", metrics={"tasks_completed": 42})

    # Get overview
    overview = dashboard.get_overview()
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class HealthReport:
    """A single health report from a component."""
    status: str
    timestamp: float = field(default_factory=time.time)
    metrics: Dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class ComponentHealth:
    """Health state for a registered component."""
    name: str
    component_type: str  # "agent", "service", "bridge", etc.
    status: str = HealthStatus.UNKNOWN
    last_report: Optional[HealthReport] = None
    registered_at: float = field(default_factory=time.time)
    history: List[HealthReport] = field(default_factory=list)
    max_history: int = 100
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def uptime_ratio(self) -> float:
        """Calculate uptime ratio from history."""
        if not self.history:
            return 0.0
        healthy = sum(1 for h in self.history if h.status == HealthStatus.HEALTHY)
        return healthy / len(self.history)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "status": self.status,
            "uptime_ratio": round(self.uptime_ratio, 3),
            "last_report_age_seconds": (
                round(time.time() - self.last_report.timestamp, 1)
                if self.last_report else None
            ),
            "metrics": self.last_report.metrics if self.last_report else {},
            "history_size": len(self.history),
        }


@dataclass
class Alert:
    """A health alert."""
    alert_id: str
    component: str
    severity: str
    message: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "component": self.component,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


class HealthDashboard:
    """Aggregated health monitoring for the pipeline system."""

    def __init__(self, stale_threshold_seconds: float = 300.0):
        self._stale_threshold = stale_threshold_seconds
        self._components: Dict[str, ComponentHealth] = {}
        self._alerts: List[Alert] = []
        self._probes: Dict[str, Callable] = {}

        # Stats
        self._total_reports = 0
        self._total_alerts = 0

    # ── Registration ─────────────────────────────────────────────────

    def register_component(
        self,
        name: str,
        component_type: str = "service",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register a component for health monitoring."""
        if name in self._components:
            return False

        self._components[name] = ComponentHealth(
            name=name,
            component_type=component_type,
            metadata=metadata or {},
        )

        logger.debug(
            "component_registered",
            component="health_dashboard",
            name=name,
            type=component_type,
        )
        return True

    def unregister_component(self, name: str) -> bool:
        """Unregister a component."""
        return self._components.pop(name, None) is not None

    # ── Health Reporting ─────────────────────────────────────────────

    def report_health(
        self,
        name: str,
        status: str,
        metrics: Optional[Dict[str, Any]] = None,
        message: str = "",
    ) -> bool:
        """Report health status for a component."""
        comp = self._components.get(name)
        if not comp:
            return False

        report = HealthReport(
            status=status,
            metrics=metrics or {},
            message=message,
        )

        old_status = comp.status
        comp.status = status
        comp.last_report = report
        comp.history.append(report)
        self._total_reports += 1

        # Trim history
        if len(comp.history) > comp.max_history:
            comp.history = comp.history[-comp.max_history:]

        # Auto-alert on status transitions
        if old_status != status:
            if status == HealthStatus.UNHEALTHY:
                self._create_alert(name, AlertSeverity.CRITICAL,
                                   f"{name} became unhealthy: {message}")
            elif status == HealthStatus.DEGRADED:
                self._create_alert(name, AlertSeverity.WARNING,
                                   f"{name} is degraded: {message}")
            elif status == HealthStatus.HEALTHY and old_status in (
                HealthStatus.UNHEALTHY, HealthStatus.DEGRADED
            ):
                # Resolve active alerts for this component
                self._resolve_alerts(name)

        return True

    # ── Health Probes ────────────────────────────────────────────────

    def register_probe(self, name: str, probe_fn: Callable) -> bool:
        """Register a health check probe function."""
        if name not in self._components:
            return False
        self._probes[name] = probe_fn
        return True

    def run_probes(self) -> Dict[str, str]:
        """Run all registered health probes and update status."""
        results = {}
        for name, probe_fn in self._probes.items():
            try:
                status = probe_fn()
                if isinstance(status, dict):
                    self.report_health(name, status.get("status", "healthy"),
                                       metrics=status.get("metrics", {}),
                                       message=status.get("message", ""))
                    results[name] = status.get("status", "healthy")
                else:
                    self.report_health(name, str(status))
                    results[name] = str(status)
            except Exception as e:
                self.report_health(name, HealthStatus.UNHEALTHY,
                                   message=f"Probe failed: {e}")
                results[name] = HealthStatus.UNHEALTHY
        return results

    # ── Queries ──────────────────────────────────────────────────────

    def get_component(self, name: str) -> Optional[Dict[str, Any]]:
        """Get health details for a component."""
        comp = self._components.get(name)
        return comp.to_dict() if comp else None

    def get_components(
        self,
        component_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all components with optional filters."""
        results = list(self._components.values())
        if component_type:
            results = [c for c in results if c.component_type == component_type]
        if status:
            results = [c for c in results if c.status == status]
        return [c.to_dict() for c in sorted(results, key=lambda c: c.name)]

    def get_overview(self) -> Dict[str, Any]:
        """Get system-wide health overview."""
        if not self._components:
            return {
                "system_status": "unknown",
                "total_components": 0,
                "status_counts": {},
                "alerts": {"active": 0, "resolved": 0},
            }

        status_counts = {}
        stale_count = 0
        now = time.time()

        for comp in self._components.values():
            status_counts[comp.status] = status_counts.get(comp.status, 0) + 1
            if comp.last_report and (now - comp.last_report.timestamp) > self._stale_threshold:
                stale_count += 1

        # Determine system status
        if status_counts.get(HealthStatus.UNHEALTHY, 0) > 0:
            system_status = HealthStatus.UNHEALTHY
        elif status_counts.get(HealthStatus.DEGRADED, 0) > 0:
            system_status = HealthStatus.DEGRADED
        elif status_counts.get(HealthStatus.UNKNOWN, 0) == len(self._components):
            system_status = HealthStatus.UNKNOWN
        else:
            system_status = HealthStatus.HEALTHY

        active_alerts = [a for a in self._alerts if not a.resolved]

        return {
            "system_status": system_status,
            "total_components": len(self._components),
            "status_counts": status_counts,
            "stale_components": stale_count,
            "alerts": {
                "active": len(active_alerts),
                "resolved": len(self._alerts) - len(active_alerts),
            },
            "uptime_avg": round(
                sum(c.uptime_ratio for c in self._components.values())
                / len(self._components), 3
            ),
        }

    def get_health_history(
        self,
        name: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get health history for a component."""
        comp = self._components.get(name)
        if not comp:
            return []

        return [
            {
                "status": h.status,
                "timestamp": h.timestamp,
                "metrics": h.metrics,
                "message": h.message,
            }
            for h in comp.history[-limit:]
        ]

    # ── Alerts ───────────────────────────────────────────────────────

    def get_alerts(
        self,
        active_only: bool = False,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get alerts."""
        results = self._alerts
        if active_only:
            results = [a for a in results if not a.resolved]
        if severity:
            results = [a for a in results if a.severity == severity]
        return [a.to_dict() for a in results]

    def resolve_alert(self, alert_id: str) -> bool:
        """Manually resolve an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = time.time()
                return True
        return False

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get dashboard statistics."""
        return {
            "total_components": len(self._components),
            "total_reports": self._total_reports,
            "total_alerts": self._total_alerts,
            "active_alerts": sum(1 for a in self._alerts if not a.resolved),
            "probes_registered": len(self._probes),
        }

    def reset(self):
        """Reset all data."""
        self._components.clear()
        self._alerts.clear()
        self._probes.clear()
        self._total_reports = 0
        self._total_alerts = 0

    # ── Internal ─────────────────────────────────────────────────────

    def _create_alert(self, component: str, severity: str, message: str):
        """Create a new alert."""
        alert = Alert(
            alert_id=f"alert-{uuid.uuid4().hex[:8]}",
            component=component,
            severity=severity,
            message=message,
        )
        self._alerts.append(alert)
        self._total_alerts += 1

    def _resolve_alerts(self, component: str):
        """Resolve all active alerts for a component."""
        now = time.time()
        for alert in self._alerts:
            if alert.component == component and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = now
