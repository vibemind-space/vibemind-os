"""
Roarboot Workers - Background tasks for Rowboat integration

Workers:
- HealthCheckWorker: Periodic health check of Rowboat Docker stack
  - Broadcasts status updates to Electron
  - Auto-restart Docker if configured (ROWBOAT_AUTO_START=true)

Usage:
    workers = create_roarboot_workers()
    for w in workers:
        await w.run()
"""

import asyncio
import logging
from typing import Optional, List

from swarm.workers.base_worker import BaseWorker, WorkerConfig
from spaces import SpaceType

logger = logging.getLogger(__name__)


class HealthCheckWorker(BaseWorker):
    """
    Periodically checks Rowboat Docker health and broadcasts status.

    Runs every 60 seconds to monitor the Rowboat container stack.
    If auto_start is enabled and containers are down, attempts restart.
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="roarboot_health_worker",
            space_type=SpaceType.ROWBOAT,
            description="Monitors Rowboat Docker stack health",
            task_timeout_seconds=30.0,
        )
        super().__init__(config, event_manager)
        self._check_interval = 60  # seconds
        self._auto_start = False

    async def execute_task(self, task) -> str:
        """Execute a health check cycle."""
        from spaces.rowboat.tools.roarboot_client import get_roarboot_client
        from spaces.rowboat.config import get_config

        config = get_config()
        self._auto_start = config.auto_start_docker

        client = get_roarboot_client()
        status = client.get_status()

        if status.get("success"):
            logger.debug("HealthCheckWorker: Rowboat is healthy")
            return "healthy"

        logger.warning(f"HealthCheckWorker: Rowboat unhealthy: {status.get('message')}")

        # Auto-restart if configured
        if self._auto_start:
            logger.info("HealthCheckWorker: Attempting auto-restart...")
            try:
                from spaces.rowboat.tools.docker_tools import start_docker
                result = start_docker()
                if result.get("success"):
                    logger.info("HealthCheckWorker: Auto-restart successful")
                    return "restarted"
                else:
                    logger.error(f"HealthCheckWorker: Auto-restart failed: {result.get('message')}")
                    return "restart_failed"
            except Exception as e:
                logger.error(f"HealthCheckWorker: Auto-restart error: {e}")
                return f"error: {e}"

        return "unhealthy"

    async def run_periodic(self):
        """
        Run health checks periodically.

        This is a standalone loop (not using the task queue)
        for continuous background monitoring.
        """
        logger.info(f"HealthCheckWorker: Starting periodic checks (every {self._check_interval}s)")

        while self._running:
            try:
                from swarm.workers.base_worker import TaskInfo
                from swarm.event_bus import SwarmEvent

                # Create a minimal task for the health check
                dummy_event = SwarmEvent(
                    event_type="roarboot.health_check",
                    payload={},
                    job_id="health_check",
                )
                task = TaskInfo(
                    task_id="health_check",
                    input_event=dummy_event,
                )

                result = await self.execute_task(task)
                logger.debug(f"HealthCheckWorker: Result: {result}")

            except Exception as e:
                logger.error(f"HealthCheckWorker: Check failed: {e}")

            await asyncio.sleep(self._check_interval)

    async def start(self):
        """Start the health check worker."""
        self._running = True
        await self.run_periodic()

    async def stop(self):
        """Stop the health check worker."""
        self._running = False
        logger.info("HealthCheckWorker: Stopped")


def create_roarboot_workers(event_manager=None) -> List[BaseWorker]:
    """
    Create all Roarboot Space workers.

    Returns:
        List of worker instances
    """
    return [
        HealthCheckWorker(event_manager),
    ]


__all__ = [
    "HealthCheckWorker",
    "create_roarboot_workers",
]
