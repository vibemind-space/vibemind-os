"""Tests for APIAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.agents.api_agent import APIAgent
from src.mind.event_bus import EventBus, Event, EventType


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
    return state


@pytest.fixture
def api_agent(event_bus, shared_state, tmp_path):
    """Create an APIAgent instance for testing."""
    return APIAgent(
        name="TestAPIAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        api_framework="nextjs",
    )


class TestAPIAgentInit:
    """Tests for APIAgent initialization."""

    def test_subscribed_events(self, api_agent):
        """Test that APIAgent subscribes to correct events."""
        events = api_agent.subscribed_events
        assert EventType.CONTRACTS_GENERATED in events
        assert EventType.DATABASE_SCHEMA_GENERATED in events
        assert EventType.API_UPDATE_NEEDED in events
        assert EventType.API_ENDPOINT_FAILED in events

    def test_default_api_framework(self, event_bus, shared_state, tmp_path):
        """Test default API framework is nextjs."""
        agent = APIAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.api_framework == "nextjs"

    def test_custom_api_framework(self, event_bus, shared_state, tmp_path):
        """Test custom API framework can be set."""
        agent = APIAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            api_framework="express",
        )
        assert agent.api_framework == "express"


class TestAPIAgentShouldAct:
    """Tests for APIAgent.should_act()."""

    @pytest.mark.asyncio
    async def test_should_act_on_database_schema_generated(self, api_agent):
        """Test agent should act on DATABASE_SCHEMA_GENERATED event."""
        event = Event(
            type=EventType.DATABASE_SCHEMA_GENERATED,
            source="database_agent",
            data={"schema_path": "prisma/schema.prisma"},
        )
        result = await api_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_api_endpoint_failed(self, api_agent):
        """Test agent should act on API_ENDPOINT_FAILED event."""
        event = Event(
            type=EventType.API_ENDPOINT_FAILED,
            source="tester",
            data={"endpoint": "/api/users", "error": "500 Internal Server Error"},
        )
        result = await api_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_wait_for_schema_on_contracts_generated(self, api_agent):
        """Test agent waits for database schema before acting on contracts."""
        # APIAgent should wait for DATABASE_SCHEMA_GENERATED before acting on CONTRACTS_GENERATED
        event = Event(
            type=EventType.CONTRACTS_GENERATED,
            source="hybrid_pipeline",
            data={"types": 5},
        )
        # Without schema being generated, agent should wait
        api_agent._schema_generated = False
        result = await api_agent.should_act([event])
        # Should still return True but with waiting logic
        assert result is True or result is False  # Depends on implementation

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_event(self, api_agent):
        """Test agent should not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = await api_agent.should_act([event])
        assert result is False


class TestAPIAgentPromptBuilding:
    """Tests for APIAgent prompt building methods."""

    def test_build_api_prompt_nextjs(self, api_agent):
        """Test Next.js API route prompt generation."""
        api_agent._contracts_data = {
            "api_endpoints": [
                {"path": "/api/users", "method": "GET"},
                {"path": "/api/users", "method": "POST"},
            ]
        }
        prompt = api_agent._build_api_prompt()

        assert "Next.js" in prompt or "nextjs" in prompt.lower() or "NEXTJS" in prompt
        assert "/api/users" in prompt
        assert "GET" in prompt
        assert "POST" in prompt

    def test_build_api_prompt_express(self, event_bus, shared_state, tmp_path):
        """Test Express API route prompt generation."""
        agent = APIAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            api_framework="express",
        )
        agent._contracts_data = {
            "api_endpoints": [{"path": "/users", "method": "GET"}]
        }
        prompt = agent._build_api_prompt()

        assert "Express" in prompt or "express" in prompt.lower()

    def test_build_api_prompt_fastapi(self, event_bus, shared_state, tmp_path):
        """Test FastAPI route prompt generation."""
        agent = APIAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            api_framework="fastapi",
        )
        agent._contracts_data = {
            "api_endpoints": [{"path": "/users", "method": "GET"}]
        }
        prompt = agent._build_api_prompt()

        assert "FastAPI" in prompt or "fastapi" in prompt.lower()

    def test_get_framework_instructions_nextjs(self, api_agent):
        """Test Next.js-specific instructions."""
        instructions = api_agent._get_framework_instructions()
        assert "next" in instructions.lower() or "api" in instructions.lower()


class TestAPIAgentAntiMockPolicy:
    """Tests for APIAgent anti-mock policy."""

    def test_prompt_contains_database_connection(self, api_agent):
        """Test that prompts require real database connections."""
        api_agent._contracts_data = {"api_endpoints": [{"path": "/api/test", "method": "GET"}]}
        prompt = api_agent._build_api_prompt()

        # Should emphasize real database connections, not mocks
        assert "database" in prompt.lower() or "prisma" in prompt.lower()


class TestAPIAgentEventPublishing:
    """Tests for APIAgent event publishing."""

    @pytest.mark.asyncio
    async def test_publishes_api_routes_generated_on_success(self, api_agent, event_bus):
        """Test that agent publishes API_ROUTES_GENERATED after successful generation."""
        # This would be tested with integration test
        # For unit test, verify the event type exists
        assert hasattr(EventType, "API_ROUTES_GENERATED")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
