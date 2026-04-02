"""
Redis Streams Client - Async communication layer for subagent orchestration.

Provides:
- Publish/subscribe to Redis streams
- Tool call pattern (request/response over streams)
- Consumer group management for parallel workers
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from uuid import uuid4

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class StreamMessage:
    """A message from a Redis stream."""
    message_id: str
    stream: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolCallResult:
    """Result from a tool call."""
    task_id: str
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class RedisStreamClient:
    """
    Async Redis Streams client for agent communication.

    Supports:
    - Publishing messages to streams
    - Subscribing to streams with handlers
    - Tool call pattern (publish request, await response)
    - Consumer groups for parallel processing
    """

    # Stream names
    STREAM_TASKS = "moire:tasks"
    STREAM_PLANNING = "moire:planning"
    STREAM_VISION = "moire:vision"
    STREAM_SPECIALIST = "moire:specialist"
    STREAM_BACKGROUND = "moire:background"
    STREAM_RESULTS = "moire:results"
    STREAM_EVENTS = "moire:events"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        consumer_group: str = "moire_agents",
        consumer_name: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"consumer_{uuid4().hex[:8]}"

        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._running = False
        self._pending_results: Dict[str, asyncio.Future] = {}
        self._result_listener_task: Optional[asyncio.Task] = None
        self._handlers: Dict[str, Callable[[StreamMessage], Awaitable[None]]] = {}

    async def connect(self) -> bool:
        """Connect to Redis server."""
        try:
            self._redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            # Test connection
            await self._redis.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}")

            # Initialize consumer groups for all streams
            await self._init_consumer_groups()

            # Start result listener for tool calls
            self._running = True
            self._result_listener_task = asyncio.create_task(
                self._listen_for_results()
            )

            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Redis server."""
        self._running = False

        if self._result_listener_task:
            self._result_listener_task.cancel()
            try:
                await self._result_listener_task
            except asyncio.CancelledError:
                pass

        if self._redis:
            await self._redis.close()
            logger.info("Disconnected from Redis")

    async def _init_consumer_groups(self):
        """Initialize consumer groups for all streams."""
        streams = [
            self.STREAM_TASKS,
            self.STREAM_PLANNING,
            self.STREAM_VISION,
            self.STREAM_SPECIALIST,
            self.STREAM_BACKGROUND,
            self.STREAM_RESULTS,
            self.STREAM_EVENTS
        ]

        for stream in streams:
            try:
                # Create stream if not exists (by adding a dummy message and deleting it)
                # Then create consumer group
                await self._redis.xgroup_create(
                    stream,
                    self.consumer_group,
                    id="0",
                    mkstream=True
                )
                logger.debug(f"Created consumer group '{self.consumer_group}' for stream '{stream}'")
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    # Group already exists, that's fine
                    logger.debug(f"Consumer group '{self.consumer_group}' already exists for '{stream}'")
                else:
                    logger.warning(f"Error creating consumer group for {stream}: {e}")

    # ==================== Publishing ====================

    async def publish(
        self,
        stream: str,
        message: Dict[str, Any],
        max_len: int = 10000
    ) -> str:
        """
        Publish a message to a stream.

        Args:
            stream: Stream name
            message: Message data (will be JSON serialized)
            max_len: Maximum stream length (older messages trimmed)

        Returns:
            Message ID
        """
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        # Serialize message to JSON string for Redis
        serialized = {
            "data": json.dumps(message),
            "timestamp": str(time.time())
        }

        message_id = await self._redis.xadd(
            stream,
            serialized,
            maxlen=max_len
        )

        logger.debug(f"Published to {stream}: {message_id}")
        return message_id

    async def publish_event(self, event_type: str, data: Dict[str, Any]):
        """Publish a broadcast event to all agents."""
        await self.publish(self.STREAM_EVENTS, {
            "event_type": event_type,
            "data": data,
            "source": self.consumer_name
        })

    # ==================== Subscribing ====================

    async def subscribe(
        self,
        stream: str,
        handler: Callable[[StreamMessage], Awaitable[None]]
    ):
        """
        Subscribe to a stream with a handler function.

        Args:
            stream: Stream name to subscribe to
            handler: Async function to handle incoming messages
        """
        self._handlers[stream] = handler
        logger.info(f"Subscribed to stream: {stream}")

    async def _ensure_consumer_group(self, stream: str):
        """Ensure consumer group exists for a stream (create if needed)."""
        try:
            await self._redis.xgroup_create(
                stream,
                self.consumer_group,
                id="0",
                mkstream=True
            )
            logger.debug(f"Created consumer group '{self.consumer_group}' for stream '{stream}'")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def read_stream(
        self,
        stream: str,
        count: int = 1,
        block_ms: int = 1000
    ) -> List[StreamMessage]:
        """
        Read messages from a stream using consumer group.

        Args:
            stream: Stream name
            count: Max messages to read
            block_ms: Block timeout in milliseconds (0 = no block)

        Returns:
            List of StreamMessage objects
        """
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        messages = []

        try:
            # Ensure consumer group exists for this stream
            await self._ensure_consumer_group(stream)

            # Read from consumer group
            result = await self._redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={stream: ">"},  # ">" = only new messages
                count=count,
                block=block_ms
            )

            if result:
                for stream_name, stream_messages in result:
                    for msg_id, msg_data in stream_messages:
                        try:
                            data = json.loads(msg_data.get("data", "{}"))
                            timestamp = float(msg_data.get("timestamp", time.time()))

                            messages.append(StreamMessage(
                                message_id=msg_id,
                                stream=stream_name,
                                data=data,
                                timestamp=timestamp
                            ))

                            # Acknowledge message
                            await self._redis.xack(stream_name, self.consumer_group, msg_id)

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse message {msg_id}: {e}")
                            # Still acknowledge to prevent reprocessing
                            await self._redis.xack(stream_name, self.consumer_group, msg_id)

        except Exception as e:
            logger.error(f"Error reading from stream {stream}: {e}")

        return messages

    async def read_with_timeout(
        self,
        stream: str,
        timeout: float = 1.0
    ) -> Optional[StreamMessage]:
        """
        Read a single message with timeout.

        Args:
            stream: Stream name
            timeout: Timeout in seconds

        Returns:
            StreamMessage or None if timeout
        """
        messages = await self.read_stream(
            stream,
            count=1,
            block_ms=int(timeout * 1000)
        )
        return messages[0] if messages else None

    # ==================== Tool Call Pattern ====================

    async def call_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: float = 30.0
    ) -> ToolCallResult:
        """
        Call a tool/subagent and wait for result.

        This implements the request/response pattern over Redis streams:
        1. Generate unique task_id
        2. Publish request to tool's stream
        3. Wait for result on results stream with matching task_id

        Args:
            tool_name: Name of the tool (maps to stream moire:{tool_name})
            params: Parameters for the tool
            timeout: Max time to wait for result

        Returns:
            ToolCallResult with success/failure and result data
        """
        task_id = str(uuid4())
        stream = f"moire:{tool_name}"
        start_time = time.time()

        # Create future for result
        result_future: asyncio.Future = asyncio.Future()
        self._pending_results[task_id] = result_future

        try:
            # Publish request
            await self.publish(stream, {
                "task_id": task_id,
                "params": params,
                "requester": self.consumer_name,
                "timeout": timeout
            })

            logger.debug(f"Tool call {task_id} to {tool_name}: {params}")

            # Wait for result
            try:
                result = await asyncio.wait_for(result_future, timeout=timeout)
                execution_time = (time.time() - start_time) * 1000

                return ToolCallResult(
                    task_id=task_id,
                    success=result.get("success", False),
                    result=result.get("result"),
                    error=result.get("error"),
                    execution_time_ms=execution_time
                )

            except asyncio.TimeoutError:
                logger.warning(f"Tool call {task_id} to {tool_name} timed out after {timeout}s")
                return ToolCallResult(
                    task_id=task_id,
                    success=False,
                    result=None,
                    error=f"Timeout after {timeout}s",
                    execution_time_ms=timeout * 1000
                )

        finally:
            # Clean up pending result
            self._pending_results.pop(task_id, None)

    async def _listen_for_results(self):
        """Background task to listen for tool call results.

        Uses XREAD (not XREADGROUP) so ALL clients see all results.
        Each client filters by task_id to find their results.
        """
        logger.info("Started result listener")

        # Track last message ID we've seen
        last_id = "$"  # Start from new messages only

        while self._running:
            try:
                # Use XREAD without consumer groups - all clients see all messages
                result = await self._redis.xread(
                    streams={self.STREAM_RESULTS: last_id},
                    count=10,
                    block=500  # 500ms block
                )

                if result:
                    for stream_name, stream_messages in result:
                        for msg_id, msg_data in stream_messages:
                            last_id = msg_id  # Update last seen ID

                            try:
                                data = json.loads(msg_data.get("data", "{}"))
                                task_id = data.get("task_id")

                                # Check if this result is for one of our pending tasks
                                if task_id and task_id in self._pending_results:
                                    future = self._pending_results[task_id]
                                    if not future.done():
                                        future.set_result(data)
                                        logger.debug(f"Received result for task {task_id}")

                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse result message {msg_id}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in result listener: {e}")
                await asyncio.sleep(0.1)

        logger.info("Result listener stopped")

    async def publish_result(
        self,
        task_id: str,
        success: bool,
        result: Any,
        error: Optional[str] = None
    ):
        """
        Publish a result for a tool call.

        Called by subagent runners to respond to tool calls.

        Args:
            task_id: The task_id from the original request
            success: Whether the operation succeeded
            result: Result data
            error: Error message if failed
        """
        await self.publish(self.STREAM_RESULTS, {
            "task_id": task_id,
            "success": success,
            "result": result,
            "error": error,
            "responder": self.consumer_name,
            "timestamp": time.time()
        })

    # ==================== Utility Methods ====================

    async def get_stream_info(self, stream: str) -> Dict[str, Any]:
        """Get information about a stream."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        try:
            info = await self._redis.xinfo_stream(stream)
            return {
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "groups": info.get("groups", 0)
            }
        except redis.ResponseError:
            return {"length": 0, "error": "Stream does not exist"}

    async def get_pending_messages(self, stream: str) -> int:
        """Get count of pending messages in consumer group."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        try:
            pending = await self._redis.xpending(stream, self.consumer_group)
            return pending.get("pending", 0) if pending else 0
        except redis.ResponseError:
            return 0

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection and stream health."""
        if not self._redis:
            return {"healthy": False, "error": "Not connected"}

        try:
            await self._redis.ping()

            streams_info = {}
            for stream in [
                self.STREAM_PLANNING,
                self.STREAM_VISION,
                self.STREAM_SPECIALIST,
                self.STREAM_RESULTS
            ]:
                streams_info[stream] = await self.get_stream_info(stream)

            return {
                "healthy": True,
                "host": self.host,
                "port": self.port,
                "consumer_group": self.consumer_group,
                "consumer_name": self.consumer_name,
                "streams": streams_info
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}


# Singleton instance
_redis_client: Optional[RedisStreamClient] = None


async def get_redis_client(
    host: str = "localhost",
    port: int = 6379
) -> RedisStreamClient:
    """Get or create the Redis client singleton."""
    global _redis_client

    if _redis_client is None:
        _redis_client = RedisStreamClient(host=host, port=port)
        await _redis_client.connect()

    return _redis_client


async def close_redis_client():
    """Close the Redis client singleton."""
    global _redis_client

    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None
