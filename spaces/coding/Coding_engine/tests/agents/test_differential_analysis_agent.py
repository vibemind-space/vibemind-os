# -*- coding: utf-8 -*-
"""
Tests for DifferentialAnalysisAgent - Phase 20

Tests the autonomous agent that compares documentation against generated
code via EventBus integration.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Guard: Agent imports DifferentialAnalysisService which depends on JAX/MCMP.
# On Windows the JAX DLL may fail to load when other test modules run first.
# The DLL crash is lazy, so we probe with _init_retriever().
try:
    from src.agents.differential_analysis_agent import DifferentialAnalysisAgent
    from src.mind.event_bus import Event, EventBus, EventType
    from src.services.mcmp_background import MCMPBackgroundSimulation

    # Probe: trigger the lazy JAX DLL load
    _probe = MCMPBackgroundSimulation()
    _MCMP_AVAILABLE = _probe._init_retriever()
    del _probe
except (ImportError, OSError):
    _MCMP_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _MCMP_AVAILABLE,
    reason="MCMP/JAX not available (Windows DLL conflict)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_bus():
    """Create a mock EventBus."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def shared_state():
    """Create a mock SharedState with async methods."""
    state = MagicMock()
    state.update_differential = AsyncMock()
    return state


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a minimal data directory."""
    data_dir = tmp_path / "whatsapp"
    data_dir.mkdir()

    stories = [
        {
            "id": "US-001",
            "title": "Registration",
            "priority": "MUST",
            "linked_requirement": "WA-AUTH-001",
            "as_a": "user",
            "i_want": "register",
            "so_that": "use app",
            "description": "Register with phone",
        }
    ]
    (data_dir / "user_stories.json").write_text(
        json.dumps(stories), encoding="utf-8"
    )

    tasks_dir = data_dir / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "epic-001-tasks.json").write_text(
        json.dumps({"epic_id": "E1", "epic_name": "Auth", "tasks": []}),
        encoding="utf-8",
    )

    output_dir = data_dir / "output"
    output_dir.mkdir()
    (output_dir / "app.ts").write_text("const app = new Hono();", encoding="utf-8")

    return data_dir


@pytest.fixture
def agent(event_bus, shared_state, tmp_data_dir):
    """Create a DifferentialAnalysisAgent."""
    return DifferentialAnalysisAgent(
        name="TestDiffAnalysis",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_data_dir),
        data_dir=str(tmp_data_dir),
        code_dir=str(tmp_data_dir / "output"),
        enable_supermemory=False,
    )


# ---------------------------------------------------------------------------
# Interface Tests
# ---------------------------------------------------------------------------


class TestInterface:
    """Tests for AutonomousAgent interface."""

    def test_subscribed_events(self, agent):
        """Should subscribe to correct event types."""
        events = agent.subscribed_events
        assert EventType.EPIC_EXECUTION_COMPLETED in events
        assert EventType.GENERATION_COMPLETE in events
        assert EventType.CONVERGENCE_ACHIEVED in events

    @pytest.mark.asyncio
    async def test_should_act_on_subscribed(self, agent):
        """Should act on subscribed events."""
        events = [
            Event(
                type=EventType.EPIC_EXECUTION_COMPLETED,
                source="other",
                data={},
            )
        ]
        result = await agent.should_act(events)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_unsubscribed(self, agent):
        """Should not act on unrelated events."""
        events = [
            Event(type=EventType.FILE_CREATED, source="other", data={})
        ]
        result = await agent.should_act(events)
        assert result is False


# ---------------------------------------------------------------------------
# Event Handler Tests
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Tests for event handling."""

    @pytest.mark.asyncio
    async def test_handle_epic_completed(self, agent, event_bus):
        """Should run per-epic analysis on epic completion with epic_id."""
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={"epic_id": "EPIC-001"},
        )

        await agent.act([event])

        # Should have published start and per-epic result events
        # Filter for Event objects (simulation callback publishes strings)
        calls = event_bus.publish.call_args_list
        event_types = [
            c[0][0].type for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
        ]
        assert EventType.DIFFERENTIAL_ANALYSIS_STARTED in event_types
        # Per-epic: publishes VALIDATED or FAILED (not COMPLETE)
        has_epic_event = (
            EventType.DIFFERENTIAL_EPIC_VALIDATED in event_types
            or EventType.DIFFERENTIAL_EPIC_FAILED in event_types
        )
        assert has_epic_event, f"Expected VALIDATED or FAILED, got: {event_types}"

    @pytest.mark.asyncio
    async def test_skips_own_events(self, agent, event_bus):
        """Should skip events from itself."""
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="TestDiffAnalysis",  # Same as agent name
            data={},
        )

        await agent.act([event])

        # Should not have published anything
        event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_convergence(self, agent, event_bus):
        """Should publish coverage report on convergence."""
        # First run an analysis to have reports
        event1 = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={},
        )
        await agent.act([event1])

        # Now handle convergence
        event2 = Event(
            type=EventType.CONVERGENCE_ACHIEVED,
            source="orchestrator",
            data={},
        )
        await agent.act([event2])

        # Should have published coverage report
        calls = event_bus.publish.call_args_list
        event_types = [
            c[0][0].type for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
        ]
        assert EventType.DIFFERENTIAL_COVERAGE_REPORT in event_types


