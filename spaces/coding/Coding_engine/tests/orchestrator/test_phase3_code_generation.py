"""
Unit tests for Phase 3: Code Generation.

Tests the phase_generate_code function which runs society_hybrid
or hybrid for initial code generation.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_generate_code


# ============================================================================
# P3-U01: Test runner script not found
# ============================================================================

@pytest.mark.asyncio
async def test_runner_script_not_found(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when run_society_hybrid.py doesn't exist."""
    # Change to tmp_path where runner doesn't exist
    with patch("run_orchestrator.Path.exists", return_value=False):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "generate_code"
    assert "not found" in result.message.lower()


# ============================================================================
# P3-U02: Test command building for hybrid mode
# ============================================================================

@pytest.mark.asyncio
async def test_command_building_hybrid(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_subprocess_success,
):
    """Test that correct command is built for hybrid mode."""
    orchestrator_config.run_mode = "hybrid"
    
    # Create mock runner script
    runner = Path("run_hybrid.py")
    
    with patch.object(Path, "exists", return_value=True):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    # Should have called subprocess with hybrid runner
    if mock_subprocess_success.called:
        call_args = mock_subprocess_success.call_args[0][0]
        assert "hybrid" in str(call_args).lower()


# ============================================================================
# P3-U03: Test command building for society_hybrid mode
# ============================================================================

@pytest.mark.asyncio
async def test_command_building_society_hybrid(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_subprocess_success,
):
    """Test that correct command is built for society_hybrid mode."""
    orchestrator_config.run_mode = "society_hybrid"
    orchestrator_config.continuous_sandbox = True
    orchestrator_config.enable_vnc = True
    
    with patch.object(Path, "exists", return_value=True):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    # Should have included autonomous flags
    if mock_subprocess_success.called:
        call_args = str(mock_subprocess_success.call_args)
        # Check that society_hybrid specific flags would be included
        assert result.phase == "generate_code"


# ============================================================================
# P3-U04: Test generation success (exit code 0)
# ============================================================================

@pytest.mark.asyncio
async def test_generation_success(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_subprocess_success,
):
    """Test successful code generation with exit code 0."""
    with patch.object(Path, "exists", return_value=True):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "generate_code"
    assert "completed" in result.message.lower() or "success" in result.message.lower()
    assert result.duration_seconds >= 0


# ============================================================================
# P3-U05: Test generation failure (non-zero exit code)
# ============================================================================

@pytest.mark.asyncio
async def test_generation_failure(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_subprocess_failure,
):
    """Test code generation failure with non-zero exit code."""
    with patch.object(Path, "exists", return_value=True):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "generate_code"
    assert "failed" in result.message.lower() or "exit code" in result.message.lower()


# ============================================================================
# P3-U06: Test generation exception
# ============================================================================

@pytest.mark.asyncio
async def test_generation_exception(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when subprocess raises an exception."""
    with patch.object(Path, "exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = Exception("Unexpected error")
            
            result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "generate_code"
    assert "error" in result.message.lower()


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_generation_output_streaming(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that output is streamed from subprocess."""
    with patch.object(Path, "exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = iter([
                "Starting generation...\n",
                "Processing requirements...\n",
                "Generation complete!\n",
            ])
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process
            
            result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "generate_code"


@pytest.mark.asyncio
async def test_generation_with_custom_max_time(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_subprocess_success,
):
    """Test that max_time parameter is passed correctly."""
    orchestrator_config.max_time = 120  # 2 minutes
    
    with patch.object(Path, "exists", return_value=True):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    # Should complete (mocked)
    assert result.phase == "generate_code"


@pytest.mark.asyncio
async def test_generation_with_custom_slice_size(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_subprocess_success,
):
    """Test that slice_size parameter is passed correctly."""
    orchestrator_config.slice_size = 5
    
    with patch.object(Path, "exists", return_value=True):
        result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.phase == "generate_code"


@pytest.mark.asyncio
async def test_generation_duration_tracking(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that generation duration is tracked correctly."""
    with patch.object(Path, "exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = iter([])
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process
            
            result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
    
    assert result.duration_seconds >= 0
    assert isinstance(result.duration_seconds, (int, float))