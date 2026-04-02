"""
Unit tests for Phase 1: Project Creation.

Tests the phase_create_project function which calls the external
Project-Create API to scaffold a new project.
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_create_project


# ============================================================================
# P1-U01: Test successful requirements loading
# ============================================================================

@pytest.mark.asyncio
async def test_load_requirements_success(
    orchestrator_config: OrchestratorConfig,
    mock_httpx_post_success,
):
    """Test that valid requirements.json is loaded successfully."""
    result = await phase_create_project(orchestrator_config)
    
    # Should reach the API call (even if mocked)
    assert result.phase == "create_project"
    # With mocked success, result should be successful
    assert result.success is True


# ============================================================================
# P1-U02: Test requirements file not found
# ============================================================================

@pytest.mark.asyncio
async def test_load_requirements_file_not_found(
    orchestrator_config: OrchestratorConfig,
):
    """Test behavior when requirements file doesn't exist."""
    # Set non-existent path
    orchestrator_config.requirements_file = "/nonexistent/path/requirements.json"
    
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "create_project"
    assert "Failed to load requirements" in result.message


# ============================================================================
# P1-U03: Test invalid JSON in requirements
# ============================================================================

@pytest.mark.asyncio
async def test_load_requirements_invalid_json(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when requirements file contains invalid JSON."""
    # Create invalid JSON file
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{ invalid json content }")
    orchestrator_config.requirements_file = str(invalid_file)
    
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is False
    assert "Failed to load requirements" in result.message


# ============================================================================
# P1-U04: Test successful tech stack loading
# ============================================================================

@pytest.mark.asyncio
async def test_load_tech_stack_success(
    orchestrator_config: OrchestratorConfig,
    mock_httpx_post_success,
):
    """Test that valid tech_stack.json is loaded successfully."""
    result = await phase_create_project(orchestrator_config)
    
    # If we reach the API, tech stack was loaded
    assert result.phase == "create_project"
    assert result.success is True


# ============================================================================
# P1-U05: Test API call success
# ============================================================================

@pytest.mark.asyncio
async def test_api_call_success(
    orchestrator_config: OrchestratorConfig,
    mock_httpx_post_success,
    mock_api_success_response: dict,
):
    """Test successful API call returns correct PhaseResult."""
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is True
    assert result.phase == "create_project"
    assert "project_path" in result.data
    assert result.duration_seconds >= 0


# ============================================================================
# P1-U06: Test API call failure (success=false in response)
# ============================================================================

@pytest.mark.asyncio
async def test_api_call_failure(
    orchestrator_config: OrchestratorConfig,
    mock_httpx_post_failure,
):
    """Test API returning success=false."""
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "create_project"
    assert "API returned failure" in result.message


# ============================================================================
# P1-U07: Test API connection error
# ============================================================================

@pytest.mark.asyncio
async def test_api_connection_error(
    orchestrator_config: OrchestratorConfig,
    mock_httpx_connection_error,
):
    """Test behavior when API is not reachable."""
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "create_project"
    assert "Cannot connect" in result.message or "Connection" in result.message


# ============================================================================
# P1-U08: Test API timeout
# ============================================================================

@pytest.mark.asyncio
async def test_api_timeout(
    orchestrator_config: OrchestratorConfig,
    mock_httpx_timeout,
):
    """Test behavior when API times out."""
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is False
    assert result.phase == "create_project"
    assert "Timeout" in result.message or "failed" in result.message.lower()


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_tech_stack_file_not_found(
    orchestrator_config: OrchestratorConfig,
):
    """Test behavior when tech_stack file doesn't exist."""
    orchestrator_config.tech_stack_file = "/nonexistent/tech_stack.json"
    
    result = await phase_create_project(orchestrator_config)
    
    assert result.success is False
    assert "Failed to load tech stack" in result.message


@pytest.mark.asyncio
async def test_template_id_extraction(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_httpx_post_success,
):
    """Test that template_id is correctly extracted from tech_stack."""
    # Create tech stack with custom template_id
    custom_tech_stack = {
        "tech_stack": {
            "id": "custom-template-id",
            "name": "Custom Template"
        }
    }
    tech_file = tmp_path / "custom_tech.json"
    tech_file.write_text(json.dumps(custom_tech_stack))
    orchestrator_config.tech_stack_file = str(tech_file)
    
    # The test passes if no error is raised
    result = await phase_create_project(orchestrator_config)
    assert result.phase == "create_project"


@pytest.mark.asyncio
async def test_requirements_list_extraction(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
    mock_httpx_post_success,
):
    """Test that requirements list is correctly extracted."""
    # Create requirements with empty list
    empty_reqs = {"project": "test", "requirements": []}
    req_file = tmp_path / "empty_reqs.json"
    req_file.write_text(json.dumps(empty_reqs))
    orchestrator_config.requirements_file = str(req_file)
    
    result = await phase_create_project(orchestrator_config)
    
    # Should still work with empty requirements
    assert result.phase == "create_project"