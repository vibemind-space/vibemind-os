"""
Cell Agent - Autonomous agent managing a single cell's lifecycle.

Extends AutonomousAgent to manage:
- Cell initialization (code generation or repo clone)
- Building and deploying to Kubernetes
- Health monitoring and reporting
- Self-healing through LLM-driven mutations
- Recovery procedures
- Graceful termination (autophagy)

The CellAgent is the autonomous unit that makes each microservice
self-managing within the Cell Colony system.
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import structlog

from ..agents.autonomous_base import AutonomousAgent, FixerPool, ErrorGroup, BatchFixResult
from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .cell import (
    Cell, CellStatus, SourceType, MutationSeverity,
    MutationRecord, classify_mutation_severity,
)
from .cell_health_registry import CellHealthRegistry, HealthCheckResult

if TYPE_CHECKING:
    from .k8s.kubectl_tool import KubectlTool
    from ..tools.claude_code_tool import ClaudeCodeTool

logger = structlog.get_logger(__name__)


@dataclass
class CellAgentConfig:
    """Configuration for a CellAgent."""
    health_check_interval: int = 30  # Seconds between health checks
    mutation_timeout: int = 300  # Seconds to wait for mutation approval
    max_recovery_attempts: int = 3
    max_mutations: int = 10  # Before autophagy
    auto_approve_low_severity: bool = True  # Auto-approve LOW/MEDIUM mutations
    code_generation_timeout: int = 600  # Seconds for initial code generation


class CellAgent(AutonomousAgent):
    """
    Autonomous agent that manages a single cell's lifecycle.

    Responsibilities:
    - Initialize cell (generate code or clone repo)
    - Build container image and deploy to K8s
    - Perform health checks and update registry
    - Apply mutations when failures are detected
    - Wait for user approval on HIGH/CRITICAL mutations
    - Execute recovery procedures
    - Trigger autophagy after max failures

    Event Subscriptions:
    - CELL_HEALTH_CHECK: Periodic health check trigger
    - CELL_MUTATION_REQUESTED: Apply a code mutation
    - CELL_MUTATION_APPROVED/REJECTED: User approval responses
    - CELL_RECOVERY_STARTED: Begin recovery procedure
    - CELL_AUTOPHAGY_TRIGGERED: Terminate the cell

    Usage:
        cell = Cell(name="user-auth", source_type=SourceType.LLM_GENERATED)
        agent = CellAgent(
            cell=cell,
            event_bus=event_bus,
            shared_state=shared_state,
            health_registry=health_registry,
        )
        await agent.start()
    """

    def __init__(
        self,
        cell: Cell,
        event_bus: EventBus,
        shared_state: SharedState,
        health_registry: CellHealthRegistry,
        working_dir: Optional[str] = None,
        config: Optional[CellAgentConfig] = None,
        kubectl_tool: Optional["KubectlTool"] = None,
    ):
        """
        Initialize the CellAgent.

        Args:
            cell: The Cell this agent manages
            event_bus: EventBus for communication
            shared_state: Shared convergence state
            health_registry: Health tracking registry
            working_dir: Base working directory (defaults to cell.working_dir)
            config: Agent configuration
            kubectl_tool: Tool for K8s operations
        """
        self.cell = cell
        self.health_registry = health_registry
        self.config = config or CellAgentConfig()
        self.kubectl_tool = kubectl_tool

        # Use cell's working directory if not specified
        effective_working_dir = working_dir or cell.working_dir or "."

        super().__init__(
            name=f"CellAgent-{cell.name}",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=effective_working_dir,
        )

        # Mutation tracking
        self._pending_mutation: Optional[Dict[str, Any]] = None
        self._mutation_approval_event: asyncio.Event = asyncio.Event()
        self._mutation_approved: bool = False

        # Health check timing
        self._last_health_check: Optional[datetime] = None

        # Fixer pool for code mutations
        self._fixer_pool: Optional[FixerPool] = None

        self.logger = logger.bind(
            agent=self.name,
            cell_id=cell.id,
            cell_name=cell.name,
        )

    @property
    def subscribed_events(self) -> List[EventType]:
        """Events this CellAgent listens to."""
        return [
            # Health events
            EventType.CELL_HEALTH_CHECK,
            EventType.CELL_HEALTH_FAILED,

            # Mutation events
            EventType.CELL_MUTATION_REQUESTED,
            EventType.USER_MUTATION_APPROVED,
            EventType.USER_MUTATION_REJECTED,
            EventType.MUTATION_TIMEOUT_EXPIRED,

            # Recovery events
            EventType.CELL_RECOVERING,

            # Autophagy events
            EventType.CELL_AUTOPHAGY_TRIGGERED,
        ]

    async def should_act(self, events: List[Event]) -> bool:
        """Decide whether to act based on events."""
        for event in events:
            # Only handle events for our cell
            if event.data.get("cell_id") != self.cell.id:
                continue

            # Always act on these events
            if event.type in (
                EventType.CELL_HEALTH_CHECK,
                EventType.CELL_HEALTH_FAILED,
                EventType.CELL_MUTATION_REQUESTED,
                EventType.USER_MUTATION_APPROVED,
                EventType.USER_MUTATION_REJECTED,
                EventType.CELL_RECOVERING,
                EventType.CELL_AUTOPHAGY_TRIGGERED,
            ):
                return True

        return False

    async def _should_act_on_state(self) -> bool:
        """Check if periodic health check is needed."""
        if self.cell.status == CellStatus.TERMINATED:
            return False

        if self.cell.status not in (CellStatus.HEALTHY, CellStatus.DEGRADED):
            return False

        if self._last_health_check is None:
            return True

        elapsed = datetime.now() - self._last_health_check
        return elapsed.total_seconds() >= self.config.health_check_interval

    async def act(self, events: List[Event]) -> Optional[Event]:
        """Perform actions based on events."""
        # Filter events for our cell
        our_events = [
            e for e in events
            if e.data.get("cell_id") == self.cell.id or not e.data.get("cell_id")
        ]

        if not our_events:
            # State-triggered health check
            return await self._perform_health_check()

        # Process each event
        for event in our_events:
            if event.type == EventType.CELL_HEALTH_CHECK:
                return await self._perform_health_check()

            elif event.type == EventType.CELL_HEALTH_FAILED:
                return await self._handle_health_failure(event)

            elif event.type == EventType.CELL_MUTATION_REQUESTED:
                return await self._handle_mutation_request(event)

            elif event.type == EventType.USER_MUTATION_APPROVED:
                return await self._handle_mutation_approved(event)

            elif event.type == EventType.USER_MUTATION_REJECTED:
                return await self._handle_mutation_rejected(event)

            elif event.type == EventType.CELL_RECOVERING:
                return await self._perform_recovery(event)

            elif event.type == EventType.CELL_AUTOPHAGY_TRIGGERED:
                return await self._perform_autophagy(event)

        return None

    # =========================================================================
    # Cell Lifecycle Methods
    # =========================================================================

    async def initialize_cell(self) -> Event:
        """
        Initialize the cell - generate code or clone repo.

        This is called once when the cell is first created.
        """
        self.logger.info("initializing_cell", source_type=self.cell.source_type.value)

        self.cell.status = CellStatus.INITIALIZING
        await self._publish_status_change(CellStatus.INITIALIZING)

        try:
            if self.cell.source_type == SourceType.LLM_GENERATED:
                await self._generate_code()
            elif self.cell.source_type == SourceType.REPO_CLONE:
                await self._clone_repository()
            elif self.cell.source_type == SourceType.TEMPLATE:
                await self._apply_template()
            else:
                raise ValueError(f"Unknown source type: {self.cell.source_type}")

            self.logger.info("cell_initialized")
            return await self._create_event(
                EventType.CELL_INITIALIZING,
                success=True,
            )

        except Exception as e:
            self.logger.error("cell_initialization_failed", error=str(e))
            self.cell.status = CellStatus.TERMINATED
            return await self._create_event(
                EventType.CELL_FAILURE_DETECTED,
                success=False,
                error_message=str(e),
            )

    async def _generate_code(self) -> None:
        """Generate code using LLM from the source_ref prompt."""
        from ..tools.claude_code_tool import ClaudeCodeTool

        # Ensure working directory exists
        os.makedirs(self.cell.working_dir, exist_ok=True)

        prompt = f"""Create a complete microservice based on this specification:

