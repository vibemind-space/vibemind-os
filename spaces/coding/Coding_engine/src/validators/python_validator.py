"""
Python Validator - Validates Python project build/setup.

Checks for proper Python project configuration and dependencies.
Can optionally run pytest or basic syntax checks.
"""

import json
import re
from pathlib import Path
from typing import Optional

from .base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)


class PythonValidator(BaseValidator):
    """
    Validator for Python projects.

    Verifies:
    1. Python project configuration exists (requirements.txt, pyproject.toml, setup.py)
    2. Dependencies can be resolved
    3. Basic syntax checking via py_compile
    """

    @property
    def name(self) -> str:
        return "Python Build"

    @property
    def check_type(self) -> str:
        return "python"

    def is_applicable(self) -> bool:
        """Check if this is a Python project."""
        python_indicators = [
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
        ]
        return any((self.project_dir / f).exists() for f in python_indicators)

    async def validate(self) -> ValidationResult:
        """Run Python project validation."""
        result = self._create_result()

        # Check for config files
        config_check = self._check_config_files()
        if config_check:
            result.add_failure(config_check)
            return result

        # Check dependencies
        dep_check = await self._check_dependencies()
        if dep_check:
            result.add_failure(dep_check)

        # Check for syntax errors in Python files
        syntax_errors = await self._check_syntax()
        for error in syntax_errors:
            result.add_failure(error)

        # If no failures, mark as passed
        if not result.failures:
            result.checks_passed.append(self.check_type)

        return result

    def _check_config_files(self) -> Optional[ValidationFailure]:
        """Check that at least one Python config file exists and is valid."""
        # Check pyproject.toml
        pyproject = self.project_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                # Just check it's readable - don't parse TOML without tomllib
                content = pyproject.read_text()
                if not content.strip():
                    return self._create_failure(
                        error_message="pyproject.toml is empty",
                        file_path="pyproject.toml",
                        suggested_fix="Add Python project configuration to pyproject.toml",
                    )
                return None
            except Exception as e:
                return self._create_failure(
                    error_message=f"Cannot read pyproject.toml: {e}",
                    file_path="pyproject.toml",
                )

        # Check requirements.txt
        requirements = self.project_dir / "requirements.txt"
        if requirements.exists():
            return None

        # Check setup.py
        setup_py = self.project_dir / "setup.py"
        if setup_py.exists():
            return None

        # No config found (but is_applicable should prevent this)
        return self._create_failure(
            error_message="No Python project configuration found",
            suggested_fix="Create requirements.txt, pyproject.toml, or setup.py",
        )

    async def _check_dependencies(self) -> Optional[ValidationFailure]:
        """Check if dependencies can be resolved."""
        requirements = self.project_dir / "requirements.txt"

        if not requirements.exists():
            return None  # No requirements to check

        # Try pip check for installed packages
        exit_code, stdout, stderr = await self._run_command(
            ["pip", "check"],
            timeout=60.0,
            use_shell=True,
        )

        if exit_code != 0:
            # pip check failed - there are broken dependencies
            combined = stdout + stderr
            if "No broken requirements found" not in combined:
                return self._create_failure(
                    error_message="Broken Python dependencies detected",
                    raw_output=combined[:1500],
                    suggested_fix="Run 'pip install -r requirements.txt' to fix dependencies",
                    severity=ValidationSeverity.WARNING,
                )

        return None

    async def _check_syntax(self) -> list[ValidationFailure]:
        """Check Python files for syntax errors."""
        failures = []

        # Find all Python files
        python_files = list(self.project_dir.rglob("*.py"))

        # Exclude common directories
        exclude_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", "dist", "build"}
        python_files = [
            f for f in python_files
            if not any(exc in f.parts for exc in exclude_dirs)
        ]

        # Limit to first 50 files for performance
        for py_file in python_files[:50]:
            exit_code, stdout, stderr = await self._run_command(
                ["python", "-m", "py_compile", str(py_file)],
                timeout=10.0,
                use_shell=True,
            )

            if exit_code != 0:
                # Parse syntax error
                error_output = stderr or stdout
                failure = self._parse_syntax_error(py_file, error_output)
                failures.append(failure)

        return failures

    def _parse_syntax_error(self, file_path: Path, error_output: str) -> ValidationFailure:
        """Parse Python syntax error output."""
        # Try to extract line number from error
        line_match = re.search(r'line (\d+)', error_output)
        line_number = int(line_match.group(1)) if line_match else None

        # Extract error message
        error_match = re.search(r'SyntaxError: (.+)', error_output)
        error_msg = error_match.group(1) if error_match else "Syntax error"

        rel_path = file_path.relative_to(self.project_dir) if file_path.is_relative_to(self.project_dir) else file_path

        return self._create_failure(
            error_message=f"Python syntax error: {error_msg}",
            file_path=str(rel_path),
            line_number=line_number,
            raw_output=error_output[:500],
            suggested_fix="Fix the syntax error in the Python file",
        )


class PythonDependencyValidator(BaseValidator):
    """
    Validator specifically for Python dependencies.

    Checks that requirements.txt dependencies are installed.
    """

    @property
    def name(self) -> str:
        return "Python Dependencies"

    @property
    def check_type(self) -> str:
        return "python_dependencies"

    def is_applicable(self) -> bool:
        """Check if this is a Python project with requirements."""
        return (self.project_dir / "requirements.txt").exists()

    async def validate(self) -> ValidationResult:
        """Validate Python dependencies are installed."""
        result = self._create_result()

        requirements_file = self.project_dir / "requirements.txt"

        if not requirements_file.exists():
            result.checks_passed.append(self.check_type)
            return result

        # Read requirements
        try:
            requirements_content = requirements_file.read_text()
            packages = self._parse_requirements(requirements_content)
        except Exception as e:
            result.add_failure(self._create_failure(
                error_message=f"Cannot read requirements.txt: {e}",
                file_path="requirements.txt",
            ))
            return result

        # Check each package
        missing = []
        for package in packages[:20]:  # Limit for performance
            exit_code, stdout, stderr = await self._run_command(
                ["pip", "show", package],
                timeout=10.0,
                use_shell=True,
            )
            if exit_code != 0:
                missing.append(package)

        if missing:
            result.add_failure(self._create_failure(
                error_message=f"Missing Python packages: {', '.join(missing[:10])}",
                file_path="requirements.txt",
                severity=ValidationSeverity.WARNING,
                suggested_fix=f"Run 'pip install -r requirements.txt' or 'pip install {' '.join(missing[:5])}'",
            ))
        else:
            result.checks_passed.append(self.check_type)

        return result

    def _parse_requirements(self, content: str) -> list[str]:
        """Parse package names from requirements.txt."""
        packages = []
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Extract package name (before version specifier)
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                packages.append(match.group(1))
        return packages
