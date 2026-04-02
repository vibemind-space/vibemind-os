"""Tests for LLM Agent Router (Phase 31 Vibe-Coding)."""
import pytest
from unittest.mock import patch, AsyncMock


# --- Keyword Fallback Tests ---

def test_keyword_fallback_debugger():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("fix this error in login.tsx") == "debugger"


def test_keyword_fallback_database():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("update the prisma schema for users") == "database-agent"


def test_keyword_fallback_api():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("create a new REST endpoint for orders") == "api-generator"


def test_keyword_fallback_test():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("run the tests and show failures") == "test-runner"


def test_keyword_fallback_coder_default():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("make the button bigger") == "coder"


def test_keyword_fallback_security():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("audit for security vulnerabilities") == "security-auditor"


def test_keyword_fallback_docker():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("restart the docker containers") == "deployment-agent"


def test_keyword_fallback_reviewer():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("review the code quality") == "code-reviewer"


def test_keyword_fallback_german_error():
    from src.api.routes.vibe import _keyword_fallback
    assert _keyword_fallback("die login seite ist kaputt") == "debugger"


# --- Route to Agent Tests ---

VALID_AGENTS = {
    "coder", "debugger", "database-agent", "api-generator",
    "test-runner", "security-auditor", "deployment-agent",
    "code-reviewer", "planner", "epic-analyzer",
    "architecture-explorer", "external-services",
}


@pytest.mark.asyncio
async def test_route_to_agent_validates_llm_response():
    from src.api.routes.vibe import route_to_agent

    with patch("src.api.routes.vibe._llm_classify", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "debugger"
        result = await route_to_agent("fix this error")
        assert result == "debugger"


@pytest.mark.asyncio
async def test_route_to_agent_invalid_response_falls_back():
    from src.api.routes.vibe import route_to_agent

    with patch("src.api.routes.vibe._llm_classify", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "invalid-agent-name"
        result = await route_to_agent("fix this bug please")
        assert result in VALID_AGENTS
        assert result == "debugger"  # keyword fallback for "fix" + "bug"


@pytest.mark.asyncio
async def test_route_to_agent_llm_failure_uses_keyword():
    from src.api.routes.vibe import route_to_agent

    with patch("src.api.routes.vibe._llm_classify", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("API error")
        result = await route_to_agent("fix this bug please")
        assert result == "debugger"


@pytest.mark.asyncio
async def test_route_to_agent_coder_for_unknown():
    from src.api.routes.vibe import route_to_agent

    with patch("src.api.routes.vibe._llm_classify", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("API error")
        result = await route_to_agent("do something nice")
        assert result == "coder"


# --- History Tests ---

def test_vibe_history_is_list():
    from src.api.routes.vibe import _vibe_history
    assert isinstance(_vibe_history, list)
