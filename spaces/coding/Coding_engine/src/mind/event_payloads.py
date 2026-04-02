"""
Event Payloads - Typed payload dataclasses for Event system.

Provides type-safe access to event data instead of untyped event.data.get("key").

Usage:
    # Old way (untyped, error-prone):
    errors = event.data.get("errors", [])
    count = event.data.get("error_count", 0)

    # New way (typed, IDE support):
    payload = event.typed  # Returns BuildFailurePayload
    errors = payload.errors
    count = payload.error_count

Benefits:
- IDE autocomplete for payload fields
- Type checking catches typos at dev time
- Self-documenting event data structure
- Validation on payload creation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .event_bus import EventType


class PayloadPriority(Enum):
    """Priority level for payloads affecting prompt construction."""
    CRITICAL = "critical"  # Must fix immediately, blocks everything
    HIGH = "high"          # Should fix soon
    MEDIUM = "medium"      # Can be deferred
    LOW = "low"            # Nice to have


@dataclass
class EventPayload:
    """
    Base class for all typed event payloads.

    All payload classes should inherit from this and define
    their fields as dataclass fields.
    """
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert payload to dictionary for backward compatibility."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, Enum):
                result[key] = value.value
            elif hasattr(value, 'to_dict'):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "EventPayload":
        """Create payload from dictionary."""
        # Filter to only include fields that exist in the dataclass
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# =============================================================================
# Build-Related Payloads
# =============================================================================

@dataclass
class BuildFailurePayload(EventPayload):
    """
    Payload for BUILD_FAILED events.

    Contains structured error information to help Claude
    understand and fix build failures.
    """
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)
    # Each error: {"file": str, "line": int, "message": str, "code": str}

    failing_command: Optional[str] = None  # e.g., "npm run build"
    exit_code: Optional[int] = None

    # Hints for Claude
    likely_causes: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)

    # Context
    build_output: Optional[str] = None  # Truncated build log
    is_type_error: bool = False
    is_import_error: bool = False
    is_syntax_error: bool = False
    is_database_error: bool = False  # Flag for database-related errors (migration/schema)

    @classmethod
    def from_build_output(cls, output: str, exit_code: int = 1) -> "BuildFailurePayload":
        """Parse build output into structured payload."""
        errors = []
        likely_causes = []
        affected_files = set()

        is_type_error = False
        is_import_error = False
        is_syntax_error = False
        is_database_error = False

        for line in output.split("\n"):
            line_lower = line.lower()

            # Detect error types
            if "ts(" in line or "type" in line_lower and "error" in line_lower:
                is_type_error = True
            if "cannot find module" in line_lower or "import" in line_lower:
                is_import_error = True
            if "syntaxerror" in line_lower or "unexpected token" in line_lower:
                is_syntax_error = True
            # Detect database errors
            if any(pattern in line_lower for pattern in [
                "relation", "does not exist", "column", "prisma", "p1001", "p2002", "p2003", "p2025",
                "econnrefused", "database", "migration", "schema"
            ]):
                is_database_error = True

            # Extract file paths
            if ".ts:" in line or ".tsx:" in line or ".js:" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    file_path = parts[0].strip()
                    affected_files.add(file_path)

                    error_entry = {"file": file_path, "message": line}
                    if len(parts) >= 3:
                        try:
                            error_entry["line"] = int(parts[1])
                        except ValueError:
                            pass
                    errors.append(error_entry)

        # Generate likely causes
        if is_import_error:
            likely_causes.append("Missing import or incorrect import path")
            likely_causes.append("Dependency not installed - check package.json")
        if is_type_error:
            likely_causes.append("TypeScript type mismatch")
            likely_causes.append("Missing type definition or incorrect interface")
        if is_syntax_error:
            likely_causes.append("Syntax error - check for missing brackets or semicolons")
        if is_database_error:
            likely_causes.append("Database schema mismatch - run prisma db push")
            likely_causes.append("Missing table or column - check Prisma schema")
            likely_causes.append("Database connection failed - check DATABASE_URL")

        return cls(
            error_count=len(errors),
            errors=errors,
            exit_code=exit_code,
            likely_causes=likely_causes,
            affected_files=list(affected_files),
            build_output=output[:2000] if len(output) > 2000 else output,
            is_type_error=is_type_error,
            is_import_error=is_import_error,
            is_syntax_error=is_syntax_error,
            is_database_error=is_database_error,
        )


@dataclass
class BuildSuccessPayload(EventPayload):
    """Payload for BUILD_SUCCEEDED events."""
    build_time_ms: int = 0
    output_dir: Optional[str] = None
    bundle_size_bytes: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    assets: list[dict] = field(default_factory=list)
    # Each asset: {"name": str, "size": int}


# =============================================================================
# Type Error Payloads
# =============================================================================

@dataclass
class TypeErrorPayload(EventPayload):
    """
    Payload for TYPE_ERROR events.

    Provides detailed TypeScript error information.
    """
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)
    # Each error: {"file": str, "line": int, "column": int, "code": str, "message": str}

    # Grouped by file for efficient fixing
    errors_by_file: dict[str, list[dict]] = field(default_factory=dict)

    # Type-specific hints
    missing_types: list[str] = field(default_factory=list)
    type_mismatches: list[dict] = field(default_factory=list)
    # Each mismatch: {"expected": str, "actual": str, "location": str}

    @classmethod
    def from_tsc_output(cls, output: str) -> "TypeErrorPayload":
        """Parse TypeScript compiler output."""
        errors = []
        errors_by_file: dict[str, list[dict]] = {}
        missing_types = []
        type_mismatches = []

        # Pattern: src/file.ts(10,5): error TS2345: ...
        import re
        pattern = r'([^(]+)\((\d+),(\d+)\):\s*error\s+(TS\d+):\s*(.+)'

        for line in output.split("\n"):
            match = re.match(pattern, line.strip())
            if match:
                file_path = match.group(1).strip()
                error = {
                    "file": file_path,
                    "line": int(match.group(2)),
                    "column": int(match.group(3)),
                    "code": match.group(4),
                    "message": match.group(5),
                }
                errors.append(error)

                if file_path not in errors_by_file:
                    errors_by_file[file_path] = []
                errors_by_file[file_path].append(error)

                # Detect missing types
                if "Cannot find name" in error["message"]:
                    type_name = re.search(r"'([^']+)'", error["message"])
                    if type_name:
                        missing_types.append(type_name.group(1))

                # Detect type mismatches
                if "is not assignable to" in error["message"]:
                    parts = error["message"].split("is not assignable to")
                    if len(parts) == 2:
                        type_mismatches.append({
                            "expected": parts[1].strip().strip("'."),
                            "actual": parts[0].strip().strip("'").replace("Type ", ""),
                            "location": f"{file_path}:{error['line']}",
                        })

        return cls(
            error_count=len(errors),
            errors=errors,
            errors_by_file=errors_by_file,
            missing_types=list(set(missing_types)),
            type_mismatches=type_mismatches,
        )


# =============================================================================
# Test-Related Payloads
# =============================================================================

@dataclass
class TestFailurePayload(EventPayload):
    """
    Payload for TEST_FAILED events.

    Contains assertion details for failed tests.
    """
    test_name: str = ""
    test_file: Optional[str] = None
    suite_name: Optional[str] = None

    # Assertion details
    expected: Optional[str] = None
    actual: Optional[str] = None
    diff: Optional[str] = None

    # Stack trace (truncated)
    stack_trace: Optional[str] = None
    error_message: Optional[str] = None

    # Context
    test_duration_ms: Optional[int] = None
    retry_count: int = 0
    is_flaky: bool = False

    # Related files
    related_source_files: list[str] = field(default_factory=list)


@dataclass
class TestSuiteResultPayload(EventPayload):
    """Payload for test suite completion (TEST_PASSED or aggregated results)."""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: int = 0

    # Failed test details
    failures: list[TestFailurePayload] = field(default_factory=list)

    # Coverage (if available)
    coverage_percent: Optional[float] = None
    uncovered_lines: dict[str, list[int]] = field(default_factory=dict)


# =============================================================================
# Mock/Validation Payloads
# =============================================================================

@dataclass
class MockViolationPayload(EventPayload):
    """
    Payload for MOCK_DETECTED events.

    Identifies mock data that should be replaced with real implementations.
    """
    violations: list[dict] = field(default_factory=list)
    # Each violation: {
    #   "file": str,
    #   "line": int,
    #   "code": str,
    #   "message": str,
    #   "suggested_fix": str,
    #   "severity": "error" | "warning"
    # }

    error_count: int = 0
    warning_count: int = 0

    # Categorized violations
    hardcoded_data: list[dict] = field(default_factory=list)
    placeholder_text: list[dict] = field(default_factory=list)
    todo_comments: list[dict] = field(default_factory=list)
    mock_functions: list[dict] = field(default_factory=list)

    @classmethod
    def from_violations(cls, violations: list[dict]) -> "MockViolationPayload":
        """Categorize violations by type."""
        hardcoded = []
        placeholder = []
        todos = []
        mocks = []
        errors = 0
        warnings = 0

        for v in violations:
            severity = v.get("severity", "error")
            if severity == "error":
                errors += 1
            else:
                warnings += 1

            code = v.get("code", "").lower()
            message = v.get("message", "").lower()

            if "mock" in code or "mock" in message:
                mocks.append(v)
            elif "todo" in code or "fixme" in code:
                todos.append(v)
            elif "lorem" in message or "placeholder" in message:
                placeholder.append(v)
            else:
                hardcoded.append(v)

        return cls(
            violations=violations,
            error_count=errors,
            warning_count=warnings,
            hardcoded_data=hardcoded,
            placeholder_text=placeholder,
            todo_comments=todos,
            mock_functions=mocks,
        )


# =============================================================================
# Code Generation Payloads
# =============================================================================

@dataclass
class CodeGeneratedPayload(EventPayload):
    """Payload for CODE_GENERATED events."""
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    total_lines: int = 0

    # Generation context
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model: Optional[str] = None

    # What was generated
    component_type: Optional[str] = None  # "component", "api", "test", etc.
    feature_id: Optional[str] = None


@dataclass
class CodeFixNeededPayload(EventPayload):
    """
    Payload for CODE_FIX_NEEDED events.

    Aggregates multiple error sources into a fix request.
    """
    priority: PayloadPriority = PayloadPriority.HIGH

    # Error sources
    build_errors: list[dict] = field(default_factory=list)
    type_errors: list[dict] = field(default_factory=list)
    test_failures: list[dict] = field(default_factory=list)
    lint_errors: list[dict] = field(default_factory=list)

    # Files to focus on
    primary_files: list[str] = field(default_factory=list)

    # Previous attempts (to avoid loops)
    previous_attempts: list[dict] = field(default_factory=list)
    # Each attempt: {"prompt": str, "result": str, "success": bool}

    attempt_count: int = 0
    max_attempts: int = 5

    # Suggested approach
    suggested_strategy: Optional[str] = None


# =============================================================================
# E2E Test Payloads
# =============================================================================

@dataclass
class E2ETestResultPayload(EventPayload):
    """Payload for E2E_TEST_PASSED or E2E_TEST_FAILED events."""
    test_name: str = ""
    test_file: Optional[str] = None
    passed: bool = False

    # Visual context
    screenshot_path: Optional[str] = None
    video_path: Optional[str] = None

    # Failure details
    error_message: Optional[str] = None
    failing_step: Optional[str] = None
    element_selector: Optional[str] = None

    # Page state
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    console_errors: list[str] = field(default_factory=list)
    network_errors: list[str] = field(default_factory=list)


@dataclass
class ScreenshotPayload(EventPayload):
    """Payload for E2E_SCREENSHOT_TAKEN events."""
    screenshot_path: str = ""
    page_url: Optional[str] = None
    viewport_size: Optional[dict] = None  # {"width": int, "height": int}

    # For UX analysis
    component_name: Optional[str] = None
    interaction_state: Optional[str] = None  # "initial", "hover", "clicked", etc.


# =============================================================================
# Sandbox/Docker Payloads
# =============================================================================

@dataclass
class SandboxTestPayload(EventPayload):
    """Payload for SANDBOX_TEST_* events."""
    container_id: Optional[str] = None
    container_name: Optional[str] = None

    # Test result
    passed: bool = False
    error_message: Optional[str] = None

    # Runtime info
    app_url: Optional[str] = None
    vnc_url: Optional[str] = None

    # Logs
    container_logs: Optional[str] = None
    health_check_results: list[dict] = field(default_factory=list)


@dataclass
class ContainerLogSeededPayload(EventPayload):
    """
    Payload for CONTAINER_LOGS_SEEDED events.

    Published by ContainerLogSeeder when logs are automatically captured.
    """
    container_id: str = ""
    container_name: str = ""
    source_event: str = ""  # Event that triggered log capture

    # Log file info
    log_file_path: str = ""
    lines_captured: int = 0

    # Container state at capture time
    exit_code: Optional[int] = None
    health_status: Optional[str] = None

    # Search results (for CONTAINER_LOG_SEARCH_COMPLETE)
    search_pattern: Optional[str] = None
    matching_entries: list[dict] = field(default_factory=list)
    total_matches: int = 0


# =============================================================================
# UX Review Payloads
# =============================================================================

@dataclass
class UXIssuePayload(EventPayload):
    """Payload for UX_ISSUE_FOUND events."""
    issues: list[dict] = field(default_factory=list)
    # Each issue: {
    #   "type": str,  # "visual", "usability", "accessibility", "consistency"
    #   "severity": str,  # "critical", "major", "minor"
    #   "description": str,
    #   "component": str,
    #   "suggestion": str,
    #   "screenshot_region": dict  # {"x": int, "y": int, "width": int, "height": int}
    # }

    # Source
    screenshot_path: Optional[str] = None
    analyzed_by: str = "UXDesignAgent"

    # Summary
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0


# =============================================================================
# Backend Chain Payloads
# =============================================================================

@dataclass
class DatabaseSchemaPayload(EventPayload):
    """Payload for DATABASE_SCHEMA_GENERATED events."""
    schema_file: str = ""
    tables: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)

    db_type: str = "prisma"  # "prisma", "drizzle", "typeorm"
    migration_needed: bool = False


@dataclass
class APIRoutesPayload(EventPayload):
    """Payload for API_ROUTES_GENERATED events."""
    routes: list[dict] = field(default_factory=list)
    # Each route: {"method": str, "path": str, "handler": str}

    openapi_spec_path: Optional[str] = None
    total_endpoints: int = 0


@dataclass
class AuthSetupPayload(EventPayload):
    """Payload for AUTH_SETUP_COMPLETE events."""
    auth_type: str = "jwt"  # "jwt", "oauth", "session"
    providers: list[str] = field(default_factory=list)

    # Generated files
    middleware_file: Optional[str] = None
    config_file: Optional[str] = None

    # Features
    has_rbac: bool = False
    has_mfa: bool = False


# =============================================================================
# Document-Related Payloads
# =============================================================================

@dataclass
class DebugReportCreatedPayload(EventPayload):
    """
    Payload for DEBUG_REPORT_CREATED events.

    Published by PlaywrightE2EAgent and ContinuousDebugAgent when debug analysis completes.
    """
    doc_id: str = ""
    issues_found: int = 0
    screenshots: list[str] = field(default_factory=list)

    # Issue categories
    visual_issues: list[dict] = field(default_factory=list)
    functional_issues: list[dict] = field(default_factory=list)
    runtime_errors: list[dict] = field(default_factory=list)

    # Context
    page_url: Optional[str] = None
    analyzed_files: list[str] = field(default_factory=list)

    # Priority
    requires_immediate_fix: bool = False
    blocking_issues: list[str] = field(default_factory=list)


@dataclass
class QualityReportCreatedPayload(EventPayload):
    """
    Payload for QUALITY_REPORT_CREATED events.

    Published by CodeQualityAgent after code analysis.
    """
    doc_id: str = ""
    requires_action: bool = False

    # Task counts
    cleanup_tasks: int = 0
    refactor_tasks: int = 0
    style_issues: int = 0

    # Detailed findings
    cleanup_items: list[dict] = field(default_factory=list)
    # Each item: {"file": str, "issue": str, "suggestion": str, "priority": str}

    refactor_items: list[dict] = field(default_factory=list)
    # Each item: {"file": str, "reason": str, "approach": str, "impact": str}

    # Metrics
    code_coverage: Optional[float] = None
    complexity_score: Optional[float] = None
    maintainability_index: Optional[float] = None


@dataclass
class ImplementationPlanPayload(EventPayload):
    """
    Payload for IMPLEMENTATION_PLAN_CREATED events.

    Published by GeneratorAgent when creating a fix plan.
    """
    doc_id: str = ""
    files_changed: int = 0
    fixes_planned: int = 0

    # What this plan responds to
    responding_to: list[str] = field(default_factory=list)
    # List of event types: ["BUILD_FAILED", "TYPE_ERROR"]

    # Planned changes
    file_changes: list[dict] = field(default_factory=list)
    # Each change: {"file": str, "action": str, "description": str}

    # Dependencies
    requires_npm_install: bool = False
    requires_build: bool = False
    requires_tests: bool = False

    # Estimated impact
    estimated_complexity: str = "medium"  # "low", "medium", "high"


@dataclass
class AgentLifecyclePayload(EventPayload):
    """
    Payload for AGENT_* lifecycle events.

    Used for agent startup, completion, and error events.
    """
    agent_name: str = ""
    action: Optional[str] = None  # "started", "completed", "failed", "idle"

    # Metrics
    actions_taken: int = 0
    events_processed: int = 0
    duration_ms: Optional[int] = None

    # Error context (if failed)
    error: Optional[str] = None
    error_type: Optional[str] = None
    stack_trace: Optional[str] = None

    # State
    is_healthy: bool = True
    queue_size: int = 0


@dataclass
class ConvergenceUpdatePayload(EventPayload):
    """
    Payload for CONVERGENCE_UPDATE events.

    Published by Orchestrator when convergence metrics change.
    """
    iteration: int = 0
    progress_percent: float = 0.0

    # Current metrics
    build_passing: bool = False
    tests_passing: bool = False
    type_errors: int = 0
    mock_violations: int = 0

    # Trend
    improving: bool = True
    stalled_iterations: int = 0

    # Active agents
    active_agents: list[str] = field(default_factory=list)
    pending_events: int = 0


@dataclass
class FileChangePayload(EventPayload):
    """
    Payload for FILE_CREATED, FILE_MODIFIED, FILE_DELETED events.
    """
    file_path: str = ""
    change_type: str = ""  # "created", "modified", "deleted"

    # Content info (for created/modified)
    lines_added: int = 0
    lines_removed: int = 0
    file_size_bytes: Optional[int] = None

    # Context
    changed_by: Optional[str] = None  # Agent name
    related_feature: Optional[str] = None


@dataclass
class DeploySucceededPayload(EventPayload):
    """
    Payload for DEPLOY_SUCCEEDED events.
    """
    deploy_url: Optional[str] = None
    container_id: Optional[str] = None

    # Runtime info
    vnc_url: Optional[str] = None
    app_port: Optional[int] = None

    # Health
    health_check_passed: bool = False
    startup_time_ms: Optional[int] = None

    # Logs
    deploy_logs: Optional[str] = None


@dataclass
class ValidationErrorPayload(EventPayload):
    """
    Payload for VALIDATION_ERROR events.
    """
    validator_name: str = ""
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)
    # Each error: {"file": str, "message": str, "rule": str, "severity": str}

    # Categories
    has_security_issues: bool = False
    has_accessibility_issues: bool = False
    has_performance_issues: bool = False

    # Suggestions
    auto_fixable: int = 0
    manual_fixes_needed: int = 0


# =============================================================================
# MCP Orchestrator Payloads (Phase 16 - LLM-planned Tool Execution)
# =============================================================================

@dataclass
class MCPTaskStartedPayload(EventPayload):
    """
    Payload for MCP_TASK_STARTED events.

    Published when the MCP Orchestrator begins processing a natural language task.
    """
    task_id: str = ""
    task: str = ""
    context: dict = field(default_factory=dict)

    # Source of the task
    triggered_by: Optional[str] = None  # Event type that triggered this, or "direct"
    working_dir: Optional[str] = None


@dataclass
class MCPTaskPlannedPayload(EventPayload):
    """
    Payload for MCP_TASK_PLANNED events.

    Published after LLM creates an execution plan.
    """
    task_id: str = ""
    task: str = ""
    steps_count: int = 0
    expected_outcome: str = ""

    # Plan details
    tools_to_use: list[str] = field(default_factory=list)
    plan_method: str = "llm"  # "llm" or "fallback"


@dataclass
class MCPTaskCompletePayload(EventPayload):
    """
    Payload for MCP_TASK_COMPLETE events.

    Published when an MCP task executes successfully.
    """
    task_id: str = ""
    task: str = ""
    success: bool = True
    steps_executed: int = 0
    total_duration: float = 0.0

    # Output
    output: Any = None
    output_files: list[str] = field(default_factory=list)

    # Metrics
    tools_called: list[str] = field(default_factory=list)
    recovery_attempts: int = 0


@dataclass
class MCPTaskFailedPayload(EventPayload):
    """
    Payload for MCP_TASK_FAILED events.

    Published when an MCP task fails.
    """
    task_id: str = ""
    task: str = ""
    steps_executed: int = 0
    total_duration: float = 0.0

    # Error details
    error: str = ""
    failed_tool: Optional[str] = None
    failed_step_index: int = -1

    # Recovery info
    recovery_attempted: bool = False
    recovery_error: Optional[str] = None

    # Context for debugging
    partial_output: Any = None


@dataclass
class MCPToolExecutionPayload(EventPayload):
    """
    Payload for MCP_TOOL_* events (STARTED, COMPLETE, FAILED).

    Published for individual tool executions within a task.
    """
    task_id: str = ""
    tool_name: str = ""
    step_index: int = 0

    # Arguments (sanitized)
    args: dict = field(default_factory=dict)
    reason: str = ""

    # Result (for COMPLETE/FAILED)
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    duration: float = 0.0


@dataclass
class MCPDockerEventPayload(EventPayload):
    """
    Payload for MCP_DOCKER_* events.

    Published when Docker operations complete via MCP Orchestrator.
    """
    task_id: str = ""
    operation: str = ""  # "container_start", "compose_up", "image_pull", etc.

    # Container info
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    image: Optional[str] = None

    # Ports
    ports: dict = field(default_factory=dict)  # {"5432": "5432"}

    # Health
    health_status: Optional[str] = None
    startup_time_ms: Optional[int] = None


@dataclass
class MCPGitEventPayload(EventPayload):
    """
    Payload for MCP_GIT_* events.

    Published when Git operations complete via MCP Orchestrator.
    """
    task_id: str = ""
    operation: str = ""  # "commit", "branch", "push", etc.

    # Commit info
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    branch: Optional[str] = None

    # Changes
    files_changed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class MCPNpmEventPayload(EventPayload):
    """
    Payload for MCP_NPM_* events.

    Published when NPM operations complete via MCP Orchestrator.
    """
    task_id: str = ""
    operation: str = ""  # "install", "build", "test", "run"

    # Result
    script: Optional[str] = None
    exit_code: int = 0
    duration_ms: int = 0

    # Metrics
    packages_installed: int = 0
    warnings: list[str] = field(default_factory=list)
    output_summary: Optional[str] = None


@dataclass
class MCPFileEventPayload(EventPayload):
    """
    Payload for MCP_FILE_* events.

    Published when filesystem operations complete via MCP Orchestrator.
    """
    task_id: str = ""
    operation: str = ""  # "create", "modify", "delete", "mkdir"

    # File info
    file_path: str = ""
    file_size: Optional[int] = None
    is_directory: bool = False

    # Content (for small files)
    content_preview: Optional[str] = None


# =============================================================================
# Git Push Agent Payloads (Autonomous Git Operations)
# =============================================================================

@dataclass
class GitPushStartedPayload(EventPayload):
    """Payload for GIT_PUSH_STARTED events."""
    working_dir: str = ""
    branch: str = ""
    remote: str = "origin"
    commit_count: int = 0
    files_changed: list[str] = field(default_factory=list)


@dataclass
class GitPushSucceededPayload(EventPayload):
    """Payload for GIT_PUSH_SUCCEEDED events."""
    branch: str = ""
    remote: str = "origin"
    commit_hash: str = ""
    commit_message: str = ""
    files_committed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    remote_url: Optional[str] = None


@dataclass
class GitPushFailedPayload(EventPayload):
    """Payload for GIT_PUSH_FAILED events."""
    branch: str = ""
    remote: str = "origin"
    error: str = ""
    error_type: str = ""  # "auth", "conflict", "network", "no_remote", "unknown"
    retry_possible: bool = True


@dataclass
class GitCommitCreatedPayload(EventPayload):
    """Payload for GIT_COMMIT_CREATED events."""
    commit_hash: str = ""
    commit_message: str = ""
    branch: str = ""
    files_committed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    author: str = "Coding Engine"


@dataclass
class PatternLearnedPayload(EventPayload):
    """Payload for PATTERN_LEARNED events (Supermemory RAG)."""
    pattern_type: str = ""  # "error_fix", "architecture", "test", "deployment"
    pattern_key: str = ""
    confidence: float = 0.0
    source_agent: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class PatternRetrievedPayload(EventPayload):
    """Payload for PATTERN_RETRIEVED events (Supermemory RAG)."""
    query: str = ""
    matches_found: int = 0
    top_match_confidence: float = 0.0
    pattern_type: str = ""
    used_by_agent: str = ""


@dataclass
class ClassificationCompletedPayload(EventPayload):
    """Payload for CLASSIFICATION_COMPLETED events."""
    content_hash: str = ""
    category: str = ""
    confidence: float = 0.0
    source: str = ""  # "local_cache", "redis_cache", "pattern", "supermemory", "llm"
    category_type: str = ""  # "error_type", "domain", "project_type", etc.
    latency_ms: float = 0.0


# =============================================================================
# Payload Registry
# =============================================================================

def get_payload_type(event_type: "EventType") -> Optional[Type[EventPayload]]:
    """
    Get the typed payload class for an event type.

    Returns None if no typed payload is registered.
    """
    from .event_bus import EventType

    PAYLOAD_TYPES: dict[EventType, Type[EventPayload]] = {
        # Build events
        EventType.BUILD_FAILED: BuildFailurePayload,
        EventType.BUILD_SUCCEEDED: BuildSuccessPayload,

        # Type errors
        EventType.TYPE_ERROR: TypeErrorPayload,

        # Test events
        EventType.TEST_FAILED: TestFailurePayload,
        EventType.TEST_PASSED: TestSuiteResultPayload,

        # Mock detection
        EventType.MOCK_DETECTED: MockViolationPayload,

        # Code generation
        EventType.CODE_GENERATED: CodeGeneratedPayload,
        EventType.CODE_FIX_NEEDED: CodeFixNeededPayload,

        # E2E tests
        EventType.E2E_TEST_PASSED: E2ETestResultPayload,
        EventType.E2E_TEST_FAILED: E2ETestResultPayload,
        EventType.E2E_SCREENSHOT_TAKEN: ScreenshotPayload,

        # Sandbox
        EventType.SANDBOX_TEST_PASSED: SandboxTestPayload,
        EventType.SANDBOX_TEST_FAILED: SandboxTestPayload,

        # Container Log Seeding
        EventType.CONTAINER_LOGS_SEEDED: ContainerLogSeededPayload,
        EventType.CONTAINER_LOG_SEARCH_COMPLETE: ContainerLogSeededPayload,

        # UX
        EventType.UX_ISSUE_FOUND: UXIssuePayload,

        # Backend chain
        EventType.DATABASE_SCHEMA_GENERATED: DatabaseSchemaPayload,
        EventType.API_ROUTES_GENERATED: APIRoutesPayload,
        EventType.AUTH_SETUP_COMPLETE: AuthSetupPayload,

        # Document events (Phase 12)
        EventType.DEBUG_REPORT_CREATED: DebugReportCreatedPayload,
        EventType.QUALITY_REPORT_CREATED: QualityReportCreatedPayload,
        EventType.IMPLEMENTATION_PLAN_CREATED: ImplementationPlanPayload,

        # Agent lifecycle (Phase 12)
        EventType.AGENT_STARTED: AgentLifecyclePayload,
        EventType.AGENT_ACTING: AgentLifecyclePayload,
        EventType.AGENT_COMPLETED: AgentLifecyclePayload,
        EventType.AGENT_ERROR: AgentLifecyclePayload,

        # System events (Phase 12)
        EventType.CONVERGENCE_UPDATE: ConvergenceUpdatePayload,
        EventType.DEPLOY_SUCCEEDED: DeploySucceededPayload,
        EventType.VALIDATION_ERROR: ValidationErrorPayload,

        # File events (Phase 12)
        EventType.FILE_CREATED: FileChangePayload,
        EventType.FILE_MODIFIED: FileChangePayload,
        EventType.FILE_DELETED: FileChangePayload,

        # MCP Orchestrator events (Phase 16)
        EventType.MCP_TASK_STARTED: MCPTaskStartedPayload,
        EventType.MCP_TASK_PLANNED: MCPTaskPlannedPayload,
        EventType.MCP_TASK_COMPLETE: MCPTaskCompletePayload,
        EventType.MCP_TASK_FAILED: MCPTaskFailedPayload,
        EventType.MCP_TOOL_STARTED: MCPToolExecutionPayload,
        EventType.MCP_TOOL_COMPLETE: MCPToolExecutionPayload,
        EventType.MCP_TOOL_FAILED: MCPToolExecutionPayload,
        EventType.MCP_DOCKER_CONTAINER_STARTED: MCPDockerEventPayload,
        EventType.MCP_DOCKER_CONTAINER_STOPPED: MCPDockerEventPayload,
        EventType.MCP_DOCKER_COMPOSE_UP: MCPDockerEventPayload,
        EventType.MCP_DOCKER_COMPOSE_DOWN: MCPDockerEventPayload,
        EventType.MCP_DOCKER_IMAGE_PULLED: MCPDockerEventPayload,
        EventType.MCP_GIT_COMMIT_CREATED: MCPGitEventPayload,
        EventType.MCP_GIT_BRANCH_CREATED: MCPGitEventPayload,
        EventType.MCP_GIT_PUSH_COMPLETE: MCPGitEventPayload,
        EventType.MCP_NPM_INSTALL_COMPLETE: MCPNpmEventPayload,
        EventType.MCP_NPM_BUILD_COMPLETE: MCPNpmEventPayload,
        EventType.MCP_NPM_TEST_COMPLETE: MCPNpmEventPayload,
        EventType.MCP_FILE_CREATED: MCPFileEventPayload,
        EventType.MCP_FILE_MODIFIED: MCPFileEventPayload,
        EventType.MCP_DIRECTORY_CREATED: MCPFileEventPayload,

        # Git Push Agent events
        EventType.GIT_PUSH_STARTED: GitPushStartedPayload,
        EventType.GIT_PUSH_SUCCEEDED: GitPushSucceededPayload,
        EventType.GIT_PUSH_FAILED: GitPushFailedPayload,
        EventType.GIT_COMMIT_CREATED: GitCommitCreatedPayload,

        # Pattern Learning events
        EventType.PATTERN_LEARNED: PatternLearnedPayload,
        EventType.PATTERN_RETRIEVED: PatternRetrievedPayload,

        # Classification events
        EventType.CLASSIFICATION_COMPLETED: ClassificationCompletedPayload,
    }

    return PAYLOAD_TYPES.get(event_type)


def get_typed_payload(event_type: "EventType", data: dict) -> Optional[EventPayload]:
    """
    Parse event data into a typed payload.

    Returns None if:
    - No payload type is registered for this event type
    - Parsing fails
    """
    payload_class = get_payload_type(event_type)
    if payload_class is None:
        return None

    try:
        return payload_class.from_dict(data)
    except Exception:
        # Fall back to None on parse error
        return None
