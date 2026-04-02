"""
Lifecycle Controller - Manages Cell state transitions and lifecycle events.

Handles:
- State transitions: pending → initializing → building → deploying → healthy
- Health monitoring: healthy ↔ degraded ↔ recovering
- Mutation lifecycle: healthy/degraded → mutating → healthy/degraded
- Termination: Any state → terminating → terminated (autophagy)

The controller enforces valid state transitions and emits appropriate events
for each lifecycle change.
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable, Awaitable

from src.colony.cell import Cell, CellStatus, MutationSeverity
from src.colony.cell_health_registry import CellHealthRegistry
from src.mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger()


class TransitionResult(str, Enum):
    """Result of a state transition attempt."""
    SUCCESS = "success"
    INVALID_TRANSITION = "invalid_transition"
    PRECONDITION_FAILED = "precondition_failed"
    TIMEOUT = "timeout"
    ERROR = "error"


# Valid state transitions
VALID_TRANSITIONS: dict[CellStatus, list[CellStatus]] = {
    CellStatus.PENDING: [CellStatus.INITIALIZING, CellStatus.TERMINATED],
    CellStatus.INITIALIZING: [CellStatus.BUILDING, CellStatus.TERMINATED],
    CellStatus.BUILDING: [CellStatus.DEPLOYING, CellStatus.TERMINATED],
    CellStatus.DEPLOYING: [CellStatus.HEALTHY, CellStatus.DEGRADED, CellStatus.TERMINATED],
    CellStatus.HEALTHY: [CellStatus.DEGRADED, CellStatus.MUTATING, CellStatus.TERMINATING],
    CellStatus.DEGRADED: [CellStatus.HEALTHY, CellStatus.RECOVERING, CellStatus.MUTATING, CellStatus.TERMINATING],
    CellStatus.RECOVERING: [CellStatus.HEALTHY, CellStatus.DEGRADED, CellStatus.TERMINATING],
    CellStatus.MUTATING: [CellStatus.HEALTHY, CellStatus.DEGRADED, CellStatus.TERMINATING],
    CellStatus.TERMINATING: [CellStatus.TERMINATED],
    CellStatus.TERMINATED: [],  # Terminal state
}

# Events emitted for each state
STATE_EVENTS: dict[CellStatus, EventType] = {
    CellStatus.PENDING: EventType.CELL_CREATED,
    CellStatus.INITIALIZING: EventType.CELL_INITIALIZING,
    CellStatus.BUILDING: EventType.BUILD_STARTED,
    CellStatus.DEPLOYING: EventType.DEPLOY_STARTED if hasattr(EventType, 'DEPLOY_STARTED') else EventType.DEPLOY_SUCCEEDED,
    CellStatus.HEALTHY: EventType.CELL_READY,
    CellStatus.DEGRADED: EventType.CELL_DEGRADED,
    CellStatus.RECOVERING: EventType.CELL_RECOVERY_STARTED if hasattr(EventType, 'CELL_RECOVERY_STARTED') else EventType.CELL_DEGRADED,
    CellStatus.MUTATING: EventType.CELL_MUTATION_STARTED,
    CellStatus.TERMINATING: EventType.CELL_AUTOPHAGY_TRIGGERED,
    CellStatus.TERMINATED: EventType.CELL_TERMINATED,
}


class LifecycleController:
    """
    Controls cell lifecycle state transitions.

    Ensures valid state transitions, emits appropriate events,
    and coordinates with the health registry.
    """

    def __init__(
        self,
        event_bus: EventBus,
        health_registry: Optional[CellHealthRegistry] = None,
    ):
        """
        Initialize the lifecycle controller.

        Args:
            event_bus: EventBus for publishing lifecycle events
            health_registry: Optional health registry for tracking cell health
        """
        self.event_bus = event_bus
        self.health_registry = health_registry or CellHealthRegistry()
        self._transition_hooks: dict[CellStatus, list[Callable[[Cell], Awaitable[bool]]]] = {}
        self._cells: dict[str, Cell] = {}
        self._transition_locks: dict[str, asyncio.Lock] = {}

    def register_cell(self, cell: Cell) -> None:
        """
        Register a cell with the controller.

        Args:
            cell: Cell to register
        """
        self._cells[cell.id] = cell
        self._transition_locks[cell.id] = asyncio.Lock()
        self.health_registry.register_cell(cell)
        logger.info("cell_registered", cell_id=cell.id, cell_name=cell.name)

    def unregister_cell(self, cell_id: str) -> None:
        """
        Unregister a cell from the controller.

        Args:
            cell_id: ID of cell to unregister
        """
        if cell_id in self._cells:
            del self._cells[cell_id]
        if cell_id in self._transition_locks:
            del self._transition_locks[cell_id]
        self.health_registry.unregister_cell(cell_id)
        logger.info("cell_unregistered", cell_id=cell_id)

    def get_cell(self, cell_id: str) -> Optional[Cell]:
        """Get a registered cell by ID."""
        return self._cells.get(cell_id)

    def add_transition_hook(
        self,
        target_state: CellStatus,
        hook: Callable[[Cell], Awaitable[bool]],
    ) -> None:
        """
        Add a hook to be called before transitioning to a state.

        Hooks can prevent transitions by returning False.

        Args:
            target_state: State to hook
            hook: Async function that receives the cell and returns True to allow transition
        """
        if target_state not in self._transition_hooks:
            self._transition_hooks[target_state] = []
        self._transition_hooks[target_state].append(hook)

    def is_valid_transition(self, from_state: CellStatus, to_state: CellStatus) -> bool:
        """
        Check if a state transition is valid.

        Args:
            from_state: Current state
            to_state: Desired state

        Returns:
            True if transition is allowed
        """
        return to_state in VALID_TRANSITIONS.get(from_state, [])

    async def transition(
        self,
        cell: Cell,
        to_state: CellStatus,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> TransitionResult:
        """
        Transition a cell to a new state.

        Args:
            cell: Cell to transition
            to_state: Target state
            reason: Reason for transition
            metadata: Additional metadata for the event

        Returns:
            TransitionResult indicating success or failure reason
        """
        # Get or create lock for this cell
        if cell.id not in self._transition_locks:
            self._transition_locks[cell.id] = asyncio.Lock()

        async with self._transition_locks[cell.id]:
            from_state = cell.status

            # Validate transition
            if not self.is_valid_transition(from_state, to_state):
                logger.warning(
                    "invalid_state_transition",
                    cell_id=cell.id,
                    from_state=from_state.value,
                    to_state=to_state.value,
                )
                return TransitionResult.INVALID_TRANSITION

            # Run transition hooks
            if to_state in self._transition_hooks:
                for hook in self._transition_hooks[to_state]:
                    try:
                        if not await hook(cell):
                            logger.info(
                                "transition_hook_rejected",
                                cell_id=cell.id,
                                to_state=to_state.value,
                            )
                            return TransitionResult.PRECONDITION_FAILED
                    except Exception as e:
                        logger.error(
                            "transition_hook_error",
                            cell_id=cell.id,
                            error=str(e),
                        )
                        return TransitionResult.ERROR

            # Perform transition
            cell.status = to_state
            logger.info(
                "cell_state_transition",
                cell_id=cell.id,
                cell_name=cell.name,
                from_state=from_state.value,
                to_state=to_state.value,
                reason=reason,
            )

            # Update timestamps based on state
            if to_state == CellStatus.INITIALIZING:
                cell.started_at = datetime.now()
            elif to_state == CellStatus.TERMINATED:
                cell.terminated_at = datetime.now()

            # Emit event
            event_type = STATE_EVENTS.get(to_state)
            if event_type:
                await self.event_bus.publish(Event(
                    type=event_type,
                    source=f"lifecycle_controller/{cell.id}",
                    data={
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "from_state": from_state.value,
                        "to_state": to_state.value,
                        "reason": reason,
                        **(metadata or {}),
                    },
                ))

            # Update health registry
            self.health_registry.update_state(cell.id, to_state)

            return TransitionResult.SUCCESS

    async def initialize_cell(self, cell: Cell, source_callback: Callable[[], Awaitable[bool]]) -> bool:
        """
        Initialize a cell (code generation or repo clone).

        Args:
            cell: Cell to initialize
            source_callback: Async function to perform initialization

        Returns:
            True if initialization succeeded
        """
        result = await self.transition(cell, CellStatus.INITIALIZING, "Starting initialization")
        if result != TransitionResult.SUCCESS:
            return False

        try:
            success = await source_callback()
            if success:
                await self.transition(cell, CellStatus.BUILDING, "Initialization complete")
                return True
            else:
                await self.transition(cell, CellStatus.TERMINATED, "Initialization failed")
                return False
        except Exception as e:
            logger.error("initialization_error", cell_id=cell.id, error=str(e))
            await self.transition(cell, CellStatus.TERMINATED, f"Initialization error: {e}")
            return False

    async def build_cell(self, cell: Cell, build_callback: Callable[[], Awaitable[bool]]) -> bool:
        """
        Build a cell (compile, package, create container).

        Args:
            cell: Cell to build
            build_callback: Async function to perform build

        Returns:
            True if build succeeded
        """
        if cell.status != CellStatus.BUILDING:
            result = await self.transition(cell, CellStatus.BUILDING, "Starting build")
            if result != TransitionResult.SUCCESS:
                return False

        try:
            success = await build_callback()
            if success:
                await self.transition(cell, CellStatus.DEPLOYING, "Build complete")
                return True
            else:
                # Build failed - could try mutation or terminate
                await self.event_bus.publish(Event(
                    type=EventType.BUILD_FAILED,
                    source=f"lifecycle_controller/{cell.id}",
                    data={"cell_id": cell.id, "cell_name": cell.name},
                ))
                return False
        except Exception as e:
            logger.error("build_error", cell_id=cell.id, error=str(e))
            await self.event_bus.publish(Event(
                type=EventType.BUILD_FAILED,
                source=f"lifecycle_controller/{cell.id}",
                data={"cell_id": cell.id, "error": str(e)},
            ))
            return False

    async def deploy_cell(self, cell: Cell, deploy_callback: Callable[[], Awaitable[bool]]) -> bool:
        """
        Deploy a cell to the cluster.

        Args:
            cell: Cell to deploy
            deploy_callback: Async function to perform deployment

        Returns:
            True if deployment succeeded
        """
        if cell.status != CellStatus.DEPLOYING:
            result = await self.transition(cell, CellStatus.DEPLOYING, "Starting deployment")
            if result != TransitionResult.SUCCESS:
                return False

        try:
            success = await deploy_callback()
            if success:
                await self.transition(cell, CellStatus.HEALTHY, "Deployment successful")
                return True
            else:
                await self.transition(cell, CellStatus.DEGRADED, "Deployment issues")
                return False
        except Exception as e:
            logger.error("deploy_error", cell_id=cell.id, error=str(e))
            await self.transition(cell, CellStatus.DEGRADED, f"Deploy error: {e}")
            return False

    async def start_recovery(self, cell: Cell, reason: str = "") -> TransitionResult:
        """
        Start recovery procedure for a degraded cell.

        Args:
            cell: Cell to recover
            reason: Reason for recovery

        Returns:
            TransitionResult
        """
        if cell.status not in (CellStatus.DEGRADED, CellStatus.HEALTHY):
            return TransitionResult.INVALID_TRANSITION

        return await self.transition(cell, CellStatus.RECOVERING, reason or "Starting recovery")

    async def complete_recovery(self, cell: Cell, success: bool) -> TransitionResult:
        """
        Complete recovery procedure.

        Args:
            cell: Cell that was being recovered
            success: Whether recovery succeeded

        Returns:
            TransitionResult
        """
        if cell.status != CellStatus.RECOVERING:
            return TransitionResult.INVALID_TRANSITION

        if success:
            cell.health_score = 0.8  # Reset to healthy threshold
            cell.consecutive_failures = 0
            return await self.transition(cell, CellStatus.HEALTHY, "Recovery successful")
        else:
            return await self.transition(cell, CellStatus.DEGRADED, "Recovery failed")

    async def start_mutation(
        self,
        cell: Cell,
        severity: MutationSeverity,
        trigger_event: str,
    ) -> TransitionResult:
        """
        Start a mutation on a cell.

        High/Critical severity mutations require approval before starting.

        Args:
            cell: Cell to mutate
            severity: Severity of the mutation
            trigger_event: Event that triggered the mutation

        Returns:
            TransitionResult
        """
        if cell.status not in (CellStatus.HEALTHY, CellStatus.DEGRADED):
            return TransitionResult.INVALID_TRANSITION

        # Check if approval is needed
        if severity in (MutationSeverity.HIGH, MutationSeverity.CRITICAL):
            # Emit approval request event
            await self.event_bus.publish(Event(
                type=EventType.MUTATION_APPROVAL_REQUIRED if hasattr(EventType, 'MUTATION_APPROVAL_REQUIRED') else EventType.CELL_MUTATION_REQUESTED,
                source=f"lifecycle_controller/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "severity": severity.value,
                    "trigger_event": trigger_event,
                    "requires_approval": True,
                },
            ))
            logger.info(
                "mutation_approval_required",
                cell_id=cell.id,
                severity=severity.value,
            )
            # Don't transition yet - wait for approval
            return TransitionResult.PRECONDITION_FAILED

        # Low/Medium severity - proceed directly
        return await self.transition(
            cell,
            CellStatus.MUTATING,
            f"Mutation started: {trigger_event}",
            metadata={"severity": severity.value, "trigger_event": trigger_event},
        )

    async def complete_mutation(self, cell: Cell, success: bool) -> TransitionResult:
        """
        Complete a mutation.

        Args:
            cell: Cell that was being mutated
            success: Whether mutation succeeded

        Returns:
            TransitionResult
        """
        if cell.status != CellStatus.MUTATING:
            return TransitionResult.INVALID_TRANSITION

        if success:
            target_state = CellStatus.HEALTHY if cell.health_score >= 0.8 else CellStatus.DEGRADED
            result = await self.transition(cell, target_state, "Mutation applied successfully")

            await self.event_bus.publish(Event(
                type=EventType.CELL_MUTATION_APPLIED,
                source=f"lifecycle_controller/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "new_version": cell.version,
                },
            ))
            return result
        else:
            # Check if we should autophagy
            if cell.should_autophagy:
                return await self.trigger_autophagy(cell, "Too many failed mutations")

            target_state = CellStatus.HEALTHY if cell.health_score >= 0.8 else CellStatus.DEGRADED
            return await self.transition(cell, target_state, "Mutation failed")

    async def trigger_autophagy(self, cell: Cell, reason: str = "") -> TransitionResult:
        """
        Trigger cell termination (autophagy).

        Args:
            cell: Cell to terminate
            reason: Reason for termination

        Returns:
            TransitionResult
        """
        if cell.status == CellStatus.TERMINATED:
            return TransitionResult.SUCCESS

        result = await self.transition(
            cell,
            CellStatus.TERMINATING,
            reason or "Autophagy triggered",
        )

        if result == TransitionResult.SUCCESS:
            await self.event_bus.publish(Event(
                type=EventType.CELL_AUTOPHAGY_TRIGGERED,
                source=f"lifecycle_controller/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "reason": reason,
                    "mutation_count": cell.mutation_count,
                },
            ))

        return result

    async def complete_termination(self, cell: Cell) -> TransitionResult:
        """
        Complete cell termination.

        Args:
            cell: Cell to finalize termination

        Returns:
            TransitionResult
        """
        if cell.status != CellStatus.TERMINATING:
            return TransitionResult.INVALID_TRANSITION

        result = await self.transition(cell, CellStatus.TERMINATED, "Termination complete")

        if result == TransitionResult.SUCCESS:
            await self.event_bus.publish(Event(
                type=EventType.CELL_AUTOPHAGY_COMPLETE,
                source=f"lifecycle_controller/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                },
            ))
            self.unregister_cell(cell.id)

        return result

    async def handle_health_check(self, cell: Cell, passed: bool, score: Optional[float] = None) -> None:
        """
        Handle a health check result and potentially trigger state changes.

        Args:
            cell: Cell that was checked
            passed: Whether health check passed
            score: Optional health score
        """
        previous_status = cell.status
        cell.update_health(passed, score)

        # Update registry
        self.health_registry.record_health_check(cell.id, passed, score or cell.health_score)

        # Emit health events
        event_type = EventType.CELL_HEALTH_PASSED if passed else EventType.CELL_HEALTH_FAILED
        await self.event_bus.publish(Event(
            type=event_type,
            source=f"lifecycle_controller/{cell.id}",
            data={
                "cell_id": cell.id,
                "cell_name": cell.name,
                "health_score": cell.health_score,
                "consecutive_failures": cell.consecutive_failures,
            },
        ))

        # Check for state transitions
        if previous_status == CellStatus.HEALTHY and cell.status == CellStatus.DEGRADED:
            await self.event_bus.publish(Event(
                type=EventType.CELL_DEGRADED,
                source=f"lifecycle_controller/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "health_score": cell.health_score,
                },
            ))

        # Check if recovery is needed
        if cell.needs_recovery and cell.status == CellStatus.DEGRADED:
            await self.event_bus.publish(Event(
                type=EventType.CELL_FAILURE_DETECTED,
                source=f"lifecycle_controller/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "health_score": cell.health_score,
                    "consecutive_failures": cell.consecutive_failures,
                },
            ))

    def get_all_cells(self) -> list[Cell]:
        """Get all registered cells."""
        return list(self._cells.values())

    def get_cells_by_status(self, status: CellStatus) -> list[Cell]:
        """Get all cells with a specific status."""
        return [c for c in self._cells.values() if c.status == status]

    def get_healthy_cells(self) -> list[Cell]:
        """Get all healthy cells."""
        return [c for c in self._cells.values() if c.is_healthy]

    def get_degraded_cells(self) -> list[Cell]:
        """Get all degraded cells."""
        return self.get_cells_by_status(CellStatus.DEGRADED)

    def get_colony_health_ratio(self) -> float:
        """Calculate overall colony health ratio."""
        if not self._cells:
            return 1.0
        healthy = sum(1 for c in self._cells.values() if c.is_healthy)
        return healthy / len(self._cells)
