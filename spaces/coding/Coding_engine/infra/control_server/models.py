"""
Pydantic Models for Control Server API.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Any, Literal
from pydantic import BaseModel, Field


class EngineStatus(str, Enum):
    """Engine status states."""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ProjectType(str, Enum):
    """Detected project types."""
    UNKNOWN = "unknown"
    WEBAPP = "webapp"
    ELECTRON = "electron"
    NODEJS = "nodejs"
    PYTHON_CLI = "python-cli"
    PYTHON_WEB = "python-web"
    RUST_CLI = "rust-cli"
    GO_CLI = "go-cli"
    TAURI = "tauri"


# ============ Git Integration Models ============

class GitConfig(BaseModel):
    """Git configuration for repository creation."""
    repo_name: Optional[str] = Field(
        default=None,
        description="Repository name (defaults to output_dir if not provided)"
    )
    description: Optional[str] = Field(
        default=None,
        description="Repository description"
    )
    private: bool = Field(
        default=True,
        description="Whether the repository should be private"
    )
    create_repo: bool = Field(
        default=True,
        description="Create repository on GitHub"
    )
    push_on_complete: bool = Field(
        default=True,
        description="Push code when generation is complete"
    )


class GitResult(BaseModel):
    """Result of git operations."""
    success: bool
    repo_url: Optional[str] = None
    clone_url: Optional[str] = None
    message: str
    error: Optional[str] = None


class GitStatusResponse(BaseModel):
    """Response for git status endpoint."""
    configured: bool = Field(description="Whether GITHUB_TOKEN is set")
    username: Optional[str] = Field(default=None, description="GitHub username if authenticated")
    message: str


# ============ Engine Models ============

class StartRequest(BaseModel):
    """Request to start the coding engine."""
    requirements_file: Optional[str] = Field(
        default=None,
        description="Path to requirements JSON file (relative to /data/requirements)"
    )
    requirements_json: Optional[dict] = Field(
        default=None,
        description="Requirements as JSON object (alternative to file)"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Output directory name (will be created under /data/output)"
    )
    run_mode: Literal["hybrid", "society_hybrid"] = "hybrid"
    # Git integration
    git_config: Optional[GitConfig] = Field(
        default=None,
        description="Git configuration for automatic repo creation and push"
    )
    # Generation settings
    max_concurrent: int = Field(default=2, ge=1, le=10)
    slice_size: int = Field(default=3, ge=1, le=100)
    enable_preview: bool = Field(default=True)
    # No timeout mode by default
    no_timeout: bool = Field(default=True)
    # VNC settings
    enable_vnc_streaming: bool = Field(default=True)


class StopRequest(BaseModel):
    """Request to stop the coding engine."""
    graceful: bool = Field(
        default=True,
        description="Wait for current iteration to complete"
    )
    save_state: bool = Field(
        default=True,
        description="Save current state before stopping"
    )


class EngineState(BaseModel):
    """Current state of the coding engine."""
    status: EngineStatus = EngineStatus.IDLE
    engine_running: bool = False
    engine_pid: Optional[int] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    requirements_file: Optional[str] = None
    output_dir: Optional[str] = None
    project_type: Optional[ProjectType] = None
    # Progress
    iterations: int = 0
    files_generated: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    cli_errors: int = 0  # CLI error counter
    build_success: Optional[bool] = None
    confidence_score: float = 0.0
    # Error
    last_error: Optional[str] = None
    # Git status
    git_repo_url: Optional[str] = None
    git_pushed: bool = False


class StatusResponse(BaseModel):
    """Response for status endpoint."""
    state: EngineState
    uptime_seconds: float = 0
    vnc_url: str = ""
    preview_url: Optional[str] = None
    api_version: str = "1.0.0"
    git_configured: bool = False


class EventType(str, Enum):
    """WebSocket event types."""
    # Engine events
    ENGINE_STARTED = "engine_started"
    ENGINE_STOPPED = "engine_stopped"
    ENGINE_ERROR = "engine_error"
    # Progress events
    ITERATION_STARTED = "iteration_started"
    ITERATION_COMPLETE = "iteration_complete"
    FILE_GENERATED = "file_generated"
    TEST_RESULT = "test_result"
    BUILD_RESULT = "build_result"
    # CLI events (code generation)
    CLI_ERROR = "cli_error"
    CLI_SUCCESS = "cli_success"
    CLI_PROMPT_SENT = "cli_prompt_sent"
    CLI_RESPONSE_RECEIVED = "cli_response_received"
    CLI_STATS_UPDATED = "cli_stats_updated"
    # Preview events
    PREVIEW_STARTED = "preview_started"
    PREVIEW_READY = "preview_ready"
    PREVIEW_ERROR = "preview_error"
    # Git events
    GIT_REPO_CREATED = "git_repo_created"
    GIT_PUSH_STARTED = "git_push_started"
    GIT_PUSH_COMPLETE = "git_push_complete"
    GIT_ERROR = "git_error"
    # Log events
    LOG_INFO = "log_info"
    LOG_WARNING = "log_warning"
    LOG_ERROR = "log_error"
    # Metrics
    METRICS_UPDATE = "metrics_update"


class WebSocketEvent(BaseModel):
    """Event sent via WebSocket."""
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict = Field(default_factory=dict)
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    healthy: bool = True
    services: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class LogEntry(BaseModel):
    """Log entry for history."""
    timestamp: datetime
    level: str
    source: str
    message: str
    data: Optional[dict] = None


class LogsResponse(BaseModel):
    """Response for logs endpoint."""
    logs: list[LogEntry]
    total: int
    offset: int
    limit: int


# ============ CLI Monitoring Models ============
class CLICallRecord(BaseModel):
    """Record of a single CLI call."""
    id: str
    timestamp: datetime
    agent: str
    prompt: str = Field(description="Truncated prompt (max 500 chars in response)")
    response: str = Field(description="Truncated response (max 500 chars in response)")
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    files_modified: list[str] = Field(default_factory=list)


class CLIStatsResponse(BaseModel):
    """Aggregated CLI statistics."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: int = 0
    success_rate: float = 0.0
    calls_per_minute: float = 0.0
    # Per-agent breakdown
    calls_by_agent: dict[str, int] = Field(default_factory=dict)
    tokens_by_agent: dict[str, int] = Field(default_factory=dict)


class CLIHistoryResponse(BaseModel):
    """Response for CLI call history."""
    calls: list[CLICallRecord]
    total: int
    offset: int
    limit: int
    stats: CLIStatsResponse