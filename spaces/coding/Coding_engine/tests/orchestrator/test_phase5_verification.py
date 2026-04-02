"""
Unit tests for Phase 5: Autonomous Verification.

Tests the phase_verification function which checks that all
quality criteria are met before proceeding to user review.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult, phase_verification


# ============================================================================
# P5-U01: Test project exists
# ============================================================================

@pytest.mark.asyncio
async def test_project_exists(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that existing project directory is detected."""
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    
    assert result.phase == "verification"
    assert result.data.get("project_exists") is True


# ============================================================================
# P5-U02: Test project missing
# ============================================================================

@pytest.mark.asyncio
async def test_project_missing(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when project directory doesn't exist."""
    non_existent = tmp_path / "nonexistent-project"
    
    result = await phase_verification(orchestrator_config, str(non_existent))
    
    assert result.success is False
    assert result.phase == "verification"
    assert "does not exist" in result.message.lower() or result.data.get("project_exists") is False


# ============================================================================
# P5-U03: Test package.json found
# ============================================================================

@pytest.mark.asyncio
async def test_package_json_found(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that package.json is detected."""
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    
    assert result.phase == "verification"
    assert result.data.get("has_package_json_or_requirements") is True


# ============================================================================
# P5-U04: Test requirements.txt found
# ============================================================================

@pytest.mark.asyncio
async def test_requirements_txt_found(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that requirements.txt is detected for Python projects."""
    # Create project with requirements.txt instead of package.json
    project = tmp_path / "python-project"
    project.mkdir()
    (project / "requirements.txt").write_text("flask==2.0.0\n")
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("print('hello')")
    
    result = await phase_verification(orchestrator_config, str(project))
    
    assert result.phase == "verification"
    assert result.data.get("has_package_json_or_requirements") is True


# ============================================================================
# P5-U05: Test no dependency file
# ============================================================================

@pytest.mark.asyncio
async def test_no_dependency_file(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when no package.json or requirements.txt exists."""
    # Create project without dependency files
    project = tmp_path / "bare-project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "index.ts").write_text("console.log('test')")
    
    result = await phase_verification(orchestrator_config, str(project))
    
    assert result.phase == "verification"
    assert result.data.get("has_package_json_or_requirements") is False


# ============================================================================
# P5-U06: Test source files found
# ============================================================================

@pytest.mark.asyncio
async def test_source_files_found(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that source files are detected."""
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    
    assert result.phase == "verification"
    assert result.data.get("has_source_files") is True


# ============================================================================
# P5-U07: Test no source files
# ============================================================================

@pytest.mark.asyncio
async def test_no_source_files(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test behavior when no source files exist."""
    # Create project with only config files
    project = tmp_path / "empty-project"
    project.mkdir()
    (project / "package.json").write_text('{"name": "test"}')
    (project / "README.md").write_text("# Empty Project")
    
    result = await phase_verification(orchestrator_config, str(project))
    
    assert result.phase == "verification"
    assert result.data.get("has_source_files") is False


# ============================================================================
# P5-U08: Test build artifacts exist
# ============================================================================

@pytest.mark.asyncio
async def test_build_artifacts_exist(
    orchestrator_config: OrchestratorConfig,
    mock_project_with_build: Path,
):
    """Test that build artifacts (node_modules, dist) are detected."""
    result = await phase_verification(orchestrator_config, str(mock_project_with_build))
    
    assert result.phase == "verification"
    assert result.data.get("build_artifacts_exist") is True


# ============================================================================
# P5-U09: Test overall success criteria
# ============================================================================

@pytest.mark.asyncio
async def test_overall_success_criteria(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that overall success requires project + source files."""
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    
    # Success requires: project_exists AND has_source_files
    assert result.success is True
    assert result.phase == "verification"
    assert result.data.get("project_exists") is True
    assert result.data.get("has_source_files") is True


# ============================================================================
# Additional Tests
# ============================================================================

@pytest.mark.asyncio
async def test_verification_with_all_criteria(
    orchestrator_config: OrchestratorConfig,
    mock_project_with_build: Path,
):
    """Test verification with all criteria met."""
    result = await phase_verification(orchestrator_config, str(mock_project_with_build))
    
    assert result.success is True
    assert result.phase == "verification"
    assert result.data.get("project_exists") is True
    assert result.data.get("has_package_json_or_requirements") is True
    assert result.data.get("has_source_files") is True
    assert result.data.get("build_artifacts_exist") is True


@pytest.mark.asyncio
async def test_verification_fails_without_source_files(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that verification fails when source files are missing."""
    # Create project without source files
    project = tmp_path / "no-source-project"
    project.mkdir()
    (project / "package.json").write_text('{"name": "test"}')
    
    result = await phase_verification(orchestrator_config, str(project))
    
    # Should fail because has_source_files is required
    assert result.success is False
    assert result.phase == "verification"


@pytest.mark.asyncio
async def test_verification_detects_various_file_types(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that various source file types are detected."""
    project = tmp_path / "multi-lang-project"
    project.mkdir()
    src = project / "src"
    src.mkdir()
    
    # Create various source files
    (src / "index.ts").write_text("// ts file")
    (src / "App.tsx").write_text("// tsx file")
    (src / "utils.js").write_text("// js file")
    (src / "Component.jsx").write_text("// jsx file")
    (src / "main.py").write_text("# py file")
    (src / "Page.vue").write_text("<!-- vue file -->")
    (src / "Component.svelte").write_text("<!-- svelte file -->")
    
    result = await phase_verification(orchestrator_config, str(project))
    
    assert result.data.get("has_source_files") is True


@pytest.mark.asyncio
async def test_verification_detects_nested_source_files(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that source files in nested directories are detected."""
    project = tmp_path / "nested-project"
    project.mkdir()
    
    # Create deeply nested source file
    nested = project / "src" / "components" / "ui" / "buttons"
    nested.mkdir(parents=True)
    (nested / "Button.tsx").write_text("export const Button = () => {}")
    
    result = await phase_verification(orchestrator_config, str(project))
    
    assert result.data.get("has_source_files") is True


@pytest.mark.asyncio
async def test_verification_message_format(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that verification message is properly formatted."""
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    
    assert isinstance(result.message, str)
    assert len(result.message) > 0
    assert "verification" in result.message.lower() or "complete" in result.message.lower()


@pytest.mark.asyncio
async def test_verification_data_structure(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that verification data has correct structure."""
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    
    required_keys = [
        "project_exists",
        "has_package_json_or_requirements",
        "has_source_files",
        "build_artifacts_exist",
    ]
    
    for key in required_keys:
        assert key in result.data
        assert isinstance(result.data[key], bool)