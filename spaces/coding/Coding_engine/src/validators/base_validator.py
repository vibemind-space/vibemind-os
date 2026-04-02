"""
Base validator interface for post-generation project validation.

Provides structured validation results similar to TestFailure for
consistent error handling and recovery via Claude Code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import time


class ValidationSeverity(Enum):
    """Severity levels for validation failures."""
    ERROR = "error"        # Must be fixed for project to work
    WARNING = "warning"    # Should be fixed but project may work
    INFO = "info"          # Suggestion for improvement


@dataclass
class ValidationFailure:
    """
    Structured representation of a validation failure.

    Designed to be analogous to TestFailure for consistent
    handling in the recovery pipeline.
    """
    check_type: str                          # e.g., "build", "typescript", "electron", "import"
    error_message: str                       # Human-readable error description
    severity: ValidationSeverity = ValidationSeverity.ERROR
    file_path: Optional[str] = None          # File where error occurred
    line_number: Optional[int] = None        # Line number if applicable
    column_number: Optional[int] = None      # Column number if applicable
    error_code: Optional[str] = None         # Error code (e.g., TS2307, E_MODULE_NOT_FOUND)
    raw_output: Optional[str] = None         # Raw command output for context
    suggested_fix: Optional[str] = None      # Heuristic hint for Claude
    related_files: list[str] = field(default_factory=list)  # Other files that may need changes

    def to_prompt_context(self) -> str:
        """Format failure for inclusion in Claude prompt."""
        lines = [
            f"## Validation Failure: {self.check_type}",
            f"**Severity:** {self.severity.value}",
            f"**Error:** {self.error_message}",
        ]

        if self.file_path:
            location = self.file_path
            if self.line_number:
                location += f":{self.line_number}"
                if self.column_number:
                    location += f":{self.column_number}"
            lines.append(f"**Location:** {location}")

        if self.error_code:
            lines.append(f"**Error Code:** {self.error_code}")

        if self.raw_output:
            lines.append(f"\n**Raw Output:**\n```\n{self.raw_output[:2000]}\n```")

        if self.suggested_fix:
            lines.append(f"\n**Suggested Fix:** {self.suggested_fix}")

        if self.related_files:
            lines.append(f"\n**Related Files:** {', '.join(self.related_files)}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "check_type": self.check_type,
            "error_message": self.error_message,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "error_code": self.error_code,
            "raw_output": self.raw_output,
            "suggested_fix": self.suggested_fix,
            "related_files": self.related_files,
        }


@dataclass
class ValidationResult:
    """
    Result of running validation checks on a project.

    Aggregates all failures and provides summary statistics.
    """
    failures: list[ValidationFailure] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    project_dir: str = ""

    @property
    def passed(self) -> bool:
        """True if no ERROR-level failures."""
        return not any(f.severity == ValidationSeverity.ERROR for f in self.failures)

    @property
    def error_count(self) -> int:
        """Count of ERROR-level failures."""
        return sum(1 for f in self.failures if f.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of WARNING-level failures."""
        return sum(1 for f in self.failures if f.severity == ValidationSeverity.WARNING)

    def add_failure(self, failure: ValidationFailure) -> None:
        """Add a failure to the result."""
        self.failures.append(failure)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another result into this one."""
        self.failures.extend(other.failures)
        self.checks_run.extend(other.checks_run)
        self.checks_passed.extend(other.checks_passed)
        self.checks_skipped.extend(other.checks_skipped)
        self.execution_time_ms += other.execution_time_ms

    def get_failures_by_type(self, check_type: str) -> list[ValidationFailure]:
        """Get failures filtered by check type."""
        return [f for f in self.failures if f.check_type == check_type]

    def get_failures_by_file(self, file_path: str) -> list[ValidationFailure]:
        """Get failures for a specific file."""
        return [f for f in self.failures if f.file_path == file_path]

    def to_prompt_context(self) -> str:
        """Format all failures for inclusion in Claude prompt."""
        if not self.failures:
            return "All validation checks passed."

        lines = [
            f"# Validation Results",
            f"**Project:** {self.project_dir}",
            f"**Errors:** {self.error_count}",
            f"**Warnings:** {self.warning_count}",
            f"**Checks Run:** {', '.join(self.checks_run)}",
            f"**Checks Passed:** {', '.join(self.checks_passed)}",
            "",
        ]

        for failure in self.failures:
            lines.append(failure.to_prompt_context())
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "failures": [f.to_dict() for f in self.failures],
            "checks_run": self.checks_run,
            "checks_passed": self.checks_passed,
            "checks_skipped": self.checks_skipped,
            "execution_time_ms": self.execution_time_ms,
            "project_dir": self.project_dir,
        }


class BaseValidator(ABC):
    """
    Abstract base class for project validators.

    Each validator checks a specific aspect of the generated project
    (e.g., TypeScript compilation, Electron startup, build success).
    """

    def __init__(self, project_dir: str):
        """
        Initialize validator with project directory.

        Args:
            project_dir: Path to the generated project
        """
        self.project_dir = Path(project_dir)

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this validator."""
        pass

    @property
    @abstractmethod
    def check_type(self) -> str:
        """Identifier for this validation type (e.g., 'typescript', 'electron')."""
        pass

    @abstractmethod
    async def validate(self) -> ValidationResult:
        """
        Run validation checks and return results.

        Returns:
            ValidationResult with any failures found
        """
        pass

    def is_applicable(self) -> bool:
        """
        Check if this validator applies to the current project.

        Override to check for project-specific files (e.g., tsconfig.json).
        Default returns True.
        """
        return True

    def _create_result(self) -> ValidationResult:
        """Create a new ValidationResult with project info."""
        return ValidationResult(
            project_dir=str(self.project_dir),
            checks_run=[self.check_type],
        )

    def _create_failure(
        self,
        error_message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        **kwargs
    ) -> ValidationFailure:
        """
        Create a ValidationFailure with this validator's check_type.

        Args:
            error_message: Description of the error
            severity: Error severity level
            **kwargs: Additional failure fields

        Returns:
            ValidationFailure instance
        """
        return ValidationFailure(
            check_type=self.check_type,
            error_message=error_message,
            severity=severity,
            **kwargs
        )

    async def _run_command(
        self,
        command: list[str],
        timeout: float = 60.0,
        cwd: Optional[Path] = None,
        use_shell: bool = None
    ) -> tuple[int, str, str]:
        """
        Run a shell command and return results.

        Args:
            command: Command and arguments
            timeout: Timeout in seconds
            cwd: Working directory (defaults to project_dir)
            use_shell: Force shell mode (auto-detected for Windows if None)

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        import asyncio
        import sys
        import shutil

        work_dir = cwd or self.project_dir
        
        # Auto-detect shell mode for Windows when using npm/npx commands
        if use_shell is None:
            use_shell = sys.platform == "win32" and command[0] in ("npx", "npm", "node")

        try:
            if use_shell:
                # On Windows, use shell=True with joined command string
                import subprocess
                
                # Join command for shell execution
                if sys.platform == "win32":
                    # On Windows, join with spaces (handle quoting if needed)
                    cmd_str = " ".join(command)
                else:
                    # On Unix, use shlex.join for proper quoting
                    import shlex
                    cmd_str = shlex.join(command)
                
                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(work_dir),
                )
            else:
                # Check if command exists first
                if not shutil.which(command[0]):
                    # Try with .cmd extension on Windows
                    if sys.platform == "win32":
                        cmd_with_ext = command[0] + ".cmd"
                        if shutil.which(cmd_with_ext):
                            command = [cmd_with_ext] + command[1:]
                        else:
                            return (-1, "", f"Command not found: {command[0]}. "
                                          f"Ensure Node.js is installed and in PATH.")
                    else:
                        return (-1, "", f"Command not found: {command[0]}")
                
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(work_dir),
                )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return (
                process.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return (-1, "", f"Command timed out after {timeout}s")
        except FileNotFoundError as e:
            # More helpful error message for missing commands
            return (-1, "", f"Command not found: {command[0]}. "
                          f"Ensure Node.js/npm is installed and in PATH. "
                          f"Error: {str(e)}")
        except Exception as e:
            return (-1, "", str(e))
