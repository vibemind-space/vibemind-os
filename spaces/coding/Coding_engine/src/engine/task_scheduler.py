"""
Task Scheduler - Manages task scheduling with dependency awareness.

This module handles:
1. Converting DAG to executable tasks
2. Dependency-aware scheduling (topological order)
3. Parallel execution of independent tasks
4. Queue management with Redis Streams
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
from enum import Enum

import redis.asyncio as redis
import structlog

from src.engine.dag_parser import DAGParser, RequirementsData, DAGNode, NodeType
from src.models.task import TaskType, TaskStatus

logger = structlog.get_logger()


# Redis Stream keys
TASK_STREAM = "coding_engine:tasks"
TASK_RESULTS = "coding_engine:results"
TASK_STATUS = "coding_engine:status"


@dataclass
class ScheduledTask:
    """A task ready to be executed."""
    task_id: str
    job_id: int
    requirement_id: str
    title: str
    description: str
    prompt: str
    task_type: str
    depends_on: list[str] = field(default_factory=list)
    depth_level: int = 0
    priority: int = 0
    metadata: dict = field(default_factory=dict)


class TaskScheduler:
    """
    Schedules tasks from a DAG for execution.

    The scheduler:
    1. Takes a parsed RequirementsData with DAG
    2. Creates ScheduledTask objects for each requirement
    3. Manages task dependencies
    4. Pushes ready tasks to Redis Streams
    5. Tracks completion and triggers dependent tasks
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self.logger = logger.bind(component="task_scheduler")

    async def connect(self):
        """Connect to Redis."""
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            self.logger.info("redis_connected", url=self.redis_url)

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def schedule_job(
        self,
        job_id: int,
        req_data: RequirementsData,
        project_context: Optional[dict] = None,
    ) -> list[ScheduledTask]:
        """
        Schedule all tasks for a job.

        Args:
            job_id: The job ID
            req_data: Parsed requirements data with DAG
            project_context: Optional project context for prompts

        Returns:
            List of scheduled tasks
        """
        await self.connect()

        dag = req_data.dag
        if dag is None or dag.number_of_nodes() == 0:
            self.logger.warning("empty_dag", job_id=job_id)
            return []

        # Create DAGParser for task type inference
        parser = DAGParser()

        # Create tasks from requirement nodes
        tasks: list[ScheduledTask] = []
        req_nodes = {n.id: n for n in req_data.nodes if n.type == NodeType.REQUIREMENT}

        for node_id, node in req_nodes.items():
            # Get dependencies from DAG
            predecessors = list(dag.predecessors(node_id)) if node_id in dag else []

            # Get depth level
            depth = dag.nodes[node_id].get('depth', 0) if node_id in dag else 0

            # Determine task type
            task_type = parser.get_task_type_for_requirement(node)

            # Generate prompt for the agent
            prompt = self._generate_task_prompt(node, project_context)

            task = ScheduledTask(
                task_id=f"{job_id}:{node_id}",
                job_id=job_id,
                requirement_id=node_id,
                title=node.name,
                description=f"Implement: {node.name}",
                prompt=prompt,
                task_type=task_type,
                depends_on=[f"{job_id}:{dep}" for dep in predecessors],
                depth_level=depth,
                priority=100 - depth,  # Higher depth = lower priority
                metadata={
                    "tag": node.tag,
                    "payload": node.payload,
                },
            )
            tasks.append(task)

        self.logger.info(
            "tasks_created",
            job_id=job_id,
            num_tasks=len(tasks),
        )

        # Initialize task status in Redis
        await self._init_task_status(tasks)

        # Schedule initial tasks (those with no dependencies)
        initial_tasks = [t for t in tasks if not t.depends_on]
        for task in initial_tasks:
            await self._enqueue_task(task)

        self.logger.info(
            "initial_tasks_scheduled",
            job_id=job_id,
            num_initial=len(initial_tasks),
        )

        return tasks

    def _generate_task_prompt(
        self,
        node: DAGNode,
        project_context: Optional[dict] = None,
    ) -> str:
        """Generate the prompt for an agent to implement a requirement."""
        prompt_parts = [
            f"# Requirement: {node.name}",
            "",
            f"**Requirement ID:** {node.id}",
            f"**Tag:** {node.tag or 'functional'}",
            "",
            "## Task",
            f"Implement the following requirement: {node.name}",
            "",
            "## Instructions",
            "1. Analyze the requirement carefully",
            "2. Design an appropriate solution",
            "3. Implement the code with proper structure",
            "4. Include necessary imports and dependencies",
            "5. Add appropriate error handling",
            "6. Write clear, maintainable code",
            "",
        ]

        # Add project context if available
        if project_context:
            prompt_parts.extend([
                "## Project Context",
                json.dumps(project_context, indent=2),
                "",
            ])

        # Add specific guidance based on tag
        if node.tag == "performance":
            prompt_parts.extend([
                "## Performance Requirements",
                "- Optimize for speed and efficiency",
                "- Consider memory usage",
                "- Add benchmarks where appropriate",
                "",
            ])
        elif node.tag == "security":
            prompt_parts.extend([
                "## Security Requirements",
                "- Follow security best practices",
                "- Validate all inputs",
                "- Handle sensitive data properly",
                "",
            ])

        prompt_parts.extend([
            "## Output",
            "Provide the implementation code and any necessary configuration.",
        ])

        return "\n".join(prompt_parts)

    async def _init_task_status(self, tasks: list[ScheduledTask]):
        """Initialize task status in Redis."""
        if not self._redis:
            return

        pipe = self._redis.pipeline()
        for task in tasks:
            status_key = f"{TASK_STATUS}:{task.task_id}"
            pipe.hset(status_key, mapping={
                "status": TaskStatus.PENDING.value,
                "job_id": str(task.job_id),
                "requirement_id": task.requirement_id,
                "task_type": task.task_type,
                "depends_on": json.dumps(task.depends_on),
                "depth_level": str(task.depth_level),
                "created_at": str(time.time()),
            })
        await pipe.execute()

    async def _enqueue_task(self, task: ScheduledTask):
        """Add a task to the queue."""
        if not self._redis:
            return

        # Update status to QUEUED
        status_key = f"{TASK_STATUS}:{task.task_id}"
        await self._redis.hset(status_key, "status", TaskStatus.QUEUED.value)

        # Add to stream
        await self._redis.xadd(
            TASK_STREAM,
            {
                "task_id": task.task_id,
                "job_id": str(task.job_id),
                "requirement_id": task.requirement_id,
                "title": task.title,
                "prompt": task.prompt,
                "task_type": task.task_type,
                "priority": str(task.priority),
                "metadata": json.dumps(task.metadata),
            },
        )

        self.logger.debug("task_enqueued", task_id=task.task_id)

    async def mark_task_completed(
        self,
        task_id: str,
        result: dict,
        all_tasks: list[ScheduledTask],
    ):
        """
        Mark a task as completed and schedule dependent tasks.

        Args:
            task_id: The completed task ID
            result: The task result
            all_tasks: All tasks for the job (to find dependents)
        """
        if not self._redis:
            return

        # Update status to COMPLETED
        status_key = f"{TASK_STATUS}:{task_id}"
        await self._redis.hset(status_key, mapping={
            "status": TaskStatus.COMPLETED.value,
            "completed_at": str(time.time()),
            "result": json.dumps(result),
        })

        # Store result
        await self._redis.hset(
            f"{TASK_RESULTS}:{task_id.split(':')[0]}",  # job_id
            task_id,
            json.dumps(result),
        )

        self.logger.info("task_completed", task_id=task_id)

        # Find and schedule dependent tasks
        for task in all_tasks:
            if task_id in task.depends_on:
                # Check if all dependencies are complete
                all_deps_complete = await self._all_deps_complete(task.depends_on)
                if all_deps_complete:
                    await self._enqueue_task(task)
                    self.logger.info(
                        "dependent_task_scheduled",
                        task_id=task.task_id,
                        triggered_by=task_id,
                    )

    async def mark_task_failed(
        self,
        task_id: str,
        error: str,
        retry_count: int = 0,
        max_retries: int = 3,
    ) -> bool:
        """
        Mark a task as failed, optionally retry.

        Returns True if task will be retried.
        """
        if not self._redis:
            return False

        status_key = f"{TASK_STATUS}:{task_id}"

        if retry_count < max_retries:
            # Retry
            await self._redis.hset(status_key, mapping={
                "status": TaskStatus.PENDING.value,
                "retry_count": str(retry_count + 1),
                "last_error": error,
            })
            self.logger.warning(
                "task_retry",
                task_id=task_id,
                retry=retry_count + 1,
                max_retries=max_retries,
            )
            return True
        else:
            # Mark as failed
            await self._redis.hset(status_key, mapping={
                "status": TaskStatus.FAILED.value,
                "failed_at": str(time.time()),
                "error": error,
            })
            self.logger.error("task_failed", task_id=task_id, error=error)
            return False

    async def _all_deps_complete(self, dep_ids: list[str]) -> bool:
        """Check if all dependencies are complete."""
        if not self._redis:
            return True

        for dep_id in dep_ids:
            status_key = f"{TASK_STATUS}:{dep_id}"
            status = await self._redis.hget(status_key, "status")
            if status != TaskStatus.COMPLETED.value:
                return False

        return True

    async def get_job_progress(self, job_id: int) -> dict:
        """Get progress statistics for a job."""
        if not self._redis:
            return {}

        # Get all task statuses for this job
        pattern = f"{TASK_STATUS}:{job_id}:*"
        keys = []
        async for key in self._redis.scan_iter(match=pattern):
            keys.append(key)

        if not keys:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "running": 0}

        stats = {
            "total": len(keys),
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "running": 0,
            "queued": 0,
        }

        pipe = self._redis.pipeline()
        for key in keys:
            pipe.hget(key, "status")

        statuses = await pipe.execute()

        for status in statuses:
            if status == TaskStatus.COMPLETED.value:
                stats["completed"] += 1
            elif status == TaskStatus.FAILED.value:
                stats["failed"] += 1
            elif status == TaskStatus.RUNNING.value:
                stats["running"] += 1
            elif status == TaskStatus.QUEUED.value:
                stats["queued"] += 1
            else:
                stats["pending"] += 1

        stats["progress_percent"] = (
            (stats["completed"] / stats["total"]) * 100
            if stats["total"] > 0
            else 0
        )

        return stats

    async def get_next_task(self, consumer_group: str, consumer_name: str) -> Optional[dict]:
        """
        Get the next task from the queue.

        Uses Redis consumer groups for distributed processing.
        """
        if not self._redis:
            return None

        try:
            # Ensure consumer group exists
            try:
                await self._redis.xgroup_create(
                    TASK_STREAM,
                    consumer_group,
                    id="0",
                    mkstream=True,
                )
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

            # Read next message
            messages = await self._redis.xreadgroup(
                consumer_group,
                consumer_name,
                {TASK_STREAM: ">"},
                count=1,
                block=5000,  # 5 second timeout
            )

            if messages:
                stream_name, entries = messages[0]
                if entries:
                    msg_id, data = entries[0]
                    return {
                        "message_id": msg_id,
                        "task_id": data.get("task_id"),
                        "job_id": int(data.get("job_id", 0)),
                        "requirement_id": data.get("requirement_id"),
                        "title": data.get("title"),
                        "prompt": data.get("prompt"),
                        "task_type": data.get("task_type"),
                        "metadata": json.loads(data.get("metadata", "{}")),
                    }

            return None

        except Exception as e:
            self.logger.error("get_next_task_error", error=str(e))
            return None

    async def ack_task(self, consumer_group: str, message_id: str):
        """Acknowledge task completion."""
        if not self._redis:
            return

        await self._redis.xack(TASK_STREAM, consumer_group, message_id)
