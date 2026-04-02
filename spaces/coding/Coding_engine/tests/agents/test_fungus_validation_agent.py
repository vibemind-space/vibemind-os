# -*- coding: utf-8 -*-
"""
Tests for FungusValidationAgent - Phase 17

Tests the autonomous validation agent that drives FungusValidationService
during epic generation.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState
from src.agents.fungus_validation_agent import FungusValidationAgent


@pytest.fixture
def event_bus():
    """Create a fresh EventBus."""
    return EventBus()


@pytest.fixture
def shared_state():
    """Create a fresh SharedState."""
    return SharedState()


@pytest.fixture
def agent(event_bus, shared_state, tmp_path):
    """Create a FungusValidationAgent for testing."""
    return FungusValidationAgent(
        name="test_fungus_validation",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        validation_interval=3,  # Lower threshold for testing
        min_files_for_validation=2,
        auto_fix_threshold=0.8,
    )


class TestFungusValidationAgentSubscription:
    """Test event subscriptions."""

    def test_subscribes_to_correct_events(self, agent):
        """Agent subscribes to all required event types."""
        expected = {
            EventType.EPIC_EXECUTION_STARTED,
            EventType.EPIC_TASK_COMPLETED,
            EventType.EPIC_TASK_FAILED,
            EventType.EPIC_EXECUTION_COMPLETED,
            EventType.FILE_CREATED,
            EventType.FILE_MODIFIED,
            EventType.CODE_GENERATED,
            EventType.BUILD_FAILED,
            EventType.TYPE_ERROR,
        }
        actual = set(agent.subscribed_events)
        assert actual == expected

    def test_name_is_set(self, agent):
        """Agent name is set correctly."""
        assert agent.name == "test_fungus_validation"


class TestFungusValidationAgentShouldAct:
    """Test should_act() logic."""

    @pytest.mark.asyncio
    async def test_should_act_on_subscribed_events(self, agent):
        """should_act() returns True for subscribed events."""
        event = Event(
            type=EventType.EPIC_EXECUTION_STARTED,
            source="test",
            data={"epic_id": "EPIC-001"},
        )
        result = await agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_events(self, agent):
        """should_act() returns False for unsubscribed events."""
        event = Event(
            type=EventType.DOCS_GENERATED,
            source="test",
            data={},
        )
        result = await agent.should_act([event])
        assert result is False


class TestFungusValidationAgentEpicLifecycle:
    """Test epic lifecycle handling."""

    @pytest.mark.asyncio
    async def test_epic_start_creates_service(self, agent):
        """EPIC_EXECUTION_STARTED creates the validation service."""
        with patch(
            "src.services.fungus_validation_service.FungusValidationService"
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=True)
            mock_instance.indexed_count = 5
            MockService.return_value = mock_instance

            event = Event(
                type=EventType.EPIC_EXECUTION_STARTED,
                source="orchestrator",
                data={"epic_id": "EPIC-001"},
            )

            await agent.act([event])

            assert agent._epic_active is True
            assert agent._current_epic_id == "EPIC-001"
            MockService.assert_called_once()
            mock_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_epic_end_stops_service(self, agent):
        """EPIC_EXECUTION_COMPLETED stops the service."""
        # Setup running service
        mock_service = MagicMock()
        mock_service.stop = AsyncMock(return_value=[])
        agent._validation_service = mock_service
        agent._epic_active = True
        agent._current_epic_id = "EPIC-001"

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={"epic_id": "EPIC-001"},
        )

        await agent.act([event])

        mock_service.stop.assert_called_once()
        assert agent._epic_active is False
        assert agent._validation_service is None

    @pytest.mark.asyncio
    async def test_no_action_before_epic_start(self, agent):
        """Events before EPIC_EXECUTION_STARTED are ignored."""
        assert agent._epic_active is False

        event = Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="executor",
            data={"task_id": "task1"},
        )

        # Should not crash
        await agent.act([event])
        assert agent._validation_service is None


class TestFungusValidationAgentTaskHandling:
    """Test task event handling."""

    @pytest.mark.asyncio
    async def test_task_completed_reindexes_files(self, agent):
        """EPIC_TASK_COMPLETED triggers re-indexing of task files."""
        mock_service = MagicMock()
        mock_service.reindex_file = AsyncMock(return_value=True)
        mock_service.add_completed_task = MagicMock()
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="executor",
            data={
                "task_id": "task1",
                "files_created": ["src/auth.ts"],
                "files_modified": ["src/app.ts"],
            },
        )

        await agent.act([event])

        assert mock_service.reindex_file.call_count == 2
        mock_service.add_completed_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_validation_threshold_triggers_round(self, agent):
        """Validation round triggered after enough files accumulated."""
        mock_service = MagicMock()
        mock_service.reindex_file = AsyncMock(return_value=True)
        mock_service.add_completed_task = MagicMock()
        mock_service.run_validation_round = AsyncMock(
            return_value=MagicMock(findings=[], round_number=1)
        )
        agent._validation_service = mock_service
        agent._epic_active = True
        agent._validation_interval = 2  # Trigger after 2 files

        # First task: 2 files → threshold met
        event = Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="executor",
            data={
                "task_id": "task1",
                "type": "schema_model",
                "title": "Create user schema",
                "files_created": ["src/a.ts", "src/b.ts"],
            },
        )

        await agent.act([event])

        # Validation should have been triggered
        mock_service.run_validation_round.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_failed_triggers_deep_validation(self, agent):
        """EPIC_TASK_FAILED triggers deep validation."""
        mock_service = MagicMock()
        mock_service.add_failed_error = MagicMock()
        mock_service.run_validation_round = AsyncMock(
            return_value=MagicMock(findings=[], round_number=1)
        )
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={
                "task_id": "task1",
                "type": "schema_model",
                "error_message": "Prisma schema not found",
            },
        )

        await agent.act([event])

        mock_service.add_failed_error.assert_called_once_with("Prisma schema not found")
        mock_service.run_validation_round.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_failed_triggers_repair_mode(self, agent):
        """BUILD_FAILED triggers repair-mode validation."""
        mock_service = MagicMock()
        mock_service.run_validation_round = AsyncMock(
            return_value=MagicMock(findings=[], round_number=1)
        )
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.BUILD_FAILED,
            source="builder",
            data={"message": "TypeScript compilation failed"},
            error_message="TypeScript compilation failed",
        )

        await agent.act([event])

        mock_service.run_validation_round.assert_called_once()
        call_args = mock_service.run_validation_round.call_args
        assert "repair" in call_args.kwargs.get("focus_query", call_args[1].get("focus_query", ""))


class TestFungusValidationAgentEventPublishing:
    """Test event publishing behavior."""

    @pytest.mark.asyncio
    async def test_high_confidence_publishes_code_fix_needed(self, agent, event_bus):
        """High-confidence error findings publish CODE_FIX_NEEDED."""
        from src.services.fungus_validation_service import ValidationFinding, ValidationReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        finding = ValidationFinding(
            finding_type="missing_import",
            severity="error",
            file_path="src/auth.ts",
            description="Missing import for PrismaClient",
            confidence=0.9,  # Above threshold
            evidence=[],
        )
        mock_service.run_validation_round = AsyncMock(
            return_value=ValidationReport(
                round_number=1,
                findings=[finding],
                files_analyzed=5,
                files_indexed=10,
            ),
        )
        mock_service.add_failed_error = MagicMock()
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={"error_message": "build failed", "type": "test"},
        )

        await agent.act([event])

        # Should have published: FUNGUS_VALIDATION_ISSUE + CODE_FIX_NEEDED + FUNGUS_VALIDATION_REPORT
        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_VALIDATION_ISSUE in event_types
        assert EventType.CODE_FIX_NEEDED in event_types
        assert EventType.FUNGUS_VALIDATION_REPORT in event_types

    @pytest.mark.asyncio
    async def test_low_confidence_only_publishes_fungus_event(self, agent, event_bus):
        """Low-confidence findings only publish FUNGUS_VALIDATION_ISSUE."""
        from src.services.fungus_validation_service import ValidationFinding, ValidationReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        finding = ValidationFinding(
            finding_type="pattern_violation",
            severity="error",
            file_path="src/auth.ts",
            description="Inconsistent naming",
            confidence=0.6,  # Below auto_fix_threshold (0.8)
            evidence=[],
        )
        mock_service.run_validation_round = AsyncMock(
            return_value=ValidationReport(
                round_number=1,
                findings=[finding],
                files_analyzed=3,
                files_indexed=10,
            ),
        )
        mock_service.add_failed_error = MagicMock()
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={"error_message": "failed", "type": "test"},
        )

        await agent.act([event])

        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_VALIDATION_ISSUE in event_types
        assert EventType.CODE_FIX_NEEDED not in event_types

    @pytest.mark.asyncio
    async def test_publishes_validation_report(self, agent, event_bus):
        """Validation round always publishes FUNGUS_VALIDATION_REPORT."""
        from src.services.fungus_validation_service import ValidationReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        mock_service.run_validation_round = AsyncMock(
            return_value=ValidationReport(
                round_number=1,
                findings=[],
                files_analyzed=5,
                files_indexed=10,
            ),
        )
        mock_service.add_failed_error = MagicMock()
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={"error_message": "error", "type": "test"},
        )

        await agent.act([event])

        report_events = [e for e in published_events if e.type == EventType.FUNGUS_VALIDATION_REPORT]
        assert len(report_events) == 1
        assert report_events[0].data["round"] == 1

    @pytest.mark.asyncio
    async def test_no_findings_publishes_passed(self, agent, event_bus):
        """No findings publishes FUNGUS_VALIDATION_PASSED."""
        from src.services.fungus_validation_service import ValidationReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        mock_service.run_validation_round = AsyncMock(
            return_value=ValidationReport(
                round_number=1,
                findings=[],
                files_analyzed=5,
                files_indexed=10,
                focus_query="test",
            ),
        )
        mock_service.add_failed_error = MagicMock()
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={"error_message": "error", "type": "test"},
        )

        await agent.act([event])

        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_VALIDATION_PASSED in event_types


class TestFungusValidationAgentGracefulDegradation:
    """Test graceful handling of errors."""

    @pytest.mark.asyncio
    async def test_handles_missing_service_gracefully(self, agent):
        """Agent handles events when service is None."""
        agent._epic_active = True
        agent._validation_service = None

        events = [
            Event(type=EventType.EPIC_TASK_COMPLETED, source="x", data={}),
            Event(type=EventType.BUILD_FAILED, source="x", data={}),
        ]

        # Should not crash
        await agent.act(events)

    @pytest.mark.asyncio
    async def test_handles_service_start_failure(self, agent):
        """Agent handles service start failure gracefully."""
        with patch(
            "src.services.fungus_validation_service.FungusValidationService"
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=False)  # Start fails
            MockService.return_value = mock_instance

            event = Event(
                type=EventType.EPIC_EXECUTION_STARTED,
                source="orchestrator",
                data={"epic_id": "EPIC-001"},
            )

            await agent.act([event])

            assert agent._epic_active is False
            assert agent._validation_service is None

    @pytest.mark.asyncio
    async def test_skips_own_events(self, agent):
        """Agent ignores events from itself."""
        mock_service = MagicMock()
        agent._validation_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.CODE_GENERATED,
            source="test_fungus_validation",  # Same as agent name
            data={"files": ["test.ts"]},
        )

        await agent.act([event])

        # Should not have called any service methods
        mock_service.reindex_file.assert_not_called()
