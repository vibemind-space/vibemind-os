"""WebSocket Manager for TRAE Backend

Manages WebSocket connections and real-time communication.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class WebSocketMessage(BaseModel):
    """WebSocket message structure"""

    type: str
    data: Dict[str, Any]
    timestamp: datetime = None

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.now()
        super().__init__(**data)


class WebSocketConnection:
    """Represents a WebSocket connection"""

    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.subscriptions: Set[str] = set()
        self.connected_at = datetime.now()
        self.last_ping = datetime.now()

    async def send_message(self, message: WebSocketMessage):
        """Send message to client"""
        try:
            await self.websocket.send_text(message.json())
        except Exception as e:
            logger.error(f"Failed to send message to {self.client_id}: {e}")
            raise

    async def send_json(self, data: Dict[str, Any]):
        """Send JSON data to client"""
        message = WebSocketMessage(type="data", data=data)
        await self.send_message(message)

    def subscribe(self, topic: str):
        """Subscribe to a topic"""
        self.subscriptions.add(topic)
        logger.debug(f"Client {self.client_id} subscribed to {topic}")

    def unsubscribe(self, topic: str):
        """Unsubscribe from a topic"""
        self.subscriptions.discard(topic)
        logger.debug(f"Client {self.client_id} unsubscribed from {topic}")

    def is_subscribed(self, topic: str) -> bool:
        """Check if subscribed to topic"""
        return topic in self.subscriptions


class WebSocketManager:
    """Manages WebSocket connections and messaging"""

    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.topics: Dict[str, Set[str]] = {}  # topic -> set of client_ids
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, client_id: str
    ) -> WebSocketConnection:
        """Accept and register a new WebSocket connection"""
        await websocket.accept()

        async with self._lock:
            connection = WebSocketConnection(websocket, client_id)
            self.connections[client_id] = connection

        logger.info(f"WebSocket client {client_id} connected")
        return connection

    async def disconnect(self, client_id: str):
        """Disconnect and cleanup a WebSocket connection"""
        async with self._lock:
            if client_id in self.connections:
                connection = self.connections[client_id]

                # Remove from all topic subscriptions
                for topic in list(connection.subscriptions):
                    await self._unsubscribe_from_topic(client_id, topic)

                del self.connections[client_id]
                logger.info(f"WebSocket client {client_id} disconnected")

    async def send_to_client(self, client_id: str, message: WebSocketMessage):
        """Send message to specific client"""
        if client_id in self.connections:
            try:
                await self.connections[client_id].send_message(message)
            except Exception as e:
                logger.error(f"Failed to send to client {client_id}: {e}")
                await self.disconnect(client_id)

    async def send_json_to_client(self, client_id: str, data: Dict[str, Any]):
        """Send JSON data to specific client"""
        message = WebSocketMessage(type="data", data=data)
        await self.send_to_client(client_id, message)

    async def broadcast(
        self, message: WebSocketMessage, exclude_clients: Optional[Set[str]] = None
    ):
        """Broadcast message to all connected clients"""
        exclude_clients = exclude_clients or set()

        disconnected_clients = []
        for client_id, connection in self.connections.items():
            if client_id not in exclude_clients:
                try:
                    await connection.send_message(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast to client {client_id}: {e}")
                    disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    async def subscribe_to_topic(self, client_id: str, topic: str):
        """Subscribe client to a topic"""
        if client_id not in self.connections:
            return False

        async with self._lock:
            connection = self.connections[client_id]
            connection.subscribe(topic)

            if topic not in self.topics:
                self.topics[topic] = set()
            self.topics[topic].add(client_id)

        return True

    async def unsubscribe_from_topic(self, client_id: str, topic: str):
        """Unsubscribe client from a topic"""
        if client_id not in self.connections:
            return False

        async with self._lock:
            await self._unsubscribe_from_topic(client_id, topic)

        return True

    async def _unsubscribe_from_topic(self, client_id: str, topic: str):
        """Internal unsubscribe method (assumes lock is held)"""
        if client_id in self.connections:
            self.connections[client_id].unsubscribe(topic)

        if topic in self.topics:
            self.topics[topic].discard(client_id)
            if not self.topics[topic]:  # Remove empty topic
                del self.topics[topic]

    async def publish_to_topic(self, topic: str, data: Dict[str, Any]):
        """Publish message to all subscribers of a topic"""
        if topic not in self.topics:
            return

        message = WebSocketMessage(
            type="topic_message", data={"topic": topic, "payload": data}
        )

        disconnected_clients = []
        for client_id in list(self.topics[topic]):
            if client_id in self.connections:
                try:
                    await self.connections[client_id].send_message(message)
                except Exception as e:
                    logger.error(
                        f"Failed to publish to client {client_id} on topic {topic}: {e}"
                    )
                    disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    async def handle_client_message(self, client_id: str, message_data: Dict[str, Any]):
        """Handle incoming message from client"""
        try:
            message_type = message_data.get("type")
            data = message_data.get("data", {})

            if message_type == "subscribe":
                topic = data.get("topic")
                if topic:
                    await self.subscribe_to_topic(client_id, topic)
                    await self.send_json_to_client(
                        client_id, {"type": "subscription_confirmed", "topic": topic}
                    )

            elif message_type == "unsubscribe":
                topic = data.get("topic")
                if topic:
                    await self.unsubscribe_from_topic(client_id, topic)
                    await self.send_json_to_client(
                        client_id, {"type": "unsubscription_confirmed", "topic": topic}
                    )

            elif message_type == "ping":
                if client_id in self.connections:
                    self.connections[client_id].last_ping = datetime.now()
                await self.send_json_to_client(
                    client_id, {"type": "pong", "timestamp": datetime.now().isoformat()}
                )

            else:
                logger.warning(
                    f"Unknown message type from client {client_id}: {message_type}"
                )

        except Exception as e:
            logger.error(f"Error handling message from client {client_id}: {e}")

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.connections)

    def get_topic_subscribers(self, topic: str) -> Set[str]:
        """Get subscribers for a topic"""
        return self.topics.get(topic, set()).copy()

    def get_client_subscriptions(self, client_id: str) -> Set[str]:
        """Get subscriptions for a client"""
        if client_id in self.connections:
            return self.connections[client_id].subscriptions.copy()
        return set()

    async def cleanup_stale_connections(self, timeout_seconds: int = 300):
        """Clean up stale connections that haven't pinged recently"""
        current_time = datetime.now()
        stale_clients = []

        for client_id, connection in self.connections.items():
            time_since_ping = (current_time - connection.last_ping).total_seconds()
            if time_since_ping > timeout_seconds:
                stale_clients.append(client_id)

        for client_id in stale_clients:
            logger.info(f"Cleaning up stale connection: {client_id}")
            await self.disconnect(client_id)

        return len(stale_clients)


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


# Convenience functions for common operations
async def send_execution_update(execution_id: str, status: str, data: Dict[str, Any]):
    """Send execution status update"""
    await websocket_manager.publish_to_topic(
        f"execution_{execution_id}",
        {
            "type": "execution_update",
            "execution_id": execution_id,
            "status": status,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        },
    )


async def send_node_result(execution_id: str, node_id: str, result: Dict[str, Any]):
    """Send node execution result"""
    await websocket_manager.publish_to_topic(
        f"execution_{execution_id}",
        {
            "type": "node_result",
            "execution_id": execution_id,
            "node_id": node_id,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        },
    )


async def send_log_message(
    execution_id: str, level: str, message: str, node_id: Optional[str] = None
):
    """Send log message"""
    await websocket_manager.publish_to_topic(
        f"execution_{execution_id}",
        {
            "type": "log_message",
            "execution_id": execution_id,
            "node_id": node_id,
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        },
    )


async def send_variable_update(execution_id: str, variables: Dict[str, Any]):
    """Send variable update"""
    await websocket_manager.publish_to_topic(
        f"execution_{execution_id}",
        {
            "type": "variable_update",
            "execution_id": execution_id,
            "variables": variables,
            "timestamp": datetime.now().isoformat(),
        },
    )
