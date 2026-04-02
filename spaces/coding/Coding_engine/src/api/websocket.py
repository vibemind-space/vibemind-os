"""
WebSocket Handler - Real-time streaming for Society of Mind events.

Provides:
1. Real-time event streaming from agents to UI
2. Convergence progress updates
3. Live file change notifications
4. Connection management for multiple clients
"""

import asyncio
import json
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import structlog
from fastapi import WebSocket, WebSocketDisconnect

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState, ConvergenceMetrics


logger = structlog.get_logger(__name__)


class WSMessageType(Enum):
    """WebSocket message types sent to clients."""
    # Connection
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    ERROR = "error"

    # Events
    EVENT = "event"
    AGENT_STATUS = "agent_status"

    # Progress
    CONVERGENCE_UPDATE = "convergence_update"
    PROGRESS = "progress"

    # Files
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"

    # Build/Test
    BUILD_STATUS = "build_status"
    TEST_RESULT = "test_result"
    VALIDATION_RESULT = "validation_result"

    # System
    SYSTEM_READY = "system_ready"
    SYSTEM_ERROR = "system_error"


@dataclass
class WSMessage:
    """WebSocket message structure."""
    type: WSMessageType
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps({
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
        })


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasting.

    Supports:
    - Multiple concurrent connections
    - Session-based subscriptions
    - Filtered event broadcasting
    """

    def __init__(self):
        # All active connections
        self.active_connections: dict[str, WebSocket] = {}

        # Session subscriptions: session_id -> set of event types
        self.subscriptions: dict[str, set[EventType]] = {}

        # Connection metadata
        self.connection_info: dict[str, dict] = {}

        self.logger = logger.bind(component="connection_manager")
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        async with self._lock:
            self.active_connections[client_id] = websocket
            self.connection_info[client_id] = {
                "connected_at": datetime.now(),
                "session_id": session_id,
                "message_count": 0,
            }

            # Subscribe to all events by default
            if session_id:
                self.subscriptions[session_id] = set(EventType)

        self.logger.info(
            "client_connected",
            client_id=client_id,
            session_id=session_id,
            total_connections=len(self.active_connections),
        )

        # Send welcome message
        await self.send_personal(
            client_id,
            WSMessage(
                type=WSMessageType.CONNECTED,
                data={
                    "client_id": client_id,
                    "session_id": session_id,
                    "message": "Connected to Society of Mind event stream",
                },
                session_id=session_id,
            ),
        )

    async def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]

            if client_id in self.connection_info:
                session_id = self.connection_info[client_id].get("session_id")
                del self.connection_info[client_id]

                # Clean up session subscription if no more connections
                if session_id:
                    session_has_connections = any(
                        info.get("session_id") == session_id
                        for info in self.connection_info.values()
                    )
                    if not session_has_connections and session_id in self.subscriptions:
                        del self.subscriptions[session_id]

        self.logger.info(
            "client_disconnected",
            client_id=client_id,
            total_connections=len(self.active_connections),
        )

    async def subscribe(
        self,
        session_id: str,
        event_types: list[EventType],
    ) -> None:
        """Subscribe a session to specific event types."""
        async with self._lock:
            if session_id not in self.subscriptions:
                self.subscriptions[session_id] = set()
            self.subscriptions[session_id].update(event_types)

        self.logger.debug(
            "session_subscribed",
            session_id=session_id,
            event_types=[e.value for e in event_types],
        )

    async def unsubscribe(
        self,
        session_id: str,
        event_types: list[EventType],
    ) -> None:
        """Unsubscribe a session from specific event types."""
        async with self._lock:
            if session_id in self.subscriptions:
                self.subscriptions[session_id] -= set(event_types)

    async def send_personal(
        self,
        client_id: str,
        message: WSMessage,
    ) -> bool:
        """Send a message to a specific client."""
        if client_id not in self.active_connections:
            return False

        try:
            websocket = self.active_connections[client_id]
            await websocket.send_text(message.to_json())

            if client_id in self.connection_info:
                self.connection_info[client_id]["message_count"] += 1

            return True
        except Exception as e:
            self.logger.error("send_failed", client_id=client_id, error=str(e))
            return False

    async def broadcast(
        self,
        message: WSMessage,
        session_id: Optional[str] = None,
    ) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast
            session_id: If provided, only broadcast to clients in this session

        Returns:
            Number of clients that received the message
        """
        sent_count = 0
        disconnected = []

        for client_id, websocket in self.active_connections.items():
            # Filter by session if specified
            if session_id:
                client_session = self.connection_info.get(client_id, {}).get("session_id")
                if client_session != session_id:
                    continue

            try:
                await websocket.send_text(message.to_json())
                sent_count += 1

                if client_id in self.connection_info:
                    self.connection_info[client_id]["message_count"] += 1

            except Exception:
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)

        return sent_count

    async def broadcast_event(
        self,
        event: Event,
        session_id: Optional[str] = None,
    ) -> int:
        """
        Broadcast an Event Bus event to subscribed clients.

        Filters by session subscriptions.
        """
        sent_count = 0
        disconnected = []

        for client_id, websocket in self.active_connections.items():
            client_info = self.connection_info.get(client_id, {})
            client_session = client_info.get("session_id")

            # Filter by session if specified
            if session_id and client_session != session_id:
                continue

            # Check subscription
            if client_session and client_session in self.subscriptions:
                if event.type not in self.subscriptions[client_session]:
                    continue

            # Send event
            try:
                message = WSMessage(
                    type=WSMessageType.EVENT,
                    data={
                        "event_type": event.type.value,
                        "source": event.source,
                        "data": event.data,
                        "file_path": event.file_path,
                        "error_message": event.error_message,
                        "success": event.success,
                        "timestamp": event.timestamp.isoformat(),
                    },
                    session_id=client_session,
                )
                await websocket.send_text(message.to_json())
                sent_count += 1

            except Exception:
                disconnected.append(client_id)

        for client_id in disconnected:
            await self.disconnect(client_id)

        return sent_count

    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self.active_connections),
            "sessions": len(self.subscriptions),
            "connections": [
                {
                    "client_id": cid,
                    "session_id": info.get("session_id"),
                    "connected_at": info.get("connected_at", datetime.now()).isoformat(),
                    "message_count": info.get("message_count", 0),
                }
                for cid, info in self.connection_info.items()
            ],
        }


