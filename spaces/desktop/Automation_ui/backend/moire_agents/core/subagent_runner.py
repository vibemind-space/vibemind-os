"""
Subagent Runner - Base class for subagent worker processes.

Each subagent type (planning, vision, specialist, background) runs as a worker
that listens to its Redis stream and publishes results back.

Usage:
    class MySubagentRunner(SubagentRunner):
        async def execute(self, task: SubagentTask) -> SubagentResult:
            # Process the task
            return SubagentResult(success=True, result={"data": "value"})

    runner = MySubagentRunner(redis_client, "planning")
    await runner.run_forever()
"""

import asyncio
import logging
import signal
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .redis_streams import RedisStreamClient, StreamMessage

logger = logging.getLogger(__name__)


class SubagentType(Enum):
    """Types of subagents."""
    PLANNING = "planning"
    VISION = "vision"
    SPECIALIST = "specialist"
    BACKGROUND = "background"


class SubagentState(Enum):
    """Subagent worker states."""
    IDLE = "idle"
    PROCESSING = "processing"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SubagentTask:
    """A task received from the Redis stream."""
    task_id: str
    params: Dict[str, Any]
    requester: str
    timeout: float
    received_at: float = field(default_factory=time.time)
    stream_message_id: Optional[str] = None

    @classmethod
    def from_stream_message(cls, message: StreamMessage) -> "SubagentTask":
        """Create a SubagentTask from a StreamMessage."""
        data = message.data
        return cls(
            task_id=data.get("task_id", ""),
            params=data.get("params", {}),
            requester=data.get("requester", "unknown"),
            timeout=data.get("timeout", 30.0),
            received_at=message.timestamp,
            stream_message_id=message.message_id
        )


