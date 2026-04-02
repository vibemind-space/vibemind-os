"""
Tests for CellAgent lifecycle and event handling.

Tests:
- Agent initialization
- Event subscription
- should_act conditions
- Health check execution
- Mutation handling
- Recovery procedures
- Autophagy triggers
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.colony.cell import Cell, CellStatus, SourceType, MutationSeverity
from src.colony.cell_agent import CellAgent, CellAgentConfig
from src.colony.cell_health_registry import CellHealthRegistry, HealthCheckResult
from src.mind.event_bus import EventBus, Event, EventType


class TestCellAgentInitialization:
    """Tests for CellAgent initialization."""

    def test_agent_name_includes_cell_name(
        self,
        sample_cell: Cell,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test that agent name includes the cell name."""
        health_registry = CellHealthRegistry()
        agent = CellAgent(
            cell=sample_cell,
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            health_registry=health_registry,
        )

        assert sample_cell.name in agent.name

    def test_agent_uses_custom_config(
        self,
        sample_cell: Cell,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
        cell_agent_config: CellAgentConfig,
    ):
        """Test that agent uses provided configuration."""
        health_registry = CellHealthRegistry()
        agent = CellAgent(
            cell=sample_cell,
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            health_registry=health_registry,
            config=cell_agent_config,
        )

        assert agent.config.health_check_interval == 30
        assert agent.config.max_mutations == 10

    def test_agent_inherits_cell_working_dir(
        self,
        sample_cell: Cell,
        mock_event_bus: MagicMock,
        mock_shared_state: MagicMock,
    ):
        """Test that agent uses cell's working directory."""
        health_registry = CellHealthRegistry()
        agent = CellAgent(
            cell=sample_cell,
            event_bus=mock_event_bus,
            shared_state=mock_shared_state,
            health_registry=health_registry,
        )

        assert agent.working_dir == sample_cell.working_dir


class TestCellAgentEventSubscription:
    """Tests for event subscriptions."""

    def test_subscribed_events(self, cell_agent: CellAgent):
        """Test that agent subscribes to correct events."""
        events = cell_agent.subscribed_events

        # Health events
        assert EventType.CELL_HEALTH_CHECK in events
        assert EventType.CELL_HEALTH_FAILED in events

        # Mutation events
        assert EventType.CELL_MUTATION_REQUESTED in events
        assert EventType.USER_MUTATION_APPROVED in events
        assert EventType.USER_MUTATION_REJECTED in events

        # Recovery events
        assert EventType.CELL_RECOVERING in events

        # Autophagy events
        assert EventType.CELL_AUTOPHAGY_TRIGGERED in events


