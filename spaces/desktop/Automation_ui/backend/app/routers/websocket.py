"""WebSocket Router for Live Desktop Streaming

Provides WebSocket endpoints for real-time desktop streaming,
workflow automation, and filesystem bridge communication.
"""

import asyncio
import base64
import json
from datetime import datetime
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..logger_config import get_logger

logger = get_logger("websocket_router")

# Define router without prefix (prefix added in main.py)
router = APIRouter(tags=["WebSocket"])

# Track which clients are streaming desktop frames
desktop_stream_subscribers: Dict[str, Set[str]] = (
    {}
)  # desktop_client_id -> set of viewer_client_ids


class ConnectionManager:
    """Manages WebSocket connections for live desktop streaming"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_info: Dict[str, Dict] = {}

    async def connect(
        self, websocket: WebSocket, client_id: str, client_info_data: Dict
    ):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.client_info[client_id] = client_info_data
        logger.info(
            f"✅ Client connected: {client_id} ({client_info_data.get('clientType', 'unknown')})"
        )

    def disconnect(self, client_id: str):
        """Remove WebSocket connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.client_info:
            del self.client_info[client_id]
        logger.info(f"🔌 Client disconnected: {client_id}")

    async def send_personal_message(self, message: str, client_id: str):
        """Send message to specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
            except Exception as e:
                logger.error(f"❌ Failed to send message to {client_id}: {e}")
                self.disconnect(client_id)

    async def send_binary_message(self, data: bytes, client_id: str):
        """Send binary data to specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_bytes(data)
            except Exception as e:
                logger.error(f"❌ Failed to send binary data to {client_id}: {e}")
                self.disconnect(client_id)

    async def broadcast(self, message: str, exclude_client: str = None):
        """Broadcast message to all connected clients"""
        disconnected_clients = []

        for client_id, connection in self.active_connections.items():
            if client_id != exclude_client:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"❌ Broadcast failed to {client_id}: {e}")
                    disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)

    def get_client_list(self) -> list:
        """Get list of connected client IDs"""
        return list(self.client_info.keys())


# Global connection manager
manager = ConnectionManager()


