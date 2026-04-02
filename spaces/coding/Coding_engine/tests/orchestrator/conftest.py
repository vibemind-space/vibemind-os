"""
Shared fixtures and mocks for orchestrator tests.
"""
import json
import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_orchestrator import OrchestratorConfig, PhaseResult


# ============================================================================
# Path Fixtures
# ============================================================================

@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_requirements_path(fixtures_dir: Path) -> Path:
    """Return path to minimal_requirements.json."""
    return fixtures_dir / "minimal_requirements.json"


@pytest.fixture
def minimal_tech_stack_path(fixtures_dir: Path) -> Path:
    """Return path to minimal_tech_stack.json."""
    return fixtures_dir / "minimal_tech_stack.json"


@pytest.fixture
def minimal_requirements(minimal_requirements_path: Path) -> dict:
    """Load and return minimal requirements as dict."""
    with open(minimal_requirements_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def minimal_tech_stack(minimal_tech_stack_path: Path) -> dict:
    """Load and return minimal tech stack as dict."""
    with open(minimal_tech_stack_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Config Fixtures
# ============================================================================

@pytest.fixture
def orchestrator_config(
    minimal_requirements_path: Path,
    minimal_tech_stack_path: Path,
    tmp_path: Path,
) -> OrchestratorConfig:
    """Create a test configuration with safe defaults."""
    return OrchestratorConfig(
        requirements_file=str(minimal_requirements_path),
        tech_stack_file=str(minimal_tech_stack_path),
        project_name="test-project",
        output_dir=str(tmp_path),
        project_create_api="http://localhost:8087",
        coding_engine_api="http://localhost:8000",
        docker_compose_dir=str(tmp_path / "infra"),
        start_docker=False,  # Don't start Docker in tests
        run_mode="society_hybrid",
        max_time=60,
        max_iterations=10,
        min_test_rate=100.0,
        slice_size=3,
        continuous_sandbox=False,
        sandbox_interval=30,
        enable_vnc=False,
        vnc_port=6080,
        auto_approve=True,  # Auto-approve for tests
        git_push=False,  # Don't push in tests
        git_private=True,
        github_token=None,
    )


@pytest.fixture
def orchestrator_config_with_docker(orchestrator_config: OrchestratorConfig) -> OrchestratorConfig:
    """Config with Docker enabled."""
    orchestrator_config.start_docker = True
    return orchestrator_config


@pytest.fixture
def orchestrator_config_with_git(orchestrator_config: OrchestratorConfig) -> OrchestratorConfig:
    """Config with Git push enabled."""
    orchestrator_config.git_push = True
    orchestrator_config.github_token = "ghp_test_token_12345"
    return orchestrator_config


# ============================================================================
# Mock Response Fixtures
# ============================================================================

@pytest.fixture
def mock_api_success_response() -> dict:
    """Mock successful API response for project creation."""
    return {
        "success": True,
        "path": "/test/output/test-project",
        "files_created": 15,
    }


@pytest.fixture
def mock_api_failure_response() -> dict:
    """Mock failed API response."""
    return {
        "success": False,
        "error": "Template not found",
    }


@pytest.fixture
def mock_health_response() -> dict:
    """Mock health check response."""
    return {
        "status": "healthy",
        "version": "1.0.0",
    }


@pytest.fixture
def mock_status_response_completed() -> dict:
    """Mock status response with completed state."""
    return {
        "state": "completed",
        "progress": 100,
        "errors": 0,
    }


@pytest.fixture
def mock_status_response_running() -> dict:
    """Mock status response with running state."""
    return {
        "state": "running",
        "progress": 45,
        "errors": 2,
    }


@pytest.fixture
def mock_git_push_response() -> dict:
    """Mock Git push response."""
    return {
        "success": True,
        "repo_url": "https://github.com/testuser/test-project",
    }


# ============================================================================
# httpx Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_httpx_post_success(mock_api_success_response: dict):
    """Mock httpx.AsyncClient.post for successful responses."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_success_response
        mock_response.raise_for_status = MagicMock()
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_httpx_post_failure(mock_api_failure_response: dict):
    """Mock httpx.AsyncClient.post for failed responses."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_failure_response
        mock_response.raise_for_status = MagicMock()
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_httpx_connection_error():
    """Mock httpx.AsyncClient for connection errors."""
    import httpx
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_httpx_timeout():
    """Mock httpx.AsyncClient for timeout errors."""
    import httpx
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("Timeout")
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_httpx_health_success(mock_health_response: dict):
    """Mock httpx for successful health check."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_health_response
        
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_httpx_git_push_success(mock_git_push_response: dict):
    """Mock httpx for successful Git push."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_git_push_response
        
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        
        mock_client.return_value = mock_instance
        yield mock_client


# ============================================================================
# subprocess Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_subprocess_success():
    """Mock subprocess.Popen for successful execution."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Success output", b"")
        mock_process.stdout = iter(["Line 1\n", "Line 2\n"])
        mock_process.wait.return_value = 0
        
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_subprocess_failure():
    """Mock subprocess.Popen for failed execution."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error: Something went wrong")
        mock_process.stdout = iter(["Error occurred\n"])
        mock_process.wait.return_value = 1
        
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_subprocess_timeout():
    """Mock subprocess.Popen for timeout."""
    import subprocess
    
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="docker-compose", timeout=300
        )
        
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_subprocess_not_found():
    """Mock subprocess.Popen for command not found."""
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.side_effect = FileNotFoundError("docker-compose not found")
        yield mock_popen


