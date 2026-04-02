"""
Agent Worker - Background worker that executes agent tasks.

This worker:
1. Pulls tasks from Redis queue
2. Selects appropriate agent based on task type
3. Executes the task
4. Reports results back
5. Triggers dependent tasks
"""
import asyncio
import json
import signal
import sys
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.models.task import TaskStatus
from src.engine.task_scheduler import TaskScheduler
from src.engine.orchestrator import Orchestrator
from src.agents.base_agent import BaseAgent, AgentConfig, AgentType
from src.agents.frontend_agent import FrontendAgent
from src.agents.backend_agent import BackendAgent
from src.agents.testing_agent import TestingAgent
from src.agents.security_agent import SecurityAgent
from src.agents.devops_agent import DevOpsAgent

logger = structlog.get_logger()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)


class AgentWorker:
    """
    Worker that processes tasks using specialized agents.

    The worker runs in a loop, pulling tasks from Redis and executing them
    with the appropriate agent based on task type.
    """

    CONSUMER_GROUP = "agent-workers"

    def __init__(self, worker_id: str = "worker-1"):
        self.worker_id = worker_id
        self.settings = get_settings()
        self.logger = logger.bind(component="agent_worker", worker_id=worker_id)

        # Database
        self._engine = create_async_engine(
            self.settings.database_url,
            pool_size=5,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Task scheduler
        self.scheduler: Optional[TaskScheduler] = None

        # Running flag
        self._running = False

        # Agent cache
        self._agents: dict[AgentType, BaseAgent] = {}

    async def start(self):
        """Start the worker."""
        self.logger.info("starting_worker")

        # Initialize scheduler
        self.scheduler = TaskScheduler(self.settings.redis_url)
        await self.scheduler.connect()

        # Initialize agents
        self._init_agents()

        # Set running flag
        self._running = True

        # Run main loop
        await self._run_loop()

    async def stop(self):
        """Stop the worker gracefully."""
        self.logger.info("stopping_worker")
        self._running = False

        if self.scheduler:
            await self.scheduler.close()

    def _init_agents(self):
        """Initialize agent instances."""
        self._agents = {
            AgentType.FRONTEND: FrontendAgent(),
            AgentType.BACKEND: BackendAgent(),
            AgentType.TESTING: TestingAgent(),
            AgentType.SECURITY: SecurityAgent(),
            AgentType.DEVOPS: DevOpsAgent(),
        }
        self.logger.info("agents_initialized", count=len(self._agents))

    def _get_agent(self, task_type: str) -> BaseAgent:
        """Get the appropriate agent for a task type."""
        try:
            agent_type = AgentType(task_type)
            if agent_type in self._agents:
                return self._agents[agent_type]
        except ValueError:
            pass

        # Default to backend agent for general tasks
        return self._agents.get(AgentType.BACKEND, BackendAgent())

    async def _run_loop(self):
        """Main processing loop."""
        self.logger.info("entering_main_loop")

        while self._running:
            try:
                # Get next task
                task_data = await self.scheduler.get_next_task(
                    self.CONSUMER_GROUP,
                    self.worker_id,
                )

                if task_data:
                    await self._process_task(task_data)
                else:
                    # No task available, brief pause
                    await asyncio.sleep(0.1)

            except Exception as e:
                self.logger.error("loop_error", error=str(e))
                await asyncio.sleep(1)

    async def _process_task(self, task_data: dict):
        """Process a single task."""
        task_id = task_data.get("task_id", "")
        job_id = task_data.get("job_id", 0)
        message_id = task_data.get("message_id", "")

        self.logger.info(
            "processing_task",
            task_id=task_id,
            job_id=job_id,
            task_type=task_data.get("task_type"),
        )

        try:
            # Get appropriate agent
            agent = self._get_agent(task_data.get("task_type", "general"))

            # Reset conversation for fresh context
            agent.reset_conversation()

            # Execute task
            prompt = task_data.get("prompt", "")
            context = task_data.get("metadata", {})

            response = await agent.execute(prompt, context)

            # Update database
            async with self._session_factory() as session:
                orchestrator = Orchestrator(session)

                if response.success:
                    # Task completed successfully
                    result = {
                        "content": response.content,
                        "files": [
                            {
                                "path": f.path,
                                "content": f.content,
                                "language": f.language,
                            }
                            for f in response.files
                        ],
                        "tokens_used": response.tokens_used,
                        "cost_usd": response.cost_usd,
                    }

                    await orchestrator.update_task_status(
                        job_id,
                        task_id.split(":")[-1],  # Extract requirement_id
                        TaskStatus.COMPLETED,
                        result=result,
                    )

                    # Check job completion
                    await orchestrator.check_job_completion(job_id)

                    self.logger.info(
                        "task_completed",
                        task_id=task_id,
                        files_generated=len(response.files),
                        tokens_used=response.tokens_used,
                    )
                else:
                    # Task failed
                    await orchestrator.update_task_status(
                        job_id,
                        task_id.split(":")[-1],
                        TaskStatus.FAILED,
                        error=response.error,
                    )

                    self.logger.error(
                        "task_failed",
                        task_id=task_id,
                        error=response.error,
                    )

                await session.commit()

            # Acknowledge message
            await self.scheduler.ack_task(self.CONSUMER_GROUP, message_id)

        except Exception as e:
            self.logger.error(
                "task_processing_error",
                task_id=task_id,
                error=str(e),
            )

            # Update as failed
            try:
                async with self._session_factory() as session:
                    orchestrator = Orchestrator(session)
                    await orchestrator.update_task_status(
                        job_id,
                        task_id.split(":")[-1],
                        TaskStatus.FAILED,
                        error=str(e),
                    )
                    await session.commit()
            except Exception:
                pass


async def main():
    """Main entry point for the worker."""
    import os

    worker_id = os.environ.get("WORKER_ID", "worker-1")
    worker = AgentWorker(worker_id)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler():
        asyncio.create_task(worker.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
