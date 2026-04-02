# -*- coding: utf-8 -*-
"""
Tests for FungusMemoryAgent - Phase 18

Tests the autonomous memory-augmented MCMP agent that discovers correlations
between Supermemory and current code during epic generation.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState
from src.agents.fungus_memory_agent import FungusMemoryAgent


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
    """Create a FungusMemoryAgent for testing."""
    return FungusMemoryAgent(
        name="test_fungus_memory",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        memory_interval=3,  # Lower threshold for testing
        min_files_for_search=2,
        auto_enrich_threshold=0.7,
    )


class TestFungusMemoryAgentSubscription:
    """Test event subscriptions."""

    def test_subscribes_to_correct_events(self, agent):
        """Agent subscribes to all required event types."""
        expected = {
            EventType.EPIC_EXECUTION_STARTED,
            EventType.EPIC_TASK_COMPLETED,
            EventType.EPIC_TASK_FAILED,
            EventType.EPIC_EXECUTION_COMPLETED,
            EventType.CODE_GENERATED,
            EventType.BUILD_FAILED,
            EventType.TYPE_ERROR,
            EventType.CODE_FIX_NEEDED,
        }
        actual = set(agent.subscribed_events)
        assert actual == expected

    def test_name_is_set(self, agent):
        """Agent name is set correctly."""
        assert agent.name == "test_fungus_memory"


class TestFungusMemoryAgentShouldAct:
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


class TestFungusMemoryAgentEpicLifecycle:
    """Test epic lifecycle handling."""

    @pytest.mark.asyncio
    async def test_epic_start_creates_service(self, agent):
        """EPIC_EXECUTION_STARTED creates the memory service."""
        with patch(
            "src.services.fungus_memory_service.FungusMemoryService"
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=True)
            mock_instance.indexed_count = 5
            mock_instance.memory_count = 3
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
        """EPIC_EXECUTION_COMPLETED stops the service and runs learning."""
        from src.services.fungus_memory_service import MemoryReport

        mock_service = MagicMock()
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[])
        )
        mock_service.store_pending_patterns = AsyncMock(return_value=0)
        mock_service.stop = AsyncMock(return_value=[])
        agent._memory_service = mock_service
        agent._epic_active = True
        agent._current_epic_id = "EPIC-001"

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={"epic_id": "EPIC-001"},
        )

        await agent.act([event])

        mock_service.run_memory_round.assert_called_once()  # Learning round
        mock_service.store_pending_patterns.assert_called_once()
        mock_service.stop.assert_called_once()
        assert agent._epic_active is False
        assert agent._memory_service is None

    @pytest.mark.asyncio
    async def test_no_action_before_epic_start(self, agent):
        """Events before EPIC_EXECUTION_STARTED are ignored."""
        assert agent._epic_active is False

        event = Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="executor",
            data={"task_id": "task1"},
        )

        await agent.act([event])
        assert agent._memory_service is None


class TestFungusMemoryAgentTaskHandling:
    """Test task event handling."""

    @pytest.mark.asyncio
    async def test_task_completed_reindexes_files(self, agent):
        """EPIC_TASK_COMPLETED triggers re-indexing of task files."""
        mock_service = MagicMock()
        mock_service.reindex_file = AsyncMock(return_value=True)
        agent._memory_service = mock_service
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

    @pytest.mark.asyncio
    async def test_task_completed_triggers_recall(self, agent):
        """Pattern recall triggered after enough files accumulated."""
        from src.services.fungus_memory_service import MemoryReport

        mock_service = MagicMock()
        mock_service.reindex_file = AsyncMock(return_value=True)
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[])
        )
        agent._memory_service = mock_service
        agent._epic_active = True
        agent._memory_interval = 2  # Trigger after 2 files

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

        mock_service.run_memory_round.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_failed_runs_fix_recall(self, agent):
        """EPIC_TASK_FAILED triggers error fix recall."""
        from src.services.fungus_memory_service import MemoryReport

        mock_service = MagicMock()
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[])
        )
        agent._memory_service = mock_service
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

        mock_service.run_memory_round.assert_called_once()
        call_args = mock_service.run_memory_round.call_args
        assert "fix" in call_args.kwargs.get("focus_query", call_args[1].get("focus_query", "")).lower()

    @pytest.mark.asyncio
    async def test_build_failed_runs_fix_recall(self, agent):
        """BUILD_FAILED triggers error fix recall."""
        from src.services.fungus_memory_service import MemoryReport

        mock_service = MagicMock()
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[])
        )
        agent._memory_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.BUILD_FAILED,
            source="builder",
            data={"message": "TypeScript compilation failed"},
            error_message="TypeScript compilation failed",
        )

        await agent.act([event])

        mock_service.run_memory_round.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_fix_needed_enriches_context(self, agent):
        """CODE_FIX_NEEDED triggers context enrichment."""
        from src.services.fungus_memory_service import MemoryReport

        mock_service = MagicMock()
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[])
        )
        agent._memory_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="validator",
            data={"description": "Missing import", "file_path": "src/auth.ts"},
        )

        await agent.act([event])

        mock_service.run_memory_round.assert_called_once()


class TestFungusMemoryAgentEventPublishing:
    """Test event publishing behavior."""

    @pytest.mark.asyncio
    async def test_publishes_fix_suggested(self, agent, event_bus):
        """Fix recall correlations publish FUNGUS_MEMORY_FIX_SUGGESTED."""
        from src.services.fungus_memory_service import MemoryCorrelation, MemoryReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        corr = MemoryCorrelation(
            memory_id="mem1",
            memory_category="error_fix",
            correlation_type="applicable_fix",
            related_code_files=["src/auth.ts"],
            relevance_score=0.9,
            description="Past fix for similar error",
            suggested_action="Apply the fix",
        )
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[corr]),
        )
        agent._memory_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={"error_message": "build failed", "type": "test"},
        )

        await agent.act([event])

        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_MEMORY_FIX_SUGGESTED in event_types
        assert EventType.FUNGUS_MEMORY_REPORT in event_types

    @pytest.mark.asyncio
    async def test_publishes_context_enriched(self, agent, event_bus):
        """Context enrichment publishes FUNGUS_MEMORY_CONTEXT_ENRICHED."""
        from src.services.fungus_memory_service import MemoryCorrelation, MemoryReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        corr = MemoryCorrelation(
            memory_id="mem1",
            memory_category="architecture",
            correlation_type="context_enrichment",
            related_code_files=["src/auth.ts"],
            relevance_score=0.8,
            description="Architecture context",
        )
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[corr]),
        )
        agent._memory_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="validator",
            data={"description": "Missing import", "file_path": "src/auth.ts"},
        )

        await agent.act([event])

        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_MEMORY_CONTEXT_ENRICHED in event_types

    @pytest.mark.asyncio
    async def test_publishes_pattern_found(self, agent, event_bus):
        """Pattern recall publishes FUNGUS_MEMORY_PATTERN_FOUND."""
        from src.services.fungus_memory_service import MemoryCorrelation, MemoryReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        mock_service.reindex_file = AsyncMock(return_value=True)
        corr = MemoryCorrelation(
            memory_id="mem1",
            memory_category="code_pattern",
            correlation_type="similar_pattern",
            related_code_files=["src/auth.ts"],
            relevance_score=0.8,
            description="Similar Hono pattern",
        )
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[corr]),
        )
        agent._memory_service = mock_service
        agent._epic_active = True
        agent._memory_interval = 1  # Trigger immediately

        event = Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="executor",
            data={
                "task_id": "task1",
                "type": "api_route",
                "title": "Create auth routes",
                "files_created": ["src/auth.ts"],
            },
        )

        await agent.act([event])

        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_MEMORY_PATTERN_FOUND in event_types

    @pytest.mark.asyncio
    async def test_publishes_memory_report(self, agent, event_bus):
        """Every round publishes FUNGUS_MEMORY_REPORT."""
        from src.services.fungus_memory_service import MemoryReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(
                round_number=1,
                correlations=[],
                code_files_analyzed=5,
                memories_searched=3,
            ),
        )
        agent._memory_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.EPIC_TASK_FAILED,
            source="executor",
            data={"error_message": "error", "type": "test"},
        )

        await agent.act([event])

        report_events = [e for e in published_events if e.type == EventType.FUNGUS_MEMORY_REPORT]
        assert len(report_events) == 1
        assert report_events[0].data["round"] == 1

    @pytest.mark.asyncio
    async def test_publishes_memory_stored(self, agent, event_bus):
        """Epic end with stored patterns publishes FUNGUS_MEMORY_STORED."""
        from src.services.fungus_memory_service import MemoryReport

        published_events = []
        original_publish = event_bus.publish

        async def capture_publish(event):
            published_events.append(event)
            await original_publish(event)

        event_bus.publish = capture_publish

        mock_service = MagicMock()
        mock_service.run_memory_round = AsyncMock(
            return_value=MemoryReport(round_number=1, correlations=[])
        )
        mock_service.store_pending_patterns = AsyncMock(return_value=2)
        mock_service.stop = AsyncMock(return_value=[])
        agent._memory_service = mock_service
        agent._epic_active = True
        agent._current_epic_id = "EPIC-001"

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={"epic_id": "EPIC-001"},
        )

        await agent.act([event])

        event_types = [e.type for e in published_events]
        assert EventType.FUNGUS_MEMORY_STORED in event_types
        stored_event = [e for e in published_events if e.type == EventType.FUNGUS_MEMORY_STORED][0]
        assert stored_event.data["patterns_stored"] == 2


class TestFungusMemoryAgentGracefulDegradation:
    """Test graceful handling of errors."""

    @pytest.mark.asyncio
    async def test_handles_missing_service_gracefully(self, agent):
        """Agent handles events when service is None."""
        agent._epic_active = True
        agent._memory_service = None

        events = [
            Event(type=EventType.EPIC_TASK_COMPLETED, source="x", data={}),
            Event(type=EventType.BUILD_FAILED, source="x", data={}),
            Event(type=EventType.CODE_FIX_NEEDED, source="x", data={}),
        ]

        await agent.act(events)  # Should not crash

    @pytest.mark.asyncio
    async def test_handles_service_start_failure(self, agent):
        """Agent handles service start failure gracefully."""
        with patch(
            "src.services.fungus_memory_service.FungusMemoryService"
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock(return_value=False)
            MockService.return_value = mock_instance

            event = Event(
                type=EventType.EPIC_EXECUTION_STARTED,
                source="orchestrator",
                data={"epic_id": "EPIC-001"},
            )

            await agent.act([event])

            assert agent._epic_active is False
            assert agent._memory_service is None

    @pytest.mark.asyncio
    async def test_skips_own_events(self, agent):
        """Agent ignores events from itself."""
        mock_service = MagicMock()
        agent._memory_service = mock_service
        agent._epic_active = True

        event = Event(
            type=EventType.CODE_GENERATED,
            source="test_fungus_memory",  # Same as agent name
            data={"files": ["test.ts"]},
        )

        await agent.act([event])

        mock_service.reindex_file.assert_not_called()
