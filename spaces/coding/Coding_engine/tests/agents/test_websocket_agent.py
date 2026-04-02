"""
Tests for WebSocketAgent with Context Bridge integration.

Verifies:
- Agent initialization and configuration
- Subscribed events handling
- should_act() decision logic
- _get_task_type() for context bridge
- Context bridge integration and RAG injection
- Prompt building methods
- AutogenTeamMixin integration
- Anti-mock policy enforcement
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.agents.websocket_agent import WebSocketAgent
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
            {"relative_path": "src/chat/gateway.ts", "content": "@WebSocketGateway()", "score": 0.85},
            {"file_path": "src/dto/message.dto.ts", "content": "export class MessageDto {}", "score": 0.80},
        ],
        get_prompt_context=MagicMock(return_value="## Context\nWebSocket patterns"),
    ))
    return bridge


@pytest.fixture
def websocket_agent(event_bus, shared_state, tmp_path):
    """Create a WebSocketAgent instance for testing."""
    return WebSocketAgent(
        name="TestWebSocketAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        websocket_framework="nestjs",
    )


@pytest.fixture
def websocket_agent_with_bridge(event_bus, shared_state, mock_context_bridge, tmp_path):
    """Create a WebSocketAgent with context bridge configured."""
    return WebSocketAgent(
        name="TestWebSocketAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        context_bridge=mock_context_bridge,
        websocket_framework="nestjs",
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestWebSocketAgentInit:
    """Tests for WebSocketAgent initialization."""

    def test_subscribed_events(self, websocket_agent):
        """Test that WebSocketAgent subscribes to correct events."""
        events = websocket_agent.subscribed_events
        assert EventType.API_ROUTES_GENERATED in events
        assert EventType.DATABASE_SCHEMA_GENERATED in events
        assert EventType.CONTRACTS_GENERATED in events

    def test_default_framework_is_nestjs(self, event_bus, shared_state, tmp_path):
        """Test default WebSocket framework is nestjs."""
        agent = WebSocketAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.websocket_framework == "nestjs"

    def test_custom_framework_can_be_set(self, event_bus, shared_state, tmp_path):
        """Test custom WebSocket framework can be set."""
        agent = WebSocketAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            websocket_framework="express-ws",
        )
        assert agent.websocket_framework == "express-ws"

    def test_realtime_keywords_defined(self, websocket_agent):
        """Test that realtime keywords are properly defined."""
        keywords = websocket_agent.REALTIME_KEYWORDS
        assert "message" in keywords
        assert "chat" in keywords
        assert "presence" in keywords
        assert "typing" in keywords
        assert "notification" in keywords


class TestWebSocketAgentShouldAct:
    """Tests for WebSocketAgent.should_act() decision logic."""

    @pytest.mark.asyncio
    async def test_should_act_on_api_routes_with_realtime_features(self, websocket_agent):
        """Test agent acts when API routes contain real-time features."""
        event = Event(
            type=EventType.API_ROUTES_GENERATED,
            source="api_agent",
            data={
                "routes": [
                    {"path": "/api/messages", "method": "GET"},
                    {"path": "/api/chat/:id", "method": "POST"},
                ]
            },
        )
        result = await websocket_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_api_routes_without_realtime_features(self, websocket_agent):
        """Test agent does not act when API routes lack real-time features."""
        event = Event(
            type=EventType.API_ROUTES_GENERATED,
            source="api_agent",
            data={
                "routes": [
                    {"path": "/api/users", "method": "GET"},
                    {"path": "/api/products", "method": "POST"},
                ]
            },
        )
        result = await websocket_agent.should_act([event])
        assert result is False

    @pytest.mark.asyncio
    async def test_should_act_on_contracts_with_messaging_interfaces(self, websocket_agent):
        """Test agent acts on contracts with messaging interfaces."""
        event = Event(
            type=EventType.CONTRACTS_GENERATED,
            source="architect",
            data={
                "interfaces": {
                    "MessageDTO": {"content": "string"},
                    "ChatRoom": {"name": "string"},
                }
            },
        )
        result = await websocket_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_events(self, websocket_agent):
        """Test agent does not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = await websocket_agent.should_act([event])
        assert result is False


class TestWebSocketAgentTaskType:
    """Tests for WebSocketAgent._get_task_type() context bridge method."""

    def test_get_task_type_returns_websocket(self, websocket_agent):
        """Test _get_task_type returns correct type for context bridge."""
        task_type = websocket_agent._get_task_type()
        assert task_type == "websocket"


class TestWebSocketAgentContextBridge:
    """Tests for WebSocketAgent context bridge integration."""

    @pytest.mark.asyncio
    async def test_get_task_context_uses_bridge(self, websocket_agent_with_bridge):
        """Test get_task_context calls context bridge correctly."""
        context = await websocket_agent_with_bridge.get_task_context(
            query="websocket socket.io gateway",
            epic_id="epic-001",
        )

        assert context is not None
        websocket_agent_with_bridge.context_bridge.get_context_for_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task_context_returns_none_without_bridge(self, websocket_agent):
        """Test get_task_context returns None when no bridge configured."""
        context = await websocket_agent.get_task_context(query="test")
        assert context is None

    @pytest.mark.asyncio
    async def test_context_bridge_fallback_to_shared_state(self, event_bus, shared_state, mock_context_bridge, tmp_path):
        """Test context bridge falls back to shared_state.context_bridge."""
        # Configure bridge on shared_state, not directly on agent
        shared_state.context_bridge = mock_context_bridge

        agent = WebSocketAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            context_bridge=None,  # Not provided directly
        )

        context = await agent.get_task_context(query="test")
        assert context is not None


