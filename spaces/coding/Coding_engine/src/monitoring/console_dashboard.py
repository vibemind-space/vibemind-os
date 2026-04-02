"""
Console Dashboard - Real-time console output for generation progress.

Subscribes to all events from the EventBus and displays them in a
formatted console output with emoji icons for visibility.

Usage:
    from src.monitoring.console_dashboard import ConsoleDashboard

    dashboard = ConsoleDashboard(event_bus)
    # Dashboard automatically subscribes and displays events
"""

import asyncio
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ..mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)


# Event type to emoji icon mapping
EVENT_ICONS = {
    # Build events
    "build_started": "🔨",
    "build_succeeded": "✅",
    "build_failed": "❌",
    "build_completed": "🔨",

    # Contract/Schema events
    "contracts_generated": "📋",
    "database_schema_generated": "🗄️",
    "database_schema_failed": "❌",
    "api_routes_generated": "🌐",
    "api_generation_failed": "❌",
    "auth_setup_complete": "🔐",
    "auth_setup_failed": "❌",
    "infrastructure_ready": "🐳",
    "env_config_failed": "❌",

    # Test events
    "test_started": "🧪",
    "test_passed": "✅",
    "test_failed": "❌",
    "tests_passed": "🧪",
    "tests_failed": "❌",
    "e2e_test_passed": "🎭",
    "e2e_test_failed": "❌",

    # Deploy events
    "deploy_started": "🚀",
    "deploy_succeeded": "🚀",
    "deploy_failed": "❌",
    "sandbox_test_started": "📦",
    "sandbox_test_passed": "✅",
    "sandbox_test_failed": "❌",

    # Agent events
    "agent_started": "🤖",
    "agent_acting": "⚡",
    "agent_completed": "🛑",
    "agent_error": "❌",

    # Code events
    "code_generated": "💻",
    "code_fixed": "🔧",
    "code_fix_needed": "🔧",
    "generation_complete": "✅",

    # Security events
    "security_scan_started": "🛡️",
    "security_scan_passed": "🛡️",
    "security_scan_failed": "❌",
    "vulnerability_detected": "⚠️",

    # UX events
    "ux_review_started": "🎨",
    "ux_review_complete": "🎨",
    "ux_issue_found": "⚠️",

    # Convergence events
    "convergence_update": "📊",
    "convergence_achieved": "🎉",

    # System events
    "system_ready": "✅",
    "system_error": "❌",

    # Documentation events
    "docs_generation_started": "📝",
    "docs_generated": "📝",

    # Docker events
    "docker_build_started": "🐳",
    "docker_build_succeeded": "🐳",
    "docker_build_failed": "❌",

    # Default
    "_default": "📌",
}


class ConsoleDashboard:
    """
    Real-time console output for generation progress.

    Subscribes to all events from the EventBus and displays them
    with formatted output and emoji icons.
    """

    def __init__(
        self,
        event_bus: "EventBus",
        show_debug: bool = False,
        show_timestamps: bool = True,
        compact_mode: bool = False,
    ):
        """
        Initialize the console dashboard.

        Args:
            event_bus: EventBus to subscribe to
            show_debug: Show debug-level events
            show_timestamps: Include timestamps in output
            compact_mode: Use compact single-line output
        """
        self.event_bus = event_bus
        self.show_debug = show_debug
        self.show_timestamps = show_timestamps
        self.compact_mode = compact_mode

        self._event_count = 0
        self._start_time = datetime.now()

        # Subscribe to all events
        self._subscribe_all()

        logger.info("console_dashboard_initialized")

    def _subscribe_all(self) -> None:
        """Subscribe to all events using wildcard subscription."""
        self.event_bus.subscribe_all(self._handle_event)

    def _handle_event(self, event: "Event") -> None:
        """
        Handle incoming event and display to console.

        Args:
            event: Event to display
        """
        self._event_count += 1

        # Get icon for event type
        event_type_value = event.type.value if hasattr(event.type, "value") else str(event.type)
        icon = EVENT_ICONS.get(event_type_value, EVENT_ICONS["_default"])

        # Build output line
        if self.compact_mode:
            line = self._format_compact(icon, event_type_value, event)
        else:
            line = self._format_full(icon, event_type_value, event)

        # Print to console
        print(line)

        # Print error message if present
        if event.error_message and not self.compact_mode:
            print(f"   ❌ Error: {event.error_message}")

    def _format_compact(self, icon: str, event_type: str, event: "Event") -> str:
        """Format event in compact single-line mode."""
        timestamp = ""
        if self.show_timestamps:
            timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] "

        success_marker = "✓" if event.success else "✗" if event.success is False else " "
        return f"{timestamp}{icon} {success_marker} [{event_type}] {event.source}"

    def _format_full(self, icon: str, event_type: str, event: "Event") -> str:
        """Format event in full multi-line mode."""
        lines = []

        # Header line
        timestamp = ""
        if self.show_timestamps:
            timestamp = f" @ {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"

        lines.append(f"{icon} [{event_type}] from {event.source}{timestamp}")

        # Add data summary if present
        if event.data:
            # Show first few key-value pairs
            data_preview = []
            for key, value in list(event.data.items())[:3]:
                if isinstance(value, (list, dict)):
                    value = f"<{type(value).__name__}:{len(value)}>"
                elif isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                data_preview.append(f"{key}={value}")

            if data_preview:
                lines.append(f"   {', '.join(data_preview)}")

        return "\n".join(lines)

    def print_summary(self) -> None:
        """Print a summary of events received."""
        duration = (datetime.now() - self._start_time).total_seconds()
        print("\n" + "=" * 60)
        print(f"📊 Console Dashboard Summary")
        print(f"   Events received: {self._event_count}")
        print(f"   Duration: {duration:.1f}s")
        print("=" * 60)

    def reset(self) -> None:
        """Reset event counter and start time."""
        self._event_count = 0
        self._start_time = datetime.now()


def create_dashboard(
    event_bus: "EventBus",
    verbose: bool = False,
) -> ConsoleDashboard:
    """
    Factory function to create a console dashboard.

    Args:
        event_bus: EventBus to subscribe to
        verbose: Enable verbose output (show debug, timestamps, full format)

    Returns:
        Configured ConsoleDashboard instance
    """
    return ConsoleDashboard(
        event_bus=event_bus,
        show_debug=verbose,
        show_timestamps=True,
        compact_mode=not verbose,
    )
