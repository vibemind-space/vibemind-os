"""
EventBus integration for dashboard event tracking.
Subscribes to relevant events and forwards them to dashboard clients.
"""

import asyncio
from datetime import datetime
from typing import Optional, Callable, Any
from sqlalchemy.ext.asyncio import AsyncSession

from src.mind.event_bus import EventBus, Event, EventType
from src.services.dashboard_service import DashboardService
from src.models.connection_event import ConnectionEvent
import structlog

logger = structlog.get_logger(__name__)


class DashboardEventTracker:
    """
    Tracks EventBus events and forwards them to dashboard.

    Subscribes to connection-related events from the EventBus and:
    1. Stores them in the database via DashboardService
    2. Broadcasts them to WebSocket clients via connection manager
    3. Tracks latency to meet <200ms SLA requirement
    """

    # Event types relevant to connection monitoring
    MONITORED_EVENT_TYPES = {
        # Process events
        EventType.AGENT_STARTED,
        EventType.AGENT_COMPLETED,
        EventType.AGENT_ERROR,

        # Build events
        EventType.BUILD_STARTED,
        EventType.BUILD_SUCCEEDED,
        EventType.BUILD_FAILED,

        # Test events
        EventType.TEST_STARTED,
        EventType.TEST_PASSED,
        EventType.TEST_FAILED,
        EventType.E2E_TEST_STARTED,
        EventType.E2E_TEST_PASSED,
        EventType.E2E_TEST_FAILED,

        # Deployment events
        EventType.DEPLOY_STARTED,
        EventType.DEPLOY_SUCCEEDED,
        EventType.DEPLOY_FAILED,

        # Sandbox events
        EventType.SANDBOX_TEST_STARTED,
        EventType.SANDBOX_TEST_PASSED,
        EventType.SANDBOX_TEST_FAILED,

        # System events
        EventType.PREVIEW_READY,
        EventType.SYSTEM_READY,
        EventType.SYSTEM_ERROR,

        # CLI events (Claude Code interactions)
        EventType.CLI_PROMPT_SENT,
        EventType.CLI_RESPONSE_RECEIVED,
        EventType.CLI_CALL_ERROR,

        # App lifecycle
        EventType.APP_LAUNCHED,
        EventType.APP_CRASHED,

        # Task progress events (Epic Orchestrator)
        EventType.TASK_PROGRESS_UPDATE,
        EventType.GENERATION_COMPLETE,
        EventType.CONVERGENCE_UPDATE,
    }

    def __init__(
        self,
        event_bus: EventBus,
        db_session_factory: Callable[[], AsyncSession],
        websocket_broadcast_callback: Optional[Callable[[str, dict, datetime], Any]] = None
    ):
        """
        Initialize dashboard event tracker.

        Args:
            event_bus: EventBus instance to subscribe to
            db_session_factory: Factory function to create database sessions
            websocket_broadcast_callback: Optional callback for WebSocket broadcasting
        """
        self.event_bus = event_bus
        self.db_session_factory = db_session_factory
        self.websocket_broadcast_callback = websocket_broadcast_callback
        self._is_running = False

    def start(self) -> None:
        """Start tracking events from EventBus."""
        if self._is_running:
            logger.warning("dashboard_event_tracker_already_running")
            return

        # Subscribe to monitored event types
        for event_type in self.MONITORED_EVENT_TYPES:
            self.event_bus.subscribe(event_type, self._handle_event)

        self._is_running = True

        logger.info(
            "dashboard_event_tracker_started",
            monitored_event_types=len(self.MONITORED_EVENT_TYPES)
        )

    def stop(self) -> None:
        """Stop tracking events."""
        self._is_running = False
        logger.info("dashboard_event_tracker_stopped")

    async def _handle_event(self, event: Event) -> None:
        """
        Handle incoming event from EventBus.

        Stores event in database and broadcasts to WebSocket clients.

        Args:
            event: Event from EventBus
        """
        try:
            event_timestamp = event.timestamp
            processing_start = datetime.utcnow()

            # Convert Event to dict for processing
            event_dict = event.to_dict()

            # Store in database (async)
            await self._store_event(event_dict)

            # Broadcast to WebSocket clients
            if self.websocket_broadcast_callback:
                await self._broadcast_event(event_dict, event_timestamp)

            # Log latency
            processing_end = datetime.utcnow()
            latency = (processing_end - event_timestamp).total_seconds() * 1000

            if latency > 200:
                logger.warning(
                    "dashboard_event_processing_latency_exceeded",
                    event_type=event.type.value,
                    latency_ms=latency,
                    sla_threshold_ms=200
                )
            else:
                logger.debug(
                    "dashboard_event_processed",
                    event_type=event.type.value,
                    latency_ms=latency
                )

        except Exception as e:
            logger.error(
                "dashboard_event_processing_failed",
                event_type=event.type.value if hasattr(event, 'type') else 'unknown',
                error=str(e)
            )

    async def _store_event(self, event_dict: dict) -> None:
        """
        Store event in database.

        Args:
            event_dict: Event dictionary
        """
        try:
            # Create database session
            async with self.db_session_factory() as session:
                service = DashboardService(session)

                # Convert and store event
                await service.record_event_from_dict(event_dict)

                logger.debug(
                    "dashboard_event_stored",
                    event_type=event_dict.get("type"),
                    source=event_dict.get("source")
                )

        except Exception as e:
            logger.error(
                "failed_to_store_dashboard_event",
                event_type=event_dict.get("type"),
                error=str(e)
            )

    async def _broadcast_event(self, event_dict: dict, event_timestamp: datetime) -> None:
        """
        Broadcast event to WebSocket clients.

        Args:
            event_dict: Event dictionary
            event_timestamp: Original event timestamp
        """
        if not self.websocket_broadcast_callback:
            return

        try:
            # Prepare event data for WebSocket
            event_data = {
                "event_type": event_dict.get("type"),
                "timestamp": event_timestamp.isoformat(),
                "source": event_dict.get("source"),
                "success": event_dict.get("success", True),
                "message": event_dict.get("data", {}).get("message"),
                "details": event_dict.get("data", {})
            }

            # Call WebSocket broadcast callback
            await self.websocket_broadcast_callback(
                "event",  # update_type
                event_data,
                event_timestamp
            )

        except Exception as e:
            logger.error(
                "failed_to_broadcast_dashboard_event",
                event_type=event_dict.get("type"),
                error=str(e)
            )

    async def track_process_change(
        self,
        process_id: int,
        process_name: str,
        change_type: str,
        details: Optional[dict] = None
    ) -> None:
        """
        Manually track a process change event.

        Args:
            process_id: Process ID
            process_name: Process name
            change_type: Type of change (started, stopped, crashed)
            details: Additional details
        """
        try:
            event_dict = {
                "type": f"PROCESS_{change_type.upper()}",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "process_monitor",
                "success": True,
                "data": {
                    "process_id": process_id,
                    "process_name": process_name,
                    "message": f"Process {process_name} (PID: {process_id}) {change_type}",
                    **(details or {})
                }
            }

            await self._handle_event_dict(event_dict)

        except Exception as e:
            logger.error(
                "failed_to_track_process_change",
                process_id=process_id,
                change_type=change_type,
                error=str(e)
            )

    async def track_connection_change(
        self,
        port: int,
        protocol: str,
        change_type: str,
        process_id: Optional[int] = None,
        process_name: Optional[str] = None,
        details: Optional[dict] = None
    ) -> None:
        """
        Manually track a connection change event.

        Args:
            port: Port number
            protocol: Protocol (TCP/UDP)
            change_type: Type of change (opened, closed, established)
            process_id: Optional process ID
            process_name: Optional process name
            details: Additional details
        """
        try:
            event_dict = {
                "type": f"CONNECTION_{change_type.upper()}",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "connection_monitor",
                "success": True,
                "data": {
                    "port": port,
                    "protocol": protocol,
                    "process_id": process_id,
                    "process_name": process_name,
                    "message": f"Port {port} ({protocol}) {change_type}",
                    **(details or {})
                }
            }

            await self._handle_event_dict(event_dict)

        except Exception as e:
            logger.error(
                "failed_to_track_connection_change",
                port=port,
                change_type=change_type,
                error=str(e)
            )

    async def _handle_event_dict(self, event_dict: dict) -> None:
        """
        Handle event from dictionary (for manual tracking).

        Args:
            event_dict: Event dictionary
        """
        event_timestamp = datetime.fromisoformat(event_dict["timestamp"])

        # Store in database
        await self._store_event(event_dict)

        # Broadcast to WebSocket clients
        if self.websocket_broadcast_callback:
            await self._broadcast_event(event_dict, event_timestamp)


def create_dashboard_event_tracker(
    event_bus: EventBus,
    db_session_factory: Callable[[], AsyncSession],
    dashboard_manager: Any = None
) -> DashboardEventTracker:
    """
    Factory function to create and start dashboard event tracker.

    Args:
        event_bus: EventBus instance
        db_session_factory: Factory to create database sessions
        dashboard_manager: Optional DashboardConnectionManager instance

    Returns:
        Initialized and started DashboardEventTracker
    """
    # Create WebSocket broadcast callback if manager provided
    websocket_callback = None
    if dashboard_manager:
        async def broadcast_callback(update_type: str, data: dict, timestamp: datetime):
            await dashboard_manager.broadcast_event(update_type, data, timestamp)

        websocket_callback = broadcast_callback

    # Create tracker
    tracker = DashboardEventTracker(
        event_bus=event_bus,
        db_session_factory=db_session_factory,
        websocket_broadcast_callback=websocket_callback
    )

    # Start tracking
    tracker.start()

    logger.info("dashboard_event_tracker_created_and_started")

    return tracker
