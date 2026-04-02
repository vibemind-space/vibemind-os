"""
Pipeline Health Monitor — Tracks agent liveness and event flow health.

Monitors:
- Agent heartbeats and activity
- Event throughput and latency
- Service connectivity (Minibook, DaveLovable, OpenClaw)
- Pipeline stuck detection (no events for N seconds)
- Error rate tracking
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import structlog

from ..mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)


@dataclass
class AgentHealth:
    """Health status of a single agent."""
    name: str
    last_event_at: float = 0.0
    event_count: int = 0
    error_count: int = 0
    is_alive: bool = True
    status: str = "idle"  # idle, active, stuck, error


@dataclass
class ServiceHealth:
    """Health status of an external service."""
    name: str
    url: str
    is_connected: bool = False
    last_check_at: float = 0.0
    response_time_ms: float = 0.0
    consecutive_failures: int = 0


@dataclass
class HealthReport:
    """Complete health report."""
    timestamp: str
    overall_status: str  # healthy, degraded, unhealthy
    pipeline_running: bool
    uptime_seconds: float
    agents: Dict[str, Dict]
    services: Dict[str, Dict]
    event_stats: Dict[str, Any]
    alerts: List[str]


class PipelineHealthMonitor:
    """Monitors the health of the entire pipeline system."""

    STUCK_THRESHOLD_SECONDS = 120  # No events for 2 min = stuck
    AGENT_TIMEOUT_SECONDS = 300  # Agent not active for 5 min = dead

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._start_time = time.time()

        # Agent tracking
        self._agents: Dict[str, AgentHealth] = {}

        # Service tracking
        self._services: Dict[str, ServiceHealth] = {}

        # Event stats
        self._event_counts: Dict[str, int] = defaultdict(int)
        self._error_events: int = 0
        self._last_event_time: float = time.time()
        self._events_per_minute: List[float] = []

        # Pipeline state
        self._pipeline_running = False
        self._alerts: List[str] = []

        self._subscribe()

    def _subscribe(self):
        """Subscribe to events for health tracking."""
        # Agent lifecycle
        self.event_bus.subscribe(EventType.AGENT_STARTED, self._on_agent_started)
        self.event_bus.subscribe(EventType.AGENT_ACTING, self._on_agent_acting)
        self.event_bus.subscribe(EventType.AGENT_COMPLETED, self._on_agent_completed)
        self.event_bus.subscribe(EventType.AGENT_ERROR, self._on_agent_error)

        # Pipeline lifecycle
        self.event_bus.subscribe(EventType.PIPELINE_STARTED, self._on_pipeline_started)
        self.event_bus.subscribe(EventType.PIPELINE_COMPLETED, self._on_pipeline_completed)
        self.event_bus.subscribe(EventType.PIPELINE_FAILED, self._on_pipeline_failed)

        # Error events
        self.event_bus.subscribe(EventType.BUILD_FAILED, self._on_error_event)
        self.event_bus.subscribe(EventType.TEST_FAILED, self._on_error_event)
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._on_error_event)
        self.event_bus.subscribe(EventType.EVOLUTION_FAILED, self._on_error_event)

        # Service connectivity
        self.event_bus.subscribe(EventType.MINIBOOK_CONNECTED, self._on_service_connected)
        self.event_bus.subscribe(EventType.MINIBOOK_DISCONNECTED, self._on_service_disconnected)

        # General event counter (catch-all via a broad subset)
        for et in [EventType.CODE_GENERATED, EventType.CODE_FIXED,
                    EventType.TREEQUEST_VERIFICATION_COMPLETE, EventType.EVOLUTION_APPLIED]:
            self.event_bus.subscribe(et, self._on_any_event)

    def register_service(self, name: str, url: str, connected: bool = False):
        """Register an external service for health tracking."""
        self._services[name] = ServiceHealth(
            name=name, url=url, is_connected=connected, last_check_at=time.time()
        )

    # --- Event Handlers ---

    async def _on_agent_started(self, event: Event):
        name = event.data.get("agent", "unknown")
        if name not in self._agents:
            self._agents[name] = AgentHealth(name=name)
        self._agents[name].status = "active"
        self._agents[name].last_event_at = time.time()
        self._agents[name].is_alive = True

    async def _on_agent_acting(self, event: Event):
        name = event.data.get("agent", "unknown")
        if name in self._agents:
            self._agents[name].status = "active"
            self._agents[name].last_event_at = time.time()
            self._agents[name].event_count += 1

    async def _on_agent_completed(self, event: Event):
        name = event.data.get("agent", "unknown")
        if name in self._agents:
            self._agents[name].status = "idle"
            self._agents[name].last_event_at = time.time()
            self._agents[name].event_count += 1

    async def _on_agent_error(self, event: Event):
        name = event.data.get("agent", "unknown")
        if name not in self._agents:
            self._agents[name] = AgentHealth(name=name)
        self._agents[name].status = "error"
        self._agents[name].error_count += 1
        self._agents[name].last_event_at = time.time()

    async def _on_pipeline_started(self, event: Event):
        self._pipeline_running = True
        self._last_event_time = time.time()

    async def _on_pipeline_completed(self, event: Event):
        self._pipeline_running = False

    async def _on_pipeline_failed(self, event: Event):
        self._pipeline_running = False
        self._alerts.append(f"Pipeline failed: {event.data.get('error', 'unknown')}")

    async def _on_error_event(self, event: Event):
        self._error_events += 1
        self._event_counts[event.type.value] += 1
        self._last_event_time = time.time()

    async def _on_service_connected(self, event: Event):
        name = event.data.get("service", "minibook")
        if name in self._services:
            self._services[name].is_connected = True
            self._services[name].consecutive_failures = 0

    async def _on_service_disconnected(self, event: Event):
        name = event.data.get("service", "minibook")
        if name in self._services:
            self._services[name].is_connected = False

    async def _on_any_event(self, event: Event):
        self._event_counts[event.type.value] += 1
        self._last_event_time = time.time()
        self._events_per_minute.append(time.time())
        # Keep only last 5 minutes
        cutoff = time.time() - 300
        self._events_per_minute = [t for t in self._events_per_minute if t > cutoff]

    # --- Health Check ---

    def check_health(self) -> HealthReport:
        """Generate a health report."""
        now = time.time()
        alerts = list(self._alerts)

        # Check agent health
        for name, agent in self._agents.items():
            if agent.status == "active" and (now - agent.last_event_at) > self.STUCK_THRESHOLD_SECONDS:
                agent.status = "stuck"
                alerts.append(f"Agent {name} appears stuck (no activity for {int(now - agent.last_event_at)}s)")
            if (now - agent.last_event_at) > self.AGENT_TIMEOUT_SECONDS:
                agent.is_alive = False

        # Check for stuck pipeline
        if self._pipeline_running and (now - self._last_event_time) > self.STUCK_THRESHOLD_SECONDS:
            alerts.append(f"Pipeline may be stuck (no events for {int(now - self._last_event_time)}s)")

        # Determine overall status
        if any(a.status == "error" for a in self._agents.values()):
            overall = "degraded"
        elif alerts:
            overall = "degraded"
        elif not self._pipeline_running:
            overall = "idle"
        else:
            overall = "healthy"

        # Event throughput
        recent_events = [t for t in self._events_per_minute if t > now - 60]
        events_per_minute = len(recent_events)

        return HealthReport(
            timestamp=datetime.now().isoformat(),
            overall_status=overall,
            pipeline_running=self._pipeline_running,
            uptime_seconds=now - self._start_time,
            agents={
                name: {
                    "status": a.status,
                    "is_alive": a.is_alive,
                    "event_count": a.event_count,
                    "error_count": a.error_count,
                    "last_active_seconds_ago": int(now - a.last_event_at) if a.last_event_at else -1,
                }
                for name, a in self._agents.items()
            },
            services={
                name: {
                    "connected": s.is_connected,
                    "url": s.url,
                    "consecutive_failures": s.consecutive_failures,
                }
                for name, s in self._services.items()
            },
            event_stats={
                "total_events": sum(self._event_counts.values()),
                "error_events": self._error_events,
                "events_per_minute": events_per_minute,
                "top_events": dict(
                    sorted(self._event_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ),
            },
            alerts=alerts,
        )

    def get_health_dict(self) -> Dict[str, Any]:
        """Get health report as a dictionary."""
        report = self.check_health()
        return {
            "timestamp": report.timestamp,
            "overall_status": report.overall_status,
            "pipeline_running": report.pipeline_running,
            "uptime_seconds": report.uptime_seconds,
            "agents": report.agents,
            "services": report.services,
            "event_stats": report.event_stats,
            "alerts": report.alerts,
        }
