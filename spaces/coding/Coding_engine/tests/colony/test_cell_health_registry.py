"""
Tests for CellHealthRegistry health tracking.

Tests:
- Cell registration/deregistration
- Health check recording
- Status tracking and transitions
- Colony summary calculations
- Mutation pending state
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.colony.cell import Cell, CellStatus, MutationSeverity
from src.colony.cell_health_registry import (
    CellHealthRegistry, CellHealthState, HealthRecord, HealthCheckResult,
)
from src.mind.event_bus import EventBus, Event, EventType


class TestCellHealthRegistryRegistration:
    """Tests for cell registration."""

    @pytest.mark.asyncio
    async def test_register_cell(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test registering a new cell."""
        health_state = await health_registry.register_cell(sample_cell)

        assert health_state.cell_id == sample_cell.id
        assert health_state.cell_name == sample_cell.name
        assert health_registry.total_cells == 1

    @pytest.mark.asyncio
    async def test_register_cell_publishes_event(
        self,
        mock_event_bus: MagicMock,
        sample_cell: Cell,
    ):
        """Test that registration publishes CELL_CREATED event."""
        registry = CellHealthRegistry(event_bus=mock_event_bus)

        await registry.register_cell(sample_cell)

        mock_event_bus.publish.assert_called()
        call_args = mock_event_bus.publish.call_args
        event = call_args[0][0]
        assert event.type == EventType.CELL_CREATED

    @pytest.mark.asyncio
    async def test_register_duplicate_cell_returns_existing(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test registering duplicate cell returns existing state."""
        state1 = await health_registry.register_cell(sample_cell)
        state2 = await health_registry.register_cell(sample_cell)

        assert state1 is state2
        assert health_registry.total_cells == 1

    @pytest.mark.asyncio
    async def test_deregister_cell(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test deregistering a cell."""
        await health_registry.register_cell(sample_cell)
        result = await health_registry.deregister_cell(sample_cell.id)

        assert result is True
        assert health_registry.total_cells == 0

    @pytest.mark.asyncio
    async def test_deregister_nonexistent_cell_returns_false(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test deregistering non-existent cell returns False."""
        result = await health_registry.deregister_cell("nonexistent")

        assert result is False


class TestCellHealthRegistryHealthChecks:
    """Tests for health check recording."""

    @pytest.mark.asyncio
    async def test_record_health_check_passed(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test recording a passed health check."""
        await health_registry.register_cell(sample_cell)

        health_state = await health_registry.record_health_check(
            cell_id=sample_cell.id,
            result=HealthCheckResult.PASSED,
            response_time_ms=120,
            status_code=200,
        )

        assert health_state is not None
        assert health_state.consecutive_failures == 0
        assert health_state.consecutive_successes == 1

    @pytest.mark.asyncio
    async def test_record_health_check_failed(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test recording a failed health check."""
        await health_registry.register_cell(sample_cell)

        health_state = await health_registry.record_health_check(
            cell_id=sample_cell.id,
            result=HealthCheckResult.FAILED,
            error_message="Connection refused",
        )

        assert health_state is not None
        assert health_state.consecutive_failures == 1
        assert health_state.health_score < 1.0

    @pytest.mark.asyncio
    async def test_record_health_check_for_unknown_cell(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test recording health check for unregistered cell."""
        result = await health_registry.record_health_check(
            cell_id="unknown",
            result=HealthCheckResult.PASSED,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_health_score_decreases_on_failure(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test that health score decreases on failures."""
        await health_registry.register_cell(sample_cell)

        initial_state = health_registry.get_cell_health(sample_cell.id)
        initial_score = initial_state.health_score

        await health_registry.record_health_check(
            cell_id=sample_cell.id,
            result=HealthCheckResult.FAILED,
        )

        final_state = health_registry.get_cell_health(sample_cell.id)
        assert final_state.health_score < initial_score

    @pytest.mark.asyncio
    async def test_status_transitions_to_degraded(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test status transitions to DEGRADED after failures."""
        sample_cell.status = CellStatus.HEALTHY
        await health_registry.register_cell(sample_cell)

        # Record multiple failures
        for _ in range(4):
            await health_registry.record_health_check(
                cell_id=sample_cell.id,
                result=HealthCheckResult.FAILED,
            )

        health_state = health_registry.get_cell_health(sample_cell.id)
        assert health_state.current_status == CellStatus.DEGRADED


class TestCellHealthState:
    """Tests for CellHealthState dataclass."""

    def test_add_check_result_updates_history(
        self,
        cell_health_state: CellHealthState,
        health_record_passed: HealthRecord,
    ):
        """Test adding check result updates history."""
        cell_health_state.add_check_result(health_record_passed)

        assert len(cell_health_state.check_history) == 1
        assert cell_health_state.last_check is not None

    def test_add_check_result_limits_history(
        self,
        cell_health_state: CellHealthState,
    ):
        """Test that history is bounded."""
        cell_health_state.max_history = 5

        for i in range(10):
            record = HealthRecord(
                result=HealthCheckResult.PASSED,
                response_time_ms=i * 10,
            )
            cell_health_state.add_check_result(record)

        assert len(cell_health_state.check_history) == 5

    def test_is_healthy_property(self, cell_health_state: CellHealthState):
        """Test is_healthy property."""
        cell_health_state.current_status = CellStatus.HEALTHY
        cell_health_state.health_score = 0.9

        assert cell_health_state.is_healthy is True

        cell_health_state.health_score = 0.7
        assert cell_health_state.is_healthy is False

    def test_needs_attention_property(self, cell_health_state: CellHealthState):
        """Test needs_attention property."""
        cell_health_state.current_status = CellStatus.HEALTHY
        cell_health_state.health_score = 1.0
        cell_health_state.consecutive_failures = 0

        assert cell_health_state.needs_attention is False

        cell_health_state.current_status = CellStatus.DEGRADED
        assert cell_health_state.needs_attention is True

    def test_recent_pass_rate(self, cell_health_state: CellHealthState):
        """Test recent_pass_rate calculation."""
        # Add 8 passes and 2 failures
        for _ in range(8):
            cell_health_state.add_check_result(
                HealthRecord(result=HealthCheckResult.PASSED)
            )
        for _ in range(2):
            cell_health_state.add_check_result(
                HealthRecord(result=HealthCheckResult.FAILED)
            )

        assert cell_health_state.recent_pass_rate == 0.8

    def test_avg_response_time(self, cell_health_state: CellHealthState):
        """Test average response time calculation."""
        times = [100, 150, 200]
        for t in times:
            cell_health_state.add_check_result(
                HealthRecord(result=HealthCheckResult.PASSED, response_time_ms=t)
            )

        assert cell_health_state.avg_response_time_ms == pytest.approx(150, rel=0.01)


class TestCellHealthRegistryQueries:
    """Tests for registry query methods."""

    @pytest.mark.asyncio
    async def test_get_cell_health(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test getting cell health state."""
        await health_registry.register_cell(sample_cell)

        health_state = health_registry.get_cell_health(sample_cell.id)

        assert health_state is not None
        assert health_state.cell_id == sample_cell.id

    def test_get_all_cells(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test getting all cells."""
        cells = health_registry.get_all_cells()

        assert isinstance(cells, dict)

    @pytest.mark.asyncio
    async def test_get_cells_by_status(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test getting cells filtered by status."""
        # Register cells with different statuses
        for i, status in enumerate([CellStatus.HEALTHY, CellStatus.HEALTHY, CellStatus.DEGRADED]):
            cell = Cell(name=f"cell-{i}", status=status)
            await health_registry.register_cell(cell)

        healthy_cells = health_registry.get_cells_by_status(CellStatus.HEALTHY)
        degraded_cells = health_registry.get_cells_by_status(CellStatus.DEGRADED)

        assert len(healthy_cells) == 2
        assert len(degraded_cells) == 1

    @pytest.mark.asyncio
    async def test_get_cells_needing_attention(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test getting cells that need attention."""
        # Register a healthy cell
        healthy_cell = Cell(name="healthy", status=CellStatus.HEALTHY)
        await health_registry.register_cell(healthy_cell)

        # Register a degraded cell
        degraded_cell = Cell(name="degraded", status=CellStatus.DEGRADED)
        await health_registry.register_cell(degraded_cell)

        cells_needing_attention = health_registry.get_cells_needing_attention()

        assert len(cells_needing_attention) == 1
        assert cells_needing_attention[0].cell_name == "degraded"


class TestCellHealthRegistryMutationTracking:
    """Tests for mutation tracking."""

    @pytest.mark.asyncio
    async def test_mark_mutation_pending(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test marking a mutation as pending."""
        await health_registry.register_cell(sample_cell)

        health_state = await health_registry.mark_mutation_pending(
            sample_cell.id,
            MutationSeverity.HIGH,
        )

        assert health_state.pending_mutation is True
        assert health_state.mutation_severity == MutationSeverity.HIGH
        assert health_state.mutation_approval_required is True

    @pytest.mark.asyncio
    async def test_mark_mutation_pending_low_severity(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test LOW severity mutation doesn't require approval."""
        await health_registry.register_cell(sample_cell)

        health_state = await health_registry.mark_mutation_pending(
            sample_cell.id,
            MutationSeverity.LOW,
        )

        assert health_state.mutation_approval_required is False

    @pytest.mark.asyncio
    async def test_clear_mutation_pending(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test clearing pending mutation state."""
        await health_registry.register_cell(sample_cell)
        await health_registry.mark_mutation_pending(
            sample_cell.id,
            MutationSeverity.CRITICAL,
        )

        health_state = await health_registry.clear_mutation_pending(sample_cell.id)

        assert health_state.pending_mutation is False
        assert health_state.mutation_approval_required is False
        assert health_state.mutation_severity is None

    @pytest.mark.asyncio
    async def test_get_cells_awaiting_approval(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test getting cells awaiting mutation approval."""
        cell1 = Cell(name="cell1")
        cell2 = Cell(name="cell2")

        await health_registry.register_cell(cell1)
        await health_registry.register_cell(cell2)

        await health_registry.mark_mutation_pending(cell1.id, MutationSeverity.HIGH)

        awaiting = health_registry.get_cells_awaiting_approval()

        assert len(awaiting) == 1
        assert awaiting[0].cell_name == "cell1"


class TestCellHealthRegistryMetrics:
    """Tests for colony-level metrics."""

    @pytest.mark.asyncio
    async def test_total_cells_count(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test total cells count."""
        for i in range(5):
            cell = Cell(name=f"cell-{i}")
            await health_registry.register_cell(cell)

        assert health_registry.total_cells == 5

    @pytest.mark.asyncio
    async def test_healthy_cells_count(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test healthy cells count."""
        for i in range(3):
            cell = Cell(name=f"healthy-{i}", status=CellStatus.HEALTHY, health_score=1.0)
            await health_registry.register_cell(cell)

        cell = Cell(name="degraded", status=CellStatus.DEGRADED, health_score=0.5)
        await health_registry.register_cell(cell)

        assert health_registry.healthy_cells == 3

    @pytest.mark.asyncio
    async def test_colony_health_ratio(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test colony health ratio calculation."""
        # 2 healthy, 2 degraded
        for i in range(2):
            cell = Cell(name=f"healthy-{i}", status=CellStatus.HEALTHY, health_score=1.0)
            await health_registry.register_cell(cell)
        for i in range(2):
            cell = Cell(name=f"degraded-{i}", status=CellStatus.DEGRADED, health_score=0.5)
            await health_registry.register_cell(cell)

        assert health_registry.colony_health_ratio == 0.5

    def test_colony_health_ratio_empty_colony(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test health ratio for empty colony."""
        assert health_registry.colony_health_ratio == 1.0

    @pytest.mark.asyncio
    async def test_get_colony_summary(
        self,
        health_registry: CellHealthRegistry,
    ):
        """Test getting colony summary."""
        for i in range(2):
            cell = Cell(name=f"healthy-{i}", status=CellStatus.HEALTHY, health_score=1.0)
            await health_registry.register_cell(cell)

        cell = Cell(name="degraded", status=CellStatus.DEGRADED, health_score=0.5)
        await health_registry.register_cell(cell)

        await health_registry.mark_mutation_pending(cell.id, MutationSeverity.HIGH)

        summary = health_registry.get_colony_summary()

        assert summary["total_cells"] == 3
        assert summary["healthy_cells"] == 2
        assert summary["degraded_cells"] == 1
        assert summary["colony_health_ratio"] == pytest.approx(0.666, rel=0.01)
        assert summary["pending_approvals"] == 1


class TestCellHealthRegistryRecovery:
    """Tests for recovery tracking."""

    @pytest.mark.asyncio
    async def test_mark_recovery_started(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test marking recovery as started."""
        await health_registry.register_cell(sample_cell)

        health_state = await health_registry.mark_recovery_started(sample_cell.id)

        assert health_state.recovery_attempts == 1
        assert health_state.last_recovery_at is not None
        assert health_state.current_status == CellStatus.RECOVERING

    @pytest.mark.asyncio
    async def test_update_cell_status(
        self,
        health_registry: CellHealthRegistry,
        sample_cell: Cell,
    ):
        """Test manually updating cell status."""
        await health_registry.register_cell(sample_cell)

        health_state = await health_registry.update_cell_status(
            sample_cell.id,
            CellStatus.HEALTHY,
        )

        assert health_state.current_status == CellStatus.HEALTHY


class TestHealthRecord:
    """Tests for HealthRecord dataclass."""

    def test_health_record_creation(self, health_record_passed: HealthRecord):
        """Test HealthRecord creation."""
        assert health_record_passed.result == HealthCheckResult.PASSED
        assert health_record_passed.response_time_ms == 120

    def test_health_record_with_error(self, health_record_failed: HealthRecord):
        """Test HealthRecord with error message."""
        assert health_record_failed.result == HealthCheckResult.FAILED
        assert health_record_failed.error_message == "Internal server error"


class TestHealthCheckResult:
    """Tests for HealthCheckResult enum."""

    def test_health_check_result_values(self):
        """Test all HealthCheckResult values exist."""
        assert HealthCheckResult.PASSED.value == "passed"
        assert HealthCheckResult.FAILED.value == "failed"
        assert HealthCheckResult.TIMEOUT.value == "timeout"
        assert HealthCheckResult.UNKNOWN.value == "unknown"
