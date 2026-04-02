"""
WebSocket handler for real-time dashboard updates.
Provides real-time event streaming with <200ms latency requirement.
"""

import asyncio
import time
from datetime import datetime
from typing import Set, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dashboard_models import RealtimeUpdate
from src.services.dashboard_service import DashboardService
from src.models.base import get_db
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard-websocket"])


class DashboardConnectionManager:
    """
    Manages WebSocket connections for real-time dashboard updates.

    Handles connection lifecycle, subscriptions, and event broadcasting
    with latency tracking to meet REQ-ea7004-017 (<200ms latency).
    """

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.subscriptions: Dict[str, Set[str]] = {}
        self.connection_timestamps: Dict[str, datetime] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """
        Accept new WebSocket connection.

        Args:
            websocket: WebSocket instance
            client_id: Unique client identifier
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.subscriptions[client_id] = set()
        self.connection_timestamps[client_id] = datetime.utcnow()

        logger.info(
            "dashboard_websocket_connected",
            client_id=client_id,
            total_connections=len(self.active_connections)
        )

    def disconnect(self, client_id: str) -> None:
        """
        Remove WebSocket connection.

        Args:
            client_id: Client identifier to disconnect
        """
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
        if client_id in self.connection_timestamps:
            del self.connection_timestamps[client_id]

        logger.info(
            "dashboard_websocket_disconnected",
            client_id=client_id,
            total_connections=len(self.active_connections)
        )

    def subscribe(self, client_id: str, update_types: Set[str]) -> None:
        """
        Subscribe client to specific update types.

        Args:
            client_id: Client identifier
            update_types: Set of update types to subscribe to
        """
        if client_id in self.subscriptions:
            self.subscriptions[client_id].update(update_types)

            logger.debug(
                "client_subscribed",
                client_id=client_id,
                update_types=list(update_types),
                total_subscriptions=len(self.subscriptions[client_id])
            )

    def unsubscribe(self, client_id: str, update_types: Set[str]) -> None:
        """
        Unsubscribe client from specific update types.

        Args:
            client_id: Client identifier
            update_types: Set of update types to unsubscribe from
        """
        if client_id in self.subscriptions:
            self.subscriptions[client_id].difference_update(update_types)

            logger.debug(
                "client_unsubscribed",
                client_id=client_id,
                update_types=list(update_types),
                remaining_subscriptions=len(self.subscriptions[client_id])
            )

    async def send_personal(self, client_id: str, message: dict) -> None:
        """
        Send message to specific client.

        Args:
            client_id: Target client identifier
            message: Message dictionary to send
        """
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(
                    "failed_to_send_personal_message",
                    client_id=client_id,
                    error=str(e)
                )
                self.disconnect(client_id)

    async def broadcast(
        self,
        message: dict,
        update_type: str = None,
        exclude_client: str = None
    ) -> int:
        """
        Broadcast message to all or filtered clients.

        Args:
            message: Message dictionary to broadcast
            update_type: Optional update type for subscription filtering
            exclude_client: Optional client ID to exclude from broadcast

        Returns:
            Number of clients message was sent to
        """
        sent_count = 0
        disconnected_clients = []

        for client_id, websocket in self.active_connections.items():
            # Skip excluded client
            if client_id == exclude_client:
                continue

            # Check subscription filter
            if update_type and update_type not in self.subscriptions.get(client_id, set()):
                continue

            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.error(
                    "failed_to_broadcast_message",
                    client_id=client_id,
                    error=str(e)
                )
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

        return sent_count

    async def broadcast_event(
        self,
        update_type: str,
        data: Dict[str, Any],
        event_timestamp: datetime = None
    ) -> Dict[str, Any]:
        """
        Broadcast real-time event with latency tracking.

        Tracks latency from event occurrence to UI update to meet
        REQ-ea7004-017 (<200ms latency requirement).

        Args:
            update_type: Type of update (event, metrics, process_change)
            data: Event data payload
            event_timestamp: Original event timestamp (for latency calculation)

        Returns:
            Broadcast statistics
        """
        broadcast_start = time.perf_counter()
        current_time = datetime.utcnow()

        # Calculate latency if event timestamp provided
        latency_ms = 0.0
        if event_timestamp:
            latency = current_time - event_timestamp
            latency_ms = latency.total_seconds() * 1000

        # Create real-time update message
        update = RealtimeUpdate(
            update_type=update_type,
            timestamp=current_time,
            latency_ms=latency_ms,
            data=data
        )

        # Broadcast to subscribed clients
        sent_count = await self.broadcast(
            message=update.model_dump(mode="json"),
            update_type=update_type
        )

        broadcast_end = time.perf_counter()
        broadcast_time_ms = (broadcast_end - broadcast_start) * 1000

        # Log if latency exceeds SLA
        if latency_ms > 200:
            logger.warning(
                "dashboard_latency_exceeded",
                latency_ms=latency_ms,
                update_type=update_type,
                sla_threshold_ms=200
            )
        else:
            logger.debug(
                "dashboard_event_broadcasted",
                update_type=update_type,
                latency_ms=latency_ms,
                broadcast_time_ms=broadcast_time_ms,
                sent_count=sent_count
            )

        return {
            "update_type": update_type,
            "latency_ms": latency_ms,
            "broadcast_time_ms": broadcast_time_ms,
            "sent_count": sent_count,
            "meets_sla": latency_ms < 200
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get connection manager statistics.

        Returns:
            Dictionary with connection stats
        """
        return {
            "active_connections": len(self.active_connections),
            "total_subscriptions": sum(len(subs) for subs in self.subscriptions.values()),
            "connection_ids": list(self.active_connections.keys())
        }


