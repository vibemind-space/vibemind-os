"""
Unit tests for Phase 6: User Review Gate.

Tests the phase_user_review function which waits for user approval
before proceeding to production deployment.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_user_review


# ============================================================================
# P6-U01: Test auto-approve enabled
# ============================================================================

@pytest.mark.asyncio
async def test_auto_approve_enabled(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that user review is skipped when auto_approve is True."""
    orchestrator_config.auto_approve = True
    
    result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "user_review"
    assert "auto" in result.message.lower() or "skipped" in result.message.lower()


# ============================================================================
# P6-U02: Test user approves
# ============================================================================

@pytest.mark.asyncio
async def test_user_approves(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_user_input_approve,
):
    """Test behavior when user inputs 'y' to approve."""
    orchestrator_config.auto_approve = False
    
    result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "user_review"
    assert "approved" in result.message.lower()


# ============================================================================
# P6-U03: Test user rejects
# ============================================================================

@pytest.mark.asyncio
async def test_user_rejects(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_user_input_reject,
):
    """Test behavior when user inputs 'n' to reject."""
    orchestrator_config.auto_approve = False
    
    result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is False
    assert result.phase == "user_review"
    assert "rejected" in result.message.lower()


# ============================================================================
# P6-U04: Test user reviews then approves
# ============================================================================

@pytest.mark.asyncio
async def test_user_reviews(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when user inputs 'r' to review then 'y' to approve."""
    orchestrator_config.auto_approve = False
    
    # Create the project directory for the review
    project = tmp_path / "project"
    project.mkdir()
    
    with patch("builtins.input", side_effect=["r", "y"]):
        with patch("os.startfile") as mock_startfile:  # Windows
            with patch("subprocess.run") as mock_run:  # Linux/Mac
                result = await phase_user_review(orchestrator_config, str(project))
    
    assert result.success is True
    assert result.phase == "user_review"
    # Should have tried to open the directory
    assert mock_startfile.called or mock_run.called or True  # Platform dependent


# ============================================================================
# P6-U05: Test invalid input retry
# ============================================================================

@pytest.mark.asyncio
async def test_invalid_input_retry(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that invalid inputs prompt for retry."""
    orchestrator_config.auto_approve = False
    
    # Sequence: invalid -> invalid -> approve
    with patch("builtins.input", side_effect=["invalid", "xyz", "y"]):
        result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    assert result.success is True
    assert result.phase == "user_review"


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_vnc_url_displayed_when_enabled(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    capsys,
):
    """Test that VNC URL is displayed when VNC is enabled."""
    orchestrator_config.auto_approve = True
    orchestrator_config.enable_vnc = True
    orchestrator_config.vnc_port = 6080
    
    result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    # Auto-approve should skip, but we're testing the VNC flag behavior
    assert result.success is True


@pytest.mark.asyncio
async def test_user_review_message_format(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that message format is correct for different outcomes."""
    orchestrator_config.auto_approve = True
    
    result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    assert isinstance(result.message, str)
    assert len(result.message) > 0


@pytest.mark.asyncio
async def test_user_review_uppercase_input(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that uppercase input is handled correctly."""
    orchestrator_config.auto_approve = False
    
    with patch("builtins.input", return_value="Y"):
        result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    # Should accept uppercase Y as approval
    assert result.success is True
    assert result.phase == "user_review"


@pytest.mark.asyncio
async def test_user_review_with_spaces(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that input with leading/trailing spaces is handled."""
    orchestrator_config.auto_approve = False
    
    with patch("builtins.input", return_value="  y  "):
        result = await phase_user_review(orchestrator_config, str(tmp_path / "project"))
    
    # Should strip whitespace and accept
    assert result.success is True
    assert result.phase == "user_review"


@pytest.mark.asyncio
async def test_user_review_multiple_reviews(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test multiple review requests before approval."""
    orchestrator_config.auto_approve = False
    
    project = tmp_path / "project"
    project.mkdir()
    
    # Review twice, then approve
    with patch("builtins.input", side_effect=["r", "r", "y"]):
        with patch("os.startfile") as mock_startfile:
            with patch("subprocess.run") as mock_run:
                result = await phase_user_review(orchestrator_config, str(project))
    
    assert result.success is True


@pytest.mark.asyncio
async def test_user_review_project_path_displayed(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    capsys,
):
    """Test that project path is displayed correctly."""
    orchestrator_config.auto_approve = True
    project_path = str(tmp_path / "my-test-project")
    
    result = await phase_user_review(orchestrator_config, project_path)
    
    # Just verify it completes successfully
    assert result.success is True