class WebSocketBridge:
    """
    Bridge between Event Bus and WebSocket clients.

    Subscribes to all events and forwards them to connected clients.
    Also provides methods to push custom updates.
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        connection_manager: Optional[ConnectionManager] = None,
    ):
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.manager = connection_manager or ConnectionManager()
        self.logger = logger.bind(component="websocket_bridge")

        self._session_id: Optional[str] = None
        self._setup_complete = False

    def setup(self, session_id: Optional[str] = None) -> None:
        """
        Set up event bus subscriptions and state change handlers.

        Args:
            session_id: Optional session ID to filter broadcasts
        """
        if self._setup_complete:
            return

        self._session_id = session_id

        # Subscribe to all events for forwarding
        self.event_bus.add_websocket_handler(self._handle_event)

        # Subscribe to state changes
        self.shared_state.on_change(self._handle_state_change)

        self._setup_complete = True
        self.logger.info("bridge_setup_complete", session_id=session_id)

    async def _handle_event(self, event: Event) -> None:
        """Forward event bus events to WebSocket clients."""
        await self.manager.broadcast_event(event, self._session_id)

        # Send specialized messages for certain event types
        if event.type == EventType.FILE_CREATED:
            await self._send_file_update(event, WSMessageType.FILE_CREATED)
        elif event.type == EventType.FILE_MODIFIED:
            await self._send_file_update(event, WSMessageType.FILE_MODIFIED)
        elif event.type in (EventType.BUILD_STARTED, EventType.BUILD_COMPLETED, EventType.BUILD_FAILED):
            await self._send_build_status(event)
        elif event.type in (EventType.TEST_PASSED, EventType.TEST_FAILED, EventType.TESTS_COMPLETED):
            await self._send_test_result(event)

    async def _handle_state_change(self, metrics: ConvergenceMetrics) -> None:
        """Forward state changes to WebSocket clients."""
        message = WSMessage(
            type=WSMessageType.CONVERGENCE_UPDATE,
            data=metrics.to_dict(),
            session_id=self._session_id,
        )
        await self.manager.broadcast(message, self._session_id)

    async def _send_file_update(self, event: Event, msg_type: WSMessageType) -> None:
        """Send file update notification."""
        message = WSMessage(
            type=msg_type,
            data={
                "file_path": event.file_path,
                "source": event.source,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            },
            session_id=self._session_id,
        )
        await self.manager.broadcast(message, self._session_id)

    async def _send_build_status(self, event: Event) -> None:
        """Send build status update."""
        status = "running"
        if event.type == EventType.BUILD_COMPLETED:
            status = "success" if event.success else "failed"
        elif event.type == EventType.BUILD_FAILED:
            status = "failed"

        message = WSMessage(
            type=WSMessageType.BUILD_STATUS,
            data={
                "status": status,
                "success": event.success,
                "error": event.error_message,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            },
            session_id=self._session_id,
        )
        await self.manager.broadcast(message, self._session_id)

    async def _send_test_result(self, event: Event) -> None:
        """Send test result update."""
        message = WSMessage(
            type=WSMessageType.TEST_RESULT,
            data={
                "event_type": event.type.value,
                "success": event.success,
                "error": event.error_message,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            },
            session_id=self._session_id,
        )
        await self.manager.broadcast(message, self._session_id)

    async def send_progress(
        self,
        progress: float,
        phase: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        """
        Send progress update to clients.

        Args:
            progress: Progress percentage (0-100)
            phase: Current phase name
            message: Human-readable status message
            details: Optional additional details
        """
        ws_message = WSMessage(
            type=WSMessageType.PROGRESS,
            data={
                "progress": progress,
                "phase": phase,
                "message": message,
                "details": details or {},
            },
            session_id=self._session_id,
        )
        await self.manager.broadcast(ws_message, self._session_id)

    async def send_agent_status(
        self,
        agent_name: str,
        status: str,
        action: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """
        Send agent status update to clients.

        Args:
            agent_name: Name of the agent
            status: Status (idle, running, completed, error)
            action: Current action being performed
            details: Optional additional details
        """
        message = WSMessage(
            type=WSMessageType.AGENT_STATUS,
            data={
                "agent": agent_name,
                "status": status,
                "action": action,
                "details": details or {},
            },
            session_id=self._session_id,
        )
        await self.manager.broadcast(message, self._session_id)


# Global connection manager instance
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the global connection manager."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager


async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    session_id: Optional[str] = None,
) -> None:
    """
    WebSocket endpoint handler.

    Args:
        websocket: FastAPI WebSocket
        client_id: Unique client identifier
        session_id: Optional session to subscribe to
    """
    manager = get_connection_manager()
    await manager.connect(websocket, client_id, session_id)

    try:
        while True:
            # Wait for incoming messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                msg_type = message.get("type")

                # Handle subscription requests
                if msg_type == "subscribe":
                    event_types = [
                        EventType(et) for et in message.get("event_types", [])
                        if et in [e.value for e in EventType]
                    ]
                    if session_id:
                        await manager.subscribe(session_id, event_types)
                        await manager.send_personal(
                            client_id,
                            WSMessage(
                                type=WSMessageType.SUBSCRIBED,
                                data={"event_types": [e.value for e in event_types]},
                            ),
                        )

                elif msg_type == "unsubscribe":
                    event_types = [
                        EventType(et) for et in message.get("event_types", [])
                        if et in [e.value for e in EventType]
                    ]
                    if session_id:
                        await manager.unsubscribe(session_id, event_types)
                        await manager.send_personal(
                            client_id,
                            WSMessage(
                                type=WSMessageType.UNSUBSCRIBED,
                                data={"event_types": [e.value for e in event_types]},
                            ),
                        )

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

            except json.JSONDecodeError:
                await manager.send_personal(
                    client_id,
                    WSMessage(
                        type=WSMessageType.ERROR,
                        data={"message": "Invalid JSON"},
                    ),
                )

    except WebSocketDisconnect:
        await manager.disconnect(client_id)
