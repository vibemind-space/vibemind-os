"""
Redis PubSub Service for TRAE Backend

Provides publish/subscribe functionality for real-time communication
between WebSocket handlers and desktop clients. Replaces Supabase
Realtime Channels for cross-instance communication.

Channels:
- desktop-frames: Desktop screen frame data
- desktop-commands: Automation commands to desktop clients
- client-registry: Desktop client registration/deregistration events
- clawdbot:commands: Incoming commands from Clawdbot messaging platforms
- clawdbot:results: Execution results back to Clawdbot
- clawdbot:notifications: Status updates and alerts for Clawdbot

Task Queue Channels (Voice → MCP Integration):
- task:created: New task created from voice/text input
- task:started: Task execution started
- task:progress: Task progress update (for multi-step tasks)
- task:validation: Vision validation result
- task:completed: Task successfully completed
- task:failed: Task execution failed
- task:learned: New pattern learned from task
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisPubSub:
    """
    Redis PubSub manager for real-time messaging.

    Usage:
        await redis_pubsub.connect("redis://localhost:6379/0")
        await redis_pubsub.subscribe("desktop-commands", handler)
        await redis_pubsub.publish("desktop-frames", {"frame": "..."})
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._handlers: Dict[str, List[Callable]] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False

    async def connect(self, redis_url: str = "redis://localhost:6379/0"):
        """
        Connect to Redis server.

        Args:
            redis_url: Redis connection URL
        """
        if self._connected:
            logger.warning("Redis already connected")
            return

        try:
            self._redis = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self._redis.ping()

            self._pubsub = self._redis.pubsub()
            self._connected = True
            logger.info(f"Redis connected: {redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            raise

    async def subscribe(self, channel: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to a channel with a message handler.

        Args:
            channel: Channel name to subscribe to
            handler: Async function to call when messages arrive
        """
        if not self._connected:
            logger.warning(f"Cannot subscribe to {channel}: not connected")
            return

        if channel not in self._handlers:
            self._handlers[channel] = []
            await self._pubsub.subscribe(channel)
            logger.info(f"Subscribed to channel: {channel}")

        self._handlers[channel].append(handler)

        # Start listener if not running
        if not self._running:
            self._running = True
            self._listener_task = asyncio.create_task(self._listen())

    async def unsubscribe(self, channel: str, handler: Optional[Callable] = None):
        """
        Unsubscribe from a channel.

        Args:
            channel: Channel name to unsubscribe from
            handler: Specific handler to remove (removes all if None)
        """
        if channel not in self._handlers:
            return

        if handler:
            self._handlers[channel] = [h for h in self._handlers[channel] if h != handler]
        else:
            self._handlers[channel] = []

        if not self._handlers[channel]:
            del self._handlers[channel]
            if self._pubsub:
                await self._pubsub.unsubscribe(channel)
            logger.info(f"Unsubscribed from channel: {channel}")

    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """
        Publish a message to a channel.

        Args:
            channel: Channel name to publish to
            message: Message data (will be JSON serialized)

        Returns:
            Number of subscribers that received the message
        """
        if not self._connected or not self._redis:
            logger.warning(f"Cannot publish to {channel}: not connected")
            return 0

        try:
            json_message = json.dumps(message)
            count = await self._redis.publish(channel, json_message)
            logger.debug(f"Published to {channel}: {count} subscribers")
            return count
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")
            return 0

    async def _listen(self):
        """Internal listener loop for incoming messages"""
        logger.info("Redis PubSub listener started")

        try:
            while self._running and self._pubsub:
                try:
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )

                    if message and message["type"] == "message":
                        channel = message["channel"]
                        data = message["data"]

                        # Parse JSON data
                        try:
                            parsed_data = json.loads(data) if isinstance(data, str) else data
                        except json.JSONDecodeError:
                            parsed_data = {"raw": data}

                        # Call all handlers for this channel
                        if channel in self._handlers:
                            for handler in self._handlers[channel]:
                                try:
                                    if asyncio.iscoroutinefunction(handler):
                                        await handler(parsed_data)
                                    else:
                                        handler(parsed_data)
                                except Exception as e:
                                    logger.error(f"Handler error for {channel}: {e}")

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Listener error: {e}")
                    await asyncio.sleep(1)

        finally:
            logger.info("Redis PubSub listener stopped")

    async def close(self):
        """Close Redis connection and cleanup"""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        if self._redis:
            await self._redis.close()
            self._redis = None

        self._handlers.clear()
        self._connected = False
        logger.info("Redis PubSub closed")

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis"""
        return self._connected

    # Convenience methods for common channels

    async def publish_frame(self, desktop_client_id: str, frame_data: Dict[str, Any]):
        """Publish a desktop frame to the frames channel"""
        await self.publish("desktop-frames", {
            "desktop_client_id": desktop_client_id,
            "frame_data": frame_data
        })

    async def publish_command(
        self,
        desktop_client_id: str,
        command_type: str,
        command_data: Dict[str, Any]
    ):
        """Publish an automation command to the commands channel"""
        await self.publish("desktop-commands", {
            "desktop_client_id": desktop_client_id,
            "command_type": command_type,
            "command_data": command_data
        })

    async def publish_client_event(
        self,
        event_type: str,
        client_id: str,
        client_info: Optional[Dict[str, Any]] = None
    ):
        """Publish a client registry event"""
        await self.publish("client-registry", {
            "event_type": event_type,  # "connected", "disconnected", "updated"
            "client_id": client_id,
            "client_info": client_info or {}
        })

    # Clawdbot integration channels

    async def publish_clawdbot_command(
        self,
        user_id: str,
        platform: str,
        text: str,
        message_id: Optional[str] = None
    ):
        """Publish an incoming Clawdbot command for processing"""
        await self.publish("clawdbot:commands", {
            "user_id": user_id,
            "platform": platform,
            "text": text,
            "message_id": message_id
        })

    async def publish_clawdbot_result(
        self,
        user_id: str,
        platform: str,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        image_base64: Optional[str] = None
    ):
        """Publish command execution result back to Clawdbot"""
        await self.publish("clawdbot:results", {
            "user_id": user_id,
            "platform": platform,
            "success": success,
            "message": message,
            "data": data,
            "image_base64": image_base64
        })

    async def publish_clawdbot_notification(
        self,
        user_id: str,
        platform: str,
        message: str,
        notification_type: str = "info"
    ):
        """Publish a notification to send via Clawdbot"""
        await self.publish("clawdbot:notifications", {
            "user_id": user_id,
            "platform": platform,
            "message": message,
            "type": notification_type
        })

    # Task Queue Channels (Voice → MCP Integration)

    async def publish_task_created(
        self,
        task_id: str,
        text: str,
        source: str = "voice",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Publish task created event"""
        await self.publish("task:created", {
            "task_id": task_id,
            "text": text,
            "source": source,
            "metadata": metadata or {},
            "status": "created"
        })

    async def publish_task_started(
        self,
        task_id: str,
        route: str,
        actions: Optional[List[Dict[str, Any]]] = None
    ):
        """Publish task started event"""
        await self.publish("task:started", {
            "task_id": task_id,
            "route": route,
            "actions": actions or [],
            "status": "running"
        })

    async def publish_task_progress(
        self,
        task_id: str,
        progress: float,
        current_step: int,
        total_steps: int,
        message: str = ""
    ):
        """Publish task progress update"""
        await self.publish("task:progress", {
            "task_id": task_id,
            "progress": progress,
            "current_step": current_step,
            "total_steps": total_steps,
            "message": message,
            "status": "running"
        })

    async def publish_task_validation(
        self,
        task_id: str,
        success: bool,
        confidence: float,
        method: str,
        reason: str = "",
        observed_changes: Optional[List[str]] = None
    ):
        """Publish task validation result"""
        await self.publish("task:validation", {
            "task_id": task_id,
            "success": success,
            "confidence": confidence,
            "method": method,
            "reason": reason,
            "observed_changes": observed_changes or [],
            "status": "validating"
        })

    async def publish_task_completed(
        self,
        task_id: str,
        success: bool,
        route: str,
        duration_ms: float,
        validation: Optional[Dict[str, Any]] = None,
        learned: bool = False
    ):
        """Publish task completed event"""
        await self.publish("task:completed", {
            "task_id": task_id,
            "success": success,
            "route": route,
            "duration_ms": duration_ms,
            "validation": validation,
            "learned": learned,
            "status": "completed"
        })

    async def publish_task_failed(
        self,
        task_id: str,
        error: str,
        route: str = "",
        duration_ms: float = 0
    ):
        """Publish task failed event"""
        await self.publish("task:failed", {
            "task_id": task_id,
            "error": error,
            "route": route,
            "duration_ms": duration_ms,
            "status": "failed"
        })

    async def publish_task_learned(
        self,
        task_id: str,
        pattern_id: str,
        task_text: str,
        confidence: float,
        actions: List[Dict[str, Any]]
    ):
        """Publish new pattern learned event"""
        await self.publish("task:learned", {
            "task_id": task_id,
            "pattern_id": pattern_id,
            "task_text": task_text,
            "confidence": confidence,
            "actions": actions,
            "status": "learned"
        })

    async def subscribe_task_events(self, handler: Callable[[Dict[str, Any]], None]):
        """Subscribe to all task events with a single handler"""
        task_channels = [
            "task:created", "task:started", "task:progress",
            "task:validation", "task:completed", "task:failed", "task:learned"
        ]
        for channel in task_channels:
            await self.subscribe(channel, handler)
        logger.info(f"Subscribed to {len(task_channels)} task channels")


# Global singleton instance
redis_pubsub = RedisPubSub()


# Convenience functions for direct access
async def get_redis_pubsub() -> RedisPubSub:
    """Get the global Redis PubSub instance"""
    return redis_pubsub
