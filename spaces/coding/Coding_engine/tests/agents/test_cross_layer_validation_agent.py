# -*- coding: utf-8 -*-
"""
Tests for CrossLayerValidationAgent (Phase 23).

Tests the autonomous agent that drives cross-layer validation
and bridges critical findings to CODE_FIX_NEEDED events.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.cross_layer_validation_agent import CrossLayerValidationAgent
from src.mind.event_bus import EventBus, Event, EventType


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
    state = MagicMock()
    state.update_cross_layer = AsyncMock()
    return state


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project for agent tests."""
    src = tmp_path / "src"
    be = src / "modules" / "auth"
    be.mkdir(parents=True)
    (be / "auth.controller.ts").write_text(
        """
@Controller('auth')
export class AuthController {
  @Post('login')
  async login() {}
}
""",
        encoding="utf-8",
    )

    fe = src / "api"
    fe.mkdir(parents=True)
    (fe / "authAPI.ts").write_text(
        """
export const login = () => fetch('/api/v1/auth/login', { method: 'POST' });
""",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def agent(event_bus, shared_state, tmp_project):
    return CrossLayerValidationAgent(
        name="TestCrossLayer",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_project),
        project_dir=str(tmp_project),
    )


# ---------------------------------------------------------------------------
# Test: Subscribed Events
# ---------------------------------------------------------------------------


class TestSubscribedEvents:
    def test_subscribes_to_epic_completed(self, agent):
        assert EventType.EPIC_EXECUTION_COMPLETED in agent.subscribed_events

    def test_subscribes_to_phase_completed(self, agent):
        assert EventType.EPIC_PHASE_COMPLETED in agent.subscribed_events

    def test_subscribes_to_generation_complete(self, agent):
        assert EventType.GENERATION_COMPLETE in agent.subscribed_events

    def test_exactly_three_subscriptions(self, agent):
        assert len(agent.subscribed_events) == 3


# ---------------------------------------------------------------------------
# Test: should_act
# ---------------------------------------------------------------------------


class TestShouldAct:
    @pytest.mark.asyncio
    async def test_should_act_on_epic_completed(self, agent):
        events = [Event(type=EventType.EPIC_EXECUTION_COMPLETED, source="epic", data={})]
        assert await agent.should_act(events) is True

    @pytest.mark.asyncio
    async def test_should_act_on_generation_complete(self, agent):
        events = [Event(type=EventType.GENERATION_COMPLETE, source="pipeline", data={})]
        assert await agent.should_act(events) is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_irrelevant_event(self, agent):
        events = [Event(type=EventType.BUILD_SUCCEEDED, source="builder", data={})]
        assert await agent.should_act(events) is False


# ---------------------------------------------------------------------------
# Test: act method
# ---------------------------------------------------------------------------


class TestActMethod:
    @pytest.mark.asyncio
    async def test_act_runs_validation_on_epic_completed(self, agent, event_bus):
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="epic",
            data={"output_dir": str(agent._project_dir)},
        )
        await agent.act([event])

        # Should publish STARTED, COMPLETE, and REPORT events
        published_types = [call.args[0].type for call in event_bus.publish.call_args_list]
        assert EventType.CROSS_LAYER_VALIDATION_STARTED in published_types
        assert EventType.CROSS_LAYER_VALIDATION_COMPLETE in published_types
        assert EventType.CROSS_LAYER_VALIDATION_REPORT in published_types

    @pytest.mark.asyncio
    async def test_act_skips_own_events(self, agent, event_bus):
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="TestCrossLayer",  # Same name as agent
            data={},
        )
        await agent.act([event])
        event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_act_handles_errors_gracefully(self, agent, event_bus):
        """Agent should catch errors and not propagate them."""
        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="epic",
            data={},
        )
        # No project_dir resolvable → should log warning, not crash
        agent._project_dir = None
        agent.working_dir = "/nonexistent/path"
        await agent.act([event])
        # Should not crash, may or may not publish

    @pytest.mark.asyncio
    async def test_act_phase_completed_api(self, agent, event_bus):
        """Phase completed with phase='api' should trigger validation."""
        event = Event(
            type=EventType.EPIC_PHASE_COMPLETED,
            source="orchestrator",
            data={"phase": "api", "output_dir": str(agent._project_dir)},
        )
        await agent.act([event])
        published_types = [call.args[0].type for call in event_bus.publish.call_args_list]
        assert EventType.CROSS_LAYER_VALIDATION_STARTED in published_types

    @pytest.mark.asyncio
    async def test_act_phase_completed_irrelevant_phase(self, agent, event_bus):
        """Phase completed with phase='database' should NOT trigger validation."""
        event = Event(
            type=EventType.EPIC_PHASE_COMPLETED,
            source="orchestrator",
            data={"phase": "database"},
        )
        await agent.act([event])
        event_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Test: CODE_FIX_NEEDED Bridge
# ---------------------------------------------------------------------------


