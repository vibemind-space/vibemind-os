"""E2E Test Models — Autonomous testing data structures."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StepType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    ASSERT_TEXT = "assert_text"
    ASSERT_URL = "assert_url"
    ASSERT_ELEMENT = "assert_element"
    ASSERT_NOT_TEXT = "assert_not_text"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    SELECT = "select"
    SCROLL = "scroll"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class TestStep(BaseModel):
    """Single step in a test case."""
    type: StepType
    target: Optional[str] = None          # element ref or selector
    value: Optional[str] = None           # text to type, URL to navigate
    expected: Optional[str] = None        # expected text/URL
    path: Optional[str] = None            # URL path for navigate
    label: Optional[str] = None           # screenshot label
    timeout_ms: int = 10000
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    duration_ms: int = 0


class TestCase(BaseModel):
    """Test case generated from a User Story."""
    story_id: str
    name: str
    description: Optional[str] = None
    steps: List[TestStep]
    status: TestStatus = TestStatus.PENDING
    error: Optional[str] = None
    duration_ms: int = 0
    screenshots: List[str] = Field(default_factory=list)


class TestResult(BaseModel):
    """Result of executing one test case."""
    test_case: TestCase
    passed: bool
    assertions_total: int = 0
    assertions_passed: int = 0
    assertions_failed: int = 0
    error_message: Optional[str] = None
    screenshots: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class TestReport(BaseModel):
    """Full E2E test report."""
    project_name: str
    app_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[TestResult] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: int = 0
    report_path: Optional[str] = None


class UserStory(BaseModel):
    """Parsed user story from project spec."""
    id: str
    title: str
    description: Optional[str] = None
    acceptance_criteria: List[str] = Field(default_factory=list)
    priority: Optional[str] = None


class E2ERunRequest(BaseModel):
    """Request to start an E2E test run."""
    project_path: str = "/app/Data/all_services/whatsapp-messaging-service_20260211_025459"
    app_url: str = "http://localhost:3100"
    max_tests: int = 20
    stories: Optional[List[str]] = None   # specific story IDs, or None for all


class E2ERunStatus(BaseModel):
    """Current status of an E2E test run."""
    running: bool = False
    progress_pct: float = 0.0
    current_test: Optional[str] = None
    total_tests: int = 0
    completed: int = 0
    passed: int = 0
    failed: int = 0
    report: Optional[TestReport] = None
