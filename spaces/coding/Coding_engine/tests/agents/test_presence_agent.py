"""
Tests for PresenceAgent with Context Bridge integration.

Verifies:
- Agent initialization and configuration
- Subscribed events handling
- should_act() decision logic
- _get_task_type() for context bridge
- Context bridge integration
- Prompt building methods
- Swarm handoff configuration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.agents.presence_agent import PresenceAgent
from src.mind.event_bus import EventBus, Event, EventType


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a mock EventBus."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def shared_state():
    """Create a mock SharedState with context_bridge fallback support."""
    state = MagicMock()
    state.get_metrics = MagicMock(return_value=MagicMock())
    state.context_bridge = None
    state.tech_stack = {"backend": {"framework": "nestjs"}}
    return state


@pytest.fixture
def mock_context_bridge():
    """Create a mock AgentContextBridge for context injection tests."""
    bridge = MagicMock()
    bridge.get_context_for_task = AsyncMock(return_value=MagicMock(
        diagrams=[],
        entities=[{"name": "User", "attributes": [{"name": "status", "type": "string"}]}],
        rag_results=[
            {"relative_path": "src/presence/service.ts", "content": "PresenceService...", "score": 0.85},
        ],
    ))
    return bridge


@pytest.fixture
def presence_agent(event_bus, shared_state, tmp_path):
    """Create a PresenceAgent instance for testing."""
    return PresenceAgent(
        name="presence_agent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
    )


@pytest.fixture
def presence_agent_with_bridge(event_bus, shared_state, mock_context_bridge, tmp_path):
    """Create a PresenceAgent with context bridge configured."""
    return PresenceAgent(
        name="presence_agent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        context_bridge=mock_context_bridge,
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestPresenceAgentInit:
    """Tests for PresenceAgent initialization."""

    def test_subscribed_events(self, presence_agent):
        """Test that PresenceAgent subscribes to correct events."""
        events = presence_agent.subscribed_events
        assert EventType.WEBSOCKET_HANDLER_GENERATED in events
        assert EventType.REDIS_PUBSUB_CONFIGURED in events

    def test_default_name(self, event_bus, shared_state, tmp_path):
        """Test default name is 'presence_agent'."""
        agent = PresenceAgent(
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "presence_agent"


class TestPresenceAgentShouldAct:
    """Tests for PresenceAgent.should_act() decision logic."""

    def test_should_act_on_websocket_handler_generated(self, presence_agent):
        """Test agent acts when WebSocket handlers are generated."""
        event = Event(
            type=EventType.WEBSOCKET_HANDLER_GENERATED,
            source="websocket_agent",
            data={"handlers": ["chat.gateway.ts"]},
        )
        result = presence_agent.should_act([event])
        assert result is True

    def test_should_act_on_redis_pubsub_configured(self, presence_agent):
        """Test agent acts when Redis Pub/Sub is configured."""
        event = Event(
            type=EventType.REDIS_PUBSUB_CONFIGURED,
            source="redis_agent",
            data={"mode": "pubsub"},
        )
        result = presence_agent.should_act([event])
        assert result is True

    def test_should_not_act_on_empty_events(self, presence_agent):
        """Test agent does not act on empty events list."""
        result = presence_agent.should_act([])
        assert result is False

    def test_should_not_act_on_unrelated_events(self, presence_agent):
        """Test agent does not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = presence_agent.should_act([event])
        assert result is False


class TestPresenceAgentTaskType:
    """Tests for _get_task_type method."""

    def test_get_task_type_returns_websocket(self, presence_agent):
        """Presence uses websocket context as it's a real-time feature."""
        task_type = presence_agent._get_task_type()
        assert task_type == "websocket"


class TestPresenceAgentContextBridge:
    """Tests for context bridge integration."""

    @pytest.mark.asyncio
    async def test_get_task_context_uses_bridge(self, presence_agent_with_bridge):
        """Test get_task_context calls context bridge correctly."""
        context = await presence_agent_with_bridge.get_task_context(
            query="presence tracking online offline",
        )
        assert context is not None
        presence_agent_with_bridge.context_bridge.get_context_for_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task_context_returns_none_without_bridge(self, presence_agent):
        """Test get_task_context returns None when no bridge configured."""
        context = await presence_agent.get_task_context(query="test")
        assert context is None


class TestPresenceAgentPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_presence_prompt_includes_components(self, presence_agent):
        """Test presence prompt includes required components."""
        events = [Event(
            type=EventType.WEBSOCKET_HANDLER_GENERATED,
            source="test",
            data={},
        )]
        prompt = presence_agent._build_presence_prompt(events)

        # Should include presence components
        assert "Presence" in prompt or "presence" in prompt.lower()
        assert "Service" in prompt or "service" in prompt.lower()

    def test_build_presence_prompt_includes_technical_requirements(self, presence_agent):
        """Test presence prompt includes technical requirements."""
        events = []
        prompt = presence_agent._build_presence_prompt(events)

        # Should include Redis and TTL requirements
        assert "Redis" in prompt or "redis" in prompt.lower()
        assert "TTL" in prompt or "expire" in prompt.lower()


class TestPresenceAgentSwarmHandoff:
    """Tests for Swarm pattern configuration."""

    def test_get_handoff_targets(self, presence_agent):
        """Test get_handoff_targets returns valid dict."""
        targets = presence_agent.get_handoff_targets()
        assert isinstance(targets, dict)
        assert len(targets) > 0

    def test_get_agent_capabilities(self, presence_agent):
        """Test get_agent_capabilities returns expected capabilities."""
        capabilities = presence_agent.get_agent_capabilities()
        assert "presence" in capabilities
        assert "typing_indicators" in capabilities
        assert "read_receipts" in capabilities
        assert "redis" in capabilities
        assert "websocket" in capabilities


class TestPresenceAgentAutogenTeam:
    """Tests for AutogenTeamMixin integration."""

    def test_is_autogen_available_returns_boolean(self, presence_agent):
        """Test is_autogen_available returns a boolean."""
        result = presence_agent.is_autogen_available()
        assert isinstance(result, bool)

    def test_get_operator_system_prompt_contains_requirements(self, presence_agent):
        """Test operator system prompt includes critical requirements."""
        prompt = presence_agent._get_operator_system_prompt()

        assert "PresenceOperator" in prompt
        assert "TTL" in prompt or "heartbeat" in prompt.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