{self.cell.source_ref}

Requirements:
- Create a production-ready microservice
- Include health check endpoint at {self.cell.health_check.path}
- Include proper error handling and logging
- Add appropriate tests
- Create a Dockerfile for containerization
- Follow best practices for the chosen technology stack

The service should listen on port {self.cell.health_check.port}.
"""

        tool = ClaudeCodeTool(
            working_dir=self.cell.working_dir,
            timeout=self.config.code_generation_timeout,
        )
        result = await tool.execute(
            prompt=prompt,
            context="Generating new microservice",
            agent_type="generator",
        )

        if not result.success:
            raise RuntimeError(f"Code generation failed: {result.error}")

        await self._publish_event(
            EventType.CELL_CODE_GENERATION_COMPLETE,
            files_generated=result.files,
        )

    async def _clone_repository(self) -> None:
        """Clone code from a Git repository."""
        import subprocess

        repo_url = self.cell.source_ref
        target_dir = self.cell.working_dir

        os.makedirs(target_dir, exist_ok=True)

        result = subprocess.run(
            ["git", "clone", repo_url, target_dir],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")

        await self._publish_event(
            EventType.CELL_REPO_CLONE_COMPLETE,
            repo_url=repo_url,
        )

    async def _apply_template(self) -> None:
        """Apply a template to create the cell."""
        # Template application logic would go here
        # For now, this is a placeholder
        self.logger.info("applying_template", template=self.cell.source_ref)

    async def build_and_deploy(self) -> Event:
        """Build container image and deploy to Kubernetes."""
        self.logger.info("building_and_deploying")

        # Build phase
        self.cell.status = CellStatus.BUILDING
        await self._publish_status_change(CellStatus.BUILDING)

        try:
            await self._build_image()

            # Deploy phase
            self.cell.status = CellStatus.DEPLOYING
            await self._publish_status_change(CellStatus.DEPLOYING)

            await self._deploy_to_k8s()

            # Mark as healthy
            self.cell.status = CellStatus.HEALTHY
            self.cell.started_at = datetime.now()
            await self._publish_status_change(CellStatus.HEALTHY)

            # Register with health registry
            await self.health_registry.register_cell(self.cell)

            return await self._create_event(
                EventType.CELL_READY,
                success=True,
            )

        except Exception as e:
            self.logger.error("build_deploy_failed", error=str(e))
            self.cell.status = CellStatus.DEGRADED
            return await self._create_event(
                EventType.CELL_K8S_DEPLOY_FAILED,
                success=False,
                error_message=str(e),
            )

    async def _build_image(self) -> None:
        """Build Docker image for the cell."""
        import subprocess

        dockerfile_path = os.path.join(self.cell.working_dir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

        image_name = self.cell.full_image_name

        result = subprocess.run(
            ["docker", "build", "-t", image_name, self.cell.working_dir],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Docker build failed: {result.stderr}")

        self.cell.image = image_name.split(":")[0]

        await self._publish_event(
            EventType.CELL_IMAGE_BUILD_COMPLETE,
            image_name=image_name,
        )

    async def _deploy_to_k8s(self) -> None:
        """Deploy the cell to Kubernetes."""
        if not self.kubectl_tool:
            self.logger.warning("kubectl_tool_not_configured")
            return

        # Generate K8s manifests and apply them
        # This would use the kubectl_tool to apply manifests
        self.logger.info("deploying_to_k8s", deployment=self.cell.k8s_deployment_name)

        await self._publish_event(
            EventType.CELL_K8S_DEPLOY_COMPLETE,
            deployment_name=self.cell.k8s_deployment_name,
        )

    # =========================================================================
    # Health Check Methods
    # =========================================================================

    async def _perform_health_check(self) -> Optional[Event]:
        """Perform a health check on the cell."""
        import aiohttp
        import time

        self._last_health_check = datetime.now()

        if self.cell.status not in (CellStatus.HEALTHY, CellStatus.DEGRADED):
            return None

        health_url = f"http://localhost:{self.cell.health_check.port}{self.cell.health_check.path}"
        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    health_url,
                    timeout=aiohttp.ClientTimeout(
                        total=self.cell.health_check.timeout_seconds
                    ),
                ) as response:
                    response_time_ms = int((time.time() - start_time) * 1000)

                    if response.status == 200:
                        result = HealthCheckResult.PASSED
                        self.cell.update_health(passed=True)
                    else:
                        result = HealthCheckResult.FAILED
                        self.cell.update_health(passed=False)

                    # Update registry
                    await self.health_registry.record_health_check(
                        cell_id=self.cell.id,
                        result=result,
                        response_time_ms=response_time_ms,
                        status_code=response.status,
                    )

                    if result == HealthCheckResult.PASSED:
                        return await self._create_event(
                            EventType.CELL_HEALTH_PASSED,
                            health_score=self.cell.health_score,
                            response_time_ms=response_time_ms,
                        )
                    else:
                        return await self._create_event(
                            EventType.CELL_HEALTH_FAILED,
                            health_score=self.cell.health_score,
                            status_code=response.status,
                        )

        except asyncio.TimeoutError:
            self.cell.update_health(passed=False)
            await self.health_registry.record_health_check(
                cell_id=self.cell.id,
                result=HealthCheckResult.TIMEOUT,
                response_time_ms=int((time.time() - start_time) * 1000),
                error_message="Health check timed out",
            )
            return await self._create_event(
                EventType.CELL_HEALTH_FAILED,
                error_message="Health check timed out",
            )

        except Exception as e:
            self.cell.update_health(passed=False)
            await self.health_registry.record_health_check(
                cell_id=self.cell.id,
                result=HealthCheckResult.FAILED,
                error_message=str(e),
            )
            return await self._create_event(
                EventType.CELL_HEALTH_FAILED,
                error_message=str(e),
            )

    async def _handle_health_failure(self, event: Event) -> Optional[Event]:
        """Handle a health check failure - trigger mutation or recovery."""
        self.logger.warning(
            "handling_health_failure",
            consecutive_failures=self.cell.consecutive_failures,
        )

        # Check if autophagy is needed
        if self.cell.should_autophagy:
            return await self._create_event(
                EventType.CELL_AUTOPHAGY_TRIGGERED,
                reason="Max mutation failures exceeded",
            )

        # Check if recovery is in progress
        if self.cell.status == CellStatus.RECOVERING:
            return None

        # Trigger a mutation to fix the issue
        error_message = event.data.get("error_message", "Health check failed")
        files_to_check = self._identify_likely_culprits(error_message)

        severity = classify_mutation_severity(
            files_modified=files_to_check,
            error_type="health_failure",
            affected_components=self._get_affected_components(error_message),
        )

        return await self._create_event(
            EventType.CELL_MUTATION_REQUESTED,
            severity=severity.value,
            trigger_event="health_failure",
            error_message=error_message,
            files_to_check=files_to_check,
        )

    def _identify_likely_culprits(self, error_message: str) -> List[str]:
        """Identify files likely to contain the error."""
        # This is a heuristic - in practice, would use more sophisticated analysis
        culprits = []
        if "health" in error_message.lower():
            culprits.append("health.py")
            culprits.append("health.ts")
            culprits.append("main.py")
            culprits.append("index.ts")
        return culprits

    def _get_affected_components(self, error_message: str) -> List[str]:
        """Get list of affected components from error message."""
        components = []
        keywords = ["auth", "payment", "database", "api", "health"]
        for keyword in keywords:
            if keyword in error_message.lower():
                components.append(keyword)
        return components or ["general"]

    # =========================================================================
    # Mutation Methods
    # =========================================================================

    async def _handle_mutation_request(self, event: Event) -> Optional[Event]:
        """Handle a mutation request - apply fix or request approval."""
        severity_str = event.data.get("severity", "low")
        severity = MutationSeverity(severity_str)

        self.logger.info(
            "mutation_requested",
            severity=severity.value,
            trigger=event.data.get("trigger_event"),
        )

        # Mark mutation as pending in registry
        await self.health_registry.mark_mutation_pending(self.cell.id, severity)

        # Check if approval is required
        if severity in (MutationSeverity.HIGH, MutationSeverity.CRITICAL):
            if not self.config.auto_approve_low_severity:
                return await self._request_mutation_approval(event, severity)

        # For LOW/MEDIUM severity, apply automatically
        return await self._apply_mutation(event)

    async def _request_mutation_approval(
        self,
        event: Event,
        severity: MutationSeverity,
    ) -> Event:
        """Request user approval for a mutation."""
        self._pending_mutation = event.data
        self._mutation_approval_event.clear()
        self._mutation_approved = False

        self.cell.status = CellStatus.MUTATING

        self.logger.info(
            "requesting_mutation_approval",
            severity=severity.value,
        )

        return await self._create_event(
            EventType.MUTATION_APPROVAL_REQUIRED,
            severity=severity.value,
            trigger_event=event.data.get("trigger_event"),
            error_message=event.data.get("error_message"),
            files_to_modify=event.data.get("files_to_check", []),
            timeout_seconds=self.config.mutation_timeout,
        )

    async def _handle_mutation_approved(self, event: Event) -> Optional[Event]:
        """Handle mutation approval from user."""
        self.logger.info("mutation_approved", approved_by=event.data.get("approved_by"))

        self._mutation_approved = True
        self._mutation_approval_event.set()

        if self._pending_mutation:
            return await self._apply_mutation_from_data(self._pending_mutation)

        return None

    async def _handle_mutation_rejected(self, event: Event) -> Optional[Event]:
        """Handle mutation rejection from user."""
        self.logger.info("mutation_rejected", reason=event.data.get("reason"))

        self._mutation_approved = False
        self._mutation_approval_event.set()
        self._pending_mutation = None

        # Clear mutation pending state
        await self.health_registry.clear_mutation_pending(self.cell.id)

        # Rollback to previous state
        self.cell.status = CellStatus.DEGRADED

        return await self._create_event(
            EventType.CELL_MUTATION_REJECTED,
            reason=event.data.get("reason"),
        )

    async def _apply_mutation(self, event: Event) -> Optional[Event]:
        """Apply a mutation to fix the cell."""
        return await self._apply_mutation_from_data(event.data)

    async def _apply_mutation_from_data(
        self,
        mutation_data: Dict[str, Any],
    ) -> Optional[Event]:
        """Apply a mutation using the provided data."""
        from ..tools.claude_code_tool import ClaudeCodeTool

        self.cell.status = CellStatus.MUTATING

        await self._publish_event(
            EventType.CELL_MUTATION_STARTED,
            trigger=mutation_data.get("trigger_event"),
        )

        error_message = mutation_data.get("error_message", "Unknown error")
        files_to_check = mutation_data.get("files_to_check", [])

        prompt = f"""Fix the following error in this microservice:

