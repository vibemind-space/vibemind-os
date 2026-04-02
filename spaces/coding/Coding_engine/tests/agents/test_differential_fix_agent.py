# -*- coding: utf-8 -*-
"""
Tests for DifferentialFixAgent - Phase 21b

Tests the bridge agent that routes differential analysis CODE_FIX_NEEDED
events to individual MCP agents (filesystem, prisma, npm) via MCPAgentPool.
"""

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.differential_fix_agent import (
    DifferentialFixAgent,
    GAP_AGENT_ROUTING,
    GAP_TYPE_KEYWORDS,
)
from src.mind.event_bus import Event, EventBus, EventType


# ---------------------------------------------------------------------------
# Mock MCPAgentResult (matches agent_pool.MCPAgentResult)
# ---------------------------------------------------------------------------


@dataclass
class MockAgentResult:
    agent: str = "filesystem"
    task: str = "fix code"
    session_id: str = "test_session"
    success: bool = True
    output: str = "Files created successfully"
    error: str = None
    duration: float = 1.0
    data: dict = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def shared_state():
    return MagicMock()


@pytest.fixture
def agent(event_bus, shared_state, tmp_path):
    return DifferentialFixAgent(
        name="TestDiffFix",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
    )


def _make_event(source_analysis="differential", **extra):
    """Helper to create CODE_FIX_NEEDED events."""
    data = {
        "reason": "Missing implementation: Phone Registration",
        "requirement_id": "WA-AUTH-001",
        "gap_description": "Phone registration endpoint not found in code.",
        "suggested_tasks": ["Create POST /auth/register endpoint"],
        "source_analysis": source_analysis,
    }
    data.update(extra)
    return Event(
        type=EventType.CODE_FIX_NEEDED,
        source="DifferentialAnalysis",
        data=data,
    )


def _make_pool_mock(result=None):
    """Create a mocked MCPAgentPool."""
    pool = MagicMock()
    pool.spawn = AsyncMock(return_value=result or MockAgentResult())
    pool.spawn_parallel = AsyncMock(return_value=[result or MockAgentResult()])
    pool.list_available = MagicMock(return_value=["filesystem", "prisma", "npm", "claude-code"])
    return pool


# ---------------------------------------------------------------------------
# subscribed_events
# ---------------------------------------------------------------------------


class TestSubscribedEvents:
    def test_subscribes_to_code_fix_needed(self, agent):
        assert EventType.CODE_FIX_NEEDED in agent.subscribed_events

    def test_only_code_fix_needed(self, agent):
        assert len(agent.subscribed_events) == 1


# ---------------------------------------------------------------------------
# should_act — filtering by source_analysis
# ---------------------------------------------------------------------------


class TestShouldAct:
    @pytest.mark.asyncio
    async def test_acts_on_differential_source(self, agent):
        event = _make_event(source_analysis="differential")
        assert await agent.should_act([event]) is True

    @pytest.mark.asyncio
    async def test_acts_on_differential_epic_source(self, agent):
        event = _make_event(source_analysis="differential_epic")
        assert await agent.should_act([event]) is True

    @pytest.mark.asyncio
    async def test_ignores_other_source(self, agent):
        event = _make_event(source_analysis="build_failure")
        assert await agent.should_act([event]) is False

    @pytest.mark.asyncio
    async def test_ignores_no_source_analysis(self, agent):
        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="BuildAgent",
            data={"reason": "build failed"},
        )
        assert await agent.should_act([event]) is False

    @pytest.mark.asyncio
    async def test_ignores_empty_source_analysis(self, agent):
        event = _make_event(source_analysis="")
        assert await agent.should_act([event]) is False

    @pytest.mark.asyncio
    async def test_ignores_non_code_fix_events(self, agent):
        event = Event(
            type=EventType.BUILD_FAILED,
            source="BuildAgent",
            data={"source_analysis": "differential"},
        )
        assert await agent.should_act([event]) is False


# ---------------------------------------------------------------------------
# act — MCP agent routing
# ---------------------------------------------------------------------------


