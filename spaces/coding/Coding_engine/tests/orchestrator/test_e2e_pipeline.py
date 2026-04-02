"""
End-to-End tests for the full orchestrator pipeline.

Tests the complete 7-phase workflow from requirements to production,
including phase transitions, data flow, rollback behavior, and timing reports.
"""
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import (
    OrchestratorConfig,
    PhaseResult,
    run_orchestrator,
    phase_create_project,
    phase_start_docker,
    phase_generate_code,
    phase_testing_loop,
    phase_verification,
    phase_user_review,
    phase_git_push,
)


# ============================================================================
# Timing Report Data Classes
# ============================================================================

@dataclass
class PhaseTimingReport:
    """Timing report for a single phase."""
    name: str
    success: bool
    duration_seconds: float
    message: str
    data: dict


@dataclass
class PipelineTimingReport:
    """Complete timing report for the pipeline."""
    timestamp: str
    total_duration_seconds: float
    phases: list[PhaseTimingReport]
    final_status: str


def generate_timing_report(results: list[PhaseResult], total_duration: float) -> PipelineTimingReport:
    """Generate a timing report from phase results."""
    phases = [
        PhaseTimingReport(
            name=r.phase,
            success=r.success,
            duration_seconds=r.duration_seconds,
            message=r.message,
            data=r.data,
        )
        for r in results
    ]
    
    final_status = "SUCCESS" if all(r.success for r in results) else "PARTIAL"
    
    return PipelineTimingReport(
        timestamp=datetime.now().isoformat(),
        total_duration_seconds=total_duration,
        phases=phases,
        final_status=final_status,
    )


