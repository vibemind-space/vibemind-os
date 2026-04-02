"""
Tests for EnvironmentReportAgent with AutoGen 0.4 compatible user input prompting.

Tests cover:
1. Basic agent instantiation
2. Sync callback handling
3. Async callback handling
4. Report generation without prompting
5. Report generation with prompting
6. Secret collection flow
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.environment_report_agent import (
    EnvironmentReportAgent,
    EnvRequirement,
    SecretInputCallback,
    COMMON_ENV_REQUIREMENTS,
)
from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState


class TestEnvironmentReportAgentInstantiation:
    """Test agent instantiation and configuration."""

    def test_basic_instantiation(self):
        """Test basic agent creation with event bus."""
        event_bus = EventBus()
        agent = EnvironmentReportAgent(event_bus=event_bus)

        assert agent.name == "EnvironmentReport"
        assert agent.prompt_for_missing is False
        assert agent.input_callback is None
        assert len(agent.env_requirements) > 0  # Common requirements

    def test_instantiation_with_prompt_enabled(self):
        """Test agent creation with prompting enabled."""
        event_bus = EventBus()
        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
        )

        assert agent.prompt_for_missing is True
        assert agent.input_callback is None

    def test_instantiation_with_sync_callback(self):
        """Test agent creation with sync input callback."""
        event_bus = EventBus()

        def sync_input(name: str, description: str) -> str:
            return f"test_value_for_{name}"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=sync_input,
        )

        assert agent.prompt_for_missing is True
        assert agent.input_callback is sync_input

    def test_instantiation_with_async_callback(self):
        """Test agent creation with async input callback."""
        event_bus = EventBus()

        async def async_input(name: str, description: str) -> str:
            return f"async_value_for_{name}"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=async_input,
        )

        assert agent.prompt_for_missing is True
        assert agent.input_callback is async_input

    def test_instantiation_with_custom_requirements(self):
        """Test agent creation with custom env requirements."""
        event_bus = EventBus()
        custom_reqs = [
            EnvRequirement("CUSTOM_API_KEY", "Custom API key", required=True),
            EnvRequirement("OPTIONAL_VAR", "Optional variable", required=False),
        ]

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            env_requirements=custom_reqs,
            use_common_requirements=False,
        )

        assert len(agent.env_requirements) == 2


class TestPromptForSecret:
    """Test the _prompt_for_secret method."""

    @pytest.mark.asyncio
    async def test_sync_callback_invocation(self):
        """Test that sync callback is properly invoked."""
        event_bus = EventBus()
        collected_args = {}

        def sync_input(name: str, description: str) -> str:
            collected_args["name"] = name
            collected_args["description"] = description
            return "test_secret_value"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=sync_input,
        )

        result = await agent._prompt_for_secret("TEST_KEY", "Test description")

        assert result == "test_secret_value"
        assert collected_args["name"] == "TEST_KEY"
        assert collected_args["description"] == "Test description"

    @pytest.mark.asyncio
    async def test_async_callback_invocation(self):
        """Test that async callback is properly awaited."""
        event_bus = EventBus()
        collected_args = {}

        async def async_input(name: str, description: str) -> str:
            collected_args["name"] = name
            collected_args["description"] = description
            await asyncio.sleep(0.01)  # Simulate async work
            return "async_secret_value"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=async_input,
        )

        result = await agent._prompt_for_secret("ASYNC_KEY", "Async description")

        assert result == "async_secret_value"
        assert collected_args["name"] == "ASYNC_KEY"

    @pytest.mark.asyncio
    async def test_callback_returning_empty_string(self):
        """Test handling of empty string from callback."""
        event_bus = EventBus()

        def empty_input(name: str, description: str) -> str:
            return ""

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=empty_input,
        )

        result = await agent._prompt_for_secret("EMPTY_KEY", "Empty test")

        assert result is None

    @pytest.mark.asyncio
    async def test_callback_exception_handling(self):
        """Test that callback exceptions are handled gracefully."""
        event_bus = EventBus()

        def failing_input(name: str, description: str) -> str:
            raise ValueError("User cancelled")

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=failing_input,
        )

        result = await agent._prompt_for_secret("FAIL_KEY", "Fail test")

        assert result is None


class TestPromptForMissingSecrets:
    """Test the _prompt_for_missing_secrets method."""

    @pytest.mark.asyncio
    async def test_prompts_only_required_secrets(self):
        """Test that only required missing secrets are prompted."""
        event_bus = EventBus()
        prompted_secrets = []

        def track_input(name: str, description: str) -> str:
            prompted_secrets.append(name)
            return f"value_for_{name}"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=track_input,
            use_common_requirements=False,
        )

        report = {
            "missing": [
                {"name": "REQUIRED_KEY", "description": "Required", "required": True},
                {"name": "OPTIONAL_KEY", "description": "Optional", "required": False},
            ]
        }

        await agent._prompt_for_missing_secrets(report)

        assert "REQUIRED_KEY" in prompted_secrets
        assert "OPTIONAL_KEY" not in prompted_secrets

    @pytest.mark.asyncio
    async def test_stores_collected_secrets_in_environ(self):
        """Test that collected secrets are stored in os.environ."""
        event_bus = EventBus()
        test_key = "TEST_ENV_STORE_KEY"

        # Ensure key doesn't exist
        if test_key in os.environ:
            del os.environ[test_key]

        def provide_secret(name: str, description: str) -> str:
            return "stored_secret_value"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=provide_secret,
            use_common_requirements=False,
        )

        report = {
            "missing": [
                {"name": test_key, "description": "Test key", "required": True},
            ]
        }

        await agent._prompt_for_missing_secrets(report)

        assert os.environ.get(test_key) == "stored_secret_value"

        # Cleanup
        del os.environ[test_key]

    @pytest.mark.asyncio
    async def test_skipped_secrets_not_stored(self):
        """Test that skipped (None) secrets are not stored."""
        event_bus = EventBus()
        test_key = "TEST_SKIP_KEY"

        # Ensure key doesn't exist
        if test_key in os.environ:
            del os.environ[test_key]

        def skip_secret(name: str, description: str) -> str:
            return ""  # Empty = skip

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=skip_secret,
            use_common_requirements=False,
        )

        report = {
            "missing": [
                {"name": test_key, "description": "Skip key", "required": True},
            ]
        }

        await agent._prompt_for_missing_secrets(report)

        assert test_key not in os.environ


class TestActMethod:
    """Test the act() method with prompting integration."""

    @pytest.mark.asyncio
    async def test_act_without_prompting(self):
        """Test act() when prompting is disabled."""
        event_bus = EventBus()
        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=False,
            use_common_requirements=False,
            env_requirements=[
                EnvRequirement("MISSING_KEY", "Missing", required=True),
            ],
        )

        result = await agent.act([])

        assert result is not None
        assert result.type == EventType.ENV_REPORT_COMPLETE
        assert result.success is False  # Missing required

    @pytest.mark.asyncio
    async def test_act_with_prompting_collects_secrets(self):
        """Test act() prompts and collects secrets when enabled."""
        event_bus = EventBus()
        test_key = "ACT_TEST_KEY"

        # Ensure key doesn't exist initially
        if test_key in os.environ:
            del os.environ[test_key]

        def provide_secret(name: str, description: str) -> str:
            return "collected_value"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=provide_secret,
            use_common_requirements=False,
            env_requirements=[
                EnvRequirement(test_key, "Test key for act", required=True),
            ],
        )

        result = await agent.act([])

        assert result is not None
        assert result.type == EventType.ENV_REPORT_COMPLETE
        # After prompting, the secret should be collected
        assert os.environ.get(test_key) == "collected_value"
        assert result.success is True  # Now configured

        # Cleanup
        del os.environ[test_key]


class TestAutoGen04Compatibility:
    """Test AutoGen 0.4 pattern compatibility."""

    @pytest.mark.asyncio
    async def test_autogen_style_sync_callback(self):
        """Test AutoGen 0.4 style sync input function."""
        event_bus = EventBus()

        # AutoGen 0.4 pattern: simple sync function
        def user_input_func(name: str, description: str) -> str:
            """Simple input function like AutoGen's input_func."""
            return f"user_provided_{name}"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=user_input_func,
        )

        result = await agent._prompt_for_secret("API_KEY", "API key description")
        assert result == "user_provided_API_KEY"

    @pytest.mark.asyncio
    async def test_autogen_style_async_callback(self):
        """Test AutoGen 0.4 style async input function."""
        event_bus = EventBus()

        # AutoGen 0.4 pattern: async function (like UserProxyAgent's async input_func)
        async def async_user_input(name: str, description: str) -> str:
            """Async input function like AutoGen's async input_func."""
            # In real usage, this might await websocket.receive_json() etc.
            await asyncio.sleep(0.001)
            return f"async_user_provided_{name}"

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=async_user_input,
        )

        result = await agent._prompt_for_secret("ASYNC_KEY", "Async key description")
        assert result == "async_user_provided_ASYNC_KEY"

    @pytest.mark.asyncio
    async def test_autogen_asyncio_to_thread_pattern(self):
        """Test the asyncio.to_thread pattern from AutoGen 0.4."""
        event_bus = EventBus()

        # This simulates the AutoGen 0.4 pattern of wrapping sync input
        # with asyncio.to_thread for non-blocking operation
        def blocking_input(name: str, description: str) -> str:
            """Simulates blocking input() call."""
            return f"blocking_result_{name}"

        async def wrapped_input(name: str, description: str) -> str:
            """Wrapper using asyncio.to_thread like AutoGen does."""
            return await asyncio.to_thread(blocking_input, name, description)

        agent = EnvironmentReportAgent(
            event_bus=event_bus,
            prompt_for_missing=True,
            input_callback=wrapped_input,
        )

        result = await agent._prompt_for_secret("THREAD_KEY", "Thread test")
        assert result == "blocking_result_THREAD_KEY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
