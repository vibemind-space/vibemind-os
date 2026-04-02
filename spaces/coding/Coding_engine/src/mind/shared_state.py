"""
Shared State - Convergence metrics and system state tracking.

Tracks all metrics needed to determine if the system has converged:
- Test results
- Build status
- Validation errors
- Type errors
- Code coverage
- Asset generation status
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ConvergenceMetrics:
    """
    Metrics that determine system convergence.

    The system is considered "ready" when all metrics meet their thresholds.
    """
    # Test metrics
    total_tests: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    test_coverage: float = 0.0  # 0-100

    # Build metrics
    build_attempted: bool = False
    build_success: bool = False
    build_errors: int = 0

    # Validation metrics
    validation_errors: int = 0
    validation_warnings: int = 0

    # Type checking metrics
    type_errors: int = 0
    type_warnings: int = 0

    # Lint metrics
    lint_errors: int = 0
    lint_warnings: int = 0

    # Asset metrics
    assets_required: int = 0
    assets_generated: int = 0

    # UI Validation metrics (FrontendValidator)
    ui_validation_attempted: bool = False
    ui_validation_score: float = 0.0  # 0-1
    ui_requirements_matched: int = 0
    ui_requirements_total: int = 0

    # Runtime Debug metrics
    runtime_tested: bool = False
    runtime_success: bool = False
    runtime_errors: int = 0

    # Playwright E2E visual testing metrics
    playwright_e2e_tested: bool = False
    playwright_e2e_success: bool = False
    playwright_e2e_tests_run: int = 0
    playwright_e2e_tests_passed: int = 0
    playwright_visual_issues: int = 0

    # Sandbox testing metrics (Docker-based)
    sandbox_tested: bool = False
    sandbox_success: bool = False
    sandbox_errors: int = 0
    sandbox_duration_ms: int = 0

    # Cloud testing metrics (GitHub Actions)
    cloud_tested: bool = False
    cloud_success: bool = False
    cloud_platforms_tested: int = 0
    cloud_platforms_passed: int = 0

    # Packaging metrics
    package_attempted: bool = False
    package_success: bool = False
    package_artifacts: int = 0

    # Code metrics
    files_generated: int = 0
    files_modified: int = 0
    lines_of_code: int = 0

    # Generator coordination (NEW)
    generator_pending: bool = False
    generator_started_at: Optional[datetime] = None

    # Deadlock detection (NEW)
    recent_error_hashes: list = field(default_factory=list)  # Last N error hashes
    consecutive_same_errors: int = 0  # Count of same error in sequence
    is_stuck: bool = False  # Deadlock detected

    # Task 14: Backend chain metrics (Database → API → Auth → Infrastructure)
    database_schema_generated: bool = False
    api_routes_generated: bool = False
    auth_setup_complete: bool = False
    infrastructure_ready: bool = False

    # =========================================================================
    # Fullstack Verification Metrics (Continuous Feedback Loop)
    # =========================================================================
    # These metrics are set by FullstackVerifierAgent when FULLSTACK_VERIFIED is published
    fullstack_verified: bool = False  # True when all components pass verification
    fullstack_score: float = 0.0  # 0.0 - 1.0 completion score
    fullstack_missing_components: list = field(default_factory=list)  # ["frontend", "backend", ...]

    # Component-level verification
    frontend_verified: bool = False
    backend_verified: bool = False
    database_verified: bool = False
    integration_verified: bool = False

    # E2E test status
    e2e_tests_passed: bool = False
    crud_tests_passed: bool = False

    # =========================================================================
    # Differential Analysis Metrics (Phase 27 — Unified Engine)
    # =========================================================================
    differential_coverage_percent: float = 0.0  # 0-100
    differential_gaps_critical: int = 0
    differential_gaps_total: int = 0

    # Cross-Layer Validation Metrics (Phase 27 — Unified Engine)
    cross_layer_issues: int = 0
    cross_layer_critical_issues: int = 0

    # Browser console errors (from BrowserConsoleAgent)
    browser_console_errors: list = field(default_factory=list)

    # Deploy status
    deploy_succeeded: bool = False
    build_succeeded: bool = False

    # =========================================================================
    # Cell Colony Metrics (Autonomous Microservice Deployment)
    # =========================================================================

    # Cell counts by status
    total_cells: int = 0
    healthy_cells: int = 0
    degraded_cells: int = 0
    failed_cells: int = 0
    cells_in_recovery: int = 0
    cells_mutating: int = 0
    cells_initializing: int = 0
    cells_terminated: int = 0

    # Mutation tracking
    mutations_in_progress: int = 0
    successful_mutations: int = 0
    failed_mutations: int = 0
    pending_approvals: int = 0  # HIGH/CRITICAL mutations awaiting approval

    # Autophagy (cell termination after max failures)
    autophagy_count: int = 0
    autophagy_in_progress: int = 0

    # Colony-level operations
    colony_rebalance_in_progress: bool = False
    colony_scale_operations: int = 0

    # Kubernetes deployment tracking
    k8s_deployments_active: int = 0
    k8s_pods_ready: int = 0
    k8s_pods_pending: int = 0
    k8s_pods_failed: int = 0

    @property
    def colony_health_ratio(self) -> float:
        """
        Ratio of healthy cells to total cells (0.0-1.0).

        A ratio below 0.8 typically triggers colony rebalancing.
        Returns 1.0 if no cells exist (healthy by default).
        """
        if self.total_cells == 0:
            return 1.0
        return self.healthy_cells / self.total_cells

    @property
    def colony_needs_rebalance(self) -> bool:
        """Whether the colony health is below threshold and needs rebalancing."""
        return self.total_cells > 0 and self.colony_health_ratio < 0.8

    @property
    def colony_convergence_ready(self) -> bool:
        """Whether the colony has converged (all cells healthy, no pending operations)."""
        return (
            self.total_cells > 0 and
            self.healthy_cells == self.total_cells and
            self.mutations_in_progress == 0 and
            self.pending_approvals == 0 and
            self.cells_in_recovery == 0 and
            not self.colony_rebalance_in_progress
        )

    @property
    def backend_chain_complete(self) -> bool:
        """Whether the entire backend chain is complete."""
        return (
            self.database_schema_generated and
            self.api_routes_generated and
            self.auth_setup_complete and
            self.infrastructure_ready
        )

    # Timing
    iteration: int = 0
    started_at: Optional[datetime] = None
    last_update: Optional[datetime] = None

    @property
    def tests_passing_rate(self) -> float:
        """Percentage of tests passing (0-100)."""
        if self.total_tests == 0:
            return 100.0  # No tests = assume passing
        return (self.tests_passed / self.total_tests) * 100

    @property
    def test_pass_rate(self) -> float:
        """Alias for tests_passing_rate for backward compatibility."""
        return self.tests_passing_rate

    @property
    def assets_complete(self) -> bool:
        """Whether all required assets are generated."""
        return self.assets_generated >= self.assets_required

    @property
    def confidence_score(self) -> float:
        """
        Overall confidence score (0-1) that the system is ready.

        Weighs multiple factors:
        - Tests passing (40%)
        - Build success (25%)
        - No validation errors (20%)
        - No type errors (15%)
        """
        score = 0.0

        # Tests (40%)
        if self.total_tests > 0:
            score += 0.4 * (self.tests_passed / self.total_tests)
        else:
            score += 0.2  # Partial credit if no tests defined

        # Build (25%)
        if self.build_success:
            score += 0.25
        elif not self.build_attempted:
            score += 0.0  # No credit until build attempted

        # Validation errors (20%)
        if self.validation_errors == 0:
            score += 0.20
        else:
            # Partial credit based on how many errors
            penalty = min(self.validation_errors * 0.02, 0.20)
            score += max(0, 0.20 - penalty)

        # Type errors (15%)
        if self.type_errors == 0:
            score += 0.15
        else:
            penalty = min(self.type_errors * 0.015, 0.15)
            score += max(0, 0.15 - penalty)

        return round(score, 3)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "tests": {
                "total": self.total_tests,
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "skipped": self.tests_skipped,
                "passing_rate": self.tests_passing_rate,
                "pass_rate": self.test_pass_rate,  # Alias for backward compatibility
                "coverage": self.test_coverage,
            },
            "build": {
                "attempted": self.build_attempted,
                "success": self.build_success,
                "errors": self.build_errors,
            },
            "validation": {
                "errors": self.validation_errors,
                "warnings": self.validation_warnings,
            },
            "types": {
                "errors": self.type_errors,
                "warnings": self.type_warnings,
            },
            "lint": {
                "errors": self.lint_errors,
                "warnings": self.lint_warnings,
            },
            "assets": {
                "required": self.assets_required,
                "generated": self.assets_generated,
                "complete": self.assets_complete,
            },
            "runtime": {
                "tested": self.runtime_tested,
                "success": self.runtime_success,
                "errors": self.runtime_errors,
            },
            "sandbox": {
                "tested": self.sandbox_tested,
                "success": self.sandbox_success,
                "errors": self.sandbox_errors,
                "duration_ms": self.sandbox_duration_ms,
            },
            "cloud": {
                "tested": self.cloud_tested,
                "success": self.cloud_success,
                "platforms_tested": self.cloud_platforms_tested,
                "platforms_passed": self.cloud_platforms_passed,
            },
            "package": {
                "attempted": self.package_attempted,
                "success": self.package_success,
                "artifacts": self.package_artifacts,
            },
            "code": {
                "files_generated": self.files_generated,
                "files_modified": self.files_modified,
                "lines_of_code": self.lines_of_code,
            },
            "generator": {
                "pending": self.generator_pending,
                "started_at": self.generator_started_at.isoformat() if self.generator_started_at else None,
            },
            "deadlock": {
                "consecutive_same_errors": self.consecutive_same_errors,
                "is_stuck": self.is_stuck,
                "recent_error_count": len(self.recent_error_hashes),
            },
            # Task 14: Backend chain metrics
            "backend_chain": {
                "database_schema_generated": self.database_schema_generated,
                "api_routes_generated": self.api_routes_generated,
                "auth_setup_complete": self.auth_setup_complete,
                "infrastructure_ready": self.infrastructure_ready,
                "chain_complete": self.backend_chain_complete,
            },
            # Fullstack Verification metrics (Continuous Feedback Loop)
            "fullstack": {
                "verified": self.fullstack_verified,
                "score": self.fullstack_score,
                "missing_components": self.fullstack_missing_components,
                "frontend_verified": self.frontend_verified,
                "backend_verified": self.backend_verified,
                "database_verified": self.database_verified,
                "integration_verified": self.integration_verified,
                "e2e_tests_passed": self.e2e_tests_passed,
                "crud_tests_passed": self.crud_tests_passed,
                "browser_errors": len(self.browser_console_errors),
                "deploy_succeeded": self.deploy_succeeded,
                "build_succeeded": self.build_succeeded,
            },
            # Differential Analysis metrics (Phase 27)
            "differential": {
                "coverage_percent": self.differential_coverage_percent,
                "gaps_critical": self.differential_gaps_critical,
                "gaps_total": self.differential_gaps_total,
            },
            # Cross-Layer Validation metrics (Phase 27)
            "cross_layer": {
                "issues": self.cross_layer_issues,
                "critical_issues": self.cross_layer_critical_issues,
            },
            # Cell Colony metrics
            "colony": {
                "total_cells": self.total_cells,
                "healthy_cells": self.healthy_cells,
                "degraded_cells": self.degraded_cells,
                "failed_cells": self.failed_cells,
                "cells_in_recovery": self.cells_in_recovery,
                "cells_mutating": self.cells_mutating,
                "cells_initializing": self.cells_initializing,
                "cells_terminated": self.cells_terminated,
                "health_ratio": self.colony_health_ratio,
                "needs_rebalance": self.colony_needs_rebalance,
                "convergence_ready": self.colony_convergence_ready,
            },
            "colony_mutations": {
                "in_progress": self.mutations_in_progress,
                "successful": self.successful_mutations,
                "failed": self.failed_mutations,
                "pending_approvals": self.pending_approvals,
            },
            "colony_autophagy": {
                "count": self.autophagy_count,
                "in_progress": self.autophagy_in_progress,
            },
            "colony_operations": {
                "rebalance_in_progress": self.colony_rebalance_in_progress,
                "scale_operations": self.colony_scale_operations,
            },
            "k8s": {
                "deployments_active": self.k8s_deployments_active,
                "pods_ready": self.k8s_pods_ready,
                "pods_pending": self.k8s_pods_pending,
                "pods_failed": self.k8s_pods_failed,
            },
            "meta": {
                "iteration": self.iteration,
                "confidence_score": self.confidence_score,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "last_update": self.last_update.isoformat() if self.last_update else None,
            },
        }


class SharedState:
    """
    Thread-safe shared state for the agent society.

    Provides atomic updates and subscriptions to state changes.
    """

    def __init__(self):
        self._metrics = ConvergenceMetrics()
        self._lock = asyncio.Lock()
        self._change_handlers: list = []
        self.logger = logger.bind(component="shared_state")

        # Review Gate State (Pause/Resume for User Review)
        self.review_paused: bool = False
        self.review_feedback: Optional[str] = None
        self.review_pause_event: asyncio.Event = asyncio.Event()
        self.review_pause_event.set()  # Initially not paused (set = running)

        # Vite server log accessor (for 500 error context)
        self._vite_log_getter: Optional[Callable[[], list[str]]] = None

        # Rich Context Storage (set by HybridPipeline for agent access)
        # These enable agents to access diagrams, entities, design tokens, etc.
        self.tech_stack: Optional[Any] = None  # TechStack dict from documentation
        self.context_provider: Optional[Any] = None  # RichContextProvider or ContextProvider
        self.context_bridge: Optional[Any] = None  # AgentContextBridge for RAG-enhanced context
        self.doc_spec: Optional[Any] = None  # DocumentationSpec when using documentation format

        # Vibe-Coding: files touched by user are protected from pipeline re-generation
        self.user_managed_files: set[str] = set()

    @property
    def metrics(self) -> ConvergenceMetrics:
        """Get current metrics (read-only snapshot)."""
        return self._metrics

    def on_change(self, handler) -> None:
        """Register a handler to be called when state changes."""
        self._change_handlers.append(handler)

    def register_vite_log_source(self, getter: Callable[[], list[str]]) -> None:
        """
        Register a function to retrieve Vite server logs.

        Called by DevServerManager to expose its log buffer for 500 error debugging.

        Args:
            getter: Function that returns list of recent log lines
        """
        self._vite_log_getter = getter
        self.logger.debug("vite_log_source_registered")

    def mark_user_managed(self, file_paths: list[str]) -> None:
        """Mark files as user-managed. Pipeline validates but won't regenerate."""
        self.user_managed_files.update(file_paths)
        self.logger.info("user_managed_files_added", files=file_paths, total=len(self.user_managed_files))

    def is_user_managed(self, file_path: str) -> bool:
        """Check if a file was modified by user vibe-coding."""
        return file_path in self.user_managed_files

    def get_vite_logs(self, count: int = 50) -> list[str]:
        """
        Get recent Vite server logs if available.

        Used by BrowserErrorDetector to provide context for 500 errors.

        Args:
            count: Maximum number of lines to return

        Returns:
            List of recent log lines, or empty list if no source registered
        """
        if self._vite_log_getter:
            try:
                return self._vite_log_getter()[:count]
            except Exception as e:
                self.logger.debug("vite_log_fetch_failed", error=str(e))
        return []

    async def _notify_change(self) -> None:
        """Notify all change handlers."""
        for handler in self._change_handlers:
            try:
                result = handler(self._metrics)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error("change_handler_error", error=str(e))

    async def update_tests(
        self,
        total: Optional[int] = None,
        passed: Optional[int] = None,
        failed: Optional[int] = None,
        skipped: Optional[int] = None,
        coverage: Optional[float] = None,
    ) -> None:
        """Update test metrics."""
        async with self._lock:
            if total is not None:
                self._metrics.total_tests = total
            if passed is not None:
                self._metrics.tests_passed = passed
            if failed is not None:
                self._metrics.tests_failed = failed
            if skipped is not None:
                self._metrics.tests_skipped = skipped
            if coverage is not None:
                self._metrics.test_coverage = coverage
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "tests_updated",
            passed=self._metrics.tests_passed,
            failed=self._metrics.tests_failed,
        )

    async def update_build(
        self,
        attempted: bool = True,
        success: Optional[bool] = None,
        errors: Optional[int] = None,
    ) -> None:
        """Update build metrics."""
        async with self._lock:
            self._metrics.build_attempted = attempted
            if success is not None:
                self._metrics.build_success = success
            if errors is not None:
                self._metrics.build_errors = errors
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug("build_updated", success=self._metrics.build_success)

    async def update_validation(
        self,
        errors: Optional[int] = None,
        warnings: Optional[int] = None,
    ) -> None:
        """Update validation metrics."""
        async with self._lock:
            if errors is not None:
                self._metrics.validation_errors = errors
            if warnings is not None:
                self._metrics.validation_warnings = warnings
            self._metrics.last_update = datetime.now()

        await self._notify_change()

    async def update_types(
        self,
        errors: Optional[int] = None,
        warnings: Optional[int] = None,
    ) -> None:
        """Update type checking metrics."""
        async with self._lock:
            if errors is not None:
                self._metrics.type_errors = errors
            if warnings is not None:
                self._metrics.type_warnings = warnings
            self._metrics.last_update = datetime.now()

        await self._notify_change()

    async def update_lint(
        self,
        errors: Optional[int] = None,
        warnings: Optional[int] = None,
    ) -> None:
        """Update lint metrics."""
        async with self._lock:
            if errors is not None:
                self._metrics.lint_errors = errors
            if warnings is not None:
                self._metrics.lint_warnings = warnings
            self._metrics.last_update = datetime.now()

        await self._notify_change()

    async def update_assets(
        self,
        required: Optional[int] = None,
        generated: Optional[int] = None,
    ) -> None:
        """Update asset metrics."""
        async with self._lock:
            if required is not None:
                self._metrics.assets_required = required
            if generated is not None:
                self._metrics.assets_generated = generated
            self._metrics.last_update = datetime.now()

        await self._notify_change()

    async def update_runtime(
        self,
        tested: Optional[bool] = None,
        success: Optional[bool] = None,
        errors: Optional[int] = None,
    ) -> None:
        """Update runtime debug metrics."""
        async with self._lock:
            if tested is not None:
                self._metrics.runtime_tested = tested
            if success is not None:
                self._metrics.runtime_success = success
            if errors is not None:
                self._metrics.runtime_errors = errors
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "runtime_updated",
            tested=self._metrics.runtime_tested,
            success=self._metrics.runtime_success,
        )

    async def update_playwright_e2e(
        self,
        tested: Optional[bool] = None,
        success: Optional[bool] = None,
        tests_run: Optional[int] = None,
        tests_passed: Optional[int] = None,
        visual_issues: Optional[int] = None,
    ) -> None:
        """Update Playwright E2E visual testing metrics."""
        async with self._lock:
            if tested is not None:
                self._metrics.playwright_e2e_tested = tested
            if success is not None:
                self._metrics.playwright_e2e_success = success
            if tests_run is not None:
                self._metrics.playwright_e2e_tests_run = tests_run
            if tests_passed is not None:
                self._metrics.playwright_e2e_tests_passed = tests_passed
            if visual_issues is not None:
                self._metrics.playwright_visual_issues = visual_issues
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "playwright_e2e_updated",
            tested=self._metrics.playwright_e2e_tested,
            success=self._metrics.playwright_e2e_success,
            tests_passed=self._metrics.playwright_e2e_tests_passed,
        )

    async def update_sandbox(
        self,
        tested: Optional[bool] = None,
        success: Optional[bool] = None,
        errors: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Update Docker sandbox testing metrics."""
        async with self._lock:
            if tested is not None:
                self._metrics.sandbox_tested = tested
            if success is not None:
                self._metrics.sandbox_success = success
            if errors is not None:
                self._metrics.sandbox_errors = errors
            if duration_ms is not None:
                self._metrics.sandbox_duration_ms = duration_ms
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "sandbox_updated",
            tested=self._metrics.sandbox_tested,
            success=self._metrics.sandbox_success,
        )

    async def update_cloud(
        self,
        tested: Optional[bool] = None,
        success: Optional[bool] = None,
        platforms_tested: Optional[int] = None,
        platforms_passed: Optional[int] = None,
    ) -> None:
        """Update cloud (GitHub Actions) testing metrics."""
        async with self._lock:
            if tested is not None:
                self._metrics.cloud_tested = tested
            if success is not None:
                self._metrics.cloud_success = success
            if platforms_tested is not None:
                self._metrics.cloud_platforms_tested = platforms_tested
            if platforms_passed is not None:
                self._metrics.cloud_platforms_passed = platforms_passed
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "cloud_updated",
            tested=self._metrics.cloud_tested,
            success=self._metrics.cloud_success,
            platforms_passed=self._metrics.cloud_platforms_passed,
        )

    async def update_package(
        self,
        attempted: Optional[bool] = None,
        success: Optional[bool] = None,
        artifacts: Optional[int] = None,
    ) -> None:
        """Update packaging metrics."""
        async with self._lock:
            if attempted is not None:
                self._metrics.package_attempted = attempted
            if success is not None:
                self._metrics.package_success = success
            if artifacts is not None:
                self._metrics.package_artifacts = artifacts
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "package_updated",
            attempted=self._metrics.package_attempted,
            success=self._metrics.package_success,
        )

    async def update_code(
        self,
        files_generated: Optional[int] = None,
        files_modified: Optional[int] = None,
        increment_generated: bool = False,
        increment_modified: bool = False,
    ) -> None:
        """Update code metrics."""
        async with self._lock:
            if files_generated is not None:
                self._metrics.files_generated = files_generated
            elif increment_generated:
                self._metrics.files_generated += 1

            if files_modified is not None:
                self._metrics.files_modified = files_modified
            elif increment_modified:
                self._metrics.files_modified += 1

            self._metrics.last_update = datetime.now()

        await self._notify_change()

    async def increment_iteration(self) -> int:
        """Increment iteration counter and return new value."""
        async with self._lock:
            self._metrics.iteration += 1
            self._metrics.last_update = datetime.now()
            return self._metrics.iteration

    async def record_fix(self, files_count: int) -> None:
        """Record a fix was applied."""
        async with self._lock:
            self._metrics.files_modified += files_count
            self._metrics.last_update = datetime.now()
        await self._notify_change()

    async def set_generator_pending(self, pending: bool) -> None:
        """Set generator pending state for coordination."""
        async with self._lock:
            self._metrics.generator_pending = pending
            if pending:
                self._metrics.generator_started_at = datetime.now()
            else:
                self._metrics.generator_started_at = None
            self._metrics.last_update = datetime.now()

        self.logger.debug(
            "generator_state_changed",
            pending=pending,
        )

    async def record_error(self, error_hash: str, max_history: int = 10, stuck_threshold: int = 3) -> bool:
        """
        Record an error for deadlock detection.
        
        Args:
            error_hash: Hash of the error message
            max_history: Maximum number of error hashes to keep
            stuck_threshold: Number of consecutive same errors to trigger stuck state
            
        Returns:
            True if system is now stuck (same error repeated)
        """
        async with self._lock:
            # Check if this is the same error as the last one
            if self._metrics.recent_error_hashes and self._metrics.recent_error_hashes[-1] == error_hash:
                self._metrics.consecutive_same_errors += 1
            else:
                self._metrics.consecutive_same_errors = 1
            
            # Add to history, keeping only last N
            self._metrics.recent_error_hashes.append(error_hash)
            if len(self._metrics.recent_error_hashes) > max_history:
                self._metrics.recent_error_hashes = self._metrics.recent_error_hashes[-max_history:]
            
            # Check if stuck
            if self._metrics.consecutive_same_errors >= stuck_threshold:
                self._metrics.is_stuck = True
                self.logger.warning(
                    "deadlock_detected",
                    error_hash=error_hash[:50],
                    consecutive_count=self._metrics.consecutive_same_errors,
                )
            
            self._metrics.last_update = datetime.now()
            return self._metrics.is_stuck

        await self._notify_change()

    async def clear_stuck_state(self) -> None:
        """Clear the stuck state after successful fix."""
        async with self._lock:
            self._metrics.is_stuck = False
            self._metrics.consecutive_same_errors = 0
            self._metrics.recent_error_hashes = []
            self._metrics.last_update = datetime.now()

        self.logger.debug("stuck_state_cleared")

    # Task 14: Backend chain metrics update methods
    async def update_backend_chain(
        self,
        database_schema_generated: Optional[bool] = None,
        api_routes_generated: Optional[bool] = None,
        auth_setup_complete: Optional[bool] = None,
        infrastructure_ready: Optional[bool] = None,
    ) -> None:
        """Update backend chain metrics."""
        async with self._lock:
            if database_schema_generated is not None:
                self._metrics.database_schema_generated = database_schema_generated
            if api_routes_generated is not None:
                self._metrics.api_routes_generated = api_routes_generated
            if auth_setup_complete is not None:
                self._metrics.auth_setup_complete = auth_setup_complete
            if infrastructure_ready is not None:
                self._metrics.infrastructure_ready = infrastructure_ready
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "backend_chain_updated",
            database=self._metrics.database_schema_generated,
            api=self._metrics.api_routes_generated,
            auth=self._metrics.auth_setup_complete,
            infra=self._metrics.infrastructure_ready,
            chain_complete=self._metrics.backend_chain_complete,
        )

    # =========================================================================
    # Fullstack Verification Metrics Update Methods (Continuous Feedback Loop)
    # =========================================================================

    async def update_fullstack(
        self,
        verified: Optional[bool] = None,
        score: Optional[float] = None,
        missing_components: Optional[list] = None,
        frontend_verified: Optional[bool] = None,
        backend_verified: Optional[bool] = None,
        database_verified: Optional[bool] = None,
        integration_verified: Optional[bool] = None,
        e2e_tests_passed: Optional[bool] = None,
        crud_tests_passed: Optional[bool] = None,
        browser_console_errors: Optional[list] = None,
        deploy_succeeded: Optional[bool] = None,
        build_succeeded: Optional[bool] = None,
    ) -> None:
        """Update fullstack verification metrics."""
        async with self._lock:
            if verified is not None:
                self._metrics.fullstack_verified = verified
            if score is not None:
                self._metrics.fullstack_score = score
            if missing_components is not None:
                self._metrics.fullstack_missing_components = missing_components
            if frontend_verified is not None:
                self._metrics.frontend_verified = frontend_verified
            if backend_verified is not None:
                self._metrics.backend_verified = backend_verified
            if database_verified is not None:
                self._metrics.database_verified = database_verified
            if integration_verified is not None:
                self._metrics.integration_verified = integration_verified
            if e2e_tests_passed is not None:
                self._metrics.e2e_tests_passed = e2e_tests_passed
            if crud_tests_passed is not None:
                self._metrics.crud_tests_passed = crud_tests_passed
            if browser_console_errors is not None:
                self._metrics.browser_console_errors = browser_console_errors
            if deploy_succeeded is not None:
                self._metrics.deploy_succeeded = deploy_succeeded
            if build_succeeded is not None:
                self._metrics.build_succeeded = build_succeeded
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "fullstack_updated",
            verified=self._metrics.fullstack_verified,
            score=self._metrics.fullstack_score,
            missing=self._metrics.fullstack_missing_components,
        )

    # =========================================================================
    # Differential Analysis + Cross-Layer Validation Update Methods (Phase 27)
    # =========================================================================

    async def update_differential(
        self,
        coverage_percent: Optional[float] = None,
        gaps_critical: Optional[int] = None,
        gaps_total: Optional[int] = None,
    ) -> None:
        """Update differential analysis metrics."""
        async with self._lock:
            if coverage_percent is not None:
                self._metrics.differential_coverage_percent = coverage_percent
            if gaps_critical is not None:
                self._metrics.differential_gaps_critical = gaps_critical
            if gaps_total is not None:
                self._metrics.differential_gaps_total = gaps_total
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "differential_updated",
            coverage=self._metrics.differential_coverage_percent,
            gaps_critical=self._metrics.differential_gaps_critical,
            gaps_total=self._metrics.differential_gaps_total,
        )

    async def update_cross_layer(
        self,
        issues: Optional[int] = None,
        critical_issues: Optional[int] = None,
    ) -> None:
        """Update cross-layer validation metrics."""
        async with self._lock:
            if issues is not None:
                self._metrics.cross_layer_issues = issues
            if critical_issues is not None:
                self._metrics.cross_layer_critical_issues = critical_issues
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "cross_layer_updated",
            issues=self._metrics.cross_layer_issues,
            critical=self._metrics.cross_layer_critical_issues,
        )

    # =========================================================================
    # Cell Colony Metrics Update Methods
    # =========================================================================

    async def update_colony_cells(
        self,
        total_cells: Optional[int] = None,
        healthy_cells: Optional[int] = None,
        degraded_cells: Optional[int] = None,
        failed_cells: Optional[int] = None,
        cells_in_recovery: Optional[int] = None,
        cells_mutating: Optional[int] = None,
        cells_initializing: Optional[int] = None,
        cells_terminated: Optional[int] = None,
    ) -> None:
        """Update cell count metrics."""
        async with self._lock:
            if total_cells is not None:
                self._metrics.total_cells = total_cells
            if healthy_cells is not None:
                self._metrics.healthy_cells = healthy_cells
            if degraded_cells is not None:
                self._metrics.degraded_cells = degraded_cells
            if failed_cells is not None:
                self._metrics.failed_cells = failed_cells
            if cells_in_recovery is not None:
                self._metrics.cells_in_recovery = cells_in_recovery
            if cells_mutating is not None:
                self._metrics.cells_mutating = cells_mutating
            if cells_initializing is not None:
                self._metrics.cells_initializing = cells_initializing
            if cells_terminated is not None:
                self._metrics.cells_terminated = cells_terminated
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "colony_cells_updated",
            total=self._metrics.total_cells,
            healthy=self._metrics.healthy_cells,
            degraded=self._metrics.degraded_cells,
            health_ratio=self._metrics.colony_health_ratio,
        )

    async def update_colony_mutations(
        self,
        in_progress: Optional[int] = None,
        successful: Optional[int] = None,
        failed: Optional[int] = None,
        pending_approvals: Optional[int] = None,
        increment_successful: bool = False,
        increment_failed: bool = False,
    ) -> None:
        """Update mutation tracking metrics."""
        async with self._lock:
            if in_progress is not None:
                self._metrics.mutations_in_progress = in_progress
            if successful is not None:
                self._metrics.successful_mutations = successful
            elif increment_successful:
                self._metrics.successful_mutations += 1
            if failed is not None:
                self._metrics.failed_mutations = failed
            elif increment_failed:
                self._metrics.failed_mutations += 1
            if pending_approvals is not None:
                self._metrics.pending_approvals = pending_approvals
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "colony_mutations_updated",
            in_progress=self._metrics.mutations_in_progress,
            successful=self._metrics.successful_mutations,
            failed=self._metrics.failed_mutations,
            pending_approvals=self._metrics.pending_approvals,
        )

    async def update_colony_autophagy(
        self,
        count: Optional[int] = None,
        in_progress: Optional[int] = None,
        increment_count: bool = False,
    ) -> None:
        """Update autophagy metrics."""
        async with self._lock:
            if count is not None:
                self._metrics.autophagy_count = count
            elif increment_count:
                self._metrics.autophagy_count += 1
            if in_progress is not None:
                self._metrics.autophagy_in_progress = in_progress
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "colony_autophagy_updated",
            count=self._metrics.autophagy_count,
            in_progress=self._metrics.autophagy_in_progress,
        )

    async def update_colony_operations(
        self,
        rebalance_in_progress: Optional[bool] = None,
        scale_operations: Optional[int] = None,
        increment_scale_ops: bool = False,
    ) -> None:
        """Update colony operation metrics."""
        async with self._lock:
            if rebalance_in_progress is not None:
                self._metrics.colony_rebalance_in_progress = rebalance_in_progress
            if scale_operations is not None:
                self._metrics.colony_scale_operations = scale_operations
            elif increment_scale_ops:
                self._metrics.colony_scale_operations += 1
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "colony_operations_updated",
            rebalance=self._metrics.colony_rebalance_in_progress,
            scale_ops=self._metrics.colony_scale_operations,
        )

    async def update_k8s_status(
        self,
        deployments_active: Optional[int] = None,
        pods_ready: Optional[int] = None,
        pods_pending: Optional[int] = None,
        pods_failed: Optional[int] = None,
    ) -> None:
        """Update Kubernetes deployment status."""
        async with self._lock:
            if deployments_active is not None:
                self._metrics.k8s_deployments_active = deployments_active
            if pods_ready is not None:
                self._metrics.k8s_pods_ready = pods_ready
            if pods_pending is not None:
                self._metrics.k8s_pods_pending = pods_pending
            if pods_failed is not None:
                self._metrics.k8s_pods_failed = pods_failed
            self._metrics.last_update = datetime.now()

        await self._notify_change()
        self.logger.debug(
            "k8s_status_updated",
            deployments=self._metrics.k8s_deployments_active,
            pods_ready=self._metrics.k8s_pods_ready,
            pods_pending=self._metrics.k8s_pods_pending,
            pods_failed=self._metrics.k8s_pods_failed,
        )

    # =========================================================================
    # Generic set/get for Custom Metrics (Used by various agents)
    # =========================================================================

    async def set(self, key: str, value: Any) -> None:
        """Set a custom metric value for agents."""
        async with self._lock:
            if not hasattr(self._metrics, '_custom'):
                object.__setattr__(self._metrics, '_custom', {})
            self._metrics._custom[key] = value
            self._metrics.last_update = datetime.now()
        await self._notify_change()
        self.logger.debug("custom_metric_set", key=key)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a custom metric value."""
        if hasattr(self._metrics, '_custom'):
            return self._metrics._custom.get(key, default)
        return default

    async def start(self) -> None:
        """Mark the start of processing."""
        async with self._lock:
            self._metrics.started_at = datetime.now()
            self._metrics.last_update = datetime.now()
            self._metrics.iteration = 0

    async def reset(self) -> None:
        """Reset all metrics."""
        async with self._lock:
            self._metrics = ConvergenceMetrics()

        self.logger.info("state_reset")

    def get_summary(self) -> str:
        """Get a human-readable summary of current state."""
        m = self._metrics
        return (
            f"Iteration {m.iteration} | "
            f"Tests: {m.tests_passed}/{m.total_tests} | "
            f"Build: {'OK' if m.build_success else 'FAIL' if m.build_attempted else 'PENDING'} | "
            f"Errors: {m.validation_errors} val, {m.type_errors} type | "
            f"Confidence: {m.confidence_score:.1%}"
        )

    # =========================================================================
    # Review Gate Methods (Pause/Resume for User Review)
    # =========================================================================

    async def pause_for_review(self) -> None:
        """Pause generation for user review."""
        async with self._lock:
            self.review_paused = True
            self.review_pause_event.clear()  # Block waiting agents
        self.logger.info("review_paused", message="Generation paused for user review")

    async def resume_from_review(self, feedback: Optional[str] = None) -> None:
        """Resume generation after user review."""
        async with self._lock:
            self.review_feedback = feedback
            self.review_paused = False
            self.review_pause_event.set()  # Unblock waiting agents
        self.logger.info(
            "review_resumed",
            has_feedback=bool(feedback),
            feedback_length=len(feedback) if feedback else 0
        )

    async def submit_review_feedback(self, feedback: str) -> None:
        """Submit additional feedback during pause."""
        async with self._lock:
            if self.review_feedback:
                self.review_feedback += "\n\n" + feedback
            else:
                self.review_feedback = feedback
        self.logger.debug(
            "review_feedback_submitted",
            feedback_length=len(feedback)
        )

    def get_review_feedback(self) -> Optional[str]:
        """Get and clear accumulated review feedback."""
        feedback = self.review_feedback
        self.review_feedback = None
        return feedback

    def get_review_status(self) -> dict:
        """Get current review gate status."""
        return {
            "paused": self.review_paused,
            "has_feedback": bool(self.review_feedback),
            "feedback_preview": self.review_feedback[:100] if self.review_feedback else None,
            "user_managed_count": len(self.user_managed_files),
        }
