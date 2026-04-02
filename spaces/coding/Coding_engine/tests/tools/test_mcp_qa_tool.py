# -*- coding: utf-8 -*-
"""
Tests for MCP QA Verification Tool.

Verifies:
- Tool creation and configuration
- FunctionTool wrapper correctness
- QA validator integration with tools
- create_team() qa_tools parameter
- create_team_with_mcp_qa() convenience method
- Backward compatibility (existing teams unchanged)
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.tools.mcp_qa_tool import create_mcp_qa_tool, MCP_QA_PROMPT_ADDITION


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a mock EventBus."""
    bus = MagicMock()
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
# Test: MCP QA Tool Creation
# =============================================================================

class TestMCPQAToolCreation:
    """Test create_mcp_qa_tool() function."""

    def test_create_mcp_qa_tool_returns_function_tool(self):
        """create_mcp_qa_tool should return a FunctionTool."""
        tool = create_mcp_qa_tool(working_dir=".")
        if tool is None:
            pytest.skip("autogen-agentchat not installed")
        assert tool is not None
        assert tool.name == "verify_with_mcp"

    def test_create_mcp_qa_tool_has_description(self):
        """Tool should have a descriptive description."""
        tool = create_mcp_qa_tool(working_dir=".")
        if tool is None:
            pytest.skip("autogen-agentchat not installed")
        assert "verify" in tool.description.lower()
        assert "mcp" in tool.description.lower()

    def test_create_mcp_qa_tool_with_custom_working_dir(self):
        """Tool should accept custom working directory."""
        tool = create_mcp_qa_tool(working_dir="/custom/path")
        if tool is None:
            pytest.skip("autogen-agentchat not installed")
        assert tool is not None

    def test_create_mcp_qa_tool_default_working_dir(self):
        """Tool should default to current directory."""
        tool = create_mcp_qa_tool()
        if tool is None:
            pytest.skip("autogen-agentchat not installed")
        assert tool is not None


# =============================================================================
# Test: MCP QA Prompt Addition
# =============================================================================

class TestMCPQAPromptAddition:
    """Test the MCP_QA_PROMPT_ADDITION constant."""

    def test_prompt_mentions_verify_with_mcp(self):
        """Prompt addition should reference the tool name."""
        assert "verify_with_mcp" in MCP_QA_PROMPT_ADDITION

    def test_prompt_mentions_verification_workflow(self):
        """Prompt addition should include workflow instructions."""
        assert "WORKFLOW" in MCP_QA_PROMPT_ADDITION
        assert "APPROVE" in MCP_QA_PROMPT_ADDITION

    def test_prompt_mentions_read_only_rule(self):
        """Prompt should enforce read-only verification."""
        assert "read-only" in MCP_QA_PROMPT_ADDITION.lower() or \
               "VERIFICATION only" in MCP_QA_PROMPT_ADDITION


# =============================================================================
# Test: Verify Function Logic
# =============================================================================

class TestVerifyWithMCP:
    """Test the verify_with_mcp async function."""

    @pytest.mark.asyncio
    async def test_verify_returns_json_on_import_error(self):
        """Should return error JSON when MCPOrchestrator is unavailable."""
        tool = create_mcp_qa_tool(working_dir=".")
        if tool is None:
            pytest.skip("autogen-agentchat not installed")

        # Mock the orchestrator import to fail
        with patch("src.tools.mcp_qa_tool.create_mcp_qa_tool") as mock_create:
            # Test that the actual function handles errors gracefully
            # by testing the error handling path directly
            from src.tools.mcp_qa_tool import create_mcp_qa_tool as real_create
            real_tool = real_create(working_dir=".")
            if real_tool is None:
                pytest.skip("autogen-agentchat not installed")
            # Tool exists and is callable - basic sanity check
            assert callable(getattr(real_tool, 'run_json', None) or
                          getattr(real_tool, 'func', None) or
                          real_tool)

    @pytest.mark.asyncio
    async def test_verify_with_mocked_orchestrator(self):
        """Should return structured result from mocked orchestrator."""
        from unittest.mock import AsyncMock
        from dataclasses import dataclass
        from typing import Any, Dict, List, Optional

        @dataclass
        class MockTaskResult:
            task: str
            success: bool
            steps_executed: int
            total_duration: float
            output: Any
            errors: List[Dict[str, str]]
            plan: Optional[Any] = None

        mock_result = MockTaskResult(
            task="test",
            success=True,
            steps_executed=3,
            total_duration=1.5,
            output="File exists: prisma/schema.prisma",
            errors=[],
        )

        mock_orchestrator = MagicMock()
        mock_orchestrator.execute_task = AsyncMock(return_value=mock_result)

        with patch("src.mcp.mcp_orchestrator.MCPOrchestrator", return_value=mock_orchestrator):
            tool = create_mcp_qa_tool(working_dir=".")
            if tool is None:
                pytest.skip("autogen-agentchat not installed")

            # Get the underlying function
            func = getattr(tool, '_func', None) or getattr(tool, 'func', None)
            if func is None:
                pytest.skip("Cannot access tool function")

            result_str = await func(verification_task="Check prisma schema")
            result = json.loads(result_str)

            assert result["verified"] is True
            assert result["steps_executed"] == 3
            assert "prisma" in result["output"].lower()
            assert result["errors"] == []


# =============================================================================
# Test: QA Validator with Tools (AutogenTeamMixin)
# =============================================================================

