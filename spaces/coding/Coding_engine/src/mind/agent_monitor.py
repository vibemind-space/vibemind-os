"""
Agent Monitor - Real-time monitoring for all autonomous agents.

Provides:
- Real-time agent status tracking
- Event logging and history
- Document flow visualization
- Performance metrics
- Dashboard output
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable
from collections import defaultdict
import structlog

from .event_bus import EventBus, Event, EventType
from .shared_state import SharedState, ConvergenceMetrics

logger = structlog.get_logger(__name__)


@dataclass
class AgentMetrics:
    """Metrics for a single agent."""
    name: str
    status: str = "idle"  # idle, starting, acting, completed, error
    actions_taken: int = 0
    errors_encountered: int = 0
    last_action: Optional[str] = None
    last_action_time: Optional[datetime] = None
    started_at: Optional[datetime] = None
    total_runtime_seconds: float = 0.0
    documents_produced: int = 0
    documents_consumed: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "actions_taken": self.actions_taken,
            "errors_encountered": self.errors_encountered,
            "last_action": self.last_action,
            "last_action_time": self.last_action_time.isoformat() if self.last_action_time else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "total_runtime_seconds": self.total_runtime_seconds,
            "documents_produced": self.documents_produced,
            "documents_consumed": self.documents_consumed,
        }


@dataclass
class EventLogEntry:
    """A logged event."""
    timestamp: datetime
    event_type: str
    source: str
    summary: str
    success: bool = True
    data: dict = field(default_factory=dict)


class AgentMonitor:
    """
    Real-time monitoring for all autonomous agents.

    Subscribes to all relevant events and provides:
    - Agent status tracking
    - Event history
    - Document flow tracking
    - Performance dashboards
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        max_event_history: int = 1000,
        display_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the agent monitor.

        Args:
            event_bus: The event bus to subscribe to
            shared_state: Shared state for metrics
            max_event_history: Maximum events to keep in history
            display_callback: Optional callback for display updates
        """
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.max_event_history = max_event_history
        self.display_callback = display_callback or self._default_display

        self._agent_metrics: dict[str, AgentMetrics] = {}
        self._event_history: list[EventLogEntry] = []
        self._document_flow: list[dict] = []
        self._lock = asyncio.Lock()
        self._running = False

        self.logger = logger.bind(component="agent_monitor")

        # Subscribe to all relevant events
        self._subscribe_to_events()

        # Known agents to track
        self._known_agents = [
            "Generator",
            "TesterTeam",
            "PlaywrightE2E",
            "CodeQuality",
            "UXDesign",
            "Documentation",
            "Tester",
            "Builder",
            "Validator",
            "Fixer",
        ]

        # Initialize metrics for known agents
        for agent_name in self._known_agents:
            self._agent_metrics[agent_name] = AgentMetrics(name=agent_name)

    def _subscribe_to_events(self) -> None:
        """Subscribe to all monitored event types."""
        # Agent lifecycle events
        self.event_bus.subscribe(EventType.AGENT_STARTED, self._on_agent_started)
        self.event_bus.subscribe(EventType.AGENT_ACTING, self._on_agent_acting)
        self.event_bus.subscribe(EventType.AGENT_COMPLETED, self._on_agent_completed)
        self.event_bus.subscribe(EventType.AGENT_ERROR, self._on_agent_error)

        # Code events
        self.event_bus.subscribe(EventType.CODE_GENERATED, self._on_code_event)
        self.event_bus.subscribe(EventType.CODE_FIXED, self._on_code_event)
        self.event_bus.subscribe(EventType.CODE_FIX_NEEDED, self._on_code_event)

        # Build events
        self.event_bus.subscribe(EventType.BUILD_STARTED, self._on_build_event)
        self.event_bus.subscribe(EventType.BUILD_SUCCEEDED, self._on_build_event)
        self.event_bus.subscribe(EventType.BUILD_FAILED, self._on_build_event)

        # Test events
        self.event_bus.subscribe(EventType.TEST_STARTED, self._on_test_event)
        self.event_bus.subscribe(EventType.TEST_PASSED, self._on_test_event)
        self.event_bus.subscribe(EventType.TEST_FAILED, self._on_test_event)
        self.event_bus.subscribe(EventType.TEST_SUITE_COMPLETE, self._on_test_event)

        # Document events
        self.event_bus.subscribe(EventType.DOCUMENT_CREATED, self._on_document_event)
        self.event_bus.subscribe(EventType.DOCUMENT_CONSUMED, self._on_document_event)
        self.event_bus.subscribe(EventType.DEBUG_REPORT_CREATED, self._on_document_event)
        self.event_bus.subscribe(EventType.IMPLEMENTATION_PLAN_CREATED, self._on_document_event)
        self.event_bus.subscribe(EventType.TEST_SPEC_CREATED, self._on_document_event)
        self.event_bus.subscribe(EventType.QUALITY_REPORT_CREATED, self._on_document_event)

        # E2E and visual testing events
        self.event_bus.subscribe(EventType.PLAYWRIGHT_E2E_STARTED, self._on_e2e_event)
        self.event_bus.subscribe(EventType.PLAYWRIGHT_E2E_PASSED, self._on_e2e_event)
        self.event_bus.subscribe(EventType.PLAYWRIGHT_E2E_FAILED, self._on_e2e_event)

        # System events
        self.event_bus.subscribe(EventType.CONVERGENCE_UPDATE, self._on_convergence_update)
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._on_system_error)

    def _get_or_create_metrics(self, agent_name: str) -> AgentMetrics:
        """Get or create metrics for an agent."""
        if agent_name not in self._agent_metrics:
            self._agent_metrics[agent_name] = AgentMetrics(name=agent_name)
        return self._agent_metrics[agent_name]

    async def _log_event(self, event: Event, summary: str) -> None:
        """Log an event to history."""
        async with self._lock:
            entry = EventLogEntry(
                timestamp=event.timestamp,
                event_type=event.type.value,
                source=event.source,
                summary=summary,
                success=event.success,
                data=event.data,
            )
            self._event_history.append(entry)

            # Trim history if needed
            if len(self._event_history) > self.max_event_history:
                self._event_history = self._event_history[-self.max_event_history:]

    def _on_agent_started(self, event: Event) -> None:
        """Handle agent started event."""
        metrics = self._get_or_create_metrics(event.source)
        metrics.status = "running"
        metrics.started_at = event.timestamp

        asyncio.create_task(self._log_event(event, f"Agent {event.source} started"))
        self._update_display()

    def _on_agent_acting(self, event: Event) -> None:
        """Handle agent acting event."""
        metrics = self._get_or_create_metrics(event.source)
        metrics.status = "acting"
        action = event.data.get("action", "unknown action")
        metrics.last_action = action
        metrics.last_action_time = event.timestamp

        asyncio.create_task(self._log_event(event, f"Agent {event.source}: {action}"))
        self._update_display()

    def _on_agent_completed(self, event: Event) -> None:
        """Handle agent completed event."""
        metrics = self._get_or_create_metrics(event.source)
        metrics.status = "completed"
        metrics.actions_taken = event.data.get("actions_taken", metrics.actions_taken)

        if metrics.started_at:
            runtime = (event.timestamp - metrics.started_at).total_seconds()
            metrics.total_runtime_seconds += runtime

        asyncio.create_task(self._log_event(
            event,
            f"Agent {event.source} completed ({metrics.actions_taken} actions)"
        ))
        self._update_display()

    def _on_agent_error(self, event: Event) -> None:
        """Handle agent error event."""
        metrics = self._get_or_create_metrics(event.source)
        metrics.status = "error"
        metrics.errors_encountered += 1

        error_msg = event.data.get("error", event.error_message or "unknown error")
        asyncio.create_task(self._log_event(event, f"Agent {event.source} ERROR: {error_msg}"))
        self._update_display()

    def _on_code_event(self, event: Event) -> None:
        """Handle code-related events."""
        summary = f"{event.source}: {event.type.value}"
        if event.file_path:
            summary += f" ({event.file_path})"

        asyncio.create_task(self._log_event(event, summary))

        # Update agent metrics
        metrics = self._get_or_create_metrics(event.source)
        if event.type in (EventType.CODE_GENERATED, EventType.CODE_FIXED):
            metrics.actions_taken += 1

        self._update_display()

    def _on_build_event(self, event: Event) -> None:
        """Handle build events."""
        status = "started" if event.type == EventType.BUILD_STARTED else \
                 "succeeded" if event.type == EventType.BUILD_SUCCEEDED else "failed"

        asyncio.create_task(self._log_event(event, f"Build {status}"))
        self._update_display()

    def _on_test_event(self, event: Event) -> None:
        """Handle test events."""
        summary = f"Test: {event.type.value}"
        if event.data:
            if "total" in event.data:
                summary += f" ({event.data.get('passed', 0)}/{event.data.get('total', 0)} passed)"

        asyncio.create_task(self._log_event(event, summary))
        self._update_display()

    def _on_document_event(self, event: Event) -> None:
        """Handle document registry events."""
        doc_id = event.data.get("doc_id", "unknown")
        summary = f"Document: {event.type.value} ({doc_id})"

        # Track document flow
        self._document_flow.append({
            "timestamp": event.timestamp.isoformat(),
            "type": event.type.value,
            "source": event.source,
            "doc_id": doc_id,
            "data": event.data,
        })

        # Update producer/consumer counts
        metrics = self._get_or_create_metrics(event.source)
        if event.type in (
            EventType.DEBUG_REPORT_CREATED,
            EventType.IMPLEMENTATION_PLAN_CREATED,
            EventType.TEST_SPEC_CREATED,
            EventType.QUALITY_REPORT_CREATED,
        ):
            metrics.documents_produced += 1
        elif event.type == EventType.DOCUMENT_CONSUMED:
            metrics.documents_consumed += 1

        asyncio.create_task(self._log_event(event, summary))
        self._update_display()

    def _on_e2e_event(self, event: Event) -> None:
        """Handle E2E testing events."""
        summary = f"E2E: {event.type.value}"
        if not event.success:
            summary += f" - {event.error_message or 'failed'}"

        asyncio.create_task(self._log_event(event, summary))
        self._update_display()

    def _on_convergence_update(self, event: Event) -> None:
        """Handle convergence update events."""
        iteration = event.data.get("iteration", 0)
        confidence = event.data.get("confidence", 0)
        summary = f"Convergence: iteration {iteration}, confidence {confidence:.1%}"

        asyncio.create_task(self._log_event(event, summary))
        self._update_display()

    def _on_system_error(self, event: Event) -> None:
        """Handle system error events."""
        error = event.error_message or event.data.get("error", "unknown")
        asyncio.create_task(self._log_event(event, f"SYSTEM ERROR: {error}"))
        self._update_display()

    def _update_display(self) -> None:
        """Update the display output."""
        if self._running:
            display = self.get_dashboard()
            self.display_callback(display)

    def _default_display(self, text: str) -> None:
        """Default display callback - print to console."""
        # Clear screen and print
        print("\033[2J\033[H", end="")  # ANSI clear screen
        print(text)

    def get_dashboard(self) -> str:
        """Generate a dashboard string."""
        lines = []
        lines.append("=" * 70)
        lines.append("                    AGENT MONITOR DASHBOARD")
        lines.append("=" * 70)
        lines.append("")

        # Shared state metrics
        metrics = self.shared_state.metrics
        lines.append(f"Iteration: {metrics.iteration:3d}  |  Confidence: {metrics.confidence_score:.1%}")
        lines.append(f"Build: {'OK' if metrics.build_success else 'FAIL' if metrics.build_attempted else 'PENDING':8}  |  "
                    f"Tests: {metrics.tests_passed}/{metrics.total_tests} passed")
        lines.append(f"Type Errors: {metrics.type_errors:3d}  |  Validation Errors: {metrics.validation_errors}")
        lines.append("")

        # Agent status table
        lines.append("-" * 70)
        lines.append(f"{'AGENT':<18} {'STATUS':<12} {'ACTIONS':<8} {'ERRORS':<7} {'DOCS':<10}")
        lines.append("-" * 70)

        for name, agent in sorted(self._agent_metrics.items()):
            status_icon = {
                "idle": "-",
                "running": ">",
                "acting": "*",
                "completed": "+",
                "error": "!",
            }.get(agent.status, "?")

            docs = f"{agent.documents_produced}^ {agent.documents_consumed}v"
            lines.append(
                f"{status_icon} {name:<16} {agent.status:<12} {agent.actions_taken:<8} "
                f"{agent.errors_encountered:<7} {docs:<10}"
            )

        lines.append("")

        # Document flow
        lines.append("-" * 70)
        lines.append("DOCUMENT FLOW (last 5)")
        lines.append("-" * 70)

        for flow in self._document_flow[-5:]:
            time_str = flow["timestamp"].split("T")[1][:8]
            lines.append(f"  {time_str} | {flow['source']:<15} -> {flow['type']}")

        if not self._document_flow:
            lines.append("  (no documents yet)")

        lines.append("")

        # Recent events
        lines.append("-" * 70)
        lines.append("RECENT EVENTS (last 10)")
        lines.append("-" * 70)

        for entry in self._event_history[-10:]:
            time_str = entry.timestamp.strftime("%H:%M:%S")
            status = "+" if entry.success else "!"
            lines.append(f"  {time_str} {status} {entry.summary[:55]}")

        if not self._event_history:
            lines.append("  (no events yet)")

        lines.append("")
        lines.append("=" * 70)

        return "\n".join(lines)

    def get_agent_status(self, agent_name: str) -> Optional[AgentMetrics]:
        """Get status for a specific agent."""
        return self._agent_metrics.get(agent_name)

    def get_all_agent_status(self) -> dict[str, dict]:
        """Get status for all agents."""
        return {name: metrics.to_dict() for name, metrics in self._agent_metrics.items()}

    def get_event_history(self, limit: int = 100) -> list[dict]:
        """Get recent event history."""
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "type": e.event_type,
                "source": e.source,
                "summary": e.summary,
                "success": e.success,
            }
            for e in self._event_history[-limit:]
        ]

    def get_document_flow(self) -> list[dict]:
        """Get document flow history."""
        return self._document_flow.copy()

    def start(self) -> None:
        """Start monitoring with display updates."""
        self._running = True
        self.logger.info("monitor_started")
        self._update_display()

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        self.logger.info("monitor_stopped")

    def print_summary(self) -> None:
        """Print a final summary."""
        print("\n" + "=" * 70)
        print("                    FINAL MONITORING SUMMARY")
        print("=" * 70)

        print("\nAgent Performance:")
        print("-" * 50)
        for name, metrics in sorted(self._agent_metrics.items()):
            if metrics.actions_taken > 0 or metrics.errors_encountered > 0:
                print(f"  {name}:")
                print(f"    Actions: {metrics.actions_taken}")
                print(f"    Errors: {metrics.errors_encountered}")
                print(f"    Documents: {metrics.documents_produced} produced, {metrics.documents_consumed} consumed")
                if metrics.total_runtime_seconds > 0:
                    print(f"    Runtime: {metrics.total_runtime_seconds:.1f}s")

        print(f"\nTotal Events Logged: {len(self._event_history)}")
        print(f"Total Document Transfers: {len(self._document_flow)}")

        # Error summary
        errors = [e for e in self._event_history if not e.success]
        if errors:
            print(f"\nErrors Encountered: {len(errors)}")
            for err in errors[-5:]:
                print(f"  - {err.summary}")

        print("=" * 70)


def create_monitor(
    event_bus: EventBus,
    shared_state: SharedState,
    display_callback: Optional[Callable[[str], None]] = None,
) -> AgentMonitor:
    """
    Create and configure an agent monitor.

    Args:
        event_bus: Event bus to monitor
        shared_state: Shared state for metrics
        display_callback: Optional custom display function

    Returns:
        Configured AgentMonitor instance
    """
    monitor = AgentMonitor(
        event_bus=event_bus,
        shared_state=shared_state,
        display_callback=display_callback,
    )
    return monitor