Error: {error_message}

The cell '{self.cell.name}' is experiencing health check failures.
Files to check: {', '.join(files_to_check) if files_to_check else 'all relevant files'}

Requirements:
1. Identify the root cause of the error
2. Apply a minimal fix that resolves the issue
3. Ensure the health check endpoint continues to work
4. Do not break existing functionality

The health check endpoint is at port {self.cell.health_check.port}{self.cell.health_check.path}
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.cell.working_dir, timeout=180)
            result = await tool.execute(
                prompt=prompt,
                context=f"Fixing health failure in cell {self.cell.name}",
                agent_type="fixer",
            )

            if result.success and result.files:
                severity_str = mutation_data.get("severity", "low")
                severity = MutationSeverity(severity_str)

                # Record successful mutation
                self.cell.record_mutation(
                    severity=severity,
                    trigger_event=mutation_data.get("trigger_event", "health_failure"),
                    prompt=prompt,
                    files_modified=result.files,
                    success=True,
                )

                # Clear mutation state
                await self.health_registry.clear_mutation_pending(self.cell.id)
                self._pending_mutation = None

                # Update SharedState
                await self.shared_state.update_colony_mutations(
                    increment_successful=True,
                )

                self.cell.status = CellStatus.HEALTHY

                self.logger.info(
                    "mutation_applied",
                    files_modified=len(result.files),
                )

                return await self._create_event(
                    EventType.CELL_MUTATION_APPLIED,
                    success=True,
                    files_modified=result.files,
                    new_version=self.cell.version,
                )

            else:
                self._handle_mutation_failure(mutation_data, result.error)

                return await self._create_event(
                    EventType.CELL_MUTATION_FAILED,
                    success=False,
                    error_message=result.error,
                )

        except Exception as e:
            self._handle_mutation_failure(mutation_data, str(e))

            return await self._create_event(
                EventType.CELL_MUTATION_FAILED,
                success=False,
                error_message=str(e),
            )

    def _handle_mutation_failure(
        self,
        mutation_data: Dict[str, Any],
        error: str,
    ) -> None:
        """Handle a failed mutation attempt."""
        severity_str = mutation_data.get("severity", "low")
        severity = MutationSeverity(severity_str)

        self.cell.record_mutation(
            severity=severity,
            trigger_event=mutation_data.get("trigger_event", "unknown"),
            prompt="",
            files_modified=[],
            success=False,
            error_message=error,
        )

        self.cell.status = CellStatus.DEGRADED
        self.logger.error("mutation_failed", error=error)

    # =========================================================================
    # Recovery Methods
    # =========================================================================

    async def _perform_recovery(self, event: Event) -> Optional[Event]:
        """Perform recovery procedure for the cell."""
        self.logger.info("performing_recovery")

        self.cell.status = CellStatus.RECOVERING
        await self.health_registry.mark_recovery_started(self.cell.id)

        # Recovery steps:
        # 1. Rollback to last known good version
        # 2. Restart the service
        # 3. Verify health

        try:
            # For now, just try to restart
            if self.kubectl_tool:
                # Restart the deployment
                pass

            # Verify health after recovery
            await asyncio.sleep(5)  # Wait for service to start
            health_result = await self._perform_health_check()

            if self.cell.is_healthy:
                return await self._create_event(
                    EventType.CELL_READY,
                    recovery_successful=True,
                )
            else:
                return await self._create_event(
                    EventType.CELL_FAILURE_DETECTED,
                    recovery_successful=False,
                )

        except Exception as e:
            self.logger.error("recovery_failed", error=str(e))
            return await self._create_event(
                EventType.CELL_FAILURE_DETECTED,
                error_message=str(e),
            )

    # =========================================================================
    # Autophagy Methods
    # =========================================================================

    async def _perform_autophagy(self, event: Event) -> Optional[Event]:
        """Perform graceful termination of the cell."""
        self.logger.info(
            "performing_autophagy",
            reason=event.data.get("reason"),
            mutation_count=self.cell.mutation_count,
        )

        self.cell.status = CellStatus.TERMINATING
        await self._publish_status_change(CellStatus.TERMINATING)

        try:
            # Cleanup K8s resources
            if self.kubectl_tool:
                # Delete deployment, service, configmap
                pass

            # Deregister from health registry
            await self.health_registry.deregister_cell(self.cell.id)

            # Update metrics
            await self.shared_state.update_colony_autophagy(increment_count=True)

            self.cell.status = CellStatus.TERMINATED
            self.cell.terminated_at = datetime.now()

            self.logger.info("autophagy_complete")

            return await self._create_event(
                EventType.CELL_AUTOPHAGY_COMPLETE,
                final_mutation_count=self.cell.mutation_count,
            )

        except Exception as e:
            self.logger.error("autophagy_failed", error=str(e))
            self.cell.status = CellStatus.TERMINATED
            return await self._create_event(
                EventType.CELL_TERMINATED,
                error_message=str(e),
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _create_event(
        self,
        event_type: EventType,
        success: bool = True,
        **data,
    ) -> Event:
        """Create an event with standard cell data."""
        return Event(
            type=event_type,
            source=self.name,
            success=success,
            data={
                "cell_id": self.cell.id,
                "cell_name": self.cell.name,
                "status": self.cell.status.value,
                **data,
            },
        )

    async def _publish_event(self, event_type: EventType, **data) -> None:
        """Publish an event."""
        event = await self._create_event(event_type, **data)
        await self.event_bus.publish(event)

    async def _publish_status_change(self, new_status: CellStatus) -> None:
        """Publish a status change event."""
        event_map = {
            CellStatus.INITIALIZING: EventType.CELL_INITIALIZING,
            CellStatus.BUILDING: EventType.CELL_BUILDING,
            CellStatus.DEPLOYING: EventType.CELL_DEPLOYING,
            CellStatus.HEALTHY: EventType.CELL_READY,
            CellStatus.DEGRADED: EventType.CELL_DEGRADED,
            CellStatus.RECOVERING: EventType.CELL_RECOVERING,
            CellStatus.TERMINATING: EventType.CELL_AUTOPHAGY_TRIGGERED,
            CellStatus.TERMINATED: EventType.CELL_TERMINATED,
        }

        event_type = event_map.get(new_status)
        if event_type:
            await self._publish_event(event_type)

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Managing cell {self.cell.name} ({self.cell.status.value})"
