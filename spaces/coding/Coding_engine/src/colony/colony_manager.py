"""
Colony Manager - Orchestrator for the Cell Colony system.

The ColonyManager:
1. Manages the lifecycle of all cells (spawn, mutate, terminate)
2. Monitors colony-wide health and triggers rebalancing
3. Handles human-in-the-loop approval for critical mutations
4. Scales the colony up/down based on demand
5. Tracks convergence using colony-specific metrics

This is the "brain" of the Cell Colony system, coordinating
all CellAgents and ensuring the colony remains healthy.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .cell import Cell, CellStatus, SourceType, MutationSeverity
from .cell_agent import CellAgent, CellAgentConfig
from .cell_health_registry import CellHealthRegistry, HealthCheckResult
from .k8s.kubectl_tool import KubectlTool
from .k8s.resource_generator import ResourceGenerator

logger = structlog.get_logger(__name__)


@dataclass
class ColonyConfig:
    """Configuration for the Colony Manager."""
    # Cell limits
    max_cells: int = 100
    min_healthy_cells: int = 1

    # Health monitoring
    health_check_interval: int = 30  # Seconds
    rebalance_threshold: float = 0.8  # Trigger rebalance below this

    # Scaling
    auto_scaling_enabled: bool = False
    scale_up_threshold: float = 0.9  # Scale up when health above this
    scale_down_threshold: float = 0.5  # Scale down when too many degraded

    # Mutation approval
    auto_approve_level: MutationSeverity = MutationSeverity.MEDIUM
    approval_timeout: int = 300  # Seconds to wait for approval

    # Kubernetes
    namespace: str = "cell-colony"
    use_kubernetes: bool = True


@dataclass
class ColonyStatus:
    """Current status of the colony."""
    phase: str = "Creating"  # Creating, Running, Rebalancing, Degraded, Terminated
    total_cells: int = 0
    healthy_cells: int = 0
    degraded_cells: int = 0
    failed_cells: int = 0
    initializing_cells: int = 0
    mutating_cells: int = 0

    # Operations
    rebalance_in_progress: bool = False
    pending_approvals: int = 0

    # Metrics
    health_ratio: float = 1.0
    total_mutations: int = 0
    successful_mutations: int = 0
    autophagy_count: int = 0

    # Timing
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "total_cells": self.total_cells,
            "healthy_cells": self.healthy_cells,
            "degraded_cells": self.degraded_cells,
            "failed_cells": self.failed_cells,
            "health_ratio": self.health_ratio,
            "rebalance_in_progress": self.rebalance_in_progress,
            "pending_approvals": self.pending_approvals,
            "total_mutations": self.total_mutations,
            "autophagy_count": self.autophagy_count,
        }


class ColonyManager:
    """
    Orchestrator for the Cell Colony system.

    Manages the lifecycle of all cells in the colony, monitors health,
    triggers mutations and recovery, and handles human-in-the-loop approval.

    Usage:
        manager = ColonyManager(
            event_bus=event_bus,
            shared_state=shared_state,
            config=ColonyConfig(namespace="my-colony"),
        )

        # Spawn a new cell
        cell = await manager.spawn_cell(
            name="user-auth",
            source_type=SourceType.LLM_GENERATED,
            source_ref="REST API for user authentication",
        )

        # Start the colony
        await manager.start()
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        config: Optional[ColonyConfig] = None,
        kubectl_tool: Optional[KubectlTool] = None,
        resource_generator: Optional[ResourceGenerator] = None,
        progress_callback: Optional[Callable[[ColonyStatus], None]] = None,
    ):
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.config = config or ColonyConfig()
        self.kubectl_tool = kubectl_tool or KubectlTool(namespace=self.config.namespace)
        self.resource_generator = resource_generator or ResourceGenerator()
        self.progress_callback = progress_callback

        # Health registry
        self.health_registry = CellHealthRegistry(
            event_bus=event_bus,
            health_threshold=self.config.rebalance_threshold,
        )

        # Cell management
        self._cells: Dict[str, Cell] = {}
        self._agents: Dict[str, CellAgent] = {}
        self._pending_approvals: Dict[str, Event] = {}

        # State
        self._status = ColonyStatus()
        self._should_stop = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._rebalance_task: Optional[asyncio.Task] = None

        # Event subscriptions
        self._subscribed = False

        self.logger = logger.bind(component="colony_manager")

    async def start(self) -> None:
        """Start the colony manager."""
        self.logger.info("starting_colony_manager")

        self._status.started_at = datetime.now()
        self._status.phase = "Running"
        self._should_stop = False

        # Subscribe to events
        await self._subscribe_to_events()

        # Start health monitoring
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # Publish colony created event
        await self._publish_event(EventType.COLONY_CREATED)

        # Update shared state
        await self._update_shared_state()

        self.logger.info("colony_manager_started", total_cells=len(self._cells))

    async def stop(self) -> None:
        """Stop the colony manager gracefully."""
        self.logger.info("stopping_colony_manager")
        self._should_stop = True

        # Stop health check loop
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all cell agents
        for agent in self._agents.values():
            await agent.stop()

        self._status.phase = "Terminated"
        self.logger.info("colony_manager_stopped")

    async def _subscribe_to_events(self) -> None:
        """Subscribe to relevant colony events."""
        if self._subscribed:
            return

        events_to_subscribe = [
            # Cell lifecycle events
            EventType.CELL_READY,
            EventType.CELL_DEGRADED,
            EventType.CELL_FAILURE_DETECTED,
            EventType.CELL_TERMINATED,

            # Mutation events
            EventType.MUTATION_APPROVAL_REQUIRED,
            EventType.USER_MUTATION_APPROVED,
            EventType.USER_MUTATION_REJECTED,
            EventType.CELL_MUTATION_APPLIED,
            EventType.CELL_MUTATION_FAILED,

            # Autophagy events
            EventType.CELL_AUTOPHAGY_COMPLETE,

            # Health events
            EventType.CELL_HEALTH_FAILED,
        ]

        for event_type in events_to_subscribe:
            self.event_bus.subscribe(event_type, self._handle_event)

        self._subscribed = True

    def _handle_event(self, event: Event) -> None:
        """Handle incoming events (sync callback)."""
        # Create async task to handle the event
        asyncio.create_task(self._handle_event_async(event))

    async def _handle_event_async(self, event: Event) -> None:
        """Handle incoming events asynchronously."""
        try:
            if event.type == EventType.CELL_READY:
                await self._handle_cell_ready(event)
            elif event.type == EventType.CELL_DEGRADED:
                await self._handle_cell_degraded(event)
            elif event.type == EventType.CELL_FAILURE_DETECTED:
                await self._handle_cell_failure(event)
            elif event.type == EventType.CELL_TERMINATED:
                await self._handle_cell_terminated(event)
            elif event.type == EventType.MUTATION_APPROVAL_REQUIRED:
                await self._handle_approval_required(event)
            elif event.type == EventType.USER_MUTATION_APPROVED:
                await self._handle_user_approved(event)
            elif event.type == EventType.USER_MUTATION_REJECTED:
                await self._handle_user_rejected(event)
            elif event.type == EventType.CELL_MUTATION_APPLIED:
                await self._handle_mutation_applied(event)
            elif event.type == EventType.CELL_MUTATION_FAILED:
                await self._handle_mutation_failed(event)
            elif event.type == EventType.CELL_AUTOPHAGY_COMPLETE:
                await self._handle_autophagy_complete(event)
            elif event.type == EventType.CELL_HEALTH_FAILED:
                await self._handle_health_failed(event)

        except Exception as e:
            self.logger.error("event_handling_failed", error=str(e), event_type=event.type.value)

    # =========================================================================
    # Cell Lifecycle Methods
    # =========================================================================

    async def spawn_cell(
        self,
        name: str,
        source_type: SourceType,
        source_ref: str,
        working_dir: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> Cell:
        """
        Spawn a new cell in the colony.

        Args:
            name: Name for the cell
            source_type: How to obtain the code
            source_ref: Reference (prompt, repo URL, template)
            working_dir: Working directory for the cell
            env_vars: Environment variables
            depends_on: Cell IDs this cell depends on

        Returns:
            The created Cell
        """
        if len(self._cells) >= self.config.max_cells:
            raise RuntimeError(f"Colony at max capacity ({self.config.max_cells} cells)")

        # Create the cell
        cell = Cell(
            name=name,
            namespace=self.config.namespace,
            source_type=source_type,
            source_ref=source_ref,
            working_dir=working_dir or f"/app/cells/{name}",
            env_vars=env_vars or {},
            depends_on=depends_on or [],
        )

        self._cells[cell.id] = cell

        self.logger.info(
            "spawning_cell",
            cell_id=cell.id,
            cell_name=name,
            source_type=source_type.value,
        )

        # Create and start the cell agent
        agent_config = CellAgentConfig(
            auto_approve_low_severity=(
                self.config.auto_approve_level in (MutationSeverity.LOW, MutationSeverity.MEDIUM)
            ),
            mutation_timeout=self.config.approval_timeout,
        )

        agent = CellAgent(
            cell=cell,
            event_bus=self.event_bus,
            shared_state=self.shared_state,
            health_registry=self.health_registry,
            config=agent_config,
            kubectl_tool=self.kubectl_tool if self.config.use_kubernetes else None,
        )

        self._agents[cell.id] = agent

        # Initialize the cell
        await agent.initialize_cell()

        # Build and deploy if initialized successfully
        if cell.status not in (CellStatus.TERMINATED,):
            await agent.build_and_deploy()

        # Start the agent
        await agent.start()

        # Update status
        await self._update_status()

        return cell

    async def terminate_cell(self, cell_id: str, reason: str = "Manual termination") -> bool:
        """
        Terminate a cell.

        Args:
            cell_id: ID of the cell to terminate
            reason: Reason for termination

        Returns:
            True if cell was terminated
        """
        if cell_id not in self._cells:
            return False

        cell = self._cells[cell_id]
        agent = self._agents.get(cell_id)

        self.logger.info(
            "terminating_cell",
            cell_id=cell_id,
            cell_name=cell.name,
            reason=reason,
        )

        # Stop the agent
        if agent:
            await agent.stop()
            del self._agents[cell_id]

        # Deregister from health registry
        await self.health_registry.deregister_cell(cell_id)

        # Delete K8s resources
        if self.config.use_kubernetes:
            await self.kubectl_tool.delete_cell_resources(cell.name)

        # Update cell status
        cell.status = CellStatus.TERMINATED
        cell.terminated_at = datetime.now()

        # Publish event
        await self._publish_event(
            EventType.CELL_TERMINATED,
            cell_id=cell_id,
            cell_name=cell.name,
            reason=reason,
        )

        await self._update_status()
        return True

    async def get_cell(self, cell_id: str) -> Optional[Cell]:
        """Get a cell by ID."""
        return self._cells.get(cell_id)

    async def get_cells_by_status(self, status: CellStatus) -> List[Cell]:
        """Get all cells with a specific status."""
        return [c for c in self._cells.values() if c.status == status]

    # =========================================================================
    # Event Handlers
    # =========================================================================

    async def _handle_cell_ready(self, event: Event) -> None:
        """Handle cell becoming ready."""
        cell_id = event.data.get("cell_id")
        if cell_id in self._cells:
            self._cells[cell_id].status = CellStatus.HEALTHY

        await self._update_status()
        await self._check_convergence()

    async def _handle_cell_degraded(self, event: Event) -> None:
        """Handle cell becoming degraded."""
        cell_id = event.data.get("cell_id")
        if cell_id in self._cells:
            self._cells[cell_id].status = CellStatus.DEGRADED

        await self._update_status()
        await self._maybe_trigger_rebalance()

    async def _handle_cell_failure(self, event: Event) -> None:
        """Handle cell failure - may trigger mutation or autophagy."""
        cell_id = event.data.get("cell_id")
        if cell_id not in self._cells:
            return

        cell = self._cells[cell_id]

        # Check if autophagy is needed
        if cell.should_autophagy:
            await self._publish_event(
                EventType.CELL_AUTOPHAGY_TRIGGERED,
                cell_id=cell_id,
                cell_name=cell.name,
                reason="Max mutation failures exceeded",
            )

        await self._update_status()

    async def _handle_cell_terminated(self, event: Event) -> None:
        """Handle cell termination."""
        await self._update_status()
        await self._maybe_spawn_replacement(event)

    async def _handle_approval_required(self, event: Event) -> None:
        """Handle mutation requiring approval."""
        cell_id = event.data.get("cell_id")
        self._pending_approvals[cell_id] = event
        self._status.pending_approvals = len(self._pending_approvals)

        self.logger.info(
            "mutation_approval_required",
            cell_id=cell_id,
            severity=event.data.get("severity"),
        )

        # Notify operator
        await self._publish_event(
            EventType.OPERATOR_NOTIFICATION,
            notification_type="mutation_approval",
            cell_id=cell_id,
            severity=event.data.get("severity"),
            timeout_seconds=event.data.get("timeout_seconds"),
        )

        # Start timeout
        asyncio.create_task(self._approval_timeout(cell_id, self.config.approval_timeout))

    async def _approval_timeout(self, cell_id: str, timeout: int) -> None:
        """Handle approval timeout."""
        await asyncio.sleep(timeout)

        if cell_id in self._pending_approvals:
            del self._pending_approvals[cell_id]
            self._status.pending_approvals = len(self._pending_approvals)

            await self._publish_event(
                EventType.MUTATION_TIMEOUT_EXPIRED,
                cell_id=cell_id,
            )

    async def _handle_user_approved(self, event: Event) -> None:
        """Handle user approving a mutation."""
        cell_id = event.data.get("cell_id")
        if cell_id in self._pending_approvals:
            del self._pending_approvals[cell_id]
            self._status.pending_approvals = len(self._pending_approvals)

    async def _handle_user_rejected(self, event: Event) -> None:
        """Handle user rejecting a mutation."""
        cell_id = event.data.get("cell_id")
        if cell_id in self._pending_approvals:
            del self._pending_approvals[cell_id]
            self._status.pending_approvals = len(self._pending_approvals)

    async def _handle_mutation_applied(self, event: Event) -> None:
        """Handle successful mutation."""
        self._status.total_mutations += 1
        self._status.successful_mutations += 1
        await self._update_status()

    async def _handle_mutation_failed(self, event: Event) -> None:
        """Handle failed mutation."""
        self._status.total_mutations += 1
        await self._update_status()

    async def _handle_autophagy_complete(self, event: Event) -> None:
        """Handle cell autophagy completion."""
        self._status.autophagy_count += 1
        await self._update_status()

    async def _handle_health_failed(self, event: Event) -> None:
        """Handle health check failure."""
        await self._update_status()
        await self._maybe_trigger_rebalance()

    # =========================================================================
    # Health Monitoring
    # =========================================================================

    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        while not self._should_stop:
            try:
                await asyncio.sleep(self.config.health_check_interval)

                # Update status from health registry
                summary = self.health_registry.get_colony_summary()
                self._status.healthy_cells = summary["healthy_cells"]
                self._status.degraded_cells = summary["degraded_cells"]
                self._status.health_ratio = summary["colony_health_ratio"]
                self._status.last_health_check = datetime.now()

                # Publish health check event
                await self._publish_event(EventType.COLONY_HEALTH_CHECK)

                # Check if rebalancing is needed
                await self._maybe_trigger_rebalance()

                # Update shared state
                await self._update_shared_state()

                # Callback
                if self.progress_callback:
                    self.progress_callback(self._status)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("health_check_error", error=str(e))

    async def _maybe_trigger_rebalance(self) -> None:
        """Check if rebalancing is needed and trigger if so."""
        if self._status.rebalance_in_progress:
            return

        if self._status.health_ratio < self.config.rebalance_threshold:
            await self._trigger_rebalance()

    async def _trigger_rebalance(self) -> None:
        """Trigger colony rebalancing."""
        self.logger.info(
            "triggering_rebalance",
            health_ratio=self._status.health_ratio,
            degraded_cells=self._status.degraded_cells,
        )

        self._status.rebalance_in_progress = True
        self._status.phase = "Rebalancing"

        await self._publish_event(EventType.COLONY_REBALANCE_STARTED)

        try:
            # Get cells needing attention
            cells_needing_attention = self.health_registry.get_cells_needing_attention()

            for health_state in cells_needing_attention:
                cell_id = health_state.cell_id
                if cell_id not in self._cells:
                    continue

                cell = self._cells[cell_id]

                # Trigger recovery or autophagy
                if cell.should_autophagy:
                    await self._publish_event(
                        EventType.CELL_AUTOPHAGY_TRIGGERED,
                        cell_id=cell_id,
                        reason="Rebalance: too many failures",
                    )
                else:
                    await self._publish_event(
                        EventType.CELL_RECOVERING,
                        cell_id=cell_id,
                    )

            await self._publish_event(EventType.COLONY_REBALANCE_COMPLETE)

        finally:
            self._status.rebalance_in_progress = False
            self._status.phase = "Running"

    async def _maybe_spawn_replacement(self, event: Event) -> None:
        """Spawn a replacement cell if needed."""
        if not self.config.auto_scaling_enabled:
            return

        if self._status.healthy_cells < self.config.min_healthy_cells:
            # Would need to spawn a replacement - but we need the original spec
            # This is a placeholder for more sophisticated replacement logic
            self.logger.info(
                "may_need_replacement",
                healthy_cells=self._status.healthy_cells,
                min_required=self.config.min_healthy_cells,
            )

    async def _check_convergence(self) -> None:
        """Check if colony has converged."""
        metrics = self.shared_state.metrics

        if metrics.colony_convergence_ready:
            self.logger.info(
                "colony_converged",
                total_cells=self._status.total_cells,
                healthy_cells=self._status.healthy_cells,
            )
            await self._publish_event(EventType.COLONY_CONVERGENCE_ACHIEVED)

    # =========================================================================
    # Status Updates
    # =========================================================================

    async def _update_status(self) -> None:
        """Update colony status from current state."""
        status_counts = {status: 0 for status in CellStatus}
        for cell in self._cells.values():
            status_counts[cell.status] += 1

        self._status.total_cells = len(self._cells)
        self._status.healthy_cells = status_counts[CellStatus.HEALTHY]
        self._status.degraded_cells = status_counts[CellStatus.DEGRADED]
        self._status.failed_cells = status_counts[CellStatus.TERMINATED]
        self._status.initializing_cells = status_counts[CellStatus.INITIALIZING]
        self._status.mutating_cells = status_counts[CellStatus.MUTATING]

        if self._status.total_cells > 0:
            self._status.health_ratio = self._status.healthy_cells / self._status.total_cells
        else:
            self._status.health_ratio = 1.0

    async def _update_shared_state(self) -> None:
        """Update SharedState with colony metrics."""
        await self.shared_state.update_colony_cells(
            total_cells=self._status.total_cells,
            healthy_cells=self._status.healthy_cells,
            degraded_cells=self._status.degraded_cells,
            cells_in_recovery=len(self.health_registry.get_cells_by_status(CellStatus.RECOVERING)),
            cells_mutating=self._status.mutating_cells,
        )

        await self.shared_state.update_colony_mutations(
            successful=self._status.successful_mutations,
            pending_approvals=self._status.pending_approvals,
        )

        await self.shared_state.update_colony_autophagy(
            count=self._status.autophagy_count,
        )

        await self.shared_state.update_colony_operations(
            rebalance_in_progress=self._status.rebalance_in_progress,
        )

    async def _publish_event(self, event_type: EventType, **data) -> None:
        """Publish a colony event."""
        event = Event(
            type=event_type,
            source="colony_manager",
            data=data,
        )
        await self.event_bus.publish(event)

    # =========================================================================
    # Public API
    # =========================================================================

    @property
    def status(self) -> ColonyStatus:
        """Get current colony status."""
        return self._status

    @property
    def cells(self) -> Dict[str, Cell]:
        """Get all cells."""
        return dict(self._cells)

    async def approve_mutation(self, cell_id: str, approved_by: str = "operator") -> bool:
        """
        Approve a pending mutation.

        Args:
            cell_id: ID of the cell
            approved_by: User who approved

        Returns:
            True if approval was processed
        """
        if cell_id not in self._pending_approvals:
            return False

        await self._publish_event(
            EventType.USER_MUTATION_APPROVED,
            cell_id=cell_id,
            approved_by=approved_by,
        )

        return True

    async def reject_mutation(self, cell_id: str, reason: str = "Rejected by operator") -> bool:
        """
        Reject a pending mutation.

        Args:
            cell_id: ID of the cell
            reason: Reason for rejection

        Returns:
            True if rejection was processed
        """
        if cell_id not in self._pending_approvals:
            return False

        await self._publish_event(
            EventType.USER_MUTATION_REJECTED,
            cell_id=cell_id,
            reason=reason,
        )

        return True

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get list of pending mutation approvals."""
        approvals = []
        for cell_id, event in self._pending_approvals.items():
            cell = self._cells.get(cell_id)
            approvals.append({
                "cell_id": cell_id,
                "cell_name": cell.name if cell else "Unknown",
                "severity": event.data.get("severity"),
                "trigger_event": event.data.get("trigger_event"),
                "error_message": event.data.get("error_message"),
                "requested_at": event.timestamp.isoformat(),
            })
        return approvals
