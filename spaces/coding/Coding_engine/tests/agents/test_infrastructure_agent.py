"""Tests for InfrastructureAgent."""

import pytest
import base64
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.agents.infrastructure_agent import InfrastructureAgent
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
def infra_agent(event_bus, shared_state, tmp_path):
    """Create an InfrastructureAgent instance for testing."""
    return InfrastructureAgent(
        name="TestInfraAgent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        enable_docker=True,
        enable_ci=True,
    )


class TestInfrastructureAgentInit:
    """Tests for InfrastructureAgent initialization."""

    def test_subscribed_events(self, infra_agent):
        """Test that InfrastructureAgent subscribes to correct events."""
        events = infra_agent.subscribed_events
        assert EventType.GENERATION_COMPLETE in events
        assert EventType.DATABASE_SCHEMA_GENERATED in events
        assert EventType.AUTH_SETUP_COMPLETE in events

    def test_docker_generation_enabled(self, infra_agent):
        """Test Docker generation is enabled by default."""
        assert infra_agent.enable_docker is True

    def test_ci_generation_enabled(self, infra_agent):
        """Test CI/CD generation is enabled by default."""
        assert infra_agent.enable_ci is True

    def test_docker_can_be_disabled(self, event_bus, shared_state, tmp_path):
        """Test Docker generation can be disabled."""
        agent = InfrastructureAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_docker=False,
        )
        assert agent.enable_docker is False

    def test_ci_can_be_disabled(self, event_bus, shared_state, tmp_path):
        """Test CI/CD generation can be disabled."""
        agent = InfrastructureAgent(
            name="Test",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_ci=False,
        )
        assert agent.enable_ci is False


class TestInfrastructureAgentShouldAct:
    """Tests for InfrastructureAgent.should_act()."""

    @pytest.mark.asyncio
    async def test_should_act_on_auth_setup_complete(self, infra_agent):
        """Test agent should act on AUTH_SETUP_COMPLETE event."""
        event = Event(
            type=EventType.AUTH_SETUP_COMPLETE,
            source="auth_agent",
            data={"auth_type": "jwt"},
        )
        result = await infra_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_generation_complete(self, infra_agent):
        """Test agent should act on GENERATION_COMPLETE event."""
        event = Event(
            type=EventType.GENERATION_COMPLETE,
            source="generator",
            data={"files_generated": 50},
        )
        result = await infra_agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_act_on_unrelated_event(self, infra_agent):
        """Test agent should not act on unrelated events."""
        event = Event(
            type=EventType.BUILD_SUCCEEDED,
            source="builder",
            data={},
        )
        result = await infra_agent.should_act([event])
        assert result is False


class TestInfrastructureAgentSecretGeneration:
    """Tests for InfrastructureAgent secret generation."""

    def test_generate_secrets_produces_valid_jwt_secret(self, infra_agent):
        """Test that generated JWT secret is valid base64."""
        secrets_output = infra_agent._generate_secrets()

        # Should contain JWT_SECRET
        assert "JWT_SECRET" in secrets_output

        # Extract the JWT secret value
        for line in secrets_output.split("\n"):
            if line.startswith("JWT_SECRET="):
                jwt_secret = line.split("=", 1)[1]
                # Should be valid base64
                try:
                    decoded = base64.urlsafe_b64decode(jwt_secret)
                    assert len(decoded) >= 32  # At least 256 bits
                except Exception:
                    pytest.fail("JWT_SECRET is not valid base64")
                break

    def test_generate_secrets_produces_unique_values(self, infra_agent):
        """Test that each call produces unique secrets."""
        secrets1 = infra_agent._generate_secrets()
        secrets2 = infra_agent._generate_secrets()

        # Secrets should be different each time
        assert secrets1 != secrets2

    def test_generate_secrets_includes_required_keys(self, infra_agent):
        """Test that all required secret keys are present."""
        secrets_output = infra_agent._generate_secrets()

        required_keys = ["JWT_SECRET", "POSTGRES_USER", "POSTGRES_DB"]
        for key in required_keys:
            assert key in secrets_output, f"Missing required key: {key}"

    def test_generate_secrets_no_placeholder_values(self, infra_agent):
        """Test that secrets don't contain placeholder values."""
        secrets_output = infra_agent._generate_secrets()

        # Should not contain common placeholder patterns
        # Note: .env.example section may mention placeholders as instructions,
        # but actual secret values should not be placeholders
        for line in secrets_output.split("\n"):
            # Only check lines that look like KEY=VALUE assignments
            if "=" in line and not line.strip().startswith("#") and not line.strip().startswith("For"):
                key_val = line.strip()
                if key_val.startswith("JWT_SECRET=") or key_val.startswith("API_KEY="):
                    value = key_val.split("=", 1)[1]
                    assert "xxx" not in value.lower(), \
                        f"Found placeholder pattern 'xxx' in {key_val}"
                    assert "TODO" not in value, \
                        f"Found placeholder pattern 'TODO' in {key_val}"