class TestCodeFixBridge:
    @pytest.mark.asyncio
    async def test_critical_findings_bridged(self, tmp_path, event_bus, shared_state):
        """Critical findings with high confidence should bridge to CODE_FIX_NEEDED."""
        # Create a project with a security issue
        src = tmp_path / "src" / "modules" / "auth"
        src.mkdir(parents=True)
        (src / "auth.service.ts").write_text(
            """
import * as bcrypt from 'bcrypt';

export class AuthService {
  async hash(pw: string) { return bcrypt.hash(pw, 10); }
  async verify(user: any, pw: string) {
    if (user.password !== pw) throw new Error();
  }
}
""",
            encoding="utf-8",
        )

        agent = CrossLayerValidationAgent(
            name="TestCrossLayer",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            project_dir=str(tmp_path),
            auto_fix_critical=True,
            auto_fix_threshold=0.8,
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="epic",
            data={},
        )
        await agent.act([event])

        # Check that CODE_FIX_NEEDED was published
        published = [call.args[0] for call in event_bus.publish.call_args_list]
        fix_events = [e for e in published if e.type == EventType.CODE_FIX_NEEDED]
        assert len(fix_events) > 0
        assert fix_events[0].data["source_analysis"] == "cross_layer_validation"

    @pytest.mark.asyncio
    async def test_no_bridge_when_disabled(self, tmp_path, event_bus, shared_state):
        """With auto_fix_critical=False, no CODE_FIX_NEEDED should be published."""
        src = tmp_path / "src" / "modules" / "auth"
        src.mkdir(parents=True)
        (src / "auth.service.ts").write_text(
            """
export class AuthService {
  async verify(user: any, pw: string) {
    if (user.password !== pw) throw new Error();
  }
}
""",
            encoding="utf-8",
        )

        agent = CrossLayerValidationAgent(
            name="TestCrossLayer",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            project_dir=str(tmp_path),
            auto_fix_critical=False,
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="epic",
            data={},
        )
        await agent.act([event])

        published = [call.args[0] for call in event_bus.publish.call_args_list]
        fix_events = [e for e in published if e.type == EventType.CODE_FIX_NEEDED]
        assert len(fix_events) == 0

    @pytest.mark.asyncio
    async def test_bridge_data_format(self, tmp_path, event_bus, shared_state):
        """CODE_FIX_NEEDED event should contain required fields."""
        src = tmp_path / "src" / "modules" / "auth"
        src.mkdir(parents=True)
        (src / "auth.service.ts").write_text(
            """
export class AuthService {
  async verify(user: any, pw: string) {
    if (user.password !== pw) throw new Error();
  }
}
""",
            encoding="utf-8",
        )

        agent = CrossLayerValidationAgent(
            name="TestCrossLayer",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            project_dir=str(tmp_path),
        )

        event = Event(
            type=EventType.EPIC_EXECUTION_COMPLETED,
            source="epic",
            data={},
        )
        await agent.act([event])

        published = [call.args[0] for call in event_bus.publish.call_args_list]
        fix_events = [e for e in published if e.type == EventType.CODE_FIX_NEEDED]

        if fix_events:
            data = fix_events[0].data
            assert "source_analysis" in data
            assert "check_mode" in data
            assert "suggestion" in data
            assert "confidence" in data


# ---------------------------------------------------------------------------
# Test: Feature Flag (Orchestrator Registration)
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_agent_can_be_instantiated(self, event_bus, shared_state, tmp_path):
        agent = CrossLayerValidationAgent(
            name="CrossLayerValidation",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "CrossLayerValidation"

    def test_agent_default_config(self, agent):
        assert agent._auto_fix_critical is True
        assert agent._auto_fix_threshold == 0.8
        assert agent._validation_running is False

    def test_agent_custom_config(self, event_bus, shared_state, tmp_path):
        agent = CrossLayerValidationAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            auto_fix_critical=False,
            auto_fix_threshold=0.5,
        )
        assert agent._auto_fix_critical is False
        assert agent._auto_fix_threshold == 0.5


# ---------------------------------------------------------------------------
# Test: Project Directory Resolution
# ---------------------------------------------------------------------------


class TestProjectDirResolution:
    def test_resolve_from_config(self, agent, tmp_project):
        event = Event(type=EventType.GENERATION_COMPLETE, source="test", data={})
        result = agent._resolve_project_dir(event)
        assert result == str(tmp_project)

    def test_resolve_from_event_data(self, event_bus, shared_state, tmp_path):
        # Create src dir so it resolves
        (tmp_path / "src").mkdir()
        agent = CrossLayerValidationAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            project_dir=None,
        )
        event = Event(
            type=EventType.GENERATION_COMPLETE,
            source="test",
            data={"project_dir": str(tmp_path)},
        )
        result = agent._resolve_project_dir(event)
        assert result == str(tmp_path)

    def test_resolve_from_working_dir_src(self, event_bus, shared_state, tmp_path):
        (tmp_path / "src").mkdir()
        agent = CrossLayerValidationAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            project_dir=None,
        )
        event = Event(type=EventType.GENERATION_COMPLETE, source="test", data={})
        result = agent._resolve_project_dir(event)
        assert result == str(tmp_path)

    def test_resolve_returns_none(self, event_bus, shared_state, tmp_path):
        agent = CrossLayerValidationAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path / "nonexistent"),
            project_dir=None,
        )
        event = Event(type=EventType.GENERATION_COMPLETE, source="test", data={})
        result = agent._resolve_project_dir(event)
        assert result is None
