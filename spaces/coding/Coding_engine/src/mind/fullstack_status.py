"""
FullstackStatus - Tracks verification status of all fullstack components.

Used by FullstackVerifierAgent to check if all components (frontend, backend,
database, integration) are generated and working. FULLSTACK_VERIFIED is the
termination condition for autonomous generation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class ComponentCheck:
    """Result of a single component check."""
    name: str
    passed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ComponentStatus:
    """Status of a fullstack component (frontend, backend, database, integration)."""
    component: str  # "frontend", "backend", "database", "integration"
    is_complete: bool = False
    checks: List[ComponentCheck] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    failing: List[str] = field(default_factory=list)
    last_checked: Optional[datetime] = None

    @property
    def passed_checks(self) -> List[str]:
        """Get names of passed checks."""
        return [c.name for c in self.checks if c.passed]

    @property
    def failed_checks(self) -> List[str]:
        """Get names of failed checks."""
        return [c.name for c in self.checks if not c.passed]

    def add_check(self, name: str, passed: bool, message: str = "", details: Dict[str, Any] = None) -> None:
        """Add a check result."""
        self.checks.append(ComponentCheck(
            name=name,
            passed=passed,
            message=message,
            details=details or {},
        ))
        if not passed:
            if name not in self.failing:
                self.failing.append(name)
        self.last_checked = datetime.now()

    def update_completeness(self) -> None:
        """Update is_complete based on checks."""
        # Complete if all checks passed and no missing/failing items
        all_passed = all(c.passed for c in self.checks) if self.checks else False
        no_missing = len(self.missing) == 0
        no_failing = len(self.failing) == 0
        self.is_complete = all_passed and no_missing and no_failing


@dataclass
class FullstackStatus:
    """
    Complete status of fullstack verification.

    Tracks frontend, backend, database, and integration components.
    FULLSTACK_VERIFIED event is published when is_complete is True.
    """

    # Component statuses
    frontend: ComponentStatus = field(default_factory=lambda: ComponentStatus(component="frontend"))
    backend: ComponentStatus = field(default_factory=lambda: ComponentStatus(component="backend"))
    database: ComponentStatus = field(default_factory=lambda: ComponentStatus(component="database"))
    integration: ComponentStatus = field(default_factory=lambda: ComponentStatus(component="integration"))

    # Overall tracking
    overall_score: float = 0.0  # 0.0 to 1.0
    iteration: int = 0
    last_verified: Optional[datetime] = None

    # Checklist definitions
    FRONTEND_CHECKS: List[str] = field(default_factory=lambda: [
        "components_exist",
        "renders_without_error",
        "no_console_errors",
        "routes_defined",
    ])

    BACKEND_CHECKS: List[str] = field(default_factory=lambda: [
        "api_responds",
        "endpoints_match_contracts",
        "auth_works",
        "health_check_passes",
    ])

    DATABASE_CHECKS: List[str] = field(default_factory=lambda: [
        "schema_exists",
        "schema_applied",
        "crud_works",
        "relations_valid",
    ])

    INTEGRATION_CHECKS: List[str] = field(default_factory=lambda: [
        "frontend_calls_backend",
        "auth_flow_works",
        "data_persists",
        "e2e_critical_flows_pass",
    ])

    @property
    def is_complete(self) -> bool:
        """Check if all fullstack components are complete."""
        return (
            self.frontend.is_complete and
            self.backend.is_complete and
            self.database.is_complete and
            self.integration.is_complete
        )

    @property
    def missing_components(self) -> List[str]:
        """Get list of incomplete component names."""
        missing = []
        if not self.frontend.is_complete:
            missing.append("frontend")
        if not self.backend.is_complete:
            missing.append("backend")
        if not self.database.is_complete:
            missing.append("database")
        if not self.integration.is_complete:
            missing.append("integration")
        return missing

    @property
    def failing_checks(self) -> Dict[str, List[str]]:
        """Get failing checks by component."""
        return {
            "frontend": self.frontend.failed_checks,
            "backend": self.backend.failed_checks,
            "database": self.database.failed_checks,
            "integration": self.integration.failed_checks,
        }

    def calculate_score(self) -> float:
        """Calculate overall completion score (0.0 to 1.0)."""
        total_checks = 0
        passed_checks = 0

        for component in [self.frontend, self.backend, self.database, self.integration]:
            total_checks += len(component.checks)
            passed_checks += len(component.passed_checks)

        if total_checks == 0:
            return 0.0

        self.overall_score = passed_checks / total_checks
        return self.overall_score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event data."""
        return {
            "is_complete": self.is_complete,
            "overall_score": self.calculate_score(),
            "iteration": self.iteration,
            "missing_components": self.missing_components,
            "failing_checks": self.failing_checks,
            "frontend": {
                "complete": self.frontend.is_complete,
                "passed": self.frontend.passed_checks,
                "failed": self.frontend.failed_checks,
                "missing": self.frontend.missing,
            },
            "backend": {
                "complete": self.backend.is_complete,
                "passed": self.backend.passed_checks,
                "failed": self.backend.failed_checks,
                "missing": self.backend.missing,
            },
            "database": {
                "complete": self.database.is_complete,
                "passed": self.database.passed_checks,
                "failed": self.database.failed_checks,
                "missing": self.database.missing,
            },
            "integration": {
                "complete": self.integration.is_complete,
                "passed": self.integration.passed_checks,
                "failed": self.integration.failed_checks,
                "missing": self.integration.missing,
            },
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FullstackStatus":
        """Create from dictionary."""
        status = cls()
        status.iteration = data.get("iteration", 0)
        status.overall_score = data.get("overall_score", 0.0)

        # Restore component statuses
        for comp_name in ["frontend", "backend", "database", "integration"]:
            comp_data = data.get(comp_name, {})
            comp_status = getattr(status, comp_name)
            comp_status.is_complete = comp_data.get("complete", False)
            comp_status.missing = comp_data.get("missing", [])

            # Reconstruct checks from passed/failed lists
            for check_name in comp_data.get("passed", []):
                comp_status.add_check(check_name, True)
            for check_name in comp_data.get("failed", []):
                comp_status.add_check(check_name, False)

        return status

    def reset_checks(self) -> None:
        """Reset all checks for a new verification cycle."""
        for component in [self.frontend, self.backend, self.database, self.integration]:
            component.checks = []
            component.failing = []
            component.is_complete = False

        self.iteration += 1
        self.overall_score = 0.0