class TestCellAgentShouldAct:
    """Tests for should_act decision logic."""

    @pytest.mark.asyncio
    async def test_should_act_on_health_check_event(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that agent acts on health check events for its cell."""
        event = Event(
            type=EventType.CELL_HEALTH_CHECK,
            source="test",
            data={"cell_id": sample_cell.id},
        )

        result = await cell_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_other_cell_events(
        self,
        cell_agent: CellAgent,
    ):
        """Test that agent ignores events for other cells."""
        event = Event(
            type=EventType.CELL_HEALTH_CHECK,
            source="test",
            data={"cell_id": "other-cell-id"},
        )

        result = await cell_agent.should_act([event])
        assert result is False

    @pytest.mark.asyncio
    async def test_should_act_on_mutation_event(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that agent acts on mutation request events."""
        event = Event(
            type=EventType.CELL_MUTATION_REQUESTED,
            source="test",
            data={
                "cell_id": sample_cell.id,
                "severity": "low",
            },
        )

        result = await cell_agent.should_act([event])
        assert result is True


class TestCellAgentHealthChecks:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_perform_health_check_on_healthy_cell(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test health check execution on healthy cell."""
        # Set cell to healthy state
        sample_cell.status = CellStatus.HEALTHY

        # Mock aiohttp response
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_get = AsyncMock(return_value=mock_response)
            mock_session_instance = MagicMock()
            mock_session_instance.get = mock_get
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock()
            mock_session.return_value = mock_session_instance

            event = await cell_agent._perform_health_check()

            # Verify health was updated
            assert sample_cell.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_health_check_skipped_for_non_running_cell(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that health check is skipped for non-running cells."""
        sample_cell.status = CellStatus.PENDING

        result = await cell_agent._perform_health_check()

        assert result is None

    @pytest.mark.asyncio
    async def test_handle_health_failure_triggers_mutation(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that health failure triggers mutation request."""
        sample_cell.status = CellStatus.DEGRADED
        sample_cell.consecutive_failures = 2

        event = Event(
            type=EventType.CELL_HEALTH_FAILED,
            source="test",
            data={
                "cell_id": sample_cell.id,
                "error_message": "Connection refused",
            },
        )

        result = await cell_agent._handle_health_failure(event)

        assert result is not None
        assert result.type == EventType.CELL_MUTATION_REQUESTED


class TestCellAgentMutations:
    """Tests for mutation handling."""

    @pytest.mark.asyncio
    async def test_handle_low_severity_mutation_auto_applies(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that LOW severity mutations auto-apply."""
        cell_agent.config.auto_approve_low_severity = True

        event = Event(
            type=EventType.CELL_MUTATION_REQUESTED,
            source="test",
            data={
                "cell_id": sample_cell.id,
                "severity": "low",
                "trigger_event": "health_failure",
            },
        )

        # Mock the apply_mutation method
        cell_agent._apply_mutation = AsyncMock(return_value=Event(
            type=EventType.CELL_MUTATION_APPLIED,
            source="test",
            data={"cell_id": sample_cell.id},
        ))

        result = await cell_agent._handle_mutation_request(event)

        cell_agent._apply_mutation.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_severity_mutation_requires_approval(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that HIGH severity mutations require approval."""
        cell_agent.config.auto_approve_low_severity = False

        event = Event(
            type=EventType.CELL_MUTATION_REQUESTED,
            source="test",
            data={
                "cell_id": sample_cell.id,
                "severity": "high",
                "trigger_event": "health_failure",
            },
        )

        result = await cell_agent._handle_mutation_request(event)

        assert result.type == EventType.MUTATION_APPROVAL_REQUIRED

    @pytest.mark.asyncio
    async def test_handle_mutation_approved(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test handling of approved mutation."""
        cell_agent._pending_mutation = {
            "cell_id": sample_cell.id,
            "severity": "high",
            "trigger_event": "health_failure",
        }

        cell_agent._apply_mutation_from_data = AsyncMock(return_value=Event(
            type=EventType.CELL_MUTATION_APPLIED,
            source="test",
            data={"cell_id": sample_cell.id},
        ))

        event = Event(
            type=EventType.USER_MUTATION_APPROVED,
            source="operator",
            data={
                "cell_id": sample_cell.id,
                "approved_by": "admin",
            },
        )

        await cell_agent._handle_mutation_approved(event)

        assert cell_agent._mutation_approved is True
        cell_agent._apply_mutation_from_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_mutation_rejected(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test handling of rejected mutation."""
        cell_agent._pending_mutation = {"cell_id": sample_cell.id}

        event = Event(
            type=EventType.USER_MUTATION_REJECTED,
            source="operator",
            data={
                "cell_id": sample_cell.id,
                "reason": "Too risky",
            },
        )

        result = await cell_agent._handle_mutation_rejected(event)

        assert cell_agent._pending_mutation is None
        assert sample_cell.status == CellStatus.DEGRADED
        assert result.type == EventType.CELL_MUTATION_REJECTED


class TestCellAgentRecovery:
    """Tests for recovery procedures."""

    @pytest.mark.asyncio
    async def test_perform_recovery(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test recovery procedure execution."""
        sample_cell.status = CellStatus.DEGRADED

        # Mock health check to return success
        cell_agent._perform_health_check = AsyncMock(return_value=Event(
            type=EventType.CELL_HEALTH_PASSED,
            source="test",
            data={"cell_id": sample_cell.id},
        ))

        # Set cell to healthy for is_healthy check
        sample_cell.status = CellStatus.HEALTHY
        sample_cell.health_score = 1.0

        event = Event(
            type=EventType.CELL_RECOVERING,
            source="test",
            data={"cell_id": sample_cell.id},
        )

        result = await cell_agent._perform_recovery(event)

        assert result is not None


class TestCellAgentAutophagy:
    """Tests for autophagy (graceful termination)."""

    @pytest.mark.asyncio
    async def test_perform_autophagy(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test autophagy procedure."""
        sample_cell.status = CellStatus.DEGRADED
        sample_cell.mutation_count = 15

        event = Event(
            type=EventType.CELL_AUTOPHAGY_TRIGGERED,
            source="colony_manager",
            data={
                "cell_id": sample_cell.id,
                "reason": "Max mutations exceeded",
            },
        )

        result = await cell_agent._perform_autophagy(event)

        assert result is not None
        assert sample_cell.status == CellStatus.TERMINATED
        assert sample_cell.terminated_at is not None

    @pytest.mark.asyncio
    async def test_autophagy_triggered_on_max_failures(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test autophagy trigger when max mutations reached."""
        from src.colony.cell import MutationRecord

        sample_cell.max_mutations = 3
        sample_cell.mutations = [
            MutationRecord(success=False) for _ in range(4)
        ]

        event = Event(
            type=EventType.CELL_HEALTH_FAILED,
            source="test",
            data={
                "cell_id": sample_cell.id,
                "error_message": "Health check failed",
            },
        )

        result = await cell_agent._handle_health_failure(event)

        assert result.type == EventType.CELL_AUTOPHAGY_TRIGGERED


class TestCellAgentEventCreation:
    """Tests for event creation helpers."""

    @pytest.mark.asyncio
    async def test_create_event_includes_cell_data(
        self,
        cell_agent: CellAgent,
        sample_cell: Cell,
    ):
        """Test that created events include cell information."""
        event = await cell_agent._create_event(
            EventType.CELL_READY,
            success=True,
            extra_data="test",
        )

        assert event.data["cell_id"] == sample_cell.id
        assert event.data["cell_name"] == sample_cell.name
        assert event.data["status"] == sample_cell.status.value
        assert event.data["extra_data"] == "test"


# Fixture for sample_cell using pytest naming conventions
@pytest.fixture
def Sample_cell(sample_cell):
    """Alias for sample_cell fixture."""
    return sample_cell
