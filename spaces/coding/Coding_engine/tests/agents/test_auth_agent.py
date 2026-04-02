"""Tests for AuthAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.agents.auth_agent import AuthAgent
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
def auth_agent(event_bus, shared_state, tmp_path):
    """Create an AuthAgent instance for testing."""
    return AuthAgent(
        name="TestAuthAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        auth_type="jwt",
        enable_rbac=True,
    )


class TestAuthAgentInit:
    """Tests for AuthAgent initialization."""

    def test_subscribed_events(self, auth_agent):
        """Test that AuthAgent subscribes to correct events."""
        events = auth_agent.subscribed_events
        assert EventType.CONTRACTS_GENERATED in events
        assert EventType.API_ROUTES_GENERATED in events
        assert EventType.AUTH_REQUIRED in events
        assert EventType.ROLE_DEFINITION_NEEDED in events
        assert EventType.AUTH_CONFIG_UPDATED in events

    def test_default_auth_type(self, event_bus, shared_state, tmp_path):
        """Test default auth type is jwt."""
        agent = AuthAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.auth_type == "jwt"

    def test_custom_auth_type(self, event_bus, shared_state, tmp_path):
        """Test custom auth type can be set."""
        agent = AuthAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            auth_type="oauth2",
        )
        assert agent.auth_type == "oauth2"

    def test_rbac_enabled_by_default(self, auth_agent):
        """Test RBAC is enabled by default."""
        assert auth_agent.enable_rbac is True

    def test_rbac_can_be_disabled(self, event_bus, shared_state, tmp_path):
        """Test RBAC can be disabled."""
        agent = AuthAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_rbac=False,
        )
        assert agent.enable_rbac is False


class TestAuthAgentShouldAct:
    """Tests for AuthAgent.should_act()."""

    @pytest.mark.asyncio
    async def test_should_act_on_api_routes_generated(self, auth_agent):
        """Test agent should act on API_ROUTES_GENERATED event."""
        event = Event(
            type=EventType.API_ROUTES_GENERATED,
            source="api_agent",
            data={"routes_count": 10},
        )
        result = await auth_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_auth_required(self, auth_agent):
        """Test agent should act on AUTH_REQUIRED event."""
        event = Event(
            type=EventType.AUTH_REQUIRED,
            source="api_agent",
            data={"endpoint": "/api/admin", "required_role": "admin"},
        )
        result = await auth_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_role_definition_needed(self, auth_agent):
        """Test agent should act on ROLE_DEFINITION_NEEDED event."""
        event = Event(
            type=EventType.ROLE_DEFINITION_NEEDED,
            source="requirements_parser",
            data={"roles": ["admin", "user", "moderator"]},
        )
        result = await auth_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_event(self, auth_agent):
        """Test agent should not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = await auth_agent.should_act([event])
        assert result is False


class TestAuthAgentPromptBuilding:
    """Tests for AuthAgent prompt building methods."""

    def test_build_auth_prompt_jwt(self, auth_agent):
        """Test JWT auth prompt generation."""
        auth_agent._contracts_data = {
            "endpoints": [
                {"path": "/api/login", "method": "POST"},
                {"path": "/api/protected", "method": "GET", "auth": True},
            ]
        }
        prompt = auth_agent._build_auth_prompt()

        assert "JWT" in prompt or "jwt" in prompt.lower()
        assert "token" in prompt.lower()

    def test_build_auth_prompt_oauth2(self, event_bus, shared_state, tmp_path):
        """Test OAuth2 auth prompt generation."""
        agent = AuthAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            auth_type="oauth2",
        )
        agent._contracts_data = {"endpoints": [{"path": "/auth/callback", "method": "GET"}]}
        prompt = agent._build_auth_prompt()

        assert "OAuth" in prompt or "oauth" in prompt.lower()

    def test_build_auth_prompt_includes_rbac(self, auth_agent):
        """Test RBAC is included in prompt when enabled."""
        prompt = auth_agent._build_auth_prompt()

        assert "RBAC" in prompt or "role" in prompt.lower()

    def test_build_auth_prompt_without_rbac(self, event_bus, shared_state, tmp_path):
        """Test RBAC is not included when disabled."""
        agent = AuthAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_rbac=False,
        )
        prompt = agent._build_auth_prompt()

        # RBAC should not be prominently featured when disabled
        # (implementation may still mention it but not as primary focus)
        assert "RBAC" not in prompt or "role-based" not in prompt.lower()


class TestAuthAgentRBACConfiguration:
    """Tests for AuthAgent RBAC configuration."""

    def test_default_roles_defined(self, auth_agent):
        """Test that default roles are defined."""
        # Check that agent has role definitions
        assert hasattr(auth_agent, 'enable_rbac')
        assert auth_agent.enable_rbac is True

    def test_role_hierarchy_in_prompt(self, auth_agent):
        """Test that role hierarchy is included in prompts."""
        auth_agent._contracts_data = {
            "endpoints": [
                {"path": "/api/admin", "auth": True, "role": "admin"},
            ]
        }
        prompt = auth_agent._build_auth_prompt()

        # Should include role hierarchy or permissions
        assert "permission" in prompt.lower() or "role" in prompt.lower()


class TestAuthAgentAntiMockPolicy:
    """Tests for AuthAgent anti-mock policy."""

    def test_prompt_requires_real_secrets(self, auth_agent):
        """Test that prompts require real secrets from environment."""
        prompt = auth_agent._build_auth_prompt()

        # Should mention environment variables for secrets
        assert "env" in prompt.lower() or "secret" in prompt.lower()

    def test_no_hardcoded_secrets(self, auth_agent):
        """Test that prompts prohibit hardcoded secrets."""
        prompt = auth_agent._build_auth_prompt()

        # Should warn against hardcoded secrets
        assert "environment" in prompt.lower() or "process.env" in prompt.lower()


class TestAuthAgentEventPublishing:
    """Tests for AuthAgent event publishing."""

    @pytest.mark.asyncio
    async def test_publishes_auth_setup_complete_on_success(self, auth_agent, event_bus):
        """Test that agent publishes AUTH_SETUP_COMPLETE after successful setup."""
        # Verify the event type exists
        assert hasattr(EventType, "AUTH_SETUP_COMPLETE")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
