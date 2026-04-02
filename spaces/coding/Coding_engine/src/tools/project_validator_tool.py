"""
Project Validator Tool - Orchestrates post-generation validation.

Runs all applicable validators and collects results for recovery processing.
Supports dynamic validator selection based on ProjectProfile.

Enhanced with:
- Batch validation for multiple projects
- ValidationPool for concurrent validation management
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import structlog

from ..validators.base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)
from ..validators.electron_validator import ElectronValidator
from ..validators.typescript_validator import TypeScriptValidator, TypeScriptBuildValidator
from ..validators.build_validator import BuildValidator, DependencyValidator
from ..validators.completeness_validator import FileCompletenessValidator
from ..validators.python_validator import PythonValidator, PythonDependencyValidator

if TYPE_CHECKING:
    from ..engine.project_analyzer import ProjectProfile


logger = structlog.get_logger(__name__)


# Registry of all available validators
VALIDATOR_REGISTRY: dict[str, type[BaseValidator]] = {
    "completeness": FileCompletenessValidator,  # Check for truncated files first
    "dependencies": DependencyValidator,
    "typescript": TypeScriptValidator,
    "typescript_build": TypeScriptBuildValidator,
    "build": BuildValidator,
    "electron": ElectronValidator,
    "python": PythonValidator,
    "python_dependencies": PythonDependencyValidator,
}


@dataclass
class BatchValidationResult:
    """Result from batch validation of multiple projects."""
    total_projects: int = 0
    successful: int = 0
    failed: int = 0
    results: dict[str, ValidationResult] = field(default_factory=dict)
    total_errors: int = 0
    total_warnings: int = 0
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "total_projects": self.total_projects,
            "successful": self.successful,
            "failed": self.failed,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "execution_time_ms": self.execution_time_ms,
            "results": {k: v.to_dict() for k, v in self.results.items()},
        }


class ValidationPool:
    """
    Pool for managing concurrent validations.
    
    Provides:
    - Semaphore-based concurrency limiting
    - Batch validation orchestration
    - Progress tracking
    """
    
    def __init__(self, max_concurrent: int = 4):
        """
        Initialize validation pool.
        
        Args:
            max_concurrent: Maximum concurrent validations
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.logger = logger.bind(component="validation_pool")
    
    async def validate_project(
        self,
        project_dir: str,
        profile: Optional["ProjectProfile"] = None,
    ) -> ValidationResult:
        """
        Validate a single project with semaphore limiting.
        
        Args:
            project_dir: Project directory to validate
            profile: Optional project profile
            
        Returns:
            ValidationResult
        """
        async with self._semaphore:
            tool = ProjectValidatorTool(project_dir, profile=profile)
            return await tool.validate(parallel=True)
    
    async def validate_batch(
        self,
        projects: list[str],
        profiles: Optional[dict[str, "ProjectProfile"]] = None,
    ) -> BatchValidationResult:
        """
        Validate multiple projects in parallel.
        
        Args:
            projects: List of project directories
            profiles: Optional dict mapping project dir to profile
            
        Returns:
            BatchValidationResult with all results
        """
        start_time = time.time()
        profiles = profiles or {}
        
        self.logger.info(
            "batch_validation_starting",
            projects=len(projects),
            max_concurrent=self.max_concurrent,
        )
        
        # Create tasks for all projects
        tasks = []
        for project_dir in projects:
            profile = profiles.get(project_dir)
            tasks.append(self.validate_project(project_dir, profile))
        
        # Execute all with gather
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build batch result
        batch_result = BatchValidationResult(
            total_projects=len(projects),
        )
        
        for project_dir, result in zip(projects, results):
            if isinstance(result, Exception):
                # Create failure result
                error_result = ValidationResult(project_dir=project_dir)
                error_result.add_failure(ValidationFailure(
                    check_type="validation_pool",
                    error_message=f"Validation crashed: {result}",
                    severity=ValidationSeverity.ERROR,
                ))
                batch_result.results[project_dir] = error_result
                batch_result.failed += 1
                batch_result.total_errors += 1
            else:
                batch_result.results[project_dir] = result
                if result.passed:
                    batch_result.successful += 1
                else:
                    batch_result.failed += 1
                batch_result.total_errors += result.error_count
                batch_result.total_warnings += result.warning_count
        
        batch_result.execution_time_ms = (time.time() - start_time) * 1000
        
        self.logger.info(
            "batch_validation_complete",
            total=batch_result.total_projects,
            successful=batch_result.successful,
            failed=batch_result.failed,
            errors=batch_result.total_errors,
            time_ms=batch_result.execution_time_ms,
        )
        
        return batch_result
    
    async def validate_files(
        self,
        project_dir: str,
        files: list[str],
        validator_types: Optional[list[str]] = None,
    ) -> ValidationResult:
        """
        Validate specific files in a project.
        
        Args:
            project_dir: Project directory
            files: List of file paths to validate
            validator_types: Optional list of validator types to use
            
        Returns:
            ValidationResult for the specified files
        """
        async with self._semaphore:
            result = ValidationResult(project_dir=project_dir)
            
            # Determine validators to use
            validator_types = validator_types or ["typescript"]
            
            for vtype in validator_types:
                if vtype in VALIDATOR_REGISTRY:
                    validator_class = VALIDATOR_REGISTRY[vtype]
                    try:
                        validator = validator_class(project_dir)
                        if validator.is_applicable():
                            # Validate with file filter if supported
                            if hasattr(validator, 'validate_files'):
                                res = await validator.validate_files(files)
                            else:
                                res = await validator.validate()
                            result.merge(res)
                    except Exception as e:
                        result.add_failure(ValidationFailure(
                            check_type=vtype,
                            error_message=f"Validator error: {e}",
                            severity=ValidationSeverity.ERROR,
                        ))
            
            return result