# ============================================================================
# Filesystem Fixtures
# ============================================================================

@pytest.fixture
def mock_project_structure(tmp_path: Path) -> Path:
    """Create a minimal project structure for verification tests."""
    project = tmp_path / "test-project"
    project.mkdir()
    
    # package.json
    (project / "package.json").write_text('{"name": "test-project", "version": "1.0.0"}')
    
    # Source directory with files
    src = project / "src"
    src.mkdir()
    (src / "index.ts").write_text('console.log("Hello World");')
    (src / "App.tsx").write_text('export function App() { return <div>Hello</div>; }')
    
    return project


@pytest.fixture
def mock_project_with_build(mock_project_structure: Path) -> Path:
    """Create project structure with build artifacts."""
    # Add node_modules
    node_modules = mock_project_structure / "node_modules"
    node_modules.mkdir()
    (node_modules / ".package-lock.json").write_text("{}")
    
    # Add dist
    dist = mock_project_structure / "dist"
    dist.mkdir()
    (dist / "index.js").write_text("// built file")
    
    return mock_project_structure


@pytest.fixture
def mock_docker_compose_dir(tmp_path: Path) -> Path:
    """Create mock docker-compose directory."""
    infra = tmp_path / "infra"
    infra.mkdir()
    (infra / "docker-compose.yml").write_text("""
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
""")
    return infra


@pytest.fixture
def mock_runner_script(tmp_path: Path) -> Path:
    """Create mock run_society_hybrid.py script."""
    script = tmp_path / "run_society_hybrid.py"
    script.write_text("""
#!/usr/bin/env python3
import sys
print("Mock runner executed")
sys.exit(0)
""")
    return script


# ============================================================================
# Input Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_user_input_approve():
    """Mock user input that approves."""
    with patch("builtins.input", return_value="y"):
        yield


@pytest.fixture
def mock_user_input_reject():
    """Mock user input that rejects."""
    with patch("builtins.input", return_value="n"):
        yield


@pytest.fixture
def mock_user_input_review_then_approve():
    """Mock user input that reviews then approves."""
    with patch("builtins.input", side_effect=["r", "y"]):
        yield


@pytest.fixture
def mock_user_input_invalid_then_approve():
    """Mock user input with invalid input then approve."""
    with patch("builtins.input", side_effect=["invalid", "x", "y"]):
        yield


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def mock_env_with_github_token():
    """Set GITHUB_TOKEN environment variable."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test_token_12345"}):
        yield


@pytest.fixture
def mock_env_without_github_token():
    """Ensure GITHUB_TOKEN is not set."""
    import os
    original = os.environ.pop("GITHUB_TOKEN", None)
    yield
    if original:
        os.environ["GITHUB_TOKEN"] = original


# ============================================================================
# Helper Functions
# ============================================================================

def assert_phase_result(result: PhaseResult, success: bool, phase: str = None):
    """Helper to assert PhaseResult properties."""
    assert result.success == success
    if phase:
        assert result.phase == phase
    assert isinstance(result.message, str)
    assert isinstance(result.duration_seconds, (int, float))
    assert isinstance(result.data, dict)