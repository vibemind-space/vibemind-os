"""WebSocket Handlers for TRAE Backend

Handles incoming WebSocket messages and coordinates with execution services.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..models.workflow import ExecutionControlRequest
from .manager import WebSocketConnection, WebSocketManager

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handles WebSocket message processing and routing"""

    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager
        self.message_handlers = {
            "subscribe_execution": self._handle_subscribe_execution,
            "unsubscribe_execution": self._handle_unsubscribe_execution,
            "execution_control": self._handle_execution_control,
            "ping": self._handle_ping,
            "get_status": self._handle_get_status,
        }

    async def handle_client_connection(self, websocket: WebSocket, client_id: str):
        """Handle new client connection and message loop"""
        connection = None
        try:
            # Accept connection
            connection = await self.websocket_manager.connect(websocket, client_id)

            # Message handling loop
            while connection.is_active:
                try:
                    # Wait for message with timeout
                    data = await asyncio.wait_for(
                        websocket.receive_text(), timeout=30.0  # 30 second timeout
                    )

                    # Process message
                    await self._process_message(client_id, data)

                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await self.websocket_manager.handle_ping(client_id)

                except WebSocketDisconnect:
                    logger.info(f"Client {client_id} disconnected")
                    break

                except Exception as e:
                    logger.error(f"Error handling message from client {client_id}: {e}")
                    await self._send_error_response(client_id, str(e))

        except Exception as e:
            logger.error(f"Error in client connection handler for {client_id}: {e}")

        finally:
            # Ensure cleanup
            if connection:
                await self.websocket_manager.disconnect(client_id)

    async def _process_message(self, client_id: str, data: str):
        """Process incoming message from client"""
        try:
            message = json.loads(data)
            message_type = message.get("type")

            if not message_type:
                await self._send_error_response(client_id, "Missing message type")
                return

            # Route message to appropriate handler
            if message_type in self.message_handlers:
                handler = self.message_handlers[message_type]
                await handler(client_id, message)
            else:
                await self._send_error_response(
                    client_id, f"Unknown message type: {message_type}"
                )

        except json.JSONDecodeError as e:
            await self._send_error_response(client_id, f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error processing message from client {client_id}: {e}")
            await self._send_error_response(client_id, f"Internal error: {e}")

    async def _handle_subscribe_execution(
        self, client_id: str, message: Dict[str, Any]
    ):
        """Handle execution subscription request"""
        execution_id = message.get("execution_id")
        if not execution_id:
            await self._send_error_response(client_id, "Missing execution_id")
            return

        await self.websocket_manager.subscribe_to_execution(client_id, execution_id)
        logger.debug(f"Client {client_id} subscribed to execution {execution_id}")

    async def _handle_unsubscribe_execution(
        self, client_id: str, message: Dict[str, Any]
    ):
        """Handle execution unsubscription request"""
        execution_id = message.get("execution_id")
        if not execution_id:
            await self._send_error_response(client_id, "Missing execution_id")
            return

        await self.websocket_manager.unsubscribe_from_execution(client_id, execution_id)
        logger.debug(f"Client {client_id} unsubscribed from execution {execution_id}")

    async def _handle_execution_control(self, client_id: str, message: Dict[str, Any]):
        """Handle execution control request (pause, resume, stop, step)"""
        try:
            execution_id = message.get("execution_id")
            action = message.get("action")

            if not execution_id or not action:
                await self._send_error_response(
                    client_id, "Missing execution_id or action"
                )
                return

            # Import here to avoid circular imports
            from ..services import (get_click_automation_service,
                                    get_desktop_automation_service,
                                    get_graph_execution_service,
                                    get_ocr_service, get_websocket_manager)

            execution_service = get_graph_execution_service(
                websocket_manager=get_websocket_manager(),
                click_service=get_click_automation_service(),
                desktop_service=get_desktop_automation_service(),
                ocr_service=get_ocr_service(),
            )

            # Execute control action
            if action == "pause":
                await execution_service.pause_execution(execution_id)
            elif action == "resume":
                await execution_service.resume_execution(execution_id)
            elif action == "stop":
                await execution_service.stop_execution(execution_id)
            elif action == "step":
                await execution_service.step_execution(execution_id)
            else:
                await self._send_error_response(client_id, f"Unknown action: {action}")
                return

            # Send confirmation
            await self.websocket_manager.send_to_client(
                client_id,
                {
                    "type": "execution_control_response",
                    "execution_id": execution_id,
                    "action": action,
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(
                f"Error handling execution control from client {client_id}: {e}"
            )
            await self._send_error_response(client_id, f"Execution control failed: {e}")

    async def _handle_ping(self, client_id: str, message: Dict[str, Any]):
        """Handle ping request"""
        await self.websocket_manager.handle_ping(client_id)

    async def _handle_get_status(self, client_id: str, message: Dict[str, Any]):
        """Handle status request"""
        execution_id = message.get("execution_id")

        try:
            # Import here to avoid circular imports
            from ..services import (get_click_automation_service,
                                    get_desktop_automation_service,
                                    get_graph_execution_service,
                                    get_ocr_service, get_websocket_manager)

            execution_service = get_graph_execution_service(
                websocket_manager=get_websocket_manager(),
                click_service=get_click_automation_service(),
                desktop_service=get_desktop_automation_service(),
                ocr_service=get_ocr_service(),
            )

            if execution_id:
                # Get specific execution status
                execution = await execution_service.get_execution_status(execution_id)
                if execution:
                    await self.websocket_manager.send_to_client(
                        client_id,
                        {
                            "type": "execution_status",
                            "execution": execution.dict(),
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                else:
                    await self._send_error_response(
                        client_id, f"Execution {execution_id} not found"
                    )
            else:
                # Get general status
                status = {
                    "type": "general_status",
                    "connected_clients": self.websocket_manager.get_connection_count(),
                    "active_executions": len(execution_service.active_executions),
                    "timestamp": datetime.now().isoformat(),
                }
                await self.websocket_manager.send_to_client(client_id, status)

        except Exception as e:
            logger.error(f"Error handling status request from client {client_id}: {e}")
            await self._send_error_response(client_id, f"Status request failed: {e}")

    async def _send_error_response(self, client_id: str, error_message: str):
        """Send error response to client"""
        await self.websocket_manager.send_to_client(
            client_id,
            {
                "type": "error",
                "message": error_message,
                "timestamp": datetime.now().isoformat(),
            },
        )


# Global handler instance
websocket_handler = None


def get_websocket_handler(websocket_manager: WebSocketManager) -> WebSocketHandler:
    """Get or create WebSocket handler instance"""
    global websocket_handler
    if websocket_handler is None:
        websocket_handler = WebSocketHandler(websocket_manager)
    return websocket_handler
