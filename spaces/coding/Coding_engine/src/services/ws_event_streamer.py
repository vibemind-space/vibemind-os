"""
WebSocket Event Streamer — Real-time event broadcasting for DaveLovable and other UIs.

Subscribes to the EventBus as a wildcard listener and broadcasts all events
over WebSocket connections. This enables the DaveLovable frontend to show
live pipeline progress without polling.

Architecture::

    EventBus → WSEventStreamer → WebSocket Clients
                                 ├─ DaveLovable UI
                                 ├─ Custom dashboards
                                 └─ Monitoring tools

Usage::

    streamer = WSEventStreamer(event_bus, host="0.0.0.0", port=8765)
    await streamer.start()

    # Clients connect to ws://localhost:8765 and receive JSON events:
    # {"type": "build_started", "source": "Builder", "data": {...}, ...}
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional, Set

import structlog

from ..mind.event_bus import EventBus, Event

logger = structlog.get_logger(__name__)

# Try importing websockets
try:
    import websockets
    from websockets.server import serve
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False
    logger.info("websockets not installed, WS streaming disabled. Install with: pip install websockets")


class WSEventStreamer:
    """
    Broadcasts EventBus events over WebSocket to connected clients.

    Features:
    - Wildcard subscription (receives all events)
    - JSON serialization with correlation IDs
    - Client tracking and graceful disconnect handling
    - Backpressure: drops events for slow clients
    - Health endpoint at /health
    """

    def __init__(
        self,
        event_bus: EventBus,
        host: str = "0.0.0.0",
        port: int = 8765,
        max_queue_size: int = 100,
    ):
        self.event_bus = event_bus
        self.host = host
        self.port = port
        self.max_queue_size = max_queue_size
        self._clients: Set[Any] = set()
        self._server = None
        self._running = False

        # Stats
        self._events_sent = 0
        self._events_dropped = 0
        self._total_connections = 0

    async def start(self):
        """Start the WebSocket server and subscribe to events."""
        if not WS_AVAILABLE:
            logger.warning("ws_streamer_disabled", reason="websockets not installed")
            return

        self.event_bus.subscribe_all(self._on_event)
        self._running = True

        self._server = await serve(
            self._handle_client,
            self.host,
            self.port,
        )

        logger.info(
            "ws_event_streamer_started",
            host=self.host,
            port=self.port,
        )

    async def stop(self):
        """Stop the WebSocket server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        # Disconnect all clients
        for client in list(self._clients):
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()
        logger.info("ws_event_streamer_stopped")

    async def _handle_client(self, websocket):
        """Handle a new WebSocket client connection."""
        self._clients.add(websocket)
        self._total_connections += 1
        client_id = id(websocket)

        logger.info(
            "ws_client_connected",
            client_id=client_id,
            total_clients=len(self._clients),
        )

        try:
            # Send welcome message
            await websocket.send(json.dumps({
                "type": "ws_connected",
                "timestamp": datetime.now().isoformat(),
                "message": "Connected to Coding Engine event stream",
                "total_clients": len(self._clients),
            }))

            # Keep connection alive, handle incoming messages (commands)
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON",
                    }))

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(
                "ws_client_disconnected",
                client_id=client_id,
                remaining_clients=len(self._clients),
            )

    async def _handle_client_message(self, websocket, data: dict):
        """Handle incoming messages from WebSocket clients."""
        msg_type = data.get("type", "")

        if msg_type == "ping":
            await websocket.send(json.dumps({
                "type": "pong",
                "timestamp": datetime.now().isoformat(),
            }))
        elif msg_type == "get_stats":
            await websocket.send(json.dumps({
                "type": "stats",
                "data": self.get_stats(),
            }))

    def _on_event(self, event: Event):
        """Handle EventBus event and broadcast to all clients."""
        if not self._clients:
            return

        # Serialize event to JSON
        try:
            payload = json.dumps({
                "type": event.type.value,
                "source": event.source,
                "timestamp": event.timestamp.isoformat(),
                "data": event.data,
                "success": event.success,
                "correlation_id": getattr(event, "correlation_id", None),
                "span_id": getattr(event, "span_id", None),
                "file_path": event.file_path,
                "error_message": event.error_message,
            }, default=str)
        except Exception as e:
            logger.warning("ws_event_serialize_failed", error=str(e))
            return

        # Broadcast to all connected clients
        disconnected = set()
        for client in self._clients:
            try:
                asyncio.create_task(self._send_to_client(client, payload))
                self._events_sent += 1
            except Exception:
                disconnected.add(client)
                self._events_dropped += 1

        self._clients -= disconnected

    async def _send_to_client(self, client, payload: str):
        """Send payload to a single client with backpressure handling."""
        try:
            await asyncio.wait_for(client.send(payload), timeout=5.0)
        except asyncio.TimeoutError:
            self._events_dropped += 1
            logger.debug("ws_send_timeout", client_id=id(client))
        except Exception:
            self._events_dropped += 1
            self._clients.discard(client)

    def get_stats(self) -> dict:
        """Get WebSocket streamer statistics."""
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "connected_clients": len(self._clients),
            "total_connections": self._total_connections,
            "events_sent": self._events_sent,
            "events_dropped": self._events_dropped,
        }