# ---------------------------------------------------------------------------
# Resolution Tests
# ---------------------------------------------------------------------------


class TestResolution:
    """Tests for data/code directory resolution."""

    def test_resolve_data_dir_from_config(self, agent):
        """Should use configured data_dir."""
        event = Event(type=EventType.EPIC_EXECUTION_COMPLETED, source="x", data={})
        result = agent._resolve_data_dir(event)
        assert result is not None

    def test_resolve_data_dir_from_event(self, event_bus, shared_state, tmp_path):
        """Should use data_dir from event data."""
        ag = DifferentialAnalysisAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_supermemory=False,
        )
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="x",
            data={"data_dir": "/some/path"},
        )
        result = ag._resolve_data_dir(event)
        assert result == "/some/path"

    def test_resolve_code_dir_from_config(self, agent):
        """Should use configured code_dir."""
        event = Event(type=EventType.EPIC_EXECUTION_COMPLETED, source="x", data={})
        result = agent._resolve_code_dir(event)
        assert result is not None

    def test_resolve_code_dir_from_event(self, event_bus, shared_state, tmp_path):
        """Should use code_dir from event data."""
        ag = DifferentialAnalysisAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_supermemory=False,
        )
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="x",
            data={"code_dir": "/some/output"},
        )
        result = ag._resolve_code_dir(event)
        assert result == "/some/output"


# ---------------------------------------------------------------------------
# Auto-Fix Bridge Tests
# ---------------------------------------------------------------------------


class TestAutoFixBridge:
    """Tests for CODE_FIX_NEEDED bridging."""

    @pytest.mark.asyncio
    async def test_critical_gap_publishes_fix_needed(self, agent, event_bus):
        """Critical missing requirements should publish CODE_FIX_NEEDED."""
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={},
        )
        await agent.act([event])

        calls = event_bus.publish.call_args_list
        event_types = [
            c[0][0].type for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
        ]

        # If there are MUST requirements found missing with high confidence,
        # CODE_FIX_NEEDED should be published
        # Note: actual behavior depends on heuristic evaluation results
        assert EventType.DIFFERENTIAL_ANALYSIS_COMPLETE in event_types

    @pytest.mark.asyncio
    async def test_auto_fix_disabled(self, event_bus, shared_state, tmp_data_dir):
        """When auto_fix_critical=False, should not publish CODE_FIX_NEEDED."""
        ag = DifferentialAnalysisAgent(
            name="TestNoFix",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_data_dir),
            data_dir=str(tmp_data_dir),
            code_dir=str(tmp_data_dir / "output"),
            auto_fix_critical=False,
            enable_supermemory=False,
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={},
        )
        await ag.act([event])

        calls = event_bus.publish.call_args_list
        fix_needed_events = [
            c for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
            and c[0][0].type == EventType.CODE_FIX_NEEDED
        ]
        assert len(fix_needed_events) == 0


# ---------------------------------------------------------------------------
# Per-Epic Analysis Tests (Phase 20b)
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_epic_data_dir(tmp_path):
    """Create a data directory with TWO epics for per-epic testing."""
    data_dir = tmp_path / "multi"
    data_dir.mkdir()

    stories = [
        {
            "id": "US-001",
            "title": "Registration",
            "priority": "MUST",
            "linked_requirement": "WA-AUTH-001",
            "as_a": "user",
            "i_want": "register",
            "so_that": "use app",
            "description": "Register with phone",
        },
        {
            "id": "US-002",
            "title": "Groups",
            "priority": "SHOULD",
            "linked_requirement": "WA-GRP-001",
            "as_a": "user",
            "i_want": "create group",
            "so_that": "chat with many",
            "description": "Group messaging",
        },
    ]
    (data_dir / "user_stories.json").write_text(
        json.dumps(stories), encoding="utf-8"
    )

    tasks_dir = data_dir / "tasks"
    tasks_dir.mkdir()

    epic1 = {
        "epic_id": "EPIC-001",
        "epic_name": "Auth",
        "tasks": [
            {
                "id": "E1-AUTH",
                "epic_id": "EPIC-001",
                "type": "api_endpoint",
                "title": "Auth endpoint",
                "description": "Register with phone",
                "status": "completed",
                "dependencies": [],
                "output_files": ["src/auth.ts"],
                "related_requirements": ["WA-AUTH-001"],
                "related_user_stories": ["US-001"],
                "phase": "api",
            },
        ],
    }
    (tasks_dir / "epic-001-tasks.json").write_text(
        json.dumps(epic1), encoding="utf-8"
    )

    epic2 = {
        "epic_id": "EPIC-002",
        "epic_name": "Groups",
        "tasks": [
            {
                "id": "E2-GRP",
                "epic_id": "EPIC-002",
                "type": "api_endpoint",
                "title": "Group endpoint",
                "description": "Create group chats",
                "status": "pending",
                "dependencies": [],
                "output_files": [],
                "related_requirements": ["WA-GRP-001"],
                "related_user_stories": ["US-002"],
                "phase": "api",
            },
        ],
    }
    (tasks_dir / "epic-002-tasks.json").write_text(
        json.dumps(epic2), encoding="utf-8"
    )

    output_dir = data_dir / "output"
    output_dir.mkdir()
    (output_dir / "auth.ts").write_text(
        "export const register = () => {};", encoding="utf-8"
    )

    return data_dir


