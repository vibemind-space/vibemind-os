"""
Deploy Agent - Autonomous agent for deployment orchestration.

This agent:
1. Listens for BUILD_SUCCEEDED and CONVERGENCE_UPDATE events
2. Waits for coding batches to complete (checks semaphore)
3. Runs deployment via DeployTool
4. Collects logs from deployment steps
5. Stores successful deployment patterns in memory
6. Publishes DEPLOY_* events
"""

import asyncio
from datetime import datetime
from typing import Optional, Any
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    deploy_started_event,
    deploy_succeeded_event,
    deploy_failed_event,
    deploy_logs_collected_event,
)
from ..mind.shared_state import SharedState
from ..tools.deploy_tool import DeployTool, DeploymentResult

logger = structlog.get_logger(__name__)


class DeployAgent(AutonomousAgent):
    """
    Autonomous deployment agent.

    Waits for successful builds, checks if coding is idle,
    then attempts deployment and logs collection.
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        coding_semaphore: asyncio.Semaphore,
        memory_tool: Optional[Any] = None,
        min_deploy_interval: int = 60,
    ):
        """
        Initialize deploy agent.

        Args:
            event_bus: EventBus for communication
            shared_state: SharedState for convergence tracking
            working_dir: Working directory for deployment
            coding_semaphore: Semaphore for coordination with coding batches
            memory_tool: Optional memory tool for storing deployment patterns
            min_deploy_interval: Minimum seconds between deployments (default 60)
        """
        super().__init__(
            name="DeployAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=5.0,  # Check every 5 seconds
            memory_tool=memory_tool,
        )

        self.coding_semaphore = coding_semaphore
        self.deploy_tool = DeployTool(working_dir)
        self.min_deploy_interval = min_deploy_interval

        self._last_deploy_time: Optional[datetime] = None
        self._last_build_success_time: Optional[datetime] = None
        self._deployment_count = 0

    @property
    def subscribed_events(self) -> list[EventType]:
        """Subscribe to build and convergence events."""
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.CONVERGENCE_UPDATE,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if deployment should run.

        Deployment conditions:
        1. Recent BUILD_SUCCEEDED event
        2. No coding batch currently running (semaphore available)
        3. Minimum interval since last deployment
        """
        # Check for recent build success
        build_succeeded = any(e.type == EventType.BUILD_SUCCEEDED for e in events)
        if build_succeeded:
            self._last_build_success_time = datetime.now()

        # No recent build success
        if not self._last_build_success_time:
            return False

        # Check minimum interval
        if self._last_deploy_time:
            elapsed = (datetime.now() - self._last_deploy_time).total_seconds()
            if elapsed < self.min_deploy_interval:
                self.logger.debug(
                    "deploy_cooldown",
                    elapsed=elapsed,
                    min_interval=self.min_deploy_interval,
                )
                return False

        # Check if coding is idle (semaphore available)
        # Try to acquire without blocking
        acquired = self.coding_semaphore.locked() == False
        if not acquired:
            self.logger.debug("deploy_waiting_for_coding_idle")
            return False

        self.logger.info("deploy_conditions_met", build_time=self._last_build_success_time.isoformat())
        return True

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Perform deployment.

        Runs build, optional package, and launch test.
        Collects logs and stores successful patterns.
        """
        self._last_deploy_time = datetime.now()
        self._deployment_count += 1

        self.logger.info(
            "deployment_started",
            attempt=self._deployment_count,
            working_dir=self.working_dir,
        )

        # Publish DEPLOY_STARTED event
        await self.event_bus.publish(deploy_started_event(
            source=self.name,
            attempt=self._deployment_count,
            working_dir=self.working_dir,
        ))

        try:
            # Run deployment
            result = await self.deploy_tool.deploy(
                include_package=False,  # Skip packaging for faster deployment
                test_launch=True,  # Always test launch
            )

            # Publish logs
            await self._publish_logs(result)

            if result.success:
                # Success!
                self.logger.info(
                    "deployment_succeeded",
                    attempt=self._deployment_count,
                    duration_ms=result.total_duration_ms,
                    steps=len(result.steps),
                )

                # Store deployment pattern in memory
                if self.memory_tool:
                    await self._store_deployment_pattern(result)

                # Publish success event
                return deploy_succeeded_event(
                    source=self.name,
                    container_id=None,
                    app_port=None,
                    health_check_passed=True,
                )

            else:
                # Failure
                self.logger.warning(
                    "deployment_failed",
                    attempt=self._deployment_count,
                    error=result.error_message,
                    duration_ms=result.total_duration_ms,
                )

                # Publish failure event
                return deploy_failed_event(
                    source=self.name,
                    error=result.error_message or "Deployment failed",
                    attempt=self._deployment_count,
                    duration_ms=result.total_duration_ms,
                    steps=[{"name": s.name, "success": s.success} for s in result.steps],
                )

        except Exception as e:
            self.logger.error(
                "deployment_error",
                attempt=self._deployment_count,
                error=str(e),
            )

            # Publish error event
            return deploy_failed_event(
                source=self.name,
                error=str(e),
                attempt=self._deployment_count,
            )

    async def _publish_logs(self, result: DeploymentResult) -> None:
        """Publish deployment logs as event."""
        await self.event_bus.publish(deploy_logs_collected_event(
            source=self.name,
            logs=result.logs,
            steps=[
                {
                    "name": s.name,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "stdout_preview": s.stdout[:200],
                    "stderr_preview": s.stderr[:200],
                }
                for s in result.steps
            ],
        ))

    async def _store_deployment_pattern(self, result: DeploymentResult) -> None:
        """
        Store successful deployment pattern in memory.

        Args:
            result: Successful deployment result
        """
        if not self.memory_tool or not self.memory_tool.enabled:
            return

        try:
            # Build content for storage
            content_parts = [
                f"Successful deployment at {datetime.now().isoformat()}",
                f"Duration: {result.total_duration_ms}ms",
                f"Steps completed: {', '.join([s.name for s in result.steps])}",
                "",
                "Step details:",
            ]

            for step in result.steps:
                content_parts.append(
                    f"- {step.name}: {step.duration_ms}ms "
                    f"({'success' if step.success else 'failed'})"
                )

            content = "\n".join(content_parts)

            # Metadata
            metadata = {
                "deployment_count": self._deployment_count,
                "total_duration_ms": result.total_duration_ms,
                "steps": [s.name for s in result.steps],
                "working_dir": self.working_dir,
            }

            # Store pattern
            await self.memory_tool.store(
                content=content,
                description="Successful deployment pattern",
                category="deployment",
                tags=["deployment", "success", "logs"],
                context=metadata,
            )

            self.logger.info(
                "deployment_pattern_stored",
                attempt=self._deployment_count,
                duration_ms=result.total_duration_ms,
            )

        except Exception as e:
            self.logger.warning("deployment_storage_failed", error=str(e))
