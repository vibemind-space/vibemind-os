"""Tests for DatabaseAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.agents.database_agent import DatabaseAgent
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
def database_agent(event_bus, shared_state, tmp_path):
    """Create a DatabaseAgent instance for testing."""
    return DatabaseAgent(
        name="TestDatabaseAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        db_type="prisma",
    )


class TestDatabaseAgentInit:
    """Tests for DatabaseAgent initialization."""

    def test_subscribed_events(self, database_agent):
        """Test that DatabaseAgent subscribes to correct events."""
        events = database_agent.subscribed_events
        assert EventType.CONTRACTS_GENERATED in events
        assert EventType.SCHEMA_UPDATE_NEEDED in events
        assert EventType.DATABASE_MIGRATION_NEEDED in events

    def test_default_db_type(self, event_bus, shared_state, tmp_path):
        """Test default database type is prisma."""
        agent = DatabaseAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.db_type == "prisma"

    def test_custom_db_type(self, event_bus, shared_state, tmp_path):
        """Test custom database type can be set."""
        agent = DatabaseAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            db_type="sqlalchemy",
        )
        assert agent.db_type == "sqlalchemy"


class TestDatabaseAgentShouldAct:
    """Tests for DatabaseAgent.should_act()."""

    @pytest.mark.asyncio
    async def test_should_act_on_contracts_generated(self, database_agent):
        """Test agent should act on CONTRACTS_GENERATED event."""
        event = Event(
            type=EventType.CONTRACTS_GENERATED,
            source="hybrid_pipeline",
            data={"types": 5, "endpoints": 10},
        )
        result = await database_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_schema_update_needed(self, database_agent):
        """Test agent should act on SCHEMA_UPDATE_NEEDED event."""
        event = Event(
            type=EventType.SCHEMA_UPDATE_NEEDED,
            source="api_agent",
            data={"reason": "new entity"},
        )
        result = await database_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_event(self, database_agent):
        """Test agent should not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = await database_agent.should_act([event])
        assert result is False


class TestDatabaseAgentPromptBuilding:
    """Tests for DatabaseAgent prompt building methods."""

    def test_build_schema_prompt_prisma(self, database_agent):
        """Test Prisma schema prompt generation."""
        database_agent._contracts_data = {
            "entities": [
                {"name": "User", "fields": [{"name": "id"}, {"name": "email"}, {"name": "name"}]},
                {"name": "Post", "fields": [{"name": "id"}, {"name": "title"}, {"name": "userId"}]},
            ]
        }
        prompt = database_agent._build_schema_prompt()

        assert "Prisma" in prompt or "PRISMA" in prompt
        assert "schema.prisma" in prompt
        assert "User" in prompt
        assert "Post" in prompt

    def test_build_schema_prompt_sqlalchemy(self, event_bus, shared_state, tmp_path):
        """Test SQLAlchemy schema prompt generation."""
        agent = DatabaseAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            db_type="sqlalchemy",
        )
        agent._contracts_data = {
            "entities": [{"name": "User", "fields": [{"name": "id"}, {"name": "email"}]}]
        }
        prompt = agent._build_schema_prompt()

        assert "SQLAlchemy" in prompt or "SQLALCHEMY" in prompt
        assert "models.py" in prompt

    def test_get_db_type_instructions_prisma(self, database_agent):
        """Test Prisma-specific instructions."""
        instructions = database_agent._get_db_type_instructions()
        assert "prisma" in instructions.lower()

    def test_get_db_type_instructions_drizzle(self, event_bus, shared_state, tmp_path):
        """Test Drizzle-specific instructions."""
        agent = DatabaseAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            db_type="drizzle",
        )
        instructions = agent._get_db_type_instructions()
        assert "drizzle" in instructions.lower()


class TestDatabaseAgentAntiMockPolicy:
    """Tests for DatabaseAgent anti-mock policy."""

    def test_prompt_contains_anti_mock_policy(self, database_agent):
        """Test that prompts include anti-mock policy."""
        database_agent._contracts_data = {"entities": [{"name": "Test"}]}
        prompt = database_agent._build_schema_prompt()

        # Check for anti-mock policy markers
        assert "REAL" in prompt or "mock" in prompt.lower() or "MOCK" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