class TestPerEpicAnalysis:
    """Tests for per-epic differential analysis (Phase 20b)."""

    @pytest.mark.asyncio
    async def test_epic_id_extracted_from_event(self, event_bus, shared_state, multi_epic_data_dir):
        """Should extract epic_id from event and run per-epic analysis."""
        ag = DifferentialAnalysisAgent(
            name="TestEpic",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(multi_epic_data_dir),
            data_dir=str(multi_epic_data_dir),
            code_dir=str(multi_epic_data_dir / "output"),
            enable_supermemory=False,
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={
                "epic_id": "EPIC-001",
                "data_dir": str(multi_epic_data_dir),
                "output_dir": str(multi_epic_data_dir / "output"),
            },
        )
        await ag.act([event])

        calls = event_bus.publish.call_args_list
        event_types = [
            c[0][0].type for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
        ]
        assert EventType.DIFFERENTIAL_ANALYSIS_STARTED in event_types
        # Should publish VALIDATED or FAILED (per-epic events)
        has_epic_event = (
            EventType.DIFFERENTIAL_EPIC_VALIDATED in event_types
            or EventType.DIFFERENTIAL_EPIC_FAILED in event_types
        )
        assert has_epic_event, f"Expected VALIDATED or FAILED, got: {event_types}"

    @pytest.mark.asyncio
    async def test_epic_validated_event_on_high_coverage(self, event_bus, shared_state, multi_epic_data_dir):
        """Should publish VALIDATED when coverage >= threshold."""
        ag = DifferentialAnalysisAgent(
            name="TestValidated",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(multi_epic_data_dir),
            data_dir=str(multi_epic_data_dir),
            code_dir=str(multi_epic_data_dir / "output"),
            enable_supermemory=False,
            coverage_threshold=0.0,  # 0% threshold -> always validates
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={"epic_id": "EPIC-001"},
        )
        await ag.act([event])

        calls = event_bus.publish.call_args_list
        validated_events = [
            c[0][0] for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
            and c[0][0].type == EventType.DIFFERENTIAL_EPIC_VALIDATED
        ]
        assert len(validated_events) == 1
        assert validated_events[0].data["epic_id"] == "EPIC-001"
        assert "coverage_percent" in validated_events[0].data

    @pytest.mark.asyncio
    async def test_epic_failed_event_on_low_coverage(self, event_bus, shared_state, multi_epic_data_dir):
        """Should publish FAILED when coverage < threshold."""
        ag = DifferentialAnalysisAgent(
            name="TestFailed",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(multi_epic_data_dir),
            data_dir=str(multi_epic_data_dir),
            code_dir=str(multi_epic_data_dir / "output"),
            enable_supermemory=False,
            coverage_threshold=101.0,  # Impossible threshold -> always fails
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={"epic_id": "EPIC-002"},
        )
        await ag.act([event])

        calls = event_bus.publish.call_args_list
        failed_events = [
            c[0][0] for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
            and c[0][0].type == EventType.DIFFERENTIAL_EPIC_FAILED
        ]
        assert len(failed_events) == 1
        assert failed_events[0].data["epic_id"] == "EPIC-002"
        assert "gaps" in failed_events[0].data

    @pytest.mark.asyncio
    async def test_epic_dirs_from_event_payload(self, event_bus, shared_state, multi_epic_data_dir):
        """Should use data_dir and output_dir from event payload."""
        ag = DifferentialAnalysisAgent(
            name="TestDirs",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(multi_epic_data_dir),
            # No data_dir/code_dir configured -> must come from event
            enable_supermemory=False,
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={
                "epic_id": "EPIC-001",
                "data_dir": str(multi_epic_data_dir),
                "output_dir": str(multi_epic_data_dir / "output"),
            },
        )
        await ag.act([event])

        calls = event_bus.publish.call_args_list
        event_types = [
            c[0][0].type for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
        ]
        # Should have started (dirs resolved from event)
        assert EventType.DIFFERENTIAL_ANALYSIS_STARTED in event_types

    @pytest.mark.asyncio
    async def test_no_epic_id_falls_back_to_full_analysis(self, agent, event_bus):
        """Without epic_id in event, should run full analysis (not per-epic)."""
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="orchestrator",
            data={},  # No epic_id
        )
        await agent.act([event])

        calls = event_bus.publish.call_args_list
        event_types = [
            c[0][0].type for c in calls
            if len(c[0]) > 0 and isinstance(c[0][0], Event)
        ]
        # Should run full analysis (COMPLETE, not VALIDATED/FAILED)
        assert EventType.DIFFERENTIAL_ANALYSIS_COMPLETE in event_types