@router.websocket("/live-desktop")
async def websocket_live_desktop(websocket: WebSocket):
    """Main WebSocket endpoint for live desktop streaming"""
    client_id = None

    try:
        # Accept WebSocket connection first
        await websocket.accept()
        logger.info("🤝 WebSocket connection accepted, waiting for handshake...")

        # Get desktop service from app state through websocket scope
        desktop_service = None
        try:
            app = websocket.scope.get("app")
            if app and hasattr(app, "state") and hasattr(app.state, "service_manager"):
                service_manager = app.state.service_manager
                desktop_service = service_manager.get_service("live_desktop")
                logger.info(
                    f"✅ Desktop service retrieved: {desktop_service is not None}"
                )
            else:
                logger.warning("⚠️ Service manager not available in app state")
        except Exception as e:
            logger.error(f"❌ Failed to get desktop service: {e}")

        # Receive handshake with timeout
        try:
            handshake_data = await asyncio.wait_for(
                websocket.receive_text(), timeout=10.0
            )
            handshake = json.loads(handshake_data)
        except asyncio.TimeoutError:
            await websocket.close(code=4000, reason="Handshake timeout")
            logger.warning("⏰ Handshake timeout")
            return
        except json.JSONDecodeError:
            await websocket.close(code=4000, reason="Invalid handshake JSON")
            logger.warning("❌ Invalid handshake JSON")
            return

        if handshake.get("type") != "handshake":
            await websocket.close(code=4000, reason="Invalid handshake type")
            logger.warning(f"❌ Invalid handshake type: {handshake.get('type')}")
            return

        client_info_data = handshake.get("clientInfo", {})
        client_id = client_info_data.get("clientId", f"client_{id(websocket)}")
        client_type = client_info_data.get("clientType", "unknown")

        # Register connection (without accepting again)
        manager.active_connections[client_id] = websocket
        manager.client_info[client_id] = client_info_data
        logger.info(f"✅ Client connected: {client_id} ({client_type})")

        # Send handshake confirmation
        handshake_response = {
            "type": "handshake_ack",
            "clientId": client_id,
            "status": "connected",
            "timestamp": datetime.now().isoformat(),
            "serverCapabilities": [
                "desktop_stream",
                "workflow_data",
                "file_operations",
                "screenshot_capture",
                "automation_triggers",
                "multi_desktop_clients",
                "task_queue",  # Voice → MCP task events
            ],
        }

        await websocket.send_text(json.dumps(handshake_response))
        logger.info(f"✅ Handshake completed for {client_id} ({client_type})")

        # Handle messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                await handle_websocket_message(
                    websocket, client_id, message, desktop_service
                )

            except json.JSONDecodeError:
                logger.warning(f"⚠️ Invalid JSON from client {client_id}")
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Invalid JSON format"})
                )

    except WebSocketDisconnect:
        logger.info(f"🔌 Client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"❌ WebSocket error for client {client_id}: {e}")
    finally:
        if client_id:
            # Stop streaming for this client and cleanup
            if desktop_service:
                try:
                    await desktop_service.stop_streaming(client_id)
                    logger.info(
                        f"🛑 Streaming stopped for disconnected client {client_id}"
                    )
                except Exception as e:
                    logger.error(f"❌ Error stopping streaming for {client_id}: {e}")
            manager.disconnect(client_id)


async def handle_websocket_message(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service=None
):
    """Handle incoming WebSocket messages"""
    message_type = message.get("type")

    try:
        if message_type == "ping":
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "pong",
                        "timestamp": message.get(
                            "timestamp", datetime.now().isoformat()
                        ),
                    }
                )
            )

        elif message_type == "frame_data":
            await handle_frame_data(websocket, client_id, message, desktop_service)

        elif message_type == "get_commands":
            await handle_get_commands(websocket, client_id, message)

        elif message_type == "client_heartbeat":
            await handle_client_heartbeat(websocket, client_id, message)

        elif message_type == "get_desktop_clients":
            await handle_get_desktop_clients(
                websocket, client_id, message, desktop_service
            )

        elif message_type == "subscribe_workflow_execution":
            await handle_subscribe_workflow_execution(websocket, client_id, message)

        elif message_type == "unsubscribe_workflow_execution":
            await handle_unsubscribe_workflow_execution(websocket, client_id, message)

        elif (
            message_type == "request_desktop_stream"
            or message_type == "start_desktop_stream"
        ):
            await handle_stream_request(websocket, client_id, message, desktop_service)

        elif message_type == "start_stream":
            # Handle start_stream from web client - subscribe to desktop client's stream
            await handle_start_stream(websocket, client_id, message)

        elif message_type == "stop_desktop_stream":
            await handle_stream_stop(websocket, client_id, message, desktop_service)

        elif message_type == "subscribe_desktop_stream":
            await handle_subscribe_desktop_stream(websocket, client_id, message)

        elif message_type == "unsubscribe_desktop_stream":
            await handle_unsubscribe_desktop_stream(websocket, client_id, message)

        elif message_type == "configure_stream":
            await handle_stream_config(websocket, client_id, message, desktop_service)

        elif message_type == "request_screenshot":
            await handle_screenshot_request(
                websocket, client_id, message, desktop_service
            )

        elif message_type == "workflow_data":
            await handle_workflow_data(client_id, message.get("data", {}))

        elif message_type == "filesystem_operation":
            await handle_filesystem_operation(websocket, client_id, message)

        elif message_type == "mcp_call":
            await handle_mcp_call(websocket, client_id, message)

        # Task Queue subscriptions
        elif message_type == "subscribe_task_queue":
            await handle_subscribe_task_queue(websocket, client_id, message)

        elif message_type == "unsubscribe_task_queue":
            await handle_unsubscribe_task_queue(websocket, client_id, message)

        elif message_type == "get_task_queue_status":
            status = await get_task_queue_status()
            await websocket.send_text(json.dumps({
                "type": "task_queue_status",
                "status": status,
                "timestamp": datetime.now().isoformat()
            }))

        elif message_type == "action_ack":
            # ACK from desktop client for a delegated action (remote mode)
            from ..services.action_router import action_router
            command_id = message.get("commandId", "")
            ack_result = {
                "success": message.get("success", False),
                "result": message.get("result", {}),
                "executionTimeMs": message.get("executionTimeMs", 0),
            }
            resolved = action_router.handle_ack(command_id, ack_result)
            if resolved:
                logger.info(f"Action ACK resolved: {command_id} (success={ack_result['success']})")

        else:
            logger.warning(f"⚠️ Unknown message type from {client_id}: {message_type}")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Unknown message type: {message_type}",
                    }
                )
            )

    except Exception as e:
        logger.error(f"❌ Error handling message from {client_id}: {e}")
        await websocket.send_text(
            json.dumps(
                {"type": "error", "message": f"Message handling error: {str(e)}"}
            )
        )


