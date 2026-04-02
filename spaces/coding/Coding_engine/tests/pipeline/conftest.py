"""
Pytest Fixtures für Pipeline Tests.

Stellt Fixtures bereit für:
- Minimal Requirements
- Test TechStack
- ConversationLogger
- Temporary Output Directories
"""
import json
import pytest
import tempfile
from pathlib import Path
from typing import Generator

from src.logging.conversation_logger import ConversationLogger, init_logger


# Minimal Requirements für schnelle Tests
MINIMAL_REQUIREMENTS = {
    "project_name": "TestProject",
    "description": "A minimal test project",
    "requirements": [
        {
            "id": "REQ-001",
            "title": "User Login",
            "description": "Users can log in with email and password",
            "type": "functional",
            "priority": "high",
            "dependencies": []
        },
        {
            "id": "REQ-002",
            "title": "Dashboard View",
            "description": "Display user dashboard with statistics",
            "type": "functional",
            "priority": "high",
            "dependencies": ["REQ-001"]
        },
        {
            "id": "REQ-003",
            "title": "User API Endpoint",
            "description": "REST API for user CRUD operations",
            "type": "functional",
            "priority": "medium",
            "dependencies": []
        }
    ]
}


MINIMAL_TECH_STACK = {
    "frontend": {
        "framework": "react",
        "language": "typescript",
        "styling": "tailwind"
    },
    "backend": {
        "framework": "fastapi",
        "language": "python",
        "database": "postgresql"
    }
}


@pytest.fixture
def minimal_requirements() -> dict:
    """Return minimal requirements for testing."""
    return MINIMAL_REQUIREMENTS.copy()


@pytest.fixture
def minimal_requirements_json() -> str:
    """Return minimal requirements as JSON string."""
    return json.dumps(MINIMAL_REQUIREMENTS)


@pytest.fixture
def minimal_tech_stack() -> dict:
    """Return minimal tech stack for testing."""
    return MINIMAL_TECH_STACK.copy()


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory(prefix="pipeline_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_log_dir() -> Generator[Path, None, None]:
    """Create a temporary log directory."""
    with tempfile.TemporaryDirectory(prefix="pipeline_logs_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def conversation_logger(temp_log_dir: Path) -> Generator[ConversationLogger, None, None]:
    """Create a ConversationLogger for testing."""
    logger = ConversationLogger(
        job_id="test_job_001",
        log_dir=temp_log_dir,
    )
    yield logger
    logger.flush()


@pytest.fixture
def global_conversation_logger(temp_log_dir: Path) -> Generator[ConversationLogger, None, None]:
    """Initialize the global conversation logger."""
    logger = init_logger("test_job_global", temp_log_dir)
    yield logger
    from src.logging.conversation_logger import cleanup_logger
    cleanup_logger()


@pytest.fixture
def requirements_file(temp_output_dir: Path, minimal_requirements: dict) -> Path:
    """Create a requirements JSON file."""
    req_file = temp_output_dir / "requirements.json"
    with open(req_file, "w", encoding="utf-8") as f:
        json.dump(minimal_requirements, f)
    return req_file


@pytest.fixture
def tech_stack_file(temp_output_dir: Path, minimal_tech_stack: dict) -> Path:
    """Create a tech stack JSON file."""
    ts_file = temp_output_dir / "tech_stack.json"
    with open(ts_file, "w", encoding="utf-8") as f:
        json.dump(minimal_tech_stack, f)
    return ts_file