class ProjectValidatorTool:
    """
    Orchestrates validation of generated projects.

    Discovers applicable validators, runs them, and aggregates results
    for consumption by the validation recovery agent.

    Can be configured with a ProjectProfile for dynamic validator selection.
    """

    # Class-level pool for batch operations
    _pool: Optional[ValidationPool] = None

    def __init__(
        self,
        project_dir: str,
        profile: Optional["ProjectProfile"] = None,
    ):
        """
        Initialize validator tool.

        Args:
            project_dir: Path to the generated project
            profile: Optional ProjectProfile for dynamic validator selection
        """
        self.project_dir = Path(project_dir)
        self.profile = profile
        self.validators: list[BaseValidator] = []

        if profile:
            self._configure_validators_from_profile(profile)
        else:
            self._discover_validators()

    @classmethod
    def get_pool(cls, max_concurrent: int = 4) -> ValidationPool:
        """Get or create the class-level validation pool."""
        if cls._pool is None:
            cls._pool = ValidationPool(max_concurrent=max_concurrent)
        return cls._pool

    @classmethod
    async def validate_batch(
        cls,
        projects: list[str],
        profiles: Optional[dict[str, "ProjectProfile"]] = None,
        max_concurrent: int = 4,
    ) -> BatchValidationResult:
        """
        Validate multiple projects in parallel.
        
        Class method for convenient batch validation.
        
        Args:
            projects: List of project directories
            profiles: Optional dict mapping project dir to profile
            max_concurrent: Maximum concurrent validations
            
        Returns:
            BatchValidationResult
        """
        pool = cls.get_pool(max_concurrent)
        return await pool.validate_batch(projects, profiles)

    @classmethod
    async def validate_files_batch(
        cls,
        project_dir: str,
        file_groups: list[list[str]],
        max_concurrent: int = 4,
    ) -> list[ValidationResult]:
        """
        Validate multiple file groups in parallel.
        
        Args:
            project_dir: Project directory
            file_groups: List of file lists to validate
            max_concurrent: Maximum concurrent validations
            
        Returns:
            List of ValidationResults
        """
        pool = cls.get_pool(max_concurrent)
        
        tasks = [
            pool.validate_files(project_dir, files)
            for files in file_groups
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [
            r if isinstance(r, ValidationResult) else ValidationResult(
                project_dir=project_dir,
                failures=[ValidationFailure(
                    check_type="batch_validation",
                    error_message=str(r),
                    severity=ValidationSeverity.ERROR,
                )]
            )
            for r in results
        ]

    def _configure_validators_from_profile(self, profile: "ProjectProfile") -> None:
        """Configure validators based on project profile."""
        # Get validator types from profile
        validator_types = profile.get_validators()

        logger.info(
            "configuring_validators_from_profile",
            project_type=profile.project_type.value,
            validators=validator_types,
        )

        for validator_type in validator_types:
            if validator_type in VALIDATOR_REGISTRY:
                validator_class = VALIDATOR_REGISTRY[validator_type]
                try:
                    validator = validator_class(str(self.project_dir))
                    if validator.is_applicable():
                        self.validators.append(validator)
                        logger.debug(
                            "validator_enabled",
                            validator=validator.name,
                            check_type=validator.check_type,
                        )
                except Exception as e:
                    logger.warning(
                        "validator_init_failed",
                        validator=validator_class.__name__,
                        error=str(e),
                    )
            else:
                logger.warning(
                    "unknown_validator_type",
                    validator_type=validator_type,
                )

    def _discover_validators(self) -> None:
        """Discover and instantiate applicable validators (fallback mode)."""
        # All available validator classes - ordered by priority
        # Completeness first (detect truncated files), then deps, types, build, runtime
        validator_classes = [
            FileCompletenessValidator,  # Check for truncated/incomplete files first
            DependencyValidator,        # Check deps installed
            TypeScriptValidator,        # Type check before build
            BuildValidator,             # Build the project
            ElectronValidator,          # Electron-specific runtime checks
        ]

        for validator_class in validator_classes:
            try:
                validator = validator_class(str(self.project_dir))
                if validator.is_applicable():
                    self.validators.append(validator)
                    logger.debug(
                        "validator_enabled",
                        validator=validator.name,
                        check_type=validator.check_type,
                    )
            except Exception as e:
                logger.warning(
                    "validator_init_failed",
                    validator=validator_class.__name__,
                    error=str(e),
                )

    async def validate(self, parallel: bool = True) -> ValidationResult:
        """
        Run all applicable validators.
    
        Args:
            parallel: Whether to run validators in parallel

        Returns:
            Aggregated ValidationResult
        """
        start_time = time.time()
        result = ValidationResult(project_dir=str(self.project_dir))

        if not self.validators:
            logger.warning("no_validators_applicable", project=str(self.project_dir))
            return result

        logger.info(
            "validation_starting",
            project=str(self.project_dir),
            validators=[v.name for v in self.validators],
        )

        if parallel:
            # Run all validators concurrently
            tasks = [v.validate() for v in self.validators]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for validator, res in zip(self.validators, results):
                if isinstance(res, Exception):
                    result.add_failure(ValidationFailure(
                        check_type=validator.check_type,
                        error_message=f"Validator {validator.name} crashed: {res}",
                        severity=ValidationSeverity.ERROR,
                    ))
                else:
                    result.merge(res)
        else:
            # Run sequentially
            for validator in self.validators:
                try:
                    res = await validator.validate()
                    result.merge(res)
                except Exception as e:
                    result.add_failure(ValidationFailure(
                        check_type=validator.check_type,
                        error_message=f"Validator {validator.name} crashed: {e}",
                        severity=ValidationSeverity.ERROR,
                    ))

        result.execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "validation_complete",
            passed=result.passed,
            errors=result.error_count,
            warnings=result.warning_count,
            duration_ms=result.execution_time_ms,
        )

        return result

    async def validate_and_report(self) -> dict:
        """
        Run validation and return structured report.

        Returns:
            Dictionary with validation results and recommendations
        """
        result = await self.validate()

        report = {
            "project": str(self.project_dir),
            "passed": result.passed,
            "summary": {
                "errors": result.error_count,
                "warnings": result.warning_count,
                "checks_run": len(result.checks_run),
                "checks_passed": len(result.checks_passed),
            },
            "failures_by_type": {},
            "recommendations": [],
        }

        # Group failures by type
        for failure in result.failures:
            if failure.check_type not in report["failures_by_type"]:
                report["failures_by_type"][failure.check_type] = []
            report["failures_by_type"][failure.check_type].append(failure.to_dict())

        # Generate recommendations
        report["recommendations"] = self._generate_recommendations(result)

        return report

    def _generate_recommendations(self, result: ValidationResult) -> list[str]:
        """Generate prioritized recommendations from failures."""
        recommendations = []

        # Prioritize by severity
        errors = [f for f in result.failures if f.severity == ValidationSeverity.ERROR]
        warnings = [f for f in result.failures if f.severity == ValidationSeverity.WARNING]

        # Error recommendations first
        for failure in errors:
            if failure.suggested_fix:
                recommendations.append(f"[ERROR] {failure.check_type}: {failure.suggested_fix}")

        # Then warnings
        for failure in warnings:
            if failure.suggested_fix:
                recommendations.append(f"[WARN] {failure.check_type}: {failure.suggested_fix}")

        return recommendations


async def validate_project(project_dir: str) -> ValidationResult:
    """
    Convenience function to validate a project.

    Args:
        project_dir: Path to project

    Returns:
        ValidationResult
    """
    tool = ProjectValidatorTool(project_dir)
    return await tool.validate()


async def validate_projects_batch(
    projects: list[str],
    max_concurrent: int = 4,
) -> BatchValidationResult:
    """
    Convenience function to validate multiple projects.
    
    Args:
        projects: List of project directories
        max_concurrent: Maximum concurrent validations
        
    Returns:
        BatchValidationResult
    """
    return await ProjectValidatorTool.validate_batch(
        projects,
        max_concurrent=max_concurrent,
    )


# CLI entry point for testing
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m src.tools.project_validator_tool <project_dir> [project_dir2 ...]")
        sys.exit(1)

    project_dirs = sys.argv[1:]

    async def main():
        if len(project_dirs) == 1:
            tool = ProjectValidatorTool(project_dirs[0])
            report = await tool.validate_and_report()
            print(json.dumps(report, indent=2))
        else:
            result = await validate_projects_batch(project_dirs)
            print(json.dumps(result.to_dict(), indent=2))

    asyncio.run(main())