async def handle_frame_data(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service=None
):
    """Handle incoming desktop frame from Desktop Capture Client

    Receives frame data from the desktop client and broadcasts it to:
    1. Frontend viewers who subscribed to this desktop stream
    2. AutoGen agents who need the frames for analysis
    """
    frame_data = message.get("frameData")
    frame_number = message.get("frameNumber", 0)
    monitor_id = message.get("monitorId", "monitor_0")
    metadata = message.get("metadata", {})

    if not frame_data:
        return

    # Store frame in StreamFrameCache for MCP tools (vision_analyze, handoff_read_screen)
    try:
        import sys
        import os
        moire_agents_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "moire_agents"
        )
        if moire_agents_path not in sys.path:
            sys.path.insert(0, moire_agents_path)

        from stream_frame_cache import StreamFrameCache
        monitor_num = int(monitor_id.replace("monitor_", "")) if isinstance(monitor_id, str) else monitor_id
        StreamFrameCache.update_frame(
            monitor_id=monitor_num,
            frame_base64=frame_data,
            metadata=metadata
        )
        logger.debug(f"📦 Frame cached for monitor {monitor_num}")
    except Exception as cache_error:
        logger.debug(f"⚠️ Cache update failed: {cache_error}")

    # Create frame message for subscribers - use 'frame_data' type to match frontend expectation
    frame_message = json.dumps(
        {
            "type": "frame_data",
            "desktopClientId": client_id,
            "clientId": client_id,
            "frameData": frame_data,
            "frameNumber": frame_number,
            "monitorId": monitor_id,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Track that this client is a desktop source
    if client_id not in desktop_stream_subscribers:
        desktop_stream_subscribers[client_id] = set()
        logger.info(f"📺 New desktop stream source registered: {client_id}")

    # Broadcast to all subscribers of this desktop client
    subscribers = desktop_stream_subscribers.get(client_id, set())
    disconnected = []

    for viewer_id in subscribers:
        if viewer_id in manager.active_connections:
            try:
                await manager.active_connections[viewer_id].send_text(frame_message)
            except Exception as e:
                logger.debug(f"Failed to send frame to {viewer_id}: {e}")
                disconnected.append(viewer_id)
        else:
            disconnected.append(viewer_id)

    # Clean up disconnected viewers
    for viewer_id in disconnected:
        desktop_stream_subscribers[client_id].discard(viewer_id)

    # Also broadcast to autogen_agent clients
    for other_client_id, info in manager.client_info.items():
        if other_client_id != client_id and info.get("clientType") == "autogen_agent":
            if other_client_id in manager.active_connections:
                try:
                    await manager.active_connections[other_client_id].send_text(
                        frame_message
                    )
                except Exception:
                    pass


async def handle_get_commands(websocket: WebSocket, client_id: str, message: Dict):
    """Handle command poll from Desktop Client

    Desktop clients periodically poll for pending commands.
    Returns empty list for now - commands are sent proactively.
    """
    # TODO: Implement command queue if needed
    await websocket.send_text(
        json.dumps(
            {
                "type": "commands",
                "commands": [],
                "timestamp": datetime.now().isoformat(),
            }
        )
    )


async def handle_client_heartbeat(websocket: WebSocket, client_id: str, message: Dict):
    """Handle heartbeat from Desktop Client over WebSocket

    This is a backup heartbeat in addition to the HTTP heartbeat.
    """
    stats = message.get("stats", {})

    # Update client info with latest stats
    if client_id in manager.client_info:
        manager.client_info[client_id]["lastHeartbeat"] = datetime.now().isoformat()
        manager.client_info[client_id]["stats"] = stats

    # Send acknowledgment
    await websocket.send_text(
        json.dumps(
            {
                "type": "heartbeat_ack",
                "clientId": client_id,
                "timestamp": datetime.now().isoformat(),
            }
        )
    )


async def handle_subscribe_desktop_stream(
    websocket: WebSocket, client_id: str, message: Dict
):
    """Subscribe to receive desktop frames from a specific desktop client"""
    desktop_client_id = message.get("desktopClientId")

    if not desktop_client_id:
        # Subscribe to all available desktop streams
        for dc_id in desktop_stream_subscribers.keys():
            desktop_stream_subscribers[dc_id].add(client_id)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "desktop_stream_subscribed",
                    "desktopClientId": "all",
                    "availableStreams": list(desktop_stream_subscribers.keys()),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
    else:
        if desktop_client_id not in desktop_stream_subscribers:
            desktop_stream_subscribers[desktop_client_id] = set()

        desktop_stream_subscribers[desktop_client_id].add(client_id)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "desktop_stream_subscribed",
                    "desktopClientId": desktop_client_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    logger.info(
        f"📺 Client {client_id} subscribed to desktop stream from {desktop_client_id or 'all'}"
    )


async def handle_unsubscribe_desktop_stream(
    websocket: WebSocket, client_id: str, message: Dict
):
    """Unsubscribe from desktop stream"""
    desktop_client_id = message.get("desktopClientId")

    if desktop_client_id:
        if desktop_client_id in desktop_stream_subscribers:
            desktop_stream_subscribers[desktop_client_id].discard(client_id)
    else:
        # Unsubscribe from all
        for subscribers in desktop_stream_subscribers.values():
            subscribers.discard(client_id)

    await websocket.send_text(
        json.dumps(
            {
                "type": "desktop_stream_unsubscribed",
                "desktopClientId": desktop_client_id or "all",
                "timestamp": datetime.now().isoformat(),
            }
        )
    )

    logger.info(f"📺 Client {client_id} unsubscribed from desktop stream")


async def handle_start_stream(websocket: WebSocket, client_id: str, message: Dict):
    """Handle start_stream request from web client

    Subscribes the web client to receive frames from a specific desktop client.
    The desktop client should already be sending frames - we just subscribe to them.
    """
    desktop_client_id = message.get("desktop_client_id") or message.get(
        "desktopClientId"
    )
    monitor_id = message.get("monitor_id", 0)

    if not desktop_client_id:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "stream_error",
                    "error": "Missing desktop_client_id",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        return

    # Subscribe this web client to the desktop client's stream
    if desktop_client_id not in desktop_stream_subscribers:
        desktop_stream_subscribers[desktop_client_id] = set()

    desktop_stream_subscribers[desktop_client_id].add(client_id)

    # Send confirmation
    await websocket.send_text(
        json.dumps(
            {
                "type": "stream_started",
                "desktop_client_id": desktop_client_id,
                "monitor_id": monitor_id,
                "timestamp": datetime.now().isoformat(),
            }
        )
    )

    logger.info(
        f"🎬 Web client {client_id} subscribed to stream from desktop client {desktop_client_id}"
    )

    # If the desktop client is connected, notify it to start capturing (if not already)
    if desktop_client_id in manager.active_connections:
        try:
            await manager.active_connections[desktop_client_id].send_text(
                json.dumps(
                    {
                        "type": "start_capture",
                        "monitor_id": monitor_id,
                        "requestedBy": client_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            )
            logger.info(f"📤 Sent start_capture to desktop client {desktop_client_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send start_capture to {desktop_client_id}: {e}")


async def handle_get_desktop_clients(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service
):
    """Handle get desktop clients request - returns list of connected desktop streaming clients"""
    try:
        desktop_clients = []

        # First: Get connected desktop capture clients from connection manager
        for other_client_id, info in manager.client_info.items():
            client_type = info.get("clientType", "")
            # Include desktop capture clients (dual_screen_desktop, desktop_capture, multi_monitor_desktop_capture)
            if client_type in [
                "dual_screen_desktop",
                "desktop_capture",
                "multi_monitor_desktop_capture",
                "desktop",
            ]:
                monitors = info.get("monitors", [])
                # Create client entry with monitor info
                client_entry = {
                    "id": other_client_id,
                    "clientId": other_client_id,
                    "name": info.get("hostname", f"Desktop {other_client_id[:8]}"),
                    "status": "connected",
                    "connected": True,
                    "clientType": client_type,
                    "monitors": monitors,
                    "availableMonitors": monitors,
                    "version": info.get("version", "unknown"),
                    "hostname": info.get("hostname", "unknown"),
                }
                desktop_clients.append(client_entry)
                logger.info(
                    f"📺 Found connected desktop client: {other_client_id} with {len(monitors)} monitors"
                )

        # If no connected desktop clients, fallback to local monitors (for testing)
        if not desktop_clients and desktop_service:
            logger.info(
                "No connected desktop clients, returning local monitors as fallback"
            )
            local_monitors = await desktop_service.get_available_monitors()
            desktop_clients = local_monitors
        elif not desktop_clients:
            # Return mock data if no service and no clients
            desktop_clients = [
                {
                    "id": "monitor_0",
                    "name": "Primary Monitor",
                    "status": "available",
                    "connected": False,
                    "resolution": {"width": 1920, "height": 1080},
                    "isPrimary": True,
                },
                {
                    "id": "monitor_1",
                    "name": "Secondary Monitor",
                    "status": "available",
                    "connected": False,
                    "resolution": {"width": 1920, "height": 1080},
                    "isPrimary": False,
                },
            ]

        response = {
            "type": "desktop_clients_list",
            "clients": desktop_clients,
            "timestamp": datetime.now().isoformat(),
        }

        await websocket.send_text(json.dumps(response))
        logger.info(
            f"📱 Sent desktop clients list to {client_id}: {len(desktop_clients)} clients"
        )

    except Exception as e:
        logger.error(f"❌ Error getting desktop clients for {client_id}: {e}")
        await websocket.send_text(
            json.dumps(
                {"type": "error", "message": f"Failed to get desktop clients: {str(e)}"}
            )
        )


async def handle_stream_request(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service
):
    """Handle desktop stream request"""
    monitor_id = message.get("monitorId", "monitor_0")

    if not desktop_service:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "stream_error",
                    "message": "Desktop service not available",
                    "monitorId": monitor_id,
                }
            )
        )
        return

    client_info = message.get("clientInfo", {})
    success = await desktop_service.start_streaming(client_id, client_info, monitor_id)

    if success:
        # Set up frame callback for this client
        def frame_callback(frame_data: bytes):
            asyncio.create_task(manager.send_binary_message(frame_data, client_id))

        desktop_service.add_frame_callback(frame_callback)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "stream_started",
                    "clientId": client_id,
                    "monitorId": monitor_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        logger.info(f"🎬 Desktop streaming started for {client_id} on {monitor_id}")
    else:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "stream_error",
                    "message": "Failed to start desktop streaming",
                    "monitorId": monitor_id,
                }
            )
        )


