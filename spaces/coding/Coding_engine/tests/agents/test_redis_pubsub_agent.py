"""
Tests for RedisPubSubAgent with Context Bridge integration.

Verifies:
- Agent initialization and configuration
- Subscribed events handling
- should_act() decision logic
- _get_task_type() for context bridge
- Context bridge integration
- Configured features by mode
- Prompt building methods
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.agents.redis_pubsub_agent import RedisPubSubAgent
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
        entities=[],
        rag_results=[
            {"relative_path": "src/redis/adapter.ts", "content": "RedisAdapter...", "score": 0.85},
        ],
    ))
    return bridge


@pytest.fixture
def redis_agent(event_bus, shared_state, tmp_path):
    """Create a RedisPubSubAgent instance for testing."""
    return RedisPubSubAgent(
        name="TestRedisPubSubAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        redis_mode="pubsub",
    )


@pytest.fixture
def redis_agent_with_bridge(event_bus, shared_state, mock_context_bridge, tmp_path):
    """Create a RedisPubSubAgent with context bridge configured."""
    return RedisPubSubAgent(
        name="TestRedisPubSubAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        context_bridge=mock_context_bridge,
        redis_mode="all",
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestRedisPubSubAgentInit:
    """Tests for RedisPubSubAgent initialization."""

    def test_subscribed_events(self, redis_agent):
        """Test that RedisPubSubAgent subscribes to correct events."""
        events = redis_agent.subscribed_events
        assert EventType.WEBSOCKET_HANDLER_GENERATED in events
        assert EventType.AUTH_SETUP_COMPLETE in events
        assert EventType.CONTRACTS_GENERATED in events

    def test_default_redis_mode(self, event_bus, shared_state, tmp_path):
        """Test default Redis mode is pubsub."""
        agent = RedisPubSubAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.redis_mode == "pubsub"

    def test_custom_redis_mode_can_be_set(self, redis_agent_with_bridge):
        """Test custom Redis mode can be set."""
        assert redis_agent_with_bridge.redis_mode == "all"


class TestRedisPubSubAgentShouldAct:
    """Tests for RedisPubSubAgent.should_act() decision logic."""

    @pytest.mark.asyncio
    async def test_should_act_on_websocket_handler_generated(self, redis_agent):
        """Test agent acts when WebSocket handlers are generated."""
        event = Event(
            type=EventType.WEBSOCKET_HANDLER_GENERATED,
            source="websocket_agent",
            data={"handlers": ["chat.gateway.ts", "notification.gateway.ts"]},
        )
        result = await redis_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_auth_with_session_cache(self, redis_agent):
        """Test agent acts when auth needs session cache."""
        event = Event(
            type=EventType.AUTH_SETUP_COMPLETE,
            source="auth_agent",
            data={"needs_session_cache": True},
        )
        result = await redis_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_auth_without_session_cache(self, redis_agent):
        """Test agent does not act when auth doesn't need session cache."""
        event = Event(
            type=EventType.AUTH_SETUP_COMPLETE,
            source="auth_agent",
            data={"needs_session_cache": False},
        )
        result = await redis_agent.should_act([event])
        assert result is False

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_events(self, redis_agent):
        """Test agent does not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = await redis_agent.should_act([event])
        assert result is False


class TestRedisPubSubAgentTaskType:
    """Tests for _get_task_type method."""

    def test_get_task_type_returns_infra(self, redis_agent):
        """Test _get_task_type returns 'infra' for context bridge."""
        task_type = redis_agent._get_task_type()
        assert task_type == "infra"


class TestRedisPubSubAgentContextBridge:
    """Tests for context bridge integration."""

    @pytest.mark.asyncio
    async def test_get_task_context_uses_bridge(self, redis_agent_with_bridge):
        """Test get_task_context calls context bridge correctly."""
        context = await redis_agent_with_bridge.get_task_context(
            query="redis ioredis pubsub",
        )
        assert context is not None
        redis_agent_with_bridge.context_bridge.get_context_for_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_bridge_fallback_to_shared_state(self, event_bus, shared_state, mock_context_bridge, tmp_path):
        """Test context bridge falls back to shared_state.context_bridge."""
        shared_state.context_bridge = mock_context_bridge
        agent = RedisPubSubAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        context = await agent.get_task_context(query="test")
        assert context is not None


class TestRedisPubSubAgentConfiguredFeatures:
    """Tests for _get_configured_features method."""

    def test_pubsub_mode_features(self, event_bus, shared_state, tmp_path):
        """Test features for pubsub mode."""
        agent = RedisPubSubAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            redis_mode="pubsub",
        )
        features = agent._get_configured_features()
        assert "pubsub" in features
        assert "websocket_adapter" in features

    def test_cache_mode_features(self, event_bus, shared_state, tmp_path):
        """Test features for cache mode."""
        agent = RedisPubSubAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            redis_mode="cache",
        )
        features = agent._get_configured_features()
        assert "cache" in features
        assert "session_store" in features

    def test_all_mode_features(self, redis_agent_with_bridge):
        """Test features for 'all' mode."""
        features = redis_agent_with_bridge._get_configured_features()
        assert "pubsub" in features
        assert "cache" in features
        assert "job_queue" in features


class TestRedisPubSubAgentPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_generation_prompt_includes_mode(self, redis_agent):
        """Test generation prompt includes Redis mode."""
        prompt = redis_agent._build_generation_prompt("Test instructions")
        assert "pubsub" in prompt.lower()

    def test_build_generation_prompt_includes_websocket_context(self, redis_agent):
        """Test generation prompt includes WebSocket handler context."""
        redis_agent._websocket_data = {
            "handlers": ["chat.gateway.ts", "notification.gateway.ts"]
        }
        prompt = redis_agent._build_generation_prompt("Test")
        assert "chat.gateway.ts" in prompt


class TestRedisPubSubAgentNeedsRedis:
    """Tests for _needs_redis detection method."""

    def test_needs_redis_with_cache_interface(self, redis_agent):
        """Test detection of cache-related interfaces."""
        data = {
            "interfaces": {
                "CacheService": {},
            }
        }
        result = redis_agent._needs_redis(data)
        assert result is True

    def test_needs_redis_with_queue_interface(self, redis_agent):
        """Test detection of queue-related interfaces."""
        data = {
            "interfaces": {
                "JobQueue": {},
            }
        }
        result = redis_agent._needs_redis(data)
        assert result is True

    def test_needs_redis_returns_false_for_unrelated(self, redis_agent):
        """Test returns False for unrelated interfaces."""
        data = {
            "interfaces": {
                "UserDTO": {},
                "ProductDTO": {},
            }
        }
        result = redis_agent._needs_redis(data)
        assert result is False

    def test_needs_redis_with_none_data(self, redis_agent):
        """Test graceful handling of None data."""
        result = redis_agent._needs_redis(None)
        assert result is False


class TestRedisPubSubAgentAutogenTeam:
    """Tests for AutogenTeamMixin integration."""

    def test_is_autogen_available_returns_boolean(self, redis_agent):
        """Test is_autogen_available returns a boolean."""
        result = redis_agent.is_autogen_available()
        assert isinstance(result, bool)

    def test_get_operator_system_prompt_contains_requirements(self, redis_agent):
        """Test operator system prompt includes critical requirements."""
        prompt = redis_agent._get_operator_system_prompt()

        assert "RedisOperator" in prompt
        assert redis_agent.redis_mode in prompt.lower()
        assert "connection" in prompt.lower()
        assert "NO MOCK" in prompt.upper() or "real" in prompt.lower()

    def test_get_validator_system_prompt_contains_checklist(self, redis_agent):
        """Test validator system prompt includes review checklist."""
        prompt = redis_agent._get_validator_system_prompt()

        assert "RedisValidator" in prompt
        assert "health" in prompt.lower()
        assert "production" in prompt.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
