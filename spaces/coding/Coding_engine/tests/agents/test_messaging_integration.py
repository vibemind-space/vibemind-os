"""
Integration tests for Messaging Agents chain.

Verifies:
- Event chain triggers between agents
- Context sharing across agents
- Task type consistency
- AutoGen team integration
- Documentation format expectations
- Error handling and fallbacks
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.agents.websocket_agent import WebSocketAgent
from src.agents.redis_pubsub_agent import RedisPubSubAgent
from src.agents.presence_agent import PresenceAgent
from src.agents.encryption_agent import EncryptionAgent
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
        diagrams=[{"diagram_type": "sequence", "content": "A->B: message"}],
        entities=[{"name": "Message", "attributes": [{"name": "content", "type": "string"}]}],
        rag_results=[
            {"relative_path": "src/gateway.ts", "content": "@WebSocketGateway()", "score": 0.9},
        ],
        get_prompt_context=MagicMock(return_value="## Context\nMessaging patterns"),
    ))
    return bridge


@pytest.fixture
def all_agents(event_bus, shared_state, mock_context_bridge, tmp_path):
    """Create all 4 messaging agents with shared context bridge."""
    return {
        "websocket": WebSocketAgent(
            name="websocket_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            context_bridge=mock_context_bridge,
        ),
        "redis": RedisPubSubAgent(
            name="redis_pubsub_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            context_bridge=mock_context_bridge,
        ),
        "presence": PresenceAgent(
            name="presence_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            context_bridge=mock_context_bridge,
        ),
        "encryption": EncryptionAgent(
            name="encryption_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            context_bridge=mock_context_bridge,
        ),
    }


# =============================================================================
# Test Classes
# =============================================================================

class TestMessagingAgentEventChain:
    """Tests for event chain triggers between agents."""

    @pytest.mark.asyncio
    async def test_websocket_triggers_redis_and_presence(self, all_agents):
        """WebSocket completion should trigger Redis and Presence agents."""
        event = Event(
            type=EventType.WEBSOCKET_HANDLER_GENERATED,
            source="websocket_agent",
            data={"handlers": ["chat.gateway.ts"]},
        )

        # Redis should act on WebSocket events (async)
        redis_should_act = await all_agents["redis"].should_act([event])
        assert redis_should_act is True

        # Presence should act on WebSocket events (sync)
        presence_should_act = all_agents["presence"].should_act([event])
        assert presence_should_act is True

    def test_auth_triggers_encryption(self, all_agents):
        """Auth setup completion should trigger Encryption agent."""
        event = Event(
            type=EventType.AUTH_SETUP_COMPLETE,
            source="auth_agent",
            data={"auth_type": "jwt"},
        )

        encryption_should_act = all_agents["encryption"].should_act([event])
        assert encryption_should_act is True

    def test_presence_triggers_encryption_chain(self, all_agents):
        """Presence agent completion should trigger Encryption agent."""
        event = Event(
            type=EventType.GENERATION_COMPLETE,
            source="presence_agent",
            data={"agent": "presence_agent"},
        )

        encryption_should_act = all_agents["encryption"].should_act([event])
        assert encryption_should_act is True


class TestMessagingAgentContextSharing:
    """Tests for context bridge sharing across agents."""

    @pytest.mark.asyncio
    async def test_all_agents_share_same_bridge(self, all_agents, mock_context_bridge):
        """All agents should use the same context bridge instance."""
        for name, agent in all_agents.items():
            assert agent.context_bridge is mock_context_bridge, f"{name} should share bridge"

    @pytest.mark.asyncio
    async def test_context_bridge_called_with_correct_task_types(self, all_agents):
        """Each agent should request context with its specific task type."""
        expected_task_types = {
            "websocket": "websocket",
            "redis": "infra",
            "presence": "websocket",
            "encryption": "auth",
        }

        for name, agent in all_agents.items():
            task_type = agent._get_task_type()
            assert task_type == expected_task_types[name], \
                f"{name} task type mismatch: {task_type} != {expected_task_types[name]}"


class TestMessagingAgentTaskTypes:
    """Tests for _get_task_type method consistency."""

    def test_all_agents_return_valid_task_types(self, all_agents):
        """All agents should return valid task types for context bridge."""
        valid_task_types = {"websocket", "infra", "auth", "database", "api", "frontend"}

        for name, agent in all_agents.items():
            task_type = agent._get_task_type()
            assert task_type in valid_task_types, \
                f"{name} returns invalid task type: {task_type}"


class TestMessagingAgentAutogenIntegration:
    """Tests for AutogenTeamMixin integration across all agents."""

    def test_all_agents_have_autogen_mixin(self, all_agents):
        """All agents should have AutogenTeamMixin methods."""
        for name, agent in all_agents.items():
            assert hasattr(agent, "is_autogen_available"), f"{name} missing is_autogen_available"
            assert hasattr(agent, "create_team"), f"{name} missing create_team"
            assert hasattr(agent, "run_team"), f"{name} missing run_team"

    def test_all_agents_is_autogen_available_returns_boolean(self, all_agents):
        """is_autogen_available should return boolean for all agents."""
        for name, agent in all_agents.items():
            result = agent.is_autogen_available()
            assert isinstance(result, bool), f"{name} is_autogen_available not boolean"

    def test_all_agents_have_operator_prompts(self, all_agents):
        """All agents should have _get_operator_system_prompt."""
        for name, agent in all_agents.items():
            assert hasattr(agent, "_get_operator_system_prompt"), \
                f"{name} missing _get_operator_system_prompt"
            prompt = agent._get_operator_system_prompt()
            assert isinstance(prompt, str), f"{name} operator prompt not string"
            assert len(prompt) > 100, f"{name} operator prompt too short"

    def test_all_agents_have_validator_prompts(self, all_agents):
        """All agents should have _get_validator_system_prompt."""
        for name, agent in all_agents.items():
            assert hasattr(agent, "_get_validator_system_prompt"), \
                f"{name} missing _get_validator_system_prompt"
            prompt = agent._get_validator_system_prompt()
            assert isinstance(prompt, str), f"{name} validator prompt not string"
            assert len(prompt) > 50, f"{name} validator prompt too short"


class TestMessagingAgentDocumentationFormat:
    """Tests for expected file paths and output format."""

    def test_websocket_generates_gateway_files(self, all_agents):
        """WebSocketAgent should target gateway file paths."""
        prompt = all_agents["websocket"]._get_operator_system_prompt()
        assert "gateway" in prompt.lower() or "Gateway" in prompt

    def test_redis_generates_adapter_files(self, all_agents):
        """RedisPubSubAgent should target adapter/service file paths."""
        prompt = all_agents["redis"]._get_operator_system_prompt()
        assert "redis" in prompt.lower() or "Redis" in prompt

    def test_presence_generates_service_files(self, all_agents):
        """PresenceAgent should target presence service file paths."""
        prompt = all_agents["presence"]._get_operator_system_prompt()
        assert "presence" in prompt.lower() or "Presence" in prompt


class TestMessagingAgentErrorHandling:
    """Tests for error handling and fallback behavior."""

    @pytest.mark.asyncio
    async def test_context_bridge_none_returns_none(self, event_bus, shared_state, tmp_path):
        """Agents without context bridge should return None from get_task_context."""
        agent = WebSocketAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            context_bridge=None,
        )

        context = await agent.get_task_context(query="test")
        assert context is None

    @pytest.mark.asyncio
    async def test_should_act_handles_empty_events(self, all_agents):
        """All agents should handle empty event lists gracefully."""
        import asyncio
        for name, agent in all_agents.items():
            result = agent.should_act([])
            # Handle async should_act (websocket, redis)
            if asyncio.iscoroutine(result):
                result = await result
            assert result is False, f"{name} should return False for empty events"


class TestMessagingAgentSwarmConfiguration:
    """Tests for Swarm pattern configuration across agents."""

    def test_presence_and_encryption_have_handoff_targets(self, all_agents):
        """Presence and Encryption agents should define handoff targets."""
        presence_targets = all_agents["presence"].get_handoff_targets()
        assert isinstance(presence_targets, dict)
        assert len(presence_targets) > 0

        encryption_targets = all_agents["encryption"].get_handoff_targets()
        assert isinstance(encryption_targets, dict)
        assert len(encryption_targets) > 0

    def test_all_agents_define_capabilities(self, all_agents):
        """All agents with Swarm support should define capabilities."""
        for name in ["presence", "encryption"]:
            agent = all_agents[name]
            capabilities = agent.get_agent_capabilities()
            assert isinstance(capabilities, list)
            assert len(capabilities) > 0


class TestMessagingAgentSubscribedEvents:
    """Tests for subscribed events configuration."""

    def test_websocket_subscribes_to_api_routes(self, all_agents):
        """WebSocketAgent should subscribe to API_ROUTES_GENERATED."""
        events = all_agents["websocket"].subscribed_events
        assert EventType.API_ROUTES_GENERATED in events

    def test_redis_subscribes_to_websocket_and_auth(self, all_agents):
        """RedisPubSubAgent should subscribe to WebSocket and Auth events."""
        events = all_agents["redis"].subscribed_events
        assert EventType.WEBSOCKET_HANDLER_GENERATED in events
        assert EventType.AUTH_SETUP_COMPLETE in events

    def test_presence_subscribes_to_websocket_and_redis(self, all_agents):
        """PresenceAgent should subscribe to WebSocket and Redis events."""
        events = all_agents["presence"].subscribed_events
        assert EventType.WEBSOCKET_HANDLER_GENERATED in events
        assert EventType.REDIS_PUBSUB_CONFIGURED in events

    def test_encryption_subscribes_to_auth(self, all_agents):
        """EncryptionAgent should subscribe to AUTH_SETUP_COMPLETE."""
        events = all_agents["encryption"].subscribed_events
        assert EventType.AUTH_SETUP_COMPLETE in events


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