async def handle_stream_stop(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service
):
    """Handle desktop stream stop request"""
    monitor_id = message.get("monitorId", "monitor_0")

    if desktop_service:
        success = await desktop_service.stop_streaming(client_id, monitor_id)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "stream_stopped",
                    "clientId": client_id,
                    "monitorId": monitor_id,
                    "success": success,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        logger.info(f"🛑 Desktop streaming stopped for {client_id} on {monitor_id}")


async def handle_stream_config(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service
):
    """Handle stream configuration"""
    if not desktop_service:
        await websocket.send_text(
            json.dumps(
                {"type": "config_error", "message": "Desktop service not available"}
            )
        )
        return

    config = message.get("config", {})
    success = await desktop_service.configure_streaming(config)

    await websocket.send_text(
        json.dumps(
            {
                "type": "config_updated",
                "success": success,
                "config": desktop_service.stream_config if success else None,
                "timestamp": datetime.now().isoformat(),
            }
        )
    )


async def handle_screenshot_request(
    websocket: WebSocket, client_id: str, message: Dict, desktop_service
):
    """Handle screenshot request"""
    if not desktop_service:
        await websocket.send_text(
            json.dumps(
                {"type": "screenshot_error", "message": "Desktop service not available"}
            )
        )
        return

    screenshot_data = await desktop_service.take_screenshot(encode_base64=True)

    if screenshot_data:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "screenshot",
                    "data": screenshot_data,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        logger.debug(f"📸 Screenshot sent to {client_id}")
    else:
        await websocket.send_text(
            json.dumps(
                {"type": "screenshot_error", "message": "Failed to capture screenshot"}
            )
        )