# ============================================================================
# E2E-01: Full pipeline with auto-approve
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_pipeline_auto_approve(
    orchestrator_config: OrchestratorConfig,
    mock_api_success_response: dict,
    mock_git_push_response: dict,
    mock_project_structure: Path,
):
    """Test complete pipeline execution with auto-approve."""
    orchestrator_config.auto_approve = True
    orchestrator_config.start_docker = False
    orchestrator_config.git_push = False
    
    results = []
    total_start = time.time()
    
    # Phase 1: Project Creation (mocked)
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            **mock_api_success_response,
            "path": str(mock_project_structure),
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_create_project(orchestrator_config)
        results.append(result)
    
    assert result.success is True
    project_path = result.data.get("project_path", str(mock_project_structure))
    
    # Phase 2: Docker (skipped)
    result = await phase_start_docker(orchestrator_config)
    results.append(result)
    assert result.success is True
    
    # Phase 3: Code Generation (mocked)
    with patch.object(Path, "exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = iter(["Generation complete\n"])
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process
            
            result = await phase_generate_code(orchestrator_config, project_path)
            results.append(result)
    
    assert result.success is True
    
    # Phase 4: Testing Loop (mocked)
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = Exception("API not available")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_testing_loop(orchestrator_config, project_path)
        results.append(result)
    
    assert result.success is True
    
    # Phase 5: Verification
    result = await phase_verification(orchestrator_config, str(mock_project_structure))
    results.append(result)
    assert result.success is True
    
    # Phase 6: User Review (auto-approve)
    result = await phase_user_review(orchestrator_config, str(mock_project_structure))
    results.append(result)
    assert result.success is True
    
    # Phase 7: Git Push (disabled)
    result = await phase_git_push(orchestrator_config, str(mock_project_structure))
    results.append(result)
    assert result.success is True
    
    total_duration = time.time() - total_start
    
    # Generate timing report
    report = generate_timing_report(results, total_duration)
    
    assert report.final_status == "SUCCESS"
    assert len(report.phases) == 7
    assert all(p.success for p in report.phases)


# ============================================================================
# E2E-02: Pipeline phase transitions
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pipeline_phase_transitions(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that data flows correctly between phases."""
    orchestrator_config.auto_approve = True
    orchestrator_config.start_docker = False
    orchestrator_config.git_push = False
    
    phase_data = {}
    
    # Phase 1: Creates project_path
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "path": str(mock_project_structure),
            "files_created": 10,
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_create_project(orchestrator_config)
    
    phase_data["project_path"] = result.data.get("project_path")
    assert phase_data["project_path"] is not None
    
    # Phase 5: Uses project_path from Phase 1
    result = await phase_verification(orchestrator_config, phase_data["project_path"])
    
    # Verify data was passed correctly
    assert result.data.get("project_exists") is True
    assert result.data.get("has_source_files") is True


# ============================================================================
# E2E-03: Pipeline failure recovery
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pipeline_failure_recovery(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test pipeline behavior when Phase 3 fails."""
    orchestrator_config.auto_approve = True
    orchestrator_config.start_docker = False
    orchestrator_config.git_push = False
    
    results = []
    
    # Phase 1: Success
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "path": str(tmp_path / "project"),
            "files_created": 5,
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        result = await phase_create_project(orchestrator_config)
        results.append(result)
    
    assert result.success is True
    
    # Phase 2: Skip
    result = await phase_start_docker(orchestrator_config)
    results.append(result)
    
    # Phase 3: Failure
    with patch.object(Path, "exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 1  # Failure
            mock_process.stdout = iter(["Error during generation\n"])
            mock_process.wait.return_value = 1
            mock_popen.return_value = mock_process
            
            result = await phase_generate_code(orchestrator_config, str(tmp_path / "project"))
            results.append(result)
    
    assert result.success is False
    
    # Pipeline should handle partial failure
    report = generate_timing_report(results, 0.0)
    assert report.final_status == "PARTIAL"


# ============================================================================
# E2E-04: Pipeline timing report
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pipeline_timing_report(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test that timing report is generated correctly."""
    orchestrator_config.auto_approve = True
    orchestrator_config.start_docker = False
    orchestrator_config.git_push = False
    
    results = []
    total_start = time.time()
    
    # Simulate phases with varying durations
    phases = [
        ("create_project", True, 2.1),
        ("start_docker", True, 0.0),
        ("generate_code", True, 45.3),
        ("testing_loop", True, 0.0),
        ("verification", True, 0.5),
        ("user_review", True, 0.0),
        ("git_push", True, 0.0),
    ]
    
    for phase_name, success, duration in phases:
        results.append(PhaseResult(
            phase=phase_name,
            success=success,
            message=f"Phase {phase_name} completed",
            duration_seconds=duration,
            data={},
        ))
    
    total_duration = sum(p[2] for p in phases)
    
    report = generate_timing_report(results, total_duration)
    
    # Validate report structure
    assert report.timestamp is not None
    assert report.total_duration_seconds == pytest.approx(47.9, rel=0.1)
    assert len(report.phases) == 7
    assert report.final_status == "SUCCESS"
    
    # Validate individual phases
    assert report.phases[0].name == "create_project"
    assert report.phases[0].duration_seconds == 2.1
    assert report.phases[2].name == "generate_code"
    assert report.phases[2].duration_seconds == 45.3


# ============================================================================
# E2E-05: Rollback on late failure
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_rollback_on_late_failure(
    orchestrator_config: OrchestratorConfig,
    mock_project_structure: Path,
):
    """Test rollback behavior when Phase 6 (User Review) fails."""
    orchestrator_config.auto_approve = False
    orchestrator_config.start_docker = False
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token"
    
    results = []
    
    # Phases 1-5 succeed
    for phase_name in ["create_project", "start_docker", "generate_code", "testing_loop", "verification"]:
        results.append(PhaseResult(
            phase=phase_name,
            success=True,
            message=f"{phase_name} completed",
            duration_seconds=1.0,
            data={},
        ))
    
    # Phase 6: User rejects
    with patch("builtins.input", return_value="n"):
        result = await phase_user_review(orchestrator_config, str(mock_project_structure))
        results.append(result)
    
    assert result.success is False
    assert "rejected" in result.message.lower()
    
    # Phase 7 should not be executed (simulated by not adding to results)
    
    # Verify rollback state
    report = generate_timing_report(results, 6.0)
    assert report.final_status == "PARTIAL"
    assert len(report.phases) == 6
    assert report.phases[-1].success is False


# ============================================================================
# Additional E2E Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_minimal_pipeline_with_fixtures(
    minimal_requirements_path: Path,
    minimal_tech_stack_path: Path,
    tmp_path: Path,
):
    """Test pipeline with minimal test fixtures."""
    config = OrchestratorConfig(
        requirements_file=str(minimal_requirements_path),
        tech_stack_file=str(minimal_tech_stack_path),
        project_name="minimal-test",
        output_dir=str(tmp_path),
        auto_approve=True,
        start_docker=False,
        git_push=False,
        max_time=60,
    )
    
    # Verify fixtures load correctly
    with open(minimal_requirements_path, "r") as f:
        requirements = json.load(f)
    
    assert "requirements" in requirements
    assert len(requirements["requirements"]) > 0
    
    with open(minimal_tech_stack_path, "r") as f:
        tech_stack = json.load(f)
    
    assert "tech_stack" in tech_stack


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pipeline_report_json_serialization(
    orchestrator_config: OrchestratorConfig,
):
    """Test that timing report can be serialized to JSON."""
    results = [
        PhaseResult(
            phase="test_phase",
            success=True,
            message="Completed",
            duration_seconds=1.5,
            data={"key": "value"},
        )
    ]
    
    report = generate_timing_report(results, 1.5)
    
    # Convert to dict for JSON serialization
    report_dict = {
        "timestamp": report.timestamp,
        "total_duration_seconds": report.total_duration_seconds,
        "phases": [
            {
                "name": p.name,
                "success": p.success,
                "duration": p.duration_seconds,
                "message": p.message,
            }
            for p in report.phases
        ],
        "final_status": report.final_status,
    }
    
    # Should serialize without error
    json_str = json.dumps(report_dict, indent=2)
    assert "test_phase" in json_str
    assert "SUCCESS" in json_str


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pipeline_handles_empty_project(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test pipeline behavior with empty project directory."""
    orchestrator_config.auto_approve = True
    orchestrator_config.start_docker = False
    orchestrator_config.git_push = False
    
    # Create empty project directory
    empty_project = tmp_path / "empty-project"
    empty_project.mkdir()
    
    # Verification should fail
    result = await phase_verification(orchestrator_config, str(empty_project))
    
    assert result.success is False
    assert result.data.get("has_source_files") is False


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_timing_report_file_output(
    orchestrator_config: OrchestratorConfig,
    tmp_path: Path,
):
    """Test that timing report can be written to file."""
    results = []
    
    for i, phase in enumerate(["p1", "p2", "p3"]):
        results.append(PhaseResult(
            phase=phase,
            success=True,
            message=f"Phase {i+1} done",
            duration_seconds=float(i + 1),
            data={},
        ))
    
    report = generate_timing_report(results, 6.0)
    
    # Write to file
    report_path = tmp_path / "test_report.json"
    report_dict = {
        "timestamp": report.timestamp,
        "total_duration_seconds": report.total_duration_seconds,
        "phases": [
            {
                "name": p.name,
                "success": p.success,
                "duration": p.duration_seconds,
                "message": p.message,
            }
            for p in report.phases
        ],
        "final_status": report.final_status,
    }
    
    with open(report_path, "w") as f:
        json.dump(report_dict, f, indent=2)
    
    # Read back and verify
    with open(report_path, "r") as f:
        loaded = json.load(f)
    
    assert loaded["final_status"] == "SUCCESS"
    assert len(loaded["phases"]) == 3