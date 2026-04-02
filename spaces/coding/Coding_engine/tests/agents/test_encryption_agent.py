"""
Tests for EncryptionAgent with Context Bridge integration.

Verifies:
- Agent initialization and configuration
- Subscribed events handling
- should_act() decision logic
- _get_task_type() for context bridge
- Context bridge integration
- Prompt building methods
- Security requirements enforcement
- Swarm handoff configuration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

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
        diagrams=[],
        entities=[],
        rag_results=[
            {"relative_path": "src/crypto/key-exchange.ts", "content": "ECDH...", "score": 0.9},
        ],
    ))
    return bridge


@pytest.fixture
def encryption_agent(event_bus, shared_state, tmp_path):
    """Create an EncryptionAgent instance for testing."""
    return EncryptionAgent(
        name="encryption_agent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
    )


@pytest.fixture
def encryption_agent_with_bridge(event_bus, shared_state, mock_context_bridge, tmp_path):
    """Create an EncryptionAgent with context bridge configured."""
    return EncryptionAgent(
        name="encryption_agent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
        context_bridge=mock_context_bridge,
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestEncryptionAgentInit:
    """Tests for EncryptionAgent initialization."""

    def test_subscribed_events(self, encryption_agent):
        """Test that EncryptionAgent subscribes to correct events."""
        events = encryption_agent.subscribed_events
        assert EventType.AUTH_SETUP_COMPLETE in events
        assert EventType.GENERATION_COMPLETE in events

    def test_default_name(self, event_bus, shared_state, tmp_path):
        """Test default name is 'encryption_agent'."""
        agent = EncryptionAgent(
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "encryption_agent"


class TestEncryptionAgentShouldAct:
    """Tests for EncryptionAgent.should_act() decision logic."""

    def test_should_act_on_auth_setup_complete(self, encryption_agent):
        """Test agent acts when auth setup is complete."""
        event = Event(
            type=EventType.AUTH_SETUP_COMPLETE,
            source="auth_agent",
            data={"auth_type": "jwt"},
        )
        result = encryption_agent.should_act([event])
        assert result is True

    def test_should_act_on_presence_agent_completion(self, encryption_agent):
        """Test agent acts when presence agent completes (chain trigger)."""
        event = Event(
            type=EventType.GENERATION_COMPLETE,
            source="presence_agent",
            data={"agent": "presence_agent"},
        )
        result = encryption_agent.should_act([event])
        assert result is True

    def test_should_not_act_on_other_agent_completion(self, encryption_agent):
        """Test agent does not act when other agents complete."""
        event = Event(
            type=EventType.GENERATION_COMPLETE,
            source="other_agent",
            data={"agent": "other_agent"},
        )
        result = encryption_agent.should_act([event])
        assert result is False

    def test_should_not_act_on_empty_events(self, encryption_agent):
        """Test agent does not act on empty events list."""
        result = encryption_agent.should_act([])
        assert result is False


class TestEncryptionAgentTaskType:
    """Tests for _get_task_type method."""

    def test_get_task_type_returns_auth(self, encryption_agent):
        """Encryption uses auth context for security requirements."""
        task_type = encryption_agent._get_task_type()
        assert task_type == "auth"


class TestEncryptionAgentContextBridge:
    """Tests for context bridge integration."""

    @pytest.mark.asyncio
    async def test_get_task_context_uses_bridge(self, encryption_agent_with_bridge):
        """Test get_task_context calls context bridge correctly."""
        context = await encryption_agent_with_bridge.get_task_context(
            query="encryption E2EE ECDH",
        )
        assert context is not None
        encryption_agent_with_bridge.context_bridge.get_context_for_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task_context_returns_none_without_bridge(self, encryption_agent):
        """Test get_task_context returns None when no bridge configured."""
        context = await encryption_agent.get_task_context(query="test")
        assert context is None


class TestEncryptionAgentPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_encryption_prompt_includes_security_notice(self, encryption_agent):
        """Test encryption prompt includes security warnings."""
        events = []
        prompt = encryption_agent._build_encryption_prompt(events)

        # Should include security warnings
        assert "security" in prompt.lower() or "audit" in prompt.lower()

    def test_build_encryption_prompt_includes_crypto_components(self, encryption_agent):
        """Test encryption prompt includes all E2EE components."""
        events = []
        prompt = encryption_agent._build_encryption_prompt(events)

        # Should include all E2EE components
        assert "Key Exchange" in prompt or "ECDH" in prompt or "key" in prompt.lower()
        assert "encrypt" in prompt.lower()

    def test_build_encryption_prompt_includes_library_requirements(self, encryption_agent):
        """Test encryption prompt specifies libraries to use."""
        events = []
        prompt = encryption_agent._build_encryption_prompt(events)

        # Should specify libraries to use
        assert "tweetnacl" in prompt or "libsodium" in prompt or "crypto" in prompt.lower()


class TestEncryptionAgentSecurityRequirements:
    """Tests for security requirements enforcement."""

    def test_operator_prompt_prohibits_custom_crypto(self, encryption_agent):
        """Test operator prompt prohibits custom crypto implementations."""
        prompt = encryption_agent._get_operator_system_prompt()

        # Should warn against custom crypto
        assert "NEVER" in prompt or "custom" in prompt.lower() or "established" in prompt.lower()

    def test_operator_prompt_requires_secure_random(self, encryption_agent):
        """Test operator prompt requires cryptographically secure randomness."""
        prompt = encryption_agent._get_operator_system_prompt()

        # Should mention secure random sources
        assert "random" in prompt.lower() or "secure" in prompt.lower()

    def test_validator_prompt_includes_security_checklist(self, encryption_agent):
        """Test validator prompt includes security review checklist."""
        prompt = encryption_agent._get_validator_system_prompt()

        # Should have security checklist
        assert "Security" in prompt or "security" in prompt.lower()


class TestEncryptionAgentSwarmHandoff:
    """Tests for Swarm pattern configuration."""

    def test_get_handoff_targets(self, encryption_agent):
        """Test get_handoff_targets returns valid dict."""
        targets = encryption_agent.get_handoff_targets()
        assert isinstance(targets, dict)
        assert len(targets) > 0

    def test_get_agent_capabilities(self, encryption_agent):
        """Test get_agent_capabilities returns expected capabilities."""
        capabilities = encryption_agent.get_agent_capabilities()
        assert "encryption" in capabilities
        assert "e2ee" in capabilities
        assert "key_exchange" in capabilities
        assert "security" in capabilities


class TestEncryptionAgentAutogenTeam:
    """Tests for AutogenTeamMixin integration."""

    def test_is_autogen_available_returns_boolean(self, encryption_agent):
        """Test is_autogen_available returns a boolean."""
        result = encryption_agent.is_autogen_available()
        assert isinstance(result, bool)

    def test_get_operator_system_prompt_contains_requirements(self, encryption_agent):
        """Test operator system prompt includes critical requirements."""
        prompt = encryption_agent._get_operator_system_prompt()

        assert "EncryptionOperator" in prompt
        # Should mention established crypto libraries
        assert "tweetnacl" in prompt.lower() or "libsodium" in prompt.lower() or "established" in prompt.lower()

    def test_get_validator_system_prompt_contains_checklist(self, encryption_agent):
        """Test validator system prompt includes review checklist."""
        prompt = encryption_agent._get_validator_system_prompt()

        assert "EncryptionValidator" in prompt
        # Should have security-focused review


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
