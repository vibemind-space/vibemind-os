"""
Tests for ColonyManager orchestration.

Tests:
- Colony initialization
- Cell spawning
- Cell termination
- Colony health monitoring
- Rebalancing logic
- Mutation approval workflow
- Scale up/down decisions
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.colony.cell import Cell, CellStatus, SourceType, MutationSeverity
from src.colony.colony_manager import ColonyManager, ColonyConfig, ColonyStatus
from src.colony.cell_health_registry import CellHealthRegistry
from src.mind.event_bus import EventBus, Event, EventType


class TestColonyManagerInitialization:
    """Tests for ColonyManager initialization."""

    def test_manager_uses_default_config(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test manager uses default config when none provided."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
        )

        assert manager.config.max_cells == 100
        assert manager.config.namespace == "cell-colony"

    def test_manager_uses_custom_config(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test manager uses provided config."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        assert manager.config.max_cells == 10
        assert manager.config.namespace == "test-colony"

    def test_manager_creates_health_registry(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test that manager creates health registry."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
        )

        assert manager.health_registry is not None
        assert isinstance(manager.health_registry, CellHealthRegistry)


class TestColonyManagerLifecycle:
    """Tests for manager lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_sets_running_phase(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test that starting manager sets Running phase."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        await manager.start()

        assert manager.status.phase == "Running"
        assert manager.status.started_at is not None

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_terminates_all_agents(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test that stopping manager terminates agents."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        await manager.start()
        await manager.stop()

        assert manager.status.phase == "Terminated"


class TestColonyCellSpawning:
    """Tests for cell spawning."""

    @pytest.mark.asyncio
    async def test_spawn_cell_creates_cell(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test spawning a new cell."""
        colony_config.use_kubernetes = False
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        # Mock the cell agent methods
        with patch("src.colony.cell_agent.CellAgent") as MockAgent:
            mock_agent = MagicMock()
            mock_agent.initialize_cell = AsyncMock()
            mock_agent.build_and_deploy = AsyncMock()
            mock_agent.start = AsyncMock()
            MockAgent.return_value = mock_agent

            cell = await manager.spawn_cell(
                name="test-service",
                source_type=SourceType.LLM_GENERATED,
                source_ref="REST API for users",
            )

            assert cell.name == "test-service"
            assert cell.source_type == SourceType.LLM_GENERATED
            assert cell.id in manager._cells

    @pytest.mark.asyncio
    async def test_spawn_cell_respects_max_cells(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test that spawning fails when at max capacity."""
        config = ColonyConfig(max_cells=0)
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=config,
        )

        with pytest.raises(RuntimeError, match="max capacity"):
            await manager.spawn_cell(
                name="test",
                source_type=SourceType.LLM_GENERATED,
                source_ref="test",
            )


class TestColonyCellTermination:
    """Tests for cell termination."""

    @pytest.mark.asyncio
    async def test_terminate_cell_removes_from_registry(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        sample_cell: Cell,
        colony_config: ColonyConfig,
    ):
        """Test that terminating a cell removes it from registry."""
        colony_config.use_kubernetes = False
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        # Add cell directly to manager
        manager._cells[sample_cell.id] = sample_cell

        result = await manager.terminate_cell(sample_cell.id, "Testing")

        assert result is True
        assert sample_cell.status == CellStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_cell_returns_false(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test terminating non-existent cell returns False."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        result = await manager.terminate_cell("nonexistent-id")

        assert result is False


class TestColonyHealthMonitoring:
    """Tests for colony health monitoring."""

    @pytest.mark.asyncio
    async def test_update_status_counts_cells_by_status(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test status update counts cells correctly."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        # Add cells with different statuses
        for i, status in enumerate([CellStatus.HEALTHY, CellStatus.HEALTHY, CellStatus.DEGRADED]):
            cell = Cell(name=f"cell-{i}", status=status)
            manager._cells[cell.id] = cell

        await manager._update_status()

        assert manager.status.total_cells == 3
        assert manager.status.healthy_cells == 2
        assert manager.status.degraded_cells == 1
        assert manager.status.health_ratio == pytest.approx(0.666, rel=0.01)


class TestColonyRebalancing:
    """Tests for colony rebalancing."""

    @pytest.mark.asyncio
    async def test_rebalance_triggered_below_threshold(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test rebalancing is triggered when health ratio drops."""
        config = ColonyConfig(rebalance_threshold=0.8)
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=config,
        )

        manager._status.health_ratio = 0.5
        manager._status.rebalance_in_progress = False

        # Mock trigger_rebalance
        manager._trigger_rebalance = AsyncMock()

        await manager._maybe_trigger_rebalance()

        manager._trigger_rebalance.assert_called_once()

    @pytest.mark.asyncio
    async def test_rebalance_not_triggered_above_threshold(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test rebalancing is not triggered when health is good."""
        config = ColonyConfig(rebalance_threshold=0.8)
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=config,
        )

        manager._status.health_ratio = 0.9
        manager._trigger_rebalance = AsyncMock()

        await manager._maybe_trigger_rebalance()

        manager._trigger_rebalance.assert_not_called()


class TestMutationApprovalWorkflow:
    """Tests for mutation approval handling."""

    @pytest.mark.asyncio
    async def test_approve_mutation(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        sample_cell: Cell,
        colony_config: ColonyConfig,
    ):
        """Test approving a pending mutation."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        # Add pending approval
        manager._pending_approvals[sample_cell.id] = Event(
            type=EventType.MUTATION_APPROVAL_REQUIRED,
            source="test",
            data={"cell_id": sample_cell.id},
        )

        result = await manager.approve_mutation(sample_cell.id, "admin")

        assert result is True
        mock_event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_reject_mutation(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        sample_cell: Cell,
        colony_config: ColonyConfig,
    ):
        """Test rejecting a pending mutation."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        # Add pending approval
        manager._pending_approvals[sample_cell.id] = Event(
            type=EventType.MUTATION_APPROVAL_REQUIRED,
            source="test",
            data={"cell_id": sample_cell.id},
        )

        result = await manager.reject_mutation(sample_cell.id, "Too risky")

        assert result is True
        mock_event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_get_pending_approvals(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        sample_cell: Cell,
        colony_config: ColonyConfig,
    ):
        """Test getting list of pending approvals."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        manager._cells[sample_cell.id] = sample_cell
        manager._pending_approvals[sample_cell.id] = Event(
            type=EventType.MUTATION_APPROVAL_REQUIRED,
            source="test",
            data={
                "cell_id": sample_cell.id,
                "severity": "high",
                "error_message": "Build failed",
            },
        )

        approvals = manager.get_pending_approvals()

        assert len(approvals) == 1
        assert approvals[0]["cell_id"] == sample_cell.id
        assert approvals[0]["severity"] == "high"


class TestColonyEventHandling:
    """Tests for event handling."""

    @pytest.mark.asyncio
    async def test_handle_cell_ready_updates_status(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        sample_cell: Cell,
        colony_config: ColonyConfig,
    ):
        """Test handling CELL_READY event."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        manager._cells[sample_cell.id] = sample_cell
        sample_cell.status = CellStatus.DEPLOYING

        event = Event(
            type=EventType.CELL_READY,
            source="test",
            data={"cell_id": sample_cell.id},
        )

        await manager._handle_cell_ready(event)

        assert sample_cell.status == CellStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_handle_mutation_applied_updates_counters(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test handling CELL_MUTATION_APPLIED event."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        initial_mutations = manager._status.total_mutations
        initial_successful = manager._status.successful_mutations

        event = Event(
            type=EventType.CELL_MUTATION_APPLIED,
            source="test",
            data={},
        )

        await manager._handle_mutation_applied(event)

        assert manager._status.total_mutations == initial_mutations + 1
        assert manager._status.successful_mutations == initial_successful + 1


class TestColonyStatusProperty:
    """Tests for colony status property."""

    def test_status_returns_current_status(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        colony_config: ColonyConfig,
    ):
        """Test status property returns current status."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        manager._status.phase = "Testing"

        assert manager.status.phase == "Testing"

    def test_cells_property_returns_copy(
        self,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        sample_cell: Cell,
        colony_config: ColonyConfig,
    ):
        """Test cells property returns a copy."""
        manager = ColonyManager(
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            config=colony_config,
        )

        manager._cells[sample_cell.id] = sample_cell
        cells = manager.cells

        # Modifying the returned dict should not affect internal state
        cells.clear()

        assert len(manager._cells) == 1


class TestColonyStatusDataclass:
    """Tests for ColonyStatus dataclass."""

    def test_colony_status_to_dict(self, colony_status: ColonyStatus):
        """Test ColonyStatus serialization."""
        data = colony_status.to_dict()

        assert data["phase"] == "Running"
        assert data["total_cells"] == 5
        assert data["healthy_cells"] == 4
        assert data["health_ratio"] == 0.8

    def test_colony_status_defaults(self):
        """Test ColonyStatus default values."""
        status = ColonyStatus()

        assert status.phase == "Creating"
        assert status.total_cells == 0
        assert status.health_ratio == 1.0
