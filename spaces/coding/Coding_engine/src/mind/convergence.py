"""
Convergence - Defines when the system is "done".

Provides flexible criteria for determining when the agent society
has achieved its goals and can stop iterating.
"""

from dataclasses import dataclass
from typing import Optional
from .shared_state import ConvergenceMetrics


@dataclass
class ConvergenceCriteria:
    """
    Configurable criteria for convergence.

    All enabled criteria must be met for convergence.
    Set a criterion to None to disable it.
    """
    # Test requirements
    min_tests_passing_rate: Optional[float] = 95.0  # Percentage (0-100)
    require_all_tests_pass: bool = False  # Strict mode: 100% required
    min_test_coverage: Optional[float] = None  # Optional coverage requirement

    # Build requirements
    require_build_success: bool = True

    # Error limits
    max_validation_errors: int = 0
    max_type_errors: int = 0
    max_lint_errors: Optional[int] = None  # None = unlimited

    # Confidence threshold
    min_confidence_score: float = 0.85  # 0-1

    # Iteration limits
    max_iterations: int = 50  # Safety limit
    min_iterations: int = 1  # Ensure at least one full pass

    # Time limits (seconds)
    max_time_seconds: Optional[int] = 600  # 10 minutes default

    # Asset requirements
    require_assets_complete: bool = False

    # UI Validation requirements (FrontendValidator)
    require_ui_validation: bool = False  # Enable UI validation via Playwright
    min_ui_validation_score: Optional[float] = 0.8  # 0-1, UI must match requirements
    require_all_ui_requirements: bool = False  # Strict: all UI requirements must match

    # Deadlock detection (NEW)
    enable_deadlock_detection: bool = True  # Enable stuck/deadlock detection
    stuck_threshold: int = 3  # Converge early if same error repeated N times
    force_converge_on_stuck: bool = True  # Force convergence when stuck (vs blocking)

    # Task 18: Backend chain completion (for full-stack projects)
    require_backend_chain_complete: bool = False  # Require DB→API→Auth→Infra chain

    # Fullstack Verification (Continuous Feedback Loop termination condition)
    require_fullstack_verified: bool = False  # Require FULLSTACK_VERIFIED event
    fullstack_components: tuple = ("frontend", "backend", "database", "integration")  # Components to verify
    min_fullstack_score: float = 0.9  # Minimum fullstack completion score (0-1)

    # Differential Analysis (Phase 27 — Unified Engine)
    require_differential_coverage: bool = False
    min_differential_coverage: Optional[float] = None  # 0-100

    # Cross-Layer Validation (Phase 27 — Unified Engine)
    max_cross_layer_critical: Optional[int] = None  # Max critical issues allowed


