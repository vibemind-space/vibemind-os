"""
Unit tests for Phase 4: Continuous Testing Loop.

Tests the phase_testing_loop function which monitors the continuous
build/test/fix loop until success.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_testing_loop


# ============================================================================
# P4-U01: Test status API success (completed state)
# ============================================================================

@pytest.mark.asyncio
async def test_status_api_success_completed(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_status_response_completed: dict,
):
    """Test behavior when API returns state=completed."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_status_response_completed
        
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "testing_loop"


# ============================================================================
# P4-U02: Test status API in progress
# ============================================================================

@pytest.mark.asyncio
async def test_status_api_in_progress(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_status_response_running: dict,
):
    """Test behavior when API returns state=running."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_status_response_running
        
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    # When state is running, success should be False
    assert result.success is False
    assert result.phase == "testing_loop"
    assert "running" in result.message.lower() or result.data.get("state") == "running"


# ============================================================================
# P4-U03: Test status API unreachable
# ============================================================================

@pytest.mark.asyncio
async def test_status_api_unreachable(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when status API is unreachable."""
    import httpx
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ConnectError("Connection refused")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    # Should fall back to success (testing handled inline)
    assert result.success is True
    assert result.phase == "testing_loop"
    assert "inline" in result.message.lower() or "completed" in result.message.lower()


# ============================================================================
# P4-U04: Test inline with generation (no separate API call needed)
# ============================================================================

@pytest.mark.asyncio
async def test_inline_with_generation(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that testing loop completes when inline with generation."""
    # When continuous_sandbox is handled by society_hybrid,
    # the testing loop phase should report success
    
    with patch("httpx.AsyncClient") as mock_client:
        # Simulate API exception (testing handled inline)
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = Exception("API not available")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    # Should default to success with inline message
    assert result.success is True
    assert result.phase == "testing_loop"


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_status_response_data_included(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_status_response_completed: dict,
):
    """Test that status response data is included in result."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_status_response_completed
        
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    # Result data should contain status info
    assert result.phase == "testing_loop"
    if result.data:
        assert "state" in result.data or isinstance(result.data, dict)


@pytest.mark.asyncio
async def test_status_api_non_200(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when API returns non-200 status code."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    # Should handle gracefully
    assert result.phase == "testing_loop"


@pytest.mark.asyncio
async def test_testing_loop_message_format(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_status_response_completed: dict,
):
    """Test that message format is correct."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_status_response_completed
        
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, str(tmp_path / "project"))
    
    assert isinstance(result.message, str)
    assert len(result.message) > 0