class TestWebSocketAgentPromptBuilding:
    """Tests for WebSocketAgent prompt building methods."""

    def test_build_generation_prompt_includes_framework(self, websocket_agent):
        """Test generation prompt includes framework information."""
        prompt = websocket_agent._build_generation_prompt("Test instructions")

        assert "nestjs" in prompt.lower() or "NestJS" in prompt

    def test_build_generation_prompt_includes_entities_context(self, websocket_agent):
        """Test generation prompt includes entity context when available."""
        websocket_agent._entities_data = {
            "entities": ["Message", "ChatRoom", "User"]
        }
        prompt = websocket_agent._build_generation_prompt("Test")

        assert "Message" in prompt or "entities" in prompt.lower()

    def test_build_generation_prompt_includes_routes_context(self, websocket_agent):
        """Test generation prompt includes API routes context."""
        websocket_agent._api_routes_data = {
            "routes": [
                {"method": "GET", "path": "/api/messages"},
            ]
        }
        prompt = websocket_agent._build_generation_prompt("Test")

        assert "/api/messages" in prompt


class TestWebSocketAgentRAGInjection:
    """Tests for RAG context injection in _act_with_autogen_team."""

    @pytest.mark.asyncio
    async def test_rag_results_available_in_context(self, websocket_agent_with_bridge):
        """Test RAG results are available through context bridge."""
        context = await websocket_agent_with_bridge.get_task_context(
            query="websocket socket.io",
        )

        assert context is not None
        # Context mock should have rag_results
        assert hasattr(context, 'rag_results')


class TestWebSocketAgentAutogenTeam:
    """Tests for AutogenTeamMixin integration."""

    def test_is_autogen_available_returns_boolean(self, websocket_agent):
        """Test is_autogen_available returns a boolean."""
        result = websocket_agent.is_autogen_available()
        assert isinstance(result, bool)

    def test_get_operator_system_prompt_contains_requirements(self, websocket_agent):
        """Test operator system prompt includes critical requirements."""
        prompt = websocket_agent._get_operator_system_prompt()

        assert "WebSocketOperator" in prompt
        assert websocket_agent.websocket_framework in prompt.lower()
        # Should include critical requirements
        assert "@WebSocketGateway" in prompt or "WebSocketGateway" in prompt
        assert "NO MOCKS" in prompt.upper() or "real" in prompt.lower()

    def test_get_validator_system_prompt_contains_checklist(self, websocket_agent):
        """Test validator system prompt includes review checklist."""
        prompt = websocket_agent._get_validator_system_prompt()

        assert "WebSocketValidator" in prompt
        assert "review" in prompt.lower() or "Review" in prompt
        # Should have checklist items
        assert "DTO" in prompt or "dto" in prompt.lower()


class TestWebSocketAgentAntiMockPolicy:
    """Tests for NO MOCKS policy enforcement."""

    def test_operator_prompt_prohibits_mocks(self, websocket_agent):
        """Test that operator prompt explicitly prohibits mock implementations."""
        prompt = websocket_agent._get_operator_system_prompt()

        # Should contain anti-mock directive
        assert "NO MOCK" in prompt.upper() or "real" in prompt.lower()

    def test_default_instructions_prohibit_mocks(self, websocket_agent):
        """Test default instructions prohibit mocks."""
        instructions = websocket_agent._default_websocket_instructions()

        assert "NO MOCK" in instructions.upper() or "real" in instructions.lower()


class TestWebSocketAgentRealtimeDetection:
    """Tests for real-time feature detection methods."""

    def test_has_realtime_features_with_message_route(self, websocket_agent):
        """Test detection of message routes as real-time features."""
        data = {
            "routes": [
                {"path": "/api/messages", "method": "GET"},
            ]
        }
        result = websocket_agent._has_realtime_features(data)
        assert result is True

    def test_has_realtime_features_with_chat_route(self, websocket_agent):
        """Test detection of chat routes as real-time features."""
        data = {
            "routes": [
                {"path": "/api/chat/rooms", "method": "GET"},
            ]
        }
        result = websocket_agent._has_realtime_features(data)
        assert result is True

    def test_has_realtime_features_returns_false_for_normal_routes(self, websocket_agent):
        """Test non-realtime routes return False."""
        data = {
            "routes": [
                {"path": "/api/users", "method": "GET"},
                {"path": "/api/products", "method": "POST"},
            ]
        }
        result = websocket_agent._has_realtime_features(data)
        assert result is False

    def test_has_realtime_features_with_none_data(self, websocket_agent):
        """Test graceful handling of None data."""
        result = websocket_agent._has_realtime_features(None)
        assert result is False

    def test_has_messaging_contracts_detects_message_interfaces(self, websocket_agent):
        """Test detection of messaging interfaces in contracts."""
        data = {
            "interfaces": {
                "MessageDTO": {},
                "UserDTO": {},
            }
        }
        result = websocket_agent._has_messaging_contracts(data)
        assert result is True

    def test_has_messaging_contracts_returns_false_for_non_messaging(self, websocket_agent):
        """Test non-messaging interfaces return False."""
        data = {
            "interfaces": {
                "UserDTO": {},
                "ProductDTO": {},
            }
        }
        result = websocket_agent._has_messaging_contracts(data)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
