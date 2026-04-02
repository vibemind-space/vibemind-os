"""
Unit tests for Phase 2: Deployment Infrastructure (Docker).

Tests the phase_start_docker function which manages Docker containers
for the coding engine.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_start_docker


# ============================================================================
# P2-U01: Test skip docker when disabled
# ============================================================================

@pytest.mark.asyncio
async def test_skip_docker_when_disabled(orchestrator_config: OrchestratorConfig):
    """Test that Docker start is skipped when --no-docker flag is set."""
    orchestrator_config.start_docker = False
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is True
    assert result.phase == "start_docker"
    assert "skipped" in result.message.lower()


# ============================================================================
# P2-U02: Test compose file not found
# ============================================================================

@pytest.mark.asyncio
async def test_compose_file_not_found(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when docker-compose.yml is missing."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(tmp_path / "nonexistent")
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "start_docker"
    assert "not found" in result.message.lower()


# ============================================================================
# P2-U03: Test docker-compose up success
# ============================================================================

@pytest.mark.asyncio
async def test_docker_compose_up_success(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_success,
    mock_httpx_health_success,
):
    """Test successful docker-compose up."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is True
    assert result.phase == "start_docker"
    assert "Docker services started" in result.message or "ready" in result.message.lower()


# ============================================================================
# P2-U04: Test docker-compose up failure
# ============================================================================

@pytest.mark.asyncio
async def test_docker_compose_up_failure(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_failure,
):
    """Test behavior when docker-compose up fails."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "start_docker"
    assert "failed" in result.message.lower()


# ============================================================================
# P2-U05: Test health check success
# ============================================================================

@pytest.mark.asyncio
async def test_health_check_success(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_success,
    mock_httpx_health_success,
):
    """Test successful health check after Docker starts."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is True
    assert result.phase == "start_docker"


# ============================================================================
# P2-U06: Test health check timeout
# ============================================================================

@pytest.mark.asyncio
async def test_health_check_timeout(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_success,
):
    """Test behavior when health check times out."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    
    # Mock httpx to always fail (simulating service never becoming ready)
    import httpx
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ConnectError("Connection refused")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        # Also patch asyncio.sleep to speed up test
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await phase_start_docker(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "start_docker"
    assert "ready" in result.message.lower() or "time" in result.message.lower()


# ============================================================================
# P2-U07: Test docker not installed
# ============================================================================

@pytest.mark.asyncio
async def test_docker_not_installed(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_not_found,
):
    """Test behavior when docker-compose is not installed."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "start_docker"
    assert "not found" in result.message.lower() or "docker" in result.message.lower()


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_docker_compose_timeout(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_timeout,
):
    """Test behavior when docker-compose times out."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "start_docker"
    assert "timed" in result.message.lower() or "timeout" in result.message.lower()


@pytest.mark.asyncio
async def test_vnc_url_in_result(
    orchestrator_config: OrchestratorConfig,
    mock_docker_compose_dir: Path,
    mock_subprocess_success,
    mock_httpx_health_success,
):
    """Test that VNC URL is included in result data when enabled."""
    orchestrator_config.start_docker = True
    orchestrator_config.docker_compose_dir = str(mock_docker_compose_dir)
    orchestrator_config.enable_vnc = True
    orchestrator_config.vnc_port = 6080
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is True
    if "vnc_url" in result.data:
        assert "6080" in result.data["vnc_url"]


@pytest.mark.asyncio
async def test_docker_compose_dir_validation(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that docker_compose_dir is properly validated."""
    orchestrator_config.start_docker = True
    
    # Directory exists but no docker-compose.yml
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    orchestrator_config.docker_compose_dir = str(empty_dir)
    
    result = await phase_start_docker(orchestrator_config)
    
    assert result.success is False
    assert "not found" in result.message.lower()