# Global connection manager instance
dashboard_manager = DashboardConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Provides real-time streaming of:
    - Connection events
    - Process metrics updates
    - System metrics updates

    **REQ-ea7004-017**: Updates with <200ms latency from backend event to UI.

    Protocol:
        Client -> Server:
            {"type": "subscribe", "update_types": ["event", "metrics", "process_change"]}
            {"type": "unsubscribe", "update_types": ["metrics"]}
            {"type": "ping"}

        Server -> Client:
            {"type": "connected", "client_id": "...", "timestamp": "..."}
            {"update_type": "event", "timestamp": "...", "latency_ms": 45.2, "data": {...}}
            {"type": "pong", "timestamp": "..."}
    """
    # Generate client ID
    import uuid
    client_id = str(uuid.uuid4())

    # Accept connection
    await dashboard_manager.connect(websocket, client_id)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat(),
            "available_updates": ["event", "metrics", "process_change"]
        })

        # Handle incoming messages
        while True:
            try:
                message = await websocket.receive_json()
                message_type = message.get("type")

                if message_type == "subscribe":
                    update_types = set(message.get("update_types", []))
                    dashboard_manager.subscribe(client_id, update_types)
                    await websocket.send_json({
                        "type": "subscribed",
                        "update_types": list(update_types),
                        "timestamp": datetime.utcnow().isoformat()
                    })

                elif message_type == "unsubscribe":
                    update_types = set(message.get("update_types", []))
                    dashboard_manager.unsubscribe(client_id, update_types)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "update_types": list(update_types),
                        "timestamp": datetime.utcnow().isoformat()
                    })

                elif message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })

                else:
                    logger.warning(
                        "unknown_websocket_message_type",
                        client_id=client_id,
                        message_type=message_type
                    )
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message_type}",
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except Exception as e:
                logger.error(
                    "websocket_message_handling_error",
                    client_id=client_id,
                    error=str(e)
                )
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error handling message: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        logger.info("websocket_client_disconnected", client_id=client_id)
        dashboard_manager.disconnect(client_id)

    except Exception as e:
        logger.error(
            "websocket_connection_error",
            client_id=client_id,
            error=str(e)
        )
        dashboard_manager.disconnect(client_id)


@router.get("/ws/stats")
async def get_websocket_stats() -> Dict[str, Any]:
    """
    Get WebSocket connection statistics.

    Returns:
        Connection manager statistics
    """
    return dashboard_manager.get_stats()


# Export connection manager for use by other modules
__all__ = ["router", "dashboard_manager", "DashboardConnectionManager"]