async def handle_workflow_data(client_id: str, data: Dict):
    """Handle workflow data from filesystem bridge"""
    logger.info(f"📊 Received workflow data from {client_id}: {len(str(data))} bytes")

    # Broadcast to other clients if needed
    await manager.broadcast(
        json.dumps(
            {
                "type": "workflow_update",
                "source": client_id,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
        ),
        exclude_client=client_id,
    )


async def handle_filesystem_operation(
    websocket: WebSocket, client_id: str, message: Dict
):
    """Handle filesystem operations"""
    operation = message.get("operation")
    path = message.get("path")

    logger.info(f"📁 Filesystem operation from {client_id}: {operation} on {path}")

    # Mock response - in real implementation, this would perform actual file operations
    await websocket.send_text(
        json.dumps(
            {
                "type": "filesystem_response",
                "operation": operation,
                "path": path,
                "success": True,
                "message": f"Operation {operation} completed",
                "timestamp": datetime.now().isoformat(),
            }
        )
    )


async def handle_mcp_call(websocket: WebSocket, client_id: str, message: Dict):
    """Handle MCP tool calls from frontend

    Forwards requests to the MCP server tools (handoff_read_screen, handoff_validate, handoff_action)
    """
    request_id = message.get("requestId")
    tool = message.get("tool")
    params = message.get("params", {})

    logger.info(
        f"🔧 MCP call from {client_id}: {tool} with params: {list(params.keys())}"
    )

    try:
        result = {"success": False, "error": "Unknown tool"}

        # Import MCP tools
        try:
            import os
            import sys

            moire_agents_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "moire_agents",
            )
            if moire_agents_path not in sys.path:
                sys.path.insert(0, moire_agents_path)

            from mcp_server_handoff import (handle_action, handle_read_screen,
                                            handle_status, handle_validate)

            mcp_available = True
        except ImportError as e:
            logger.warning(f"⚠️ MCP tools not available: {e}")
            mcp_available = False

        if mcp_available:
            if tool == "handoff_read_screen":
                monitor_id = params.get("monitor_id", 0)
                region = params.get("region")
                mcp_result = await handle_read_screen(
                    region=region, monitor_id=monitor_id
                )
                result = {
                    "success": True,
                    "text": mcp_result.get("text", ""),
                    "location": None,
                }

            elif tool == "handoff_validate":
                target = params.get("target", "")
                mcp_result = await handle_validate(target=target)
                if mcp_result.get("found"):
                    result = {
                        "success": True,
                        "location": {
                            "x": mcp_result.get("location", {}).get("x", 0),
                            "y": mcp_result.get("location", {}).get("y", 0),
                        },
                        "confidence": mcp_result.get("confidence", 0),
                    }
                else:
                    result = {"success": False, "error": "Element not found"}

            elif tool == "handoff_action":
                action_type = params.get("action_type", "")
                action_params = params.get("params", {})
                mcp_result = await handle_action(
                    action_type=action_type, params=action_params
                )
                result = {
                    "success": mcp_result.get("success", False),
                    "error": mcp_result.get("error"),
                }

            elif tool == "handoff_status":
                mcp_result = await handle_status()
                result = {"success": True, "status": mcp_result}

            else:
                result = {"success": False, "error": f"Unknown MCP tool: {tool}"}
        else:
            result = {"success": False, "error": "MCP tools not available"}

        # Send response
        await websocket.send_text(
            json.dumps(
                {
                    "type": "mcp_result",
                    "requestId": request_id,
                    "tool": tool,
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

        logger.info(f"✅ MCP call completed: {tool} -> success={result.get('success')}")

    except Exception as e:
        logger.error(f"❌ MCP call error: {e}")
        await websocket.send_text(
            json.dumps(
                {
                    "type": "mcp_result",
                    "requestId": request_id,
                    "tool": tool,
                    "result": {"success": False, "error": str(e)},
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )


@router.get("/health")
async def websocket_health():
    """WebSocket router health check"""
    return {
        "status": "ok",
        "router": "websocket",
        "active_connections": manager.get_connection_count(),
        "clients": manager.get_client_list(),
        "endpoints": ["/ws/live-desktop", "/ws/echo", "/ws/health"],
    }


# Workflow execution subscription management
workflow_execution_subscribers: Dict[str, Set[str]] = (
    {}
)  # execution_id -> set of client_ids


async def handle_subscribe_workflow_execution(
    websocket: WebSocket, client_id: str, message: Dict
):
    """Handle workflow execution subscription"""
    execution_id = message.get("executionId")

    if not execution_id:
        await websocket.send_text(
            json.dumps({"type": "subscription_error", "message": "Missing executionId"})
        )
        return

    # Add client to subscribers
    if execution_id not in workflow_execution_subscribers:
        workflow_execution_subscribers[execution_id] = set()

    workflow_execution_subscribers[execution_id].add(client_id)

    await websocket.send_text(
        json.dumps(
            {
                "type": "workflow_execution_subscribed",
                "executionId": execution_id,
                "clientId": client_id,
                "timestamp": datetime.now().isoformat(),
            }
        )
    )

    logger.info(
        f"📊 Client {client_id} subscribed to workflow execution {execution_id}"
    )


async def handle_unsubscribe_workflow_execution(
    websocket: WebSocket, client_id: str, message: Dict
):
    """Handle workflow execution unsubscription"""
    execution_id = message.get("executionId")

    if not execution_id:
        await websocket.send_text(
            json.dumps(
                {"type": "unsubscription_error", "message": "Missing executionId"}
            )
        )
        return

    # Remove client from subscribers
    if execution_id in workflow_execution_subscribers:
        workflow_execution_subscribers[execution_id].discard(client_id)

        # Clean up empty subscription sets
        if not workflow_execution_subscribers[execution_id]:
            del workflow_execution_subscribers[execution_id]

    await websocket.send_text(
        json.dumps(
            {
                "type": "workflow_execution_unsubscribed",
                "executionId": execution_id,
                "clientId": client_id,
                "timestamp": datetime.now().isoformat(),
            }
        )
    )

    logger.info(
        f"📊 Client {client_id} unsubscribed from workflow execution {execution_id}"
    )


async def broadcast_workflow_execution_update(execution_id: str, update_data: Dict):
    """Broadcast workflow execution update to subscribed clients"""
    if execution_id not in workflow_execution_subscribers:
        return

    subscribers = workflow_execution_subscribers[execution_id].copy()
    disconnected_clients = []

    message = json.dumps(
        {
            "type": "workflow_execution_update",
            "executionId": execution_id,
            "data": update_data,
            "timestamp": datetime.now().isoformat(),
        }
    )

    for client_id in subscribers:
        if client_id in manager.active_connections:
            try:
                await manager.active_connections[client_id].send_text(message)
            except Exception as e:
                logger.error(f"❌ Failed to send workflow update to {client_id}: {e}")
                disconnected_clients.append(client_id)
        else:
            disconnected_clients.append(client_id)

    # Clean up disconnected clients
    for client_id in disconnected_clients:
        workflow_execution_subscribers[execution_id].discard(client_id)

    if disconnected_clients:
        logger.info(
            f"🧹 Cleaned up {len(disconnected_clients)} disconnected clients from execution {execution_id}"
        )


async def broadcast_node_execution_update(
    execution_id: str, node_id: str, node_data: Dict
):
    """Broadcast individual node execution update"""
    update_data = {"type": "node_update", "nodeId": node_id, "nodeData": node_data}

    await broadcast_workflow_execution_update(execution_id, update_data)
    logger.debug(
        f"📊 Broadcasted node update for {node_id} in execution {execution_id}"
    )


async def broadcast_execution_status_update(execution_id: str, status_data: Dict):
    """Broadcast execution status update"""
    update_data = {"type": "status_update", "statusData": status_data}

    await broadcast_workflow_execution_update(execution_id, update_data)
    logger.debug(f"📊 Broadcasted status update for execution {execution_id}")


async def broadcast_desktop_frame(
    execution_id: str, frame_data: bytes, frame_id: int, desktop_client_id: str
):
    """Broadcast a single desktop frame to all subscribers of a workflow execution."""
    try:
        frame_message = {
            "type": "desktop_frame",
            "frameNumber": frame_id,
            "desktopClientId": desktop_client_id,
            "data": base64.b64encode(frame_data).decode("utf-8"),
            "timestamp": datetime.now().isoformat(),
        }
        await broadcast_workflow_execution_update(execution_id, frame_message)
        logger.debug(
            f"🌍 Broadcasted frame {frame_id} from {desktop_client_id} to {execution_id}"
        )
    except Exception:
        logger.exception(
            f"🌍 Failed to broadcast frame {frame_id} from {desktop_client_id} to {execution_id}"
        )


@router.websocket("/echo")
async def websocket_echo(websocket: WebSocket):
    """Simple echo WebSocket endpoint for testing"""
    await websocket.accept()
    logger.info("🔄 WebSocket echo connection accepted")

    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
            logger.debug(f"🔄 Echoed: {data[:50]}...")
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket echo connection disconnected")


# === Task Queue Bridge (Redis → WebSocket) ===

# Track clients subscribed to task queue events
task_queue_subscribers: Set[str] = set()


async def handle_subscribe_task_queue(websocket: WebSocket, client_id: str, message: Dict):
    """Handle task queue subscription request"""
    task_queue_subscribers.add(client_id)
    logger.info(f"📋 Client {client_id} subscribed to task queue events")

    await websocket.send_text(json.dumps({
        "type": "task_queue_subscribed",
        "clientId": client_id,
        "timestamp": datetime.now().isoformat()
    }))


async def handle_unsubscribe_task_queue(websocket: WebSocket, client_id: str, message: Dict):
    """Handle task queue unsubscription request"""
    task_queue_subscribers.discard(client_id)
    logger.info(f"📋 Client {client_id} unsubscribed from task queue events")

    await websocket.send_text(json.dumps({
        "type": "task_queue_unsubscribed",
        "clientId": client_id,
        "timestamp": datetime.now().isoformat()
    }))


async def broadcast_task_event(event_data: Dict[str, Any]):
    """Broadcast task event to all subscribed WebSocket clients.

    Called by Redis PubSub handler when task events are received.
    """
    if not task_queue_subscribers:
        return

    # Add timestamp if not present
    if "timestamp" not in event_data:
        event_data["timestamp"] = datetime.now().isoformat()

    # Wrap in task_event message type
    message = {
        "type": "task_event",
        "event": event_data.get("status", "unknown"),
        "data": event_data
    }
    message_json = json.dumps(message)

    disconnected_clients = []

    for client_id in task_queue_subscribers:
        if client_id in manager.active_connections:
            try:
                await manager.active_connections[client_id].send_text(message_json)
                logger.debug(f"📋 Task event sent to {client_id}: {event_data.get('status')}")
            except Exception as e:
                logger.error(f"❌ Failed to send task event to {client_id}: {e}")
                disconnected_clients.append(client_id)
        else:
            disconnected_clients.append(client_id)

    # Cleanup disconnected subscribers
    for client_id in disconnected_clients:
        task_queue_subscribers.discard(client_id)


async def setup_task_queue_bridge():
    """Setup Redis → WebSocket bridge for task events.

    Call this during app startup to subscribe to Redis task channels.
    """
    try:
        from ..services.redis_pubsub import redis_pubsub
        import os

        # Connect to Redis if not already connected
        if not redis_pubsub.is_connected:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            await redis_pubsub.connect(redis_url)

        # Subscribe to all task events with broadcast handler
        await redis_pubsub.subscribe_task_events(broadcast_task_event)

        logger.info("✅ Task Queue Bridge setup complete - Redis → WebSocket")
        return True

    except Exception as e:
        logger.warning(f"⚠️ Task Queue Bridge setup failed (Redis may not be running): {e}")
        return False


async def get_task_queue_status() -> Dict[str, Any]:
    """Get task queue bridge status"""
    try:
        from ..services.redis_pubsub import redis_pubsub
        redis_connected = redis_pubsub.is_connected
    except:
        redis_connected = False

    return {
        "subscribers": len(task_queue_subscribers),
        "subscriber_ids": list(task_queue_subscribers),
        "redis_connected": redis_connected,
        "active_connections": manager.get_connection_count()
    }
