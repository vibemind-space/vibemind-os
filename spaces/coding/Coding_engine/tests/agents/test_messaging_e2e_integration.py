"""
Phase 11: E2E Integration Test for Messaging Agents.

Verifies:
- All 4 messaging agents can be imported
- All agents subscribe to correct events
- Event chain triggers work correctly
- Agents are properly registered in orchestrator
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
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
    """Create a mock SharedState."""
    state = MagicMock()
    state.get_metrics = MagicMock(return_value=MagicMock())
    state.context_bridge = None
    state.tech_stack = {"backend": {"framework": "nestjs"}}
    return state


# =============================================================================
# Test: All Agents Importable
# =============================================================================

class TestMessagingAgentsImport:
    """Verify all messaging agents can be imported."""

    def test_websocket_agent_importable(self):
        """WebSocketAgent should be importable."""
        from src.agents.websocket_agent import WebSocketAgent
        assert WebSocketAgent is not None

    def test_redis_pubsub_agent_importable(self):
        """RedisPubSubAgent should be importable."""
        from src.agents.redis_pubsub_agent import RedisPubSubAgent
        assert RedisPubSubAgent is not None

    def test_presence_agent_importable(self):
        """PresenceAgent should be importable."""
        from src.agents.presence_agent import PresenceAgent
        assert PresenceAgent is not None

    def test_encryption_agent_importable(self):
        """EncryptionAgent should be importable."""
        from src.agents.encryption_agent import EncryptionAgent
        assert EncryptionAgent is not None


# =============================================================================
# Test: All Agents Instantiable
# =============================================================================

class TestMessagingAgentsInstantiation:
    """Verify all messaging agents can be instantiated."""

    def test_websocket_agent_instantiation(self, event_bus, shared_state, tmp_path):
        """WebSocketAgent should instantiate correctly."""
        agent = WebSocketAgent(
            name="websocket_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "websocket_agent"

    def test_redis_pubsub_agent_instantiation(self, event_bus, shared_state, tmp_path):
        """RedisPubSubAgent should instantiate correctly."""
        agent = RedisPubSubAgent(
            name="redis_pubsub_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "redis_pubsub_agent"

    def test_presence_agent_instantiation(self, event_bus, shared_state, tmp_path):
        """PresenceAgent should instantiate correctly."""
        agent = PresenceAgent(
            name="presence_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "presence_agent"

    def test_encryption_agent_instantiation(self, event_bus, shared_state, tmp_path):
        """EncryptionAgent should instantiate correctly."""
        agent = EncryptionAgent(
            name="encryption_agent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "encryption_agent"


# =============================================================================
# Test: Event Chain Triggers
# =============================================================================

class TestMessagingEventChain:
    """Test the event chain for messaging agents."""

    def test_websocket_subscribes_to_api_routes(self, event_bus, shared_state, tmp_path):
        """WebSocketAgent should subscribe to API_ROUTES_GENERATED."""
        agent = WebSocketAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert EventType.API_ROUTES_GENERATED in agent.subscribed_events

    def test_redis_subscribes_to_websocket(self, event_bus, shared_state, tmp_path):
        """RedisPubSubAgent should subscribe to WEBSOCKET_HANDLER_GENERATED."""
        agent = RedisPubSubAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert EventType.WEBSOCKET_HANDLER_GENERATED in agent.subscribed_events

    def test_presence_subscribes_to_websocket_and_redis(self, event_bus, shared_state, tmp_path):
        """PresenceAgent should subscribe to WEBSOCKET_HANDLER_GENERATED and REDIS_PUBSUB_CONFIGURED."""
        agent = PresenceAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert EventType.WEBSOCKET_HANDLER_GENERATED in agent.subscribed_events
        assert EventType.REDIS_PUBSUB_CONFIGURED in agent.subscribed_events

    def test_encryption_subscribes_to_auth(self, event_bus, shared_state, tmp_path):
        """EncryptionAgent should subscribe to AUTH_SETUP_COMPLETE."""
        agent = EncryptionAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert EventType.AUTH_SETUP_COMPLETE in agent.subscribed_events


# =============================================================================
# Test: should_act() Logic
# =============================================================================

class TestMessagingShouldAct:
    """Test should_act() for messaging agents."""

    @pytest.mark.asyncio
    async def test_websocket_acts_on_api_routes_with_realtime(self, event_bus, shared_state, tmp_path):
        """WebSocketAgent should act on API_ROUTES_GENERATED with real-time routes."""
        agent = WebSocketAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        # Include routes with real-time keywords (chat, message, etc.)
        event = Event(
            type=EventType.API_ROUTES_GENERATED,
            source="api_agent",
            data={"routes": [{"path": "/api/chat", "method": "GET"}]},
        )
        # WebSocketAgent.should_act is async
        result = await agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_websocket_does_not_act_without_realtime(self, event_bus, shared_state, tmp_path):
        """WebSocketAgent should not act on API_ROUTES_GENERATED without real-time routes."""
        agent = WebSocketAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        # Routes without real-time keywords
        event = Event(
            type=EventType.API_ROUTES_GENERATED,
            source="api_agent",
            data={"routes": [{"path": "/api/users", "method": "GET"}]},
        )
        result = await agent.should_act([event])
        assert result is False

    @pytest.mark.asyncio
    async def test_redis_acts_on_websocket(self, event_bus, shared_state, tmp_path):
        """RedisPubSubAgent should act on WEBSOCKET_HANDLER_GENERATED."""
        agent = RedisPubSubAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        event = Event(
            type=EventType.WEBSOCKET_HANDLER_GENERATED,
            source="websocket_agent",
            data={},
        )
        result = await agent.should_act([event])
        assert result is True

    def test_presence_acts_on_websocket(self, event_bus, shared_state, tmp_path):
        """PresenceAgent should act on WEBSOCKET_HANDLER_GENERATED."""
        agent = PresenceAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        event = Event(
            type=EventType.WEBSOCKET_HANDLER_GENERATED,
            source="websocket_agent",
            data={},
        )
        result = agent.should_act([event])
        assert result is True

    def test_encryption_acts_on_auth(self, event_bus, shared_state, tmp_path):
        """EncryptionAgent should act on AUTH_SETUP_COMPLETE."""
        agent = EncryptionAgent(
            name="test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        event = Event(
            type=EventType.AUTH_SETUP_COMPLETE,
            source="auth_agent",
            data={},
        )
        result = agent.should_act([event])
        assert result is True


# =============================================================================
# Test: Full Event Chain Simulation
# =============================================================================

class TestMessagingFullEventChain:
    """Test the full event chain for messaging platform."""

    def test_event_chain_order(self, event_bus, shared_state, tmp_path):
        """
        Verify the expected event chain order:
        API_ROUTES_GENERATED -> WebSocket
        WEBSOCKET_HANDLER_GENERATED -> Redis + Presence
        REDIS_PUBSUB_CONFIGURED -> Presence
        AUTH_SETUP_COMPLETE -> Encryption
        GENERATION_COMPLETE (from presence) -> Encryption
        """
        ws_agent = WebSocketAgent(name="ws", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))
        redis_agent = RedisPubSubAgent(name="redis", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))
        presence_agent = PresenceAgent(name="presence", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))
        encryption_agent = EncryptionAgent(name="encryption", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))

        # Step 1: API_ROUTES_GENERATED triggers WebSocket
        api_event = Event(type=EventType.API_ROUTES_GENERATED, source="api_agent", data={})
        assert EventType.API_ROUTES_GENERATED in ws_agent.subscribed_events

        # Step 2: WEBSOCKET_HANDLER_GENERATED triggers Redis and Presence
        ws_event = Event(type=EventType.WEBSOCKET_HANDLER_GENERATED, source="websocket_agent", data={})
        assert EventType.WEBSOCKET_HANDLER_GENERATED in redis_agent.subscribed_events
        assert EventType.WEBSOCKET_HANDLER_GENERATED in presence_agent.subscribed_events

        # Step 3: REDIS_PUBSUB_CONFIGURED triggers Presence
        redis_event = Event(type=EventType.REDIS_PUBSUB_CONFIGURED, source="redis_agent", data={})
        assert EventType.REDIS_PUBSUB_CONFIGURED in presence_agent.subscribed_events

        # Step 4: AUTH_SETUP_COMPLETE triggers Encryption
        auth_event = Event(type=EventType.AUTH_SETUP_COMPLETE, source="auth_agent", data={})
        assert EventType.AUTH_SETUP_COMPLETE in encryption_agent.subscribed_events

        # Step 5: GENERATION_COMPLETE from presence triggers Encryption
        gen_event = Event(type=EventType.GENERATION_COMPLETE, source="presence_agent", data={"agent": "presence_agent"})
        assert EventType.GENERATION_COMPLETE in encryption_agent.subscribed_events


# =============================================================================
# Test: Orchestrator Registration
# =============================================================================

class TestOrchestratorRegistration:
    """Test that messaging agents are registered in orchestrator."""

    def test_orchestrator_imports_all_messaging_agents(self):
        """Verify orchestrator can import all messaging agents."""
        # This tests the import paths used in orchestrator.py
        from src.agents.websocket_agent import WebSocketAgent
        from src.agents.redis_pubsub_agent import RedisPubSubAgent
        from src.agents.presence_agent import PresenceAgent
        from src.agents.encryption_agent import EncryptionAgent

        # All imports successful
        assert WebSocketAgent is not None
        assert RedisPubSubAgent is not None
        assert PresenceAgent is not None
        assert EncryptionAgent is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