class TestAct:
    @pytest.mark.asyncio
    async def test_calls_pool_spawn(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        mock_pool.spawn_parallel = AsyncMock(return_value=[
            MockAgentResult(agent="claude-code"),
            MockAgentResult(agent="filesystem"),
        ])
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        # Default gap routes to claude-code + filesystem = spawn_parallel
        mock_pool.spawn_parallel.assert_called_once()
        tasks = mock_pool.spawn_parallel.call_args.args[0]
        agent_names = [t["agent"] for t in tasks]
        assert "claude-code" in agent_names
        assert "WA-AUTH-001" in tasks[0]["task"]

    @pytest.mark.asyncio
    async def test_task_description_format(self, agent):
        mock_pool = _make_pool_mock()
        mock_pool.spawn_parallel = AsyncMock(return_value=[
            MockAgentResult(agent="claude-code"),
            MockAgentResult(agent="filesystem"),
        ])
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        tasks = mock_pool.spawn_parallel.call_args.args[0]
        # claude-code task has the requirement description
        claude_task = next(t for t in tasks if t["agent"] == "claude-code")
        assert "phone registration" in claude_task["task"].lower()

    @pytest.mark.asyncio
    async def test_publishes_fix_complete_on_success(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        published_types = [
            call.args[0].type for call in event_bus.publish.call_args_list
        ]
        assert EventType.DIFFERENTIAL_FIX_COMPLETE in published_types

    @pytest.mark.asyncio
    async def test_publishes_code_fixed_on_success(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        published_types = [
            call.args[0].type for call in event_bus.publish.call_args_list
        ]
        assert EventType.CODE_FIXED in published_types

    @pytest.mark.asyncio
    async def test_no_code_fixed_on_failure(self, agent, event_bus):
        mock_pool = _make_pool_mock(
            result=MockAgentResult(success=False, error="timeout")
        )
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        published_types = [
            call.args[0].type for call in event_bus.publish.call_args_list
        ]
        assert EventType.CODE_FIXED not in published_types
        assert EventType.DIFFERENTIAL_FIX_COMPLETE in published_types

    @pytest.mark.asyncio
    async def test_fix_complete_contains_success_flag(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        fix_events = [
            call.args[0]
            for call in event_bus.publish.call_args_list
            if call.args[0].type == EventType.DIFFERENTIAL_FIX_COMPLETE
        ]
        assert len(fix_events) == 1
        assert fix_events[0].data["success"] is True
        assert fix_events[0].data["requirement_id"] == "WA-AUTH-001"

    @pytest.mark.asyncio
    async def test_fix_complete_includes_agents_used(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        fix_events = [
            call.args[0]
            for call in event_bus.publish.call_args_list
            if call.args[0].type == EventType.DIFFERENTIAL_FIX_COMPLETE
        ]
        assert "agents_used" in fix_events[0].data
        assert "filesystem" in fix_events[0].data["agents_used"]

    @pytest.mark.asyncio
    async def test_fix_complete_includes_gap_type(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        fix_events = [
            call.args[0]
            for call in event_bus.publish.call_args_list
            if call.args[0].type == EventType.DIFFERENTIAL_FIX_COMPLETE
        ]
        assert "gap_type" in fix_events[0].data

    @pytest.mark.asyncio
    async def test_context_includes_epic_id(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event(epic_id="EPIC-001")
        await agent.act([event])

        fix_events = [
            call.args[0]
            for call in event_bus.publish.call_args_list
            if call.args[0].type == EventType.DIFFERENTIAL_FIX_COMPLETE
        ]
        assert fix_events[0].data["epic_id"] == "EPIC-001"


# ---------------------------------------------------------------------------
# Pool unavailable
# ---------------------------------------------------------------------------


class TestPoolUnavailable:
    @pytest.mark.asyncio
    async def test_graceful_skip_when_unavailable(self, agent, event_bus):
        """When pool can't be initialized, skip without error."""
        agent._pool = None
        with patch.object(agent, "_get_pool", return_value=None):
            event = _make_event()
            await agent.act([event])

        # No events published (no crash)
        event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_spawn_exception_publishes_failure(self, agent, event_bus):
        """When pool.spawn raises, publish DIFFERENTIAL_FIX_COMPLETE with success=False."""
        mock_pool = _make_pool_mock()
        mock_pool.spawn = AsyncMock(side_effect=RuntimeError("connection lost"))
        mock_pool.spawn_parallel = AsyncMock(side_effect=RuntimeError("connection lost"))
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        fix_events = [
            call.args[0]
            for call in event_bus.publish.call_args_list
            if call.args[0].type == EventType.DIFFERENTIAL_FIX_COMPLETE
        ]
        assert len(fix_events) == 1
        assert fix_events[0].data["success"] is False
        assert "connection lost" in fix_events[0].data["error"]


# ---------------------------------------------------------------------------
# Multiple gaps
# ---------------------------------------------------------------------------


class TestMultipleGaps:
    @pytest.mark.asyncio
    async def test_processes_multiple_gaps_sequentially(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        mock_pool.spawn_parallel = AsyncMock(return_value=[
            MockAgentResult(agent="claude-code"),
            MockAgentResult(agent="filesystem"),
        ])
        agent._pool = mock_pool

        events = [
            _make_event(requirement_id="WA-AUTH-001"),
            _make_event(requirement_id="WA-AUTH-002"),
        ]
        events[1].data["requirement_id"] = "WA-AUTH-002"

        await agent.act(events)

        # Default gap routes to claude-code + filesystem → spawn_parallel called per gap
        assert mock_pool.spawn_parallel.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_own_events(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event()
        event.source = "TestDiffFix"  # Same as agent name

        await agent.act([event])

        mock_pool.spawn.assert_not_called()

    @pytest.mark.asyncio
    async def test_fix_count_increments(self, agent):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        assert agent._fix_count == 0

        await agent.act([_make_event()])
        assert agent._fix_count == 1

        await agent.act([_make_event()])
        assert agent._fix_count == 2


# ---------------------------------------------------------------------------
# _is_differential_fix static method
# ---------------------------------------------------------------------------


class TestIsDifferentialFix:
    def test_differential(self):
        event = _make_event(source_analysis="differential")
        assert DifferentialFixAgent._is_differential_fix(event) is True

    def test_differential_epic(self):
        event = _make_event(source_analysis="differential_epic")
        assert DifferentialFixAgent._is_differential_fix(event) is True

    def test_differential_fix(self):
        event = _make_event(source_analysis="differential_fix")
        assert DifferentialFixAgent._is_differential_fix(event) is True

    def test_build_failure(self):
        event = _make_event(source_analysis="build_failure")
        assert DifferentialFixAgent._is_differential_fix(event) is False

    def test_empty(self):
        event = _make_event(source_analysis="")
        assert DifferentialFixAgent._is_differential_fix(event) is False

    def test_wrong_event_type(self):
        event = Event(
            type=EventType.BUILD_FAILED,
            source="X",
            data={"source_analysis": "differential"},
        )
        assert DifferentialFixAgent._is_differential_fix(event) is False


# ---------------------------------------------------------------------------
# _determine_gap_type — keyword detection
# ---------------------------------------------------------------------------


class TestDetermineGapType:
    def test_schema_gap(self):
        event = _make_event(
            gap_description="Prisma schema missing User model with phone field."
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "schema"

    def test_schema_from_table_keyword(self):
        event = _make_event(
            gap_description="Database table for sessions not found."
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "schema"

    def test_migration_gap(self):
        event = _make_event(
            gap_description="Database migration for user table not applied."
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "migration"

    def test_dependency_gap(self):
        event = _make_event(
            gap_description="Cannot find module 'bcrypt'. Package not installed."
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "dependency"

    def test_dependency_from_npm_keyword(self):
        event = _make_event(
            gap_description="Missing npm dependency for authentication."
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "dependency"

    def test_api_gap_defaults_to_default(self):
        event = _make_event(
            gap_description="REST endpoint for phone registration missing."
        )
        # "endpoint" is not in any keyword list, so defaults
        assert DifferentialFixAgent._determine_gap_type(event) == "default"

    def test_default_for_generic_gap(self):
        event = _make_event(
            gap_description="Implementation incomplete for authentication flow."
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "default"

    def test_keywords_from_suggested_tasks(self):
        event = _make_event(
            gap_description="Missing functionality.",
            suggested_tasks=["Create Prisma schema for User model"],
        )
        # "prisma" and "schema" from suggested_tasks
        assert DifferentialFixAgent._determine_gap_type(event) == "schema"

    def test_keywords_from_reason(self):
        event = _make_event(
            gap_description="",
            reason="Missing npm package bcrypt for password hashing",
        )
        assert DifferentialFixAgent._determine_gap_type(event) == "dependency"


# ---------------------------------------------------------------------------
# Gap-type routing to agents
# ---------------------------------------------------------------------------


class TestGapTypeRouting:
    @pytest.mark.asyncio
    async def test_schema_gap_routes_to_claude_code_and_prisma(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        mock_pool.spawn_parallel = AsyncMock(return_value=[
            MockAgentResult(agent="claude-code"),
            MockAgentResult(agent="prisma"),
        ])
        agent._pool = mock_pool

        event = _make_event(
            gap_description="Prisma schema missing User model."
        )
        await agent.act([event])

        # Schema gap routes to claude-code + prisma = spawn_parallel
        mock_pool.spawn_parallel.assert_called_once()
        tasks = mock_pool.spawn_parallel.call_args.args[0]
        agent_names = [t["agent"] for t in tasks]
        assert "claude-code" in agent_names
        assert "prisma" in agent_names

    @pytest.mark.asyncio
    async def test_dependency_gap_routes_to_npm(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        agent._pool = mock_pool

        event = _make_event(
            gap_description="Missing npm package bcrypt."
        )
        await agent.act([event])

        # Dependency gap routes to npm only = single spawn
        mock_pool.spawn.assert_called_once()
        assert mock_pool.spawn.call_args.args[0] == "npm"

    @pytest.mark.asyncio
    async def test_default_gap_routes_to_claude_code(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        mock_pool.spawn_parallel = AsyncMock(return_value=[
            MockAgentResult(agent="claude-code"),
            MockAgentResult(agent="filesystem"),
        ])
        agent._pool = mock_pool

        event = _make_event(
            gap_description="REST endpoint for login missing."
        )
        await agent.act([event])

        # Default gap routes to claude-code + filesystem = spawn_parallel
        mock_pool.spawn_parallel.assert_called_once()
        tasks = mock_pool.spawn_parallel.call_args.args[0]
        agent_names = [t["agent"] for t in tasks]
        assert "claude-code" in agent_names

    @pytest.mark.asyncio
    async def test_unavailable_agent_falls_back_to_filesystem(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        # Only filesystem available (no claude-code, no prisma)
        mock_pool.list_available = MagicMock(return_value=["filesystem"])
        agent._pool = mock_pool

        event = _make_event(
            gap_description="Prisma schema missing User model."
        )
        await agent.act([event])

        # Even though schema gap wants claude-code+prisma, only filesystem available (fallback)
        mock_pool.spawn.assert_called_once()
        assert mock_pool.spawn.call_args.args[0] == "filesystem"

    @pytest.mark.asyncio
    async def test_no_agents_available_skips(self, agent, event_bus):
        mock_pool = _make_pool_mock()
        mock_pool.list_available = MagicMock(return_value=[])
        agent._pool = mock_pool

        event = _make_event()
        await agent.act([event])

        mock_pool.spawn.assert_not_called()
        mock_pool.spawn_parallel.assert_not_called()
        event_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# _build_agent_task — task description per agent type
# ---------------------------------------------------------------------------


class TestBuildAgentTask:
    def test_filesystem_task_format(self):
        task = DifferentialFixAgent._build_agent_task(
            "filesystem", "WA-001", "Missing endpoint", ["Create file"]
        )
        assert "Task:" in task
        assert "Description:" in task
        assert "WA-001" in task
        assert "Create file" in task

    def test_prisma_task_format(self):
        task = DifferentialFixAgent._build_agent_task(
            "prisma", "WA-002", "Missing schema", ["Add User model"]
        )
        assert "Prisma" in task
        assert "WA-002" in task
        assert "schema" in task.lower()

    def test_npm_task_format(self):
        task = DifferentialFixAgent._build_agent_task(
            "npm", "WA-003", "Missing bcrypt", ["Install bcrypt"]
        )
        assert "dependency" in task.lower() or "package" in task.lower()
        assert "WA-003" in task

    def test_claude_code_task_format(self):
        task = DifferentialFixAgent._build_agent_task(
            "claude-code", "WA-005", "Missing auth endpoints", ["Create auth controller"]
        )
        assert "WA-005" in task
        assert "NestJS" in task
        assert "Missing auth endpoints" in task
        assert "Create auth controller" in task

    def test_unknown_agent_uses_filesystem_format(self):
        task = DifferentialFixAgent._build_agent_task(
            "unknown_agent", "WA-004", "Something missing", []
        )
        assert "Task:" in task
        assert "Description:" in task


# ---------------------------------------------------------------------------
# GAP_AGENT_ROUTING completeness
# ---------------------------------------------------------------------------


class TestGapAgentRouting:
    def test_all_routing_keys_have_agents(self):
        for key, agents in GAP_AGENT_ROUTING.items():
            assert len(agents) > 0, f"Routing key '{key}' has no agents"

    def test_default_exists(self):
        assert "default" in GAP_AGENT_ROUTING

    def test_default_includes_claude_code(self):
        assert "claude-code" in GAP_AGENT_ROUTING["default"]

    def test_default_includes_filesystem(self):
        assert "filesystem" in GAP_AGENT_ROUTING["default"]

    def test_schema_includes_claude_code(self):
        assert "claude-code" in GAP_AGENT_ROUTING["schema"]

    def test_schema_includes_prisma(self):
        assert "prisma" in GAP_AGENT_ROUTING["schema"]

    def test_dependency_includes_npm(self):
        assert "npm" in GAP_AGENT_ROUTING["dependency"]