def is_converged(
    metrics: ConvergenceMetrics,
    criteria: ConvergenceCriteria,
    elapsed_seconds: float = 0,
) -> tuple[bool, list[str]]:
    """
    Check if the system has converged.

    Args:
        metrics: Current system metrics
        criteria: Convergence criteria to check against
        elapsed_seconds: Time elapsed since start

    Returns:
        Tuple of (converged: bool, reasons: list[str])
        - If converged, reasons lists why we're done
        - If not converged, reasons lists what's blocking
    """
    blocking_reasons = []
    success_reasons = []

    # Check minimum iterations
    if metrics.iteration < criteria.min_iterations:
        blocking_reasons.append(
            f"Minimum iterations not reached ({metrics.iteration}/{criteria.min_iterations})"
        )
        return False, blocking_reasons

    # Check max iterations (force convergence)
    if metrics.iteration >= criteria.max_iterations:
        success_reasons.append(f"Maximum iterations reached ({criteria.max_iterations})")
        return True, success_reasons

    # Check time limit (force convergence)
    if criteria.max_time_seconds and elapsed_seconds >= criteria.max_time_seconds:
        success_reasons.append(f"Time limit reached ({criteria.max_time_seconds}s)")
        return True, success_reasons

    # Check deadlock/stuck state (NEW)
    if criteria.enable_deadlock_detection and metrics.is_stuck:
        if criteria.force_converge_on_stuck:
            success_reasons.append(
                f"Deadlock detected - same error repeated {metrics.consecutive_same_errors}x"
            )
            return True, success_reasons
        else:
            # Just report it but don't force convergence
            blocking_reasons.append(
                f"System stuck - same error repeated {metrics.consecutive_same_errors}x"
            )

    # Check test requirements
    if criteria.require_all_tests_pass:
        if metrics.tests_failed > 0:
            blocking_reasons.append(f"{metrics.tests_failed} tests still failing")
    elif criteria.min_tests_passing_rate is not None:
        if metrics.tests_passing_rate < criteria.min_tests_passing_rate:
            blocking_reasons.append(
                f"Tests passing rate {metrics.tests_passing_rate:.1f}% < {criteria.min_tests_passing_rate}%"
            )

    # Check test coverage
    if criteria.min_test_coverage is not None:
        if metrics.test_coverage < criteria.min_test_coverage:
            blocking_reasons.append(
                f"Test coverage {metrics.test_coverage:.1f}% < {criteria.min_test_coverage}%"
            )

    # Check build success
    if criteria.require_build_success:
        if not metrics.build_attempted:
            blocking_reasons.append("Build not yet attempted")
        elif not metrics.build_success:
            blocking_reasons.append("Build is failing")

    # Check validation errors
    if metrics.validation_errors > criteria.max_validation_errors:
        blocking_reasons.append(
            f"{metrics.validation_errors} validation errors > max {criteria.max_validation_errors}"
        )

    # Check type errors
    if metrics.type_errors > criteria.max_type_errors:
        blocking_reasons.append(
            f"{metrics.type_errors} type errors > max {criteria.max_type_errors}"
        )

    # Check lint errors (if limit set)
    if criteria.max_lint_errors is not None:
        if metrics.lint_errors > criteria.max_lint_errors:
            blocking_reasons.append(
                f"{metrics.lint_errors} lint errors > max {criteria.max_lint_errors}"
            )

    # Check confidence score
    if metrics.confidence_score < criteria.min_confidence_score:
        blocking_reasons.append(
            f"Confidence {metrics.confidence_score:.1%} < {criteria.min_confidence_score:.1%}"
        )

    # Check assets
    if criteria.require_assets_complete and not metrics.assets_complete:
        blocking_reasons.append(
            f"Assets incomplete ({metrics.assets_generated}/{metrics.assets_required})"
        )

    # Check UI validation
    if criteria.require_ui_validation:
        if not metrics.ui_validation_attempted:
            blocking_reasons.append("UI validation not yet attempted")
        elif criteria.require_all_ui_requirements:
            if metrics.ui_requirements_matched < metrics.ui_requirements_total:
                blocking_reasons.append(
                    f"UI requirements not fully matched ({metrics.ui_requirements_matched}/{metrics.ui_requirements_total})"
                )
        elif criteria.min_ui_validation_score is not None:
            if metrics.ui_validation_score < criteria.min_ui_validation_score:
                blocking_reasons.append(
                    f"UI validation score {metrics.ui_validation_score:.1%} < {criteria.min_ui_validation_score:.1%}"
                )

    # Task 18: Check backend chain completion (for full-stack projects)
    if criteria.require_backend_chain_complete:
        if not metrics.backend_chain_complete:
            # Report which parts are incomplete
            missing = []
            if not metrics.database_schema_generated:
                missing.append("database schema")
            if not metrics.api_routes_generated:
                missing.append("API routes")
            if not metrics.auth_setup_complete:
                missing.append("auth setup")
            if not metrics.infrastructure_ready:
                missing.append("infrastructure")
            blocking_reasons.append(
                f"Backend chain incomplete: missing {', '.join(missing)}"
            )

    # Fullstack Verification (Continuous Feedback Loop termination condition)
    if criteria.require_fullstack_verified:
        if not metrics.fullstack_verified:
            missing = metrics.fullstack_missing_components or []
            if missing:
                blocking_reasons.append(
                    f"Fullstack incomplete: missing {', '.join(missing)}"
                )
            else:
                blocking_reasons.append("Fullstack verification not yet completed")
        elif metrics.fullstack_score < criteria.min_fullstack_score:
            blocking_reasons.append(
                f"Fullstack score {metrics.fullstack_score:.1%} < {criteria.min_fullstack_score:.1%}"
            )

    # Differential coverage check (Phase 27)
    if criteria.require_differential_coverage and criteria.min_differential_coverage is not None:
        if metrics.differential_coverage_percent < criteria.min_differential_coverage:
            blocking_reasons.append(
                f"Differential coverage {metrics.differential_coverage_percent:.1f}% "
                f"< {criteria.min_differential_coverage}%"
            )

    # Cross-layer critical issues check (Phase 27)
    if criteria.max_cross_layer_critical is not None:
        if metrics.cross_layer_critical_issues > criteria.max_cross_layer_critical:
            blocking_reasons.append(
                f"{metrics.cross_layer_critical_issues} critical cross-layer issues "
                f"> max {criteria.max_cross_layer_critical}"
            )

    # Determine convergence
    if blocking_reasons:
        return False, blocking_reasons
    else:
        success_reasons.append("All convergence criteria met")
        return True, success_reasons


