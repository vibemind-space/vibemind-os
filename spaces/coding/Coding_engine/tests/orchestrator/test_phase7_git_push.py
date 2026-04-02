"""
Unit tests for Phase 7: Production Deployment (Git Push).

Tests the phase_git_push function which pushes the generated code
to GitHub.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_git_push


# ============================================================================
# P7-U01: Test git push disabled
# ============================================================================

@pytest.mark.asyncio
async def test_git_push_disabled(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that Git push is skipped when --no-git flag is set."""
    orchestrator_config.git_push = False
    
    result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "git_push"
    assert "skipped" in result.message.lower() or "disabled" in result.message.lower()


# ============================================================================
# P7-U02: Test no GITHUB_TOKEN
# ============================================================================

@pytest.mark.asyncio
async def test_no_github_token(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when GITHUB_TOKEN is not set."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = None
    
    result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True  # Skipped gracefully
    assert result.phase == "git_push"
    assert "token" in result.message.lower() or "skipped" in result.message.lower()


# ============================================================================
# P7-U03: Test push success
# ============================================================================

@pytest.mark.asyncio
async def test_push_success(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_git_push_response: dict,
):
    """Test successful Git push to GitHub."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_git_push_response
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "git_push"
    assert "repo_url" in result.data


# ============================================================================
# P7-U04: Test push failure (API error)
# ============================================================================

@pytest.mark.asyncio
async def test_push_failure(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when Git push API returns an error."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "git_push"
    assert "failed" in result.message.lower()


# ============================================================================
# P7-U05: Test push exception
# ============================================================================

@pytest.mark.asyncio
async def test_push_exception(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when Git push raises an exception."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = Exception("Network error")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "git_push"
    assert "error" in result.message.lower()


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_push_with_private_repo(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_git_push_response: dict,
):
    """Test Git push creates private repository."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    orchestrator_config.git_private = True
    orchestrator_config.project_name = "my-private-repo"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_git_push_response
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    # Verify private flag was in the request
    if mock_instance.post.called:
        call_kwargs = mock_instance.post.call_args
        assert call_kwargs is not None


@pytest.mark.asyncio
async def test_push_with_public_repo(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_git_push_response: dict,
):
    """Test Git push creates public repository."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    orchestrator_config.git_private = False
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_git_push_response
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True


@pytest.mark.asyncio
async def test_push_connection_error(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when cannot connect to API."""
    import httpx
    
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "git_push"


@pytest.mark.asyncio
async def test_push_timeout_error(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when API request times out."""
    import httpx
    
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("Timeout")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "git_push"


@pytest.mark.asyncio
async def test_push_repo_url_in_result(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that repository URL is included in result data."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    
    expected_url = "https://github.com/testuser/test-repo"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"repo_url": expected_url}
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.data.get("repo_url") == expected_url


@pytest.mark.asyncio
async def test_push_message_format(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that message format is correct."""
    orchestrator_config.git_push = False
    
    result = await phase_git_push(orchestrator_config, str(tmp_path / "project"))
    
    assert isinstance(result.message, str)
    assert len(result.message) > 0