@dataclass
class SubagentResult:
    """Result from processing a subagent task."""
    success: bool
    result: Any
    error: Optional[str] = None
    confidence: float = 1.0
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SubagentRunner(ABC):
    """
    Base class for subagent workers.

    Subagent runners:
    1. Connect to Redis
    2. Listen to their assigned stream (e.g., moire:planning)
    3. Process incoming tasks by calling the execute() method
    4. Publish results to moire:results

    Subclasses must implement the execute() method.
    """

    def __init__(
        self,
        redis_client: RedisStreamClient,
        agent_type: SubagentType,
        worker_id: Optional[str] = None,
        max_concurrent: int = 1
    ):
        """
        Initialize the subagent runner.

        Args:
            redis_client: Connected RedisStreamClient
            agent_type: Type of subagent (determines stream to listen to)
            worker_id: Unique ID for this worker (auto-generated if not provided)
            max_concurrent: Max concurrent tasks to process
        """
        self.redis = redis_client
        self.agent_type = agent_type
        self.worker_id = worker_id or f"{agent_type.value}_{id(self)}"
        self.max_concurrent = max_concurrent

        self.stream = f"moire:{agent_type.value}"
        self.state = SubagentState.IDLE
        self._running = False
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stats = {
            "tasks_processed": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "total_execution_time_ms": 0
        }

    @abstractmethod
    async def execute(self, task: SubagentTask) -> SubagentResult:
        """
        Execute a task. Must be implemented by subclasses.

        Args:
            task: The task to execute

        Returns:
            SubagentResult with success/failure and result data
        """
        pass

    async def run_forever(self):
        """
        Main loop: read from stream, execute tasks, publish results.

        Runs until stop() is called or the process is terminated.
        """
        logger.info(f"Starting {self.agent_type.value} runner: {self.worker_id}")
        logger.info(f"Listening on stream: {self.stream}")

        self._running = True
        self.state = SubagentState.IDLE

        # Set up signal handlers for graceful shutdown
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        except (NotImplementedError, RuntimeError):
            # Signal handlers not available (e.g., on Windows in some contexts)
            pass

        while self._running:
            try:
                # Read message from stream
                message = await self.redis.read_with_timeout(
                    self.stream,
                    timeout=1.0
                )

                if message:
                    # Process task with concurrency limit
                    async with self._semaphore:
                        await self._process_message(message)

            except asyncio.CancelledError:
                logger.info(f"Runner {self.worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Error in runner loop: {e}", exc_info=True)
                self.state = SubagentState.ERROR
                await asyncio.sleep(1.0)  # Backoff on error

        logger.info(f"Runner {self.worker_id} stopped")
        self.state = SubagentState.STOPPED

    async def stop(self):
        """Stop the runner gracefully."""
        logger.info(f"Stopping runner {self.worker_id}")
        self._running = False

        # Wait for active tasks to complete
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks")
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)

    async def _process_message(self, message: StreamMessage):
        """Process a single message from the stream."""
        task = SubagentTask.from_stream_message(message)
        start_time = time.time()

        logger.info(f"Processing task {task.task_id} from {task.requester}")
        self.state = SubagentState.PROCESSING

        try:
            # Execute the task
            result = await asyncio.wait_for(
                self.execute(task),
                timeout=task.timeout
            )

            execution_time = (time.time() - start_time) * 1000
            result.execution_time_ms = execution_time

            # Publish result
            await self.redis.publish_result(
                task_id=task.task_id,
                success=result.success,
                result={
                    "data": result.result,
                    "confidence": result.confidence,
                    "metadata": result.metadata,
                    "worker_id": self.worker_id,
                    "agent_type": self.agent_type.value,
                    "execution_time_ms": execution_time
                },
                error=result.error
            )

            # Update stats
            self._stats["tasks_processed"] += 1
            self._stats["total_execution_time_ms"] += execution_time
            if result.success:
                self._stats["tasks_succeeded"] += 1
            else:
                self._stats["tasks_failed"] += 1

            logger.info(
                f"Task {task.task_id} completed: success={result.success}, "
                f"time={execution_time:.1f}ms"
            )

        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            logger.warning(f"Task {task.task_id} timed out after {task.timeout}s")

            await self.redis.publish_result(
                task_id=task.task_id,
                success=False,
                result=None,
                error=f"Task timed out after {task.timeout}s"
            )

            self._stats["tasks_processed"] += 1
            self._stats["tasks_failed"] += 1

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Task {task.task_id} failed: {e}", exc_info=True)

            await self.redis.publish_result(
                task_id=task.task_id,
                success=False,
                result=None,
                error=str(e)
            )

            self._stats["tasks_processed"] += 1
            self._stats["tasks_failed"] += 1

        finally:
            self.state = SubagentState.IDLE

    def get_stats(self) -> Dict[str, Any]:
        """Get runner statistics."""
        avg_time = 0
        if self._stats["tasks_processed"] > 0:
            avg_time = (
                self._stats["total_execution_time_ms"] /
                self._stats["tasks_processed"]
            )

        return {
            **self._stats,
            "worker_id": self.worker_id,
            "agent_type": self.agent_type.value,
            "state": self.state.value,
            "average_execution_time_ms": avg_time
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check runner health."""
        redis_health = await self.redis.health_check()

        return {
            "healthy": self._running and redis_health.get("healthy", False),
            "state": self.state.value,
            "worker_id": self.worker_id,
            "agent_type": self.agent_type.value,
            "stream": self.stream,
            "stats": self.get_stats(),
            "redis": redis_health
        }


class MultiWorkerRunner:
    """
    Manages multiple subagent workers of the same type.

    Useful for scaling out subagent processing by running multiple
    concurrent workers listening to the same stream.
    """

    def __init__(
        self,
        runner_class: type,
        redis_client: RedisStreamClient,
        agent_type: SubagentType,
        num_workers: int = 3,
        **runner_kwargs
    ):
        """
        Initialize multi-worker runner.

        Args:
            runner_class: SubagentRunner subclass to instantiate
            redis_client: Shared Redis client
            agent_type: Type of subagent
            num_workers: Number of worker instances
            **runner_kwargs: Additional args passed to runner constructor
        """
        self.runners: List[SubagentRunner] = []
        self._tasks: List[asyncio.Task] = []

        for i in range(num_workers):
            worker_id = f"{agent_type.value}_worker_{i}"
            runner = runner_class(
                redis_client=redis_client,
                agent_type=agent_type,
                worker_id=worker_id,
                **runner_kwargs
            )
            self.runners.append(runner)

    async def start_all(self):
        """Start all workers."""
        logger.info(f"Starting {len(self.runners)} workers")
        self._tasks = [
            asyncio.create_task(runner.run_forever())
            for runner in self.runners
        ]

    async def stop_all(self):
        """Stop all workers."""
        logger.info("Stopping all workers")
        for runner in self.runners:
            await runner.stop()

        # Wait for all tasks
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def wait(self):
        """Wait for all workers to complete."""
        if self._tasks:
            await asyncio.gather(*self._tasks)

    def get_all_stats(self) -> List[Dict[str, Any]]:
        """Get stats from all workers."""
        return [runner.get_stats() for runner in self.runners]