def get_progress_percentage(
    metrics: ConvergenceMetrics,
    criteria: ConvergenceCriteria,
) -> float:
    """
    Estimate overall progress toward convergence (0-100).

    Useful for progress bars and user feedback.
    """
    weights = {
        "tests": 0.30,
        "build": 0.25,
        "validation": 0.20,
        "types": 0.15,
        "confidence": 0.10,
    }

    progress = 0.0

    # Tests progress
    if criteria.min_tests_passing_rate:
        test_progress = min(
            metrics.tests_passing_rate / criteria.min_tests_passing_rate,
            1.0
        )
        progress += weights["tests"] * test_progress
    else:
        progress += weights["tests"]  # Full credit if no test requirement

    # Build progress
    if criteria.require_build_success:
        if metrics.build_success:
            progress += weights["build"]
        elif metrics.build_attempted:
            progress += weights["build"] * 0.5  # Partial for attempt
    else:
        progress += weights["build"]

    # Validation progress (inverse of errors)
    if criteria.max_validation_errors == 0:
        if metrics.validation_errors == 0:
            progress += weights["validation"]
        else:
            # Diminishing returns as errors increase
            progress += weights["validation"] * max(0, 1 - (metrics.validation_errors * 0.1))
    else:
        progress += weights["validation"]

    # Type errors progress
    if criteria.max_type_errors == 0:
        if metrics.type_errors == 0:
            progress += weights["types"]
        else:
            progress += weights["types"] * max(0, 1 - (metrics.type_errors * 0.1))
    else:
        progress += weights["types"]

    # Confidence progress
    if metrics.confidence_score >= criteria.min_confidence_score:
        progress += weights["confidence"]
    else:
        progress += weights["confidence"] * (
            metrics.confidence_score / criteria.min_confidence_score
        )

    return round(progress * 100, 1)


# Preset criteria configurations

STRICT_CRITERIA = ConvergenceCriteria(
    require_all_tests_pass=True,
    require_build_success=True,
    max_validation_errors=0,
    max_type_errors=0,
    max_lint_errors=0,
    min_confidence_score=0.95,
)

RELAXED_CRITERIA = ConvergenceCriteria(
    min_tests_passing_rate=80.0,
    require_build_success=True,
    max_validation_errors=5,
    max_type_errors=10,
    min_confidence_score=0.70,
    max_iterations=20,
)

FAST_ITERATION_CRITERIA = ConvergenceCriteria(
    min_tests_passing_rate=70.0,
    require_build_success=True,
    max_validation_errors=10,
    max_type_errors=20,
    min_confidence_score=0.60,
    max_iterations=10,
    max_time_seconds=300,  # 5 minutes
)

DEFAULT_CRITERIA = ConvergenceCriteria()  # Uses default values

# Full automation - no human intervention allowed
AUTONOMOUS_CRITERIA = ConvergenceCriteria(
    # ALL tests must pass - no exceptions
    require_all_tests_pass=True,
    min_tests_passing_rate=100.0,

    # Build must succeed
    require_build_success=True,

    # Zero tolerance for errors
    max_validation_errors=0,
    max_type_errors=0,
    max_lint_errors=0,

    # High confidence required
    min_confidence_score=0.95,

    # Extended limits for autonomous operation
    max_iterations=200,  # More attempts allowed
    min_iterations=3,    # Ensure multiple passes
    max_time_seconds=3600,  # 1 hour timeout

    # All assets required
    require_assets_complete=True,

    # Task 18: Require full backend chain for full-stack projects
    require_backend_chain_complete=True,

    # Fullstack Verification - TERMINATION CONDITION
    require_fullstack_verified=True,
    min_fullstack_score=0.95,

    # Differential Analysis + Cross-Layer (Phase 27)
    require_differential_coverage=True,
    min_differential_coverage=80.0,
    max_cross_layer_critical=0,
)


# Fullstack-focused criteria (for frontend+backend+database projects)
FULLSTACK_CRITERIA = ConvergenceCriteria(
    # Tests
    min_tests_passing_rate=90.0,
    require_build_success=True,

    # Errors
    max_validation_errors=0,
    max_type_errors=0,

    # Confidence
    min_confidence_score=0.85,

    # Limits
    max_iterations=100,
    min_iterations=2,
    max_time_seconds=1800,  # 30 minutes

    # Backend chain
    require_backend_chain_complete=True,

    # Fullstack verification as termination condition
    require_fullstack_verified=True,
    min_fullstack_score=0.9,
)