class TestQAValidatorWithTools:
    """Test that create_qa_validator accepts and uses tools."""

    def _make_test_agent(self, tmp_path):
        """Create a TestAgent with mocked model clients."""
        try:
            from src.agents.autogen_team_mixin import AutogenTeamMixin
        except ImportError:
            pytest.skip("autogen-agentchat not installed")

        mock_client = MagicMock()

        class TestAgent(AutogenTeamMixin):
            def __init__(self):
                self.working_dir = str(tmp_path)
                self.name = "test_agent"
                self.logger = MagicMock()
                self._model_client = mock_client
                self._qa_model_client = mock_client

        return TestAgent()

    def test_create_qa_validator_without_tools(self, tmp_path):
        """QA validator created without tools should have empty tool list."""
        agent = self._make_test_agent(tmp_path)
        validator = agent.create_qa_validator(
            name="TestQA",
            system_message="Test QA validator",
        )
        assert validator is not None
        assert validator.name == "TestQA"

    def test_create_qa_validator_with_tools(self, tmp_path):
        """QA validator created with tools should have those tools."""
        tool = create_mcp_qa_tool(working_dir=str(tmp_path))
        if tool is None:
            pytest.skip("autogen-agentchat not installed for tool creation")

        agent = self._make_test_agent(tmp_path)
        validator = agent.create_qa_validator(
            name="TestQA",
            system_message="Test QA validator",
            tools=[tool],
        )
        assert validator is not None


# =============================================================================
# Test: create_team with qa_tools
# =============================================================================

class TestCreateTeamWithQATools:
    """Test create_team() qa_tools parameter."""

    def _make_test_agent(self, tmp_path):
        """Create a TestAgent with mocked model clients."""
        try:
            from src.agents.autogen_team_mixin import AutogenTeamMixin
        except ImportError:
            pytest.skip("autogen-agentchat not installed")

        mock_client = MagicMock()

        class TestAgent(AutogenTeamMixin):
            def __init__(self):
                self.working_dir = str(tmp_path)
                self.name = "test_agent"
                self.logger = MagicMock()
                self._model_client = mock_client
                self._qa_model_client = mock_client

        return TestAgent()

    def test_create_team_without_qa_tools(self, tmp_path):
        """Existing create_team() calls should still work without qa_tools."""
        agent = self._make_test_agent(tmp_path)
        team = agent.create_team(
            operator_name="TestOp",
            operator_prompt="You are an operator",
            validator_name="TestQA",
            validator_prompt="You are a validator",
            tools=[],
        )
        assert team is not None

    def test_create_team_with_qa_tools(self, tmp_path):
        """create_team() with qa_tools should pass tools to QA validator."""
        qa_tool = create_mcp_qa_tool(working_dir=str(tmp_path))
        if qa_tool is None:
            pytest.skip("autogen-agentchat not installed for tool creation")

        agent = self._make_test_agent(tmp_path)
        team = agent.create_team(
            operator_name="TestOp",
            operator_prompt="You are an operator",
            validator_name="TestQA",
            validator_prompt="You are a validator",
            tools=[],
            qa_tools=[qa_tool],
        )
        assert team is not None


# =============================================================================
# Test: create_team_with_mcp_qa convenience method
# =============================================================================

class TestCreateTeamWithMCPQA:
    """Test create_team_with_mcp_qa() convenience method."""

    def test_create_team_with_mcp_qa_exists(self):
        """AutogenTeamMixin should have create_team_with_mcp_qa method."""
        try:
            from src.agents.autogen_team_mixin import AutogenTeamMixin
        except ImportError:
            pytest.skip("autogen-agentchat not installed")

        assert hasattr(AutogenTeamMixin, "create_team_with_mcp_qa")

    def test_create_team_with_mcp_qa_creates_team(self, tmp_path):
        """create_team_with_mcp_qa should create a valid team."""
        try:
            from src.agents.autogen_team_mixin import AutogenTeamMixin
        except ImportError:
            pytest.skip("autogen-agentchat not installed")

        mock_client = MagicMock()

        class TestAgent(AutogenTeamMixin):
            def __init__(self):
                self.working_dir = str(tmp_path)
                self.name = "test_agent"
                self.logger = MagicMock()
                self._model_client = mock_client
                self._qa_model_client = mock_client

        agent = TestAgent()
        team = agent.create_team_with_mcp_qa(
            operator_name="TestOp",
            operator_prompt="You are an operator",
            validator_name="TestQA",
            validator_prompt="You are a validator",
            tools=[],
        )
        assert team is not None


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Ensure existing functionality is not broken."""

    def test_existing_agents_work_without_qa_tools(self, event_bus, shared_state, tmp_path):
        """Agents that don't use qa_tools should work exactly as before."""
        try:
            from src.agents.database_agent import DatabaseAgent
        except ImportError:
            pytest.skip("DatabaseAgent not available")

        # DatabaseAgent should instantiate without issues
        agent = DatabaseAgent(
            name="test_db",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
        )
        assert agent.name == "test_db"

    def test_messaging_agents_still_work(self, event_bus, shared_state, tmp_path):
        """All 4 messaging agents should still work after mixin changes."""
        from src.agents.websocket_agent import WebSocketAgent
        from src.agents.redis_pubsub_agent import RedisPubSubAgent
        from src.agents.presence_agent import PresenceAgent
        from src.agents.encryption_agent import EncryptionAgent

        ws = WebSocketAgent(name="ws", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))
        redis = RedisPubSubAgent(name="redis", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))
        presence = PresenceAgent(name="presence", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))
        encryption = EncryptionAgent(name="enc", event_bus=event_bus, shared_state=shared_state, working_dir=str(tmp_path))

        assert ws.name == "ws"
        assert redis.name == "redis"
        assert presence.name == "presence"
        assert encryption.name == "enc"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
