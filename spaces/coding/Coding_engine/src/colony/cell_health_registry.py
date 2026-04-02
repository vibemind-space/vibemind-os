"""
Cell Health Registry - Centralized health state tracking for all cells.

Provides:
- Real-time health monitoring for all cells in the colony
- Health score calculations based on metrics
- Degradation detection and recovery tracking
- Historical health data for analysis
- Integration with EventBus for health events
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import structlog

from .cell import Cell, CellStatus, MutationSeverity
from ..mind.event_bus import EventBus, EventType, Event

logger = structlog.get_logger(__name__)


class HealthCheckResult(str, Enum):
    """Result of a health check."""
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class HealthRecord:
    """Single health check record."""
    timestamp: datetime = field(default_factory=datetime.now)
    result: HealthCheckResult = HealthCheckResult.UNKNOWN
    response_time_ms: int = 0
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class CellHealthState:
    """
    Complete health state for a single cell.

    Tracks current health, history, and computed scores.
    """
    cell_id: str
    cell_name: str

    # Current state
    current_status: CellStatus = CellStatus.PENDING
    health_score: float = 1.0  # 0.0-1.0
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    # History
    check_history: List[HealthRecord] = field(default_factory=list)
    max_history: int = 100

    # Timing
    registered_at: datetime = field(default_factory=datetime.now)
    last_state_change: Optional[datetime] = None
    time_in_current_state: timedelta = field(default_factory=timedelta)

    # Recovery tracking
    recovery_attempts: int = 0
    last_recovery_at: Optional[datetime] = None

    # Mutation tracking
    pending_mutation: bool = False
    mutation_approval_required: bool = False
    mutation_severity: Optional[MutationSeverity] = None

    def add_check_result(self, record: HealthRecord) -> None:
        """Add a health check result and update computed values."""
        self.check_history.append(record)

        # Keep history bounded
        if len(self.check_history) > self.max_history:
            self.check_history = self.check_history[-self.max_history:]

        self.last_check = record.timestamp

        if record.result == HealthCheckResult.PASSED:
            self.consecutive_failures = 0
            self.consecutive_successes += 1
            self._update_health_score(passed=True)
        else:
            self.consecutive_successes = 0
            self.consecutive_failures += 1
            self._update_health_score(passed=False)

    def _update_health_score(self, passed: bool) -> None:
        """Update health score based on check result."""
        if passed:
            # Gradual recovery
            self.health_score = min(1.0, self.health_score + 0.1)
        else:
            # Faster degradation
            self.health_score = max(0.0, self.health_score - 0.2)

    def update_status(self, new_status: CellStatus) -> None:
        """Update cell status and track state change."""
        if new_status != self.current_status:
            now = datetime.now()
            if self.last_state_change:
                self.time_in_current_state = now - self.last_state_change
            self.last_state_change = now
            self.current_status = new_status

    @property
    def is_healthy(self) -> bool:
        """Whether the cell is currently healthy."""
        return self.current_status == CellStatus.HEALTHY and self.health_score >= 0.8

    @property
    def needs_attention(self) -> bool:
        """Whether the cell needs attention (degraded or failing)."""
        return (
            self.current_status == CellStatus.DEGRADED or
            self.health_score < 0.8 or
            self.consecutive_failures >= 3
        )

    @property
    def recent_pass_rate(self) -> float:
        """Pass rate of last 10 health checks."""
        recent = self.check_history[-10:] if self.check_history else []
        if not recent:
            return 1.0
        passed = sum(1 for r in recent if r.result == HealthCheckResult.PASSED)
        return passed / len(recent)

    @property
    def avg_response_time_ms(self) -> float:
        """Average response time of recent checks."""
        recent = [r for r in self.check_history[-10:] if r.response_time_ms > 0]
        if not recent:
            return 0.0
        return sum(r.response_time_ms for r in recent) / len(recent)


class CellHealthRegistry:
    """
    Centralized registry for cell health state.

    Provides:
    - Registration and deregistration of cells
    - Health check recording and analysis
    - Status transition management
    - Event publishing for health changes
    - Aggregated health metrics for the colony

    Usage:
        registry = CellHealthRegistry(event_bus)
        await registry.register_cell(cell)
        await registry.record_health_check(cell.id, HealthCheckResult.PASSED, 120)
        health = registry.get_cell_health(cell.id)
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        health_threshold: float = 0.8,
        failure_threshold: int = 3,
    ):
        self._cells: Dict[str, CellHealthState] = {}
        self._event_bus = event_bus
        self._health_threshold = health_threshold
        self._failure_threshold = failure_threshold
        self._lock = asyncio.Lock()
        self._change_handlers: List[Callable] = []
        self.logger = logger.bind(component="cell_health_registry")

    async def register_cell(self, cell: Cell) -> CellHealthState:
        """
        Register a new cell in the health registry.

        Args:
            cell: The Cell to register

        Returns:
            The created CellHealthState
        """
        async with self._lock:
            if cell.id in self._cells:
                self.logger.warning("cell_already_registered", cell_id=cell.id)
                return self._cells[cell.id]

            health_state = CellHealthState(
                cell_id=cell.id,
                cell_name=cell.name,
                current_status=cell.status,
                health_score=cell.health_score,
            )
            self._cells[cell.id] = health_state

            self.logger.info(
                "cell_registered",
                cell_id=cell.id,
                cell_name=cell.name,
            )

            if self._event_bus:
                await self._event_bus.publish(Event(
                    type=EventType.CELL_CREATED,
                    source="cell_health_registry",
                    data={
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "status": cell.status.value,
                    },
                ))

            return health_state

    async def deregister_cell(self, cell_id: str) -> bool:
        """
        Remove a cell from the registry.

        Args:
            cell_id: ID of the cell to remove

        Returns:
            True if cell was removed, False if not found
        """
        async with self._lock:
            if cell_id not in self._cells:
                return False

            health_state = self._cells.pop(cell_id)

            self.logger.info(
                "cell_deregistered",
                cell_id=cell_id,
                cell_name=health_state.cell_name,
            )

            if self._event_bus:
                await self._event_bus.publish(Event(
                    type=EventType.CELL_TERMINATED,
                    source="cell_health_registry",
                    data={
                        "cell_id": cell_id,
                        "cell_name": health_state.cell_name,
                        "final_status": health_state.current_status.value,
                        "final_health_score": health_state.health_score,
                    },
                ))

            return True

    async def record_health_check(
        self,
        cell_id: str,
        result: HealthCheckResult,
        response_time_ms: int = 0,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        metrics: Optional[Dict[str, float]] = None,
    ) -> Optional[CellHealthState]:
        """
        Record a health check result for a cell.

        Args:
            cell_id: ID of the cell
            result: Result of the health check
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code if applicable
            error_message: Error message if failed
            metrics: Additional metrics from the check

        Returns:
            Updated CellHealthState or None if cell not found
        """
        async with self._lock:
            if cell_id not in self._cells:
                self.logger.warning("health_check_for_unknown_cell", cell_id=cell_id)
                return None

            health_state = self._cells[cell_id]
            old_score = health_state.health_score
            old_status = health_state.current_status

            record = HealthRecord(
                result=result,
                response_time_ms=response_time_ms,
                status_code=status_code,
                error_message=error_message,
                metrics=metrics or {},
            )
            health_state.add_check_result(record)

            # Determine if status should change
            new_status = self._determine_status(health_state)
            if new_status != old_status:
                health_state.update_status(new_status)
                await self._publish_status_change(health_state, old_status, new_status)

            # Publish health score update if significant change
            if abs(health_state.health_score - old_score) >= 0.1:
                await self._publish_health_score_update(health_state)

            # Check if cell needs recovery
            if health_state.needs_attention and self._event_bus:
                await self._publish_failure_detected(health_state, error_message)

            self.logger.debug(
                "health_check_recorded",
                cell_id=cell_id,
                result=result.value,
                health_score=health_state.health_score,
                status=health_state.current_status.value,
            )

            return health_state

    def _determine_status(self, health_state: CellHealthState) -> CellStatus:
        """Determine appropriate status based on health metrics."""
        if health_state.current_status == CellStatus.TERMINATED:
            return CellStatus.TERMINATED

        if health_state.current_status == CellStatus.MUTATING:
            # Don't change status during mutation
            return CellStatus.MUTATING

        if health_state.health_score >= self._health_threshold:
            if health_state.consecutive_successes >= 2:
                return CellStatus.HEALTHY
            return health_state.current_status

        if health_state.consecutive_failures >= self._failure_threshold:
            if health_state.recovery_attempts > 3:
                return CellStatus.TERMINATING  # Prepare for autophagy
            return CellStatus.DEGRADED

        if health_state.health_score < 0.5:
            return CellStatus.DEGRADED

        return health_state.current_status

    async def _publish_status_change(
        self,
        health_state: CellHealthState,
        old_status: CellStatus,
        new_status: CellStatus,
    ) -> None:
        """Publish status change event."""
        if not self._event_bus:
            return

        event_type = {
            CellStatus.HEALTHY: EventType.CELL_READY,
            CellStatus.DEGRADED: EventType.CELL_DEGRADED,
            CellStatus.RECOVERING: EventType.CELL_RECOVERING,
            CellStatus.TERMINATED: EventType.CELL_TERMINATED,
        }.get(new_status)

        if event_type:
            await self._event_bus.publish(Event(
                type=event_type,
                source="cell_health_registry",
                data={
                    "cell_id": health_state.cell_id,
                    "cell_name": health_state.cell_name,
                    "old_status": old_status.value,
                    "new_status": new_status.value,
                    "health_score": health_state.health_score,
                },
            ))

    async def _publish_health_score_update(self, health_state: CellHealthState) -> None:
        """Publish health score update event."""
        if not self._event_bus:
            return

        await self._event_bus.publish(Event(
            type=EventType.CELL_HEALTH_SCORE_UPDATED,
            source="cell_health_registry",
            data={
                "cell_id": health_state.cell_id,
                "health_score": health_state.health_score,
                "recent_pass_rate": health_state.recent_pass_rate,
                "avg_response_time_ms": health_state.avg_response_time_ms,
            },
        ))

    async def _publish_failure_detected(
        self,
        health_state: CellHealthState,
        error_message: Optional[str],
    ) -> None:
        """Publish cell failure detection event."""
        if not self._event_bus:
            return

        await self._event_bus.publish(Event(
            type=EventType.CELL_FAILURE_DETECTED,
            source="cell_health_registry",
            data={
                "cell_id": health_state.cell_id,
                "cell_name": health_state.cell_name,
                "health_score": health_state.health_score,
                "consecutive_failures": health_state.consecutive_failures,
                "recovery_attempts": health_state.recovery_attempts,
                "error_message": error_message,
            },
        ))

    async def update_cell_status(
        self,
        cell_id: str,
        new_status: CellStatus,
    ) -> Optional[CellHealthState]:
        """
        Manually update a cell's status.

        Args:
            cell_id: ID of the cell
            new_status: New status to set

        Returns:
            Updated CellHealthState or None if not found
        """
        async with self._lock:
            if cell_id not in self._cells:
                return None

            health_state = self._cells[cell_id]
            old_status = health_state.current_status

            if new_status != old_status:
                health_state.update_status(new_status)
                await self._publish_status_change(health_state, old_status, new_status)

            return health_state

    async def mark_recovery_started(self, cell_id: str) -> Optional[CellHealthState]:
        """Mark that recovery has started for a cell."""
        async with self._lock:
            if cell_id not in self._cells:
                return None

            health_state = self._cells[cell_id]
            health_state.recovery_attempts += 1
            health_state.last_recovery_at = datetime.now()
            health_state.update_status(CellStatus.RECOVERING)

            self.logger.info(
                "cell_recovery_started",
                cell_id=cell_id,
                recovery_attempt=health_state.recovery_attempts,
            )

            return health_state

    async def mark_mutation_pending(
        self,
        cell_id: str,
        severity: MutationSeverity,
    ) -> Optional[CellHealthState]:
        """Mark that a mutation is pending for a cell."""
        async with self._lock:
            if cell_id not in self._cells:
                return None

            health_state = self._cells[cell_id]
            health_state.pending_mutation = True
            health_state.mutation_severity = severity
            health_state.mutation_approval_required = severity in (
                MutationSeverity.HIGH,
                MutationSeverity.CRITICAL,
            )

            self.logger.info(
                "cell_mutation_pending",
                cell_id=cell_id,
                severity=severity.value,
                approval_required=health_state.mutation_approval_required,
            )

            return health_state

    async def clear_mutation_pending(self, cell_id: str) -> Optional[CellHealthState]:
        """Clear pending mutation flag for a cell."""
        async with self._lock:
            if cell_id not in self._cells:
                return None

            health_state = self._cells[cell_id]
            health_state.pending_mutation = False
            health_state.mutation_approval_required = False
            health_state.mutation_severity = None

            return health_state

    def get_cell_health(self, cell_id: str) -> Optional[CellHealthState]:
        """Get health state for a specific cell."""
        return self._cells.get(cell_id)

    def get_all_cells(self) -> Dict[str, CellHealthState]:
        """Get health state for all registered cells."""
        return dict(self._cells)

    def get_cells_by_status(self, status: CellStatus) -> List[CellHealthState]:
        """Get all cells with a specific status."""
        return [
            state for state in self._cells.values()
            if state.current_status == status
        ]

    def get_cells_needing_attention(self) -> List[CellHealthState]:
        """Get all cells that need attention."""
        return [
            state for state in self._cells.values()
            if state.needs_attention
        ]

    def get_cells_awaiting_approval(self) -> List[CellHealthState]:
        """Get all cells with pending mutation approval."""
        return [
            state for state in self._cells.values()
            if state.mutation_approval_required
        ]

    @property
    def total_cells(self) -> int:
        """Total number of registered cells."""
        return len(self._cells)

    @property
    def healthy_cells(self) -> int:
        """Number of healthy cells."""
        return sum(1 for s in self._cells.values() if s.is_healthy)

    @property
    def degraded_cells(self) -> int:
        """Number of degraded cells."""
        return sum(
            1 for s in self._cells.values()
            if s.current_status == CellStatus.DEGRADED
        )

    @property
    def colony_health_ratio(self) -> float:
        """Ratio of healthy cells to total cells."""
        if self.total_cells == 0:
            return 1.0
        return self.healthy_cells / self.total_cells

    def get_colony_summary(self) -> Dict[str, Any]:
        """Get summary of colony health state."""
        status_counts = {}
        for status in CellStatus:
            count = sum(
                1 for s in self._cells.values()
                if s.current_status == status
            )
            if count > 0:
                status_counts[status.value] = count

        return {
            "total_cells": self.total_cells,
            "healthy_cells": self.healthy_cells,
            "degraded_cells": self.degraded_cells,
            "colony_health_ratio": self.colony_health_ratio,
            "status_distribution": status_counts,
            "cells_needing_attention": len(self.get_cells_needing_attention()),
            "pending_approvals": len(self.get_cells_awaiting_approval()),
        }