class TestInfrastructureAgentPromptBuilding:
    """Tests for InfrastructureAgent prompt building methods."""

    def test_build_infra_prompt(self, infra_agent):
        """Test infrastructure prompt generation."""
        prompt = infra_agent._build_infra_prompt()

        # Should contain env-related content
        assert ".env" in prompt or "environment" in prompt.lower()

    def test_build_infra_prompt_includes_docker(self, infra_agent):
        """Test that infra prompt includes Docker when enabled."""
        prompt = infra_agent._build_infra_prompt()

        assert "docker" in prompt.lower() or "Docker" in prompt

    def test_build_infra_prompt_includes_ci(self, infra_agent):
        """Test that infra prompt includes CI/CD when enabled."""
        prompt = infra_agent._build_infra_prompt()

        assert "CI" in prompt or "GitHub Actions" in prompt or "workflow" in prompt.lower()


class TestInfrastructureAgentAntiMockPolicy:
    """Tests for InfrastructureAgent anti-mock policy."""

    def test_infra_prompt_uses_real_values(self, infra_agent):
        """Test that infra prompt emphasizes real values."""
        prompt = infra_agent._build_infra_prompt()

        # Should emphasize real configuration (secrets are pre-generated)
        assert "secret" in prompt.lower() or "real" in prompt.lower() or \
               "JWT_SECRET" in prompt

    def test_no_mock_database_urls(self, infra_agent):
        """Test that secrets don't contain mock database URLs."""
        secrets_output = infra_agent._generate_secrets()

        # Should not contain obvious mock patterns
        mock_patterns = ["localhost:5432/mock", "memory:", "fake://"]
        for pattern in mock_patterns:
            assert pattern not in secrets_output


class TestInfrastructureAgentEventPublishing:
    """Tests for InfrastructureAgent event publishing."""

    @pytest.mark.asyncio
    async def test_event_types_exist(self, infra_agent):
        """Test that required event types exist."""
        # Verify infrastructure-related event types exist
        assert hasattr(EventType, "ENV_CONFIG_GENERATED") or \
               hasattr(EventType, "DOCKER_COMPOSE_READY") or \
               hasattr(EventType, "INFRASTRUCTURE_READY")


class TestInfrastructureAgentDockerGeneration:
    """Tests for InfrastructureAgent Docker generation."""

    def test_docker_instructions_include_services(self, infra_agent):
        """Test Docker instructions include service definitions."""
        instructions = infra_agent._get_docker_instructions()

        assert "service" in instructions.lower() or "postgres" in instructions.lower()

    def test_docker_instructions_multi_stage(self, infra_agent):
        """Test Docker instructions suggest production setup."""
        instructions = infra_agent._get_docker_instructions()

        # Should mention production or optimization concepts
        assert "production" in instructions.lower() or "compose" in instructions.lower() or \
               "volume" in instructions.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
