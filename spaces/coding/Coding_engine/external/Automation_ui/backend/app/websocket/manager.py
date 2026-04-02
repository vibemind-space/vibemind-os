"""WebSocket Manager for TRAE Backend

Manages WebSocket connections and message broadcasting for real-time workflow execution updates.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from ..models.workflow import (ExecutionStatus, NodeExecutionResult,
                               WorkflowExecution)

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """Represents a WebSocket connection with metadata"""

    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.connected_at = datetime.now()
        self.subscribed_executions: Set[str] = set()
        self.is_active = True

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Send message to client, return success status"""
        try:
            if self.is_active:
                await self.websocket.send_text(json.dumps(message))
                return True
        except Exception as e:
            logger.error(f"Failed to send message to client {self.client_id}: {e}")
            self.is_active = False
        return False

    def subscribe_to_execution(self, execution_id: str):
        """Subscribe to execution updates"""
        self.subscribed_executions.add(execution_id)
        logger.debug(f"Client {self.client_id} subscribed to execution {execution_id}")

    def unsubscribe_from_execution(self, execution_id: str):
        """Unsubscribe from execution updates"""
        self.subscribed_executions.discard(execution_id)
        logger.debug(
            f"Client {self.client_id} unsubscribed from execution {execution_id}"
        )

    def is_subscribed_to(self, execution_id: str) -> bool:
        """Check if client is subscribed to execution"""
        return execution_id in self.subscribed_executions


class WebSocketManager:
    """Manages WebSocket connections and message broadcasting"""

    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.execution_subscribers: Dict[str, Set[str]] = (
            {}
        )  # execution_id -> set of client_ids
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, client_id: str
    ) -> WebSocketConnection:
        """Accept new WebSocket connection"""
        await websocket.accept()

        async with self._lock:
            # Disconnect existing connection with same client_id
            if client_id in self.connections:
                await self.disconnect(client_id)

            connection = WebSocketConnection(websocket, client_id)
            self.connections[client_id] = connection

            logger.info(
                f"WebSocket client {client_id} connected. Total connections: {len(self.connections)}"
            )

            # Send connection confirmation
            await connection.send_message(
                {
                    "type": "connection_established",
                    "client_id": client_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return connection

    async def disconnect(self, client_id: str):
        """Disconnect WebSocket client"""
        async with self._lock:
            if client_id in self.connections:
                connection = self.connections[client_id]
                connection.is_active = False

                # Remove from all execution subscriptions
                for execution_id in list(connection.subscribed_executions):
                    self._unsubscribe_client_from_execution(client_id, execution_id)

                # Close WebSocket if still open
                try:
                    await connection.websocket.close()
                except Exception as e:
                    logger.debug(f"Error closing WebSocket for client {client_id}: {e}")

                del self.connections[client_id]
                logger.info(
                    f"WebSocket client {client_id} disconnected. Total connections: {len(self.connections)}"
                )

    async def subscribe_to_execution(self, client_id: str, execution_id: str):
        """Subscribe client to execution updates"""
        async with self._lock:
            if client_id in self.connections:
                connection = self.connections[client_id]
                connection.subscribe_to_execution(execution_id)

                # Add to execution subscribers
                if execution_id not in self.execution_subscribers:
                    self.execution_subscribers[execution_id] = set()
                self.execution_subscribers[execution_id].add(client_id)

                # Send subscription confirmation
                await connection.send_message(
                    {
                        "type": "subscription_confirmed",
                        "execution_id": execution_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    async def unsubscribe_from_execution(self, client_id: str, execution_id: str):
        """Unsubscribe client from execution updates"""
        async with self._lock:
            self._unsubscribe_client_from_execution(client_id, execution_id)

            if client_id in self.connections:
                connection = self.connections[client_id]
                await connection.send_message(
                    {
                        "type": "unsubscription_confirmed",
                        "execution_id": execution_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    def _unsubscribe_client_from_execution(self, client_id: str, execution_id: str):
        """Internal method to unsubscribe client (no lock needed)"""
        if client_id in self.connections:
            self.connections[client_id].unsubscribe_from_execution(execution_id)

        if execution_id in self.execution_subscribers:
            self.execution_subscribers[execution_id].discard(client_id)
            if not self.execution_subscribers[execution_id]:
                del self.execution_subscribers[execution_id]

    async def broadcast_execution_update(self, execution: WorkflowExecution):
        """Broadcast execution status update to subscribed clients"""
        message = {
            "type": "execution_status_update",
            "execution_id": execution.id,
            "status": execution.status,
            "current_node": execution.current_node,
            "progress": execution.progress,
            "timestamp": datetime.now().isoformat(),
        }

        await self._broadcast_to_execution_subscribers(execution.id, message)

    async def broadcast_node_result(
        self, execution_id: str, node_result: NodeExecutionResult
    ):
        """Broadcast node execution result to subscribed clients"""
        message = {
            "type": "node_result",
            "execution_id": execution_id,
            "node_id": node_result.node_id,
            "status": node_result.status,
            "result": node_result.result,
            "error": node_result.error,
            "duration_ms": node_result.duration_ms,
            "timestamp": datetime.now().isoformat(),
        }

        await self._broadcast_to_execution_subscribers(execution_id, message)

    async def broadcast_execution_log(
        self, execution_id: str, log_message: str, level: str = "info"
    ):
        """Broadcast execution log message to subscribed clients"""
        message = {
            "type": "execution_log",
            "execution_id": execution_id,
            "message": log_message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
        }

        await self._broadcast_to_execution_subscribers(execution_id, message)

    async def broadcast_variable_update(
        self, execution_id: str, variable_name: str, variable_value: Any
    ):
        """Broadcast variable update to subscribed clients"""
        message = {
            "type": "variable_update",
            "execution_id": execution_id,
            "variable_name": variable_name,
            "variable_value": variable_value,
            "timestamp": datetime.now().isoformat(),
        }

        await self._broadcast_to_execution_subscribers(execution_id, message)

    async def _broadcast_to_execution_subscribers(
        self, execution_id: str, message: Dict[str, Any]
    ):
        """Broadcast message to all clients subscribed to execution"""
        if execution_id not in self.execution_subscribers:
            return

        subscriber_ids = list(self.execution_subscribers[execution_id])
        disconnected_clients = []

        for client_id in subscriber_ids:
            if client_id in self.connections:
                connection = self.connections[client_id]
                success = await connection.send_message(message)
                if not success:
                    disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    async def send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """Send message to specific client"""
        if client_id in self.connections:
            connection = self.connections[client_id]
            return await connection.send_message(message)
        return False

    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        client_ids = list(self.connections.keys())
        disconnected_clients = []

        for client_id in client_ids:
            connection = self.connections[client_id]
            success = await connection.send_message(message)
            if not success:
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return len(self.connections)

    def get_execution_subscriber_count(self, execution_id: str) -> int:
        """Get number of clients subscribed to execution"""
        return len(self.execution_subscribers.get(execution_id, set()))

    async def handle_ping(self, client_id: str):
        """Handle ping from client"""
        await self.send_to_client(
            client_id, {"type": "pong", "timestamp": datetime.now().isoformat()}
        )


# Global WebSocket manager instance
websocket_manager = WebSocketManager()
