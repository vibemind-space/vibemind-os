"""
Build Validator - Validates project build process.

Runs npm run build and checks for successful compilation.
Also validates that output artifacts exist.
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


class BuildValidator(BaseValidator):
    """
    Validator that runs the project build.

    Executes npm run build and verifies:
    1. Build completes without errors
    2. Expected output files are generated
    """

    @property
    def name(self) -> str:
        return "Project Build"

    @property
    def check_type(self) -> str:
        return "build"

    def is_applicable(self) -> bool:
        """Check if project has build script."""
        pkg_json = self.project_dir / "package.json"
        if not pkg_json.exists():
            return False

        try:
            with open(pkg_json) as f:
                pkg = json.load(f)
            return "build" in pkg.get("scripts", {})
        except Exception:
            return False

    async def validate(self) -> ValidationResult:
        """Run the build and check for errors."""
        result = self._create_result()

        # Try npm run build with shell=True for Windows compatibility
        exit_code, stdout, stderr = await self._run_command(
            ["npm", "run", "build"],
            timeout=180.0,
            use_shell=True,  # Force shell mode for npm commands
        )

        combined_output = stdout + stderr

        # Check for command not found errors
        if exit_code == -1 or "Command not found" in combined_output or "nicht finden" in combined_output:
            result.add_failure(self._create_failure(
                error_message="Build command (npm) not available",
                raw_output=combined_output[:2000],
                suggested_fix="Ensure Node.js and npm are installed and in PATH.",
                error_code="TOOL_NOT_FOUND",
            ))
            return result

        # Build succeeded, verify outputs
        if exit_code == 0:
            output_check = await self._verify_build_outputs()
            if output_check:
                result.add_failure(output_check)
            else:
                result.checks_passed.append(self.check_type)
        else:
            # Build failed, analyze errors
            failure = self._analyze_build_error(combined_output)
            result.add_failure(failure)

        return result

    async def _verify_build_outputs(self) -> Optional[ValidationFailure]:
        """
        Verify that build outputs exist.

        Returns:
            ValidationFailure if outputs missing, None otherwise
        """
        # Check for common output directories
        output_dirs = ["dist", "build", "out"]

        for dir_name in output_dirs:
            dir_path = self.project_dir / dir_name
            if dir_path.exists() and any(dir_path.iterdir()):
                return None  # Found output

        # Check package.json for main/module fields
        pkg_json = self.project_dir / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json) as f:
                    pkg = json.load(f)

                main_file = pkg.get("main")
                if main_file:
                    main_path = self.project_dir / main_file
                    if main_path.exists():
                        return None
            except Exception:
                pass

        return self._create_failure(
            error_message="Build output not found",
            severity=ValidationSeverity.WARNING,
            suggested_fix="Check that build script generates output to dist/, build/, or out/",
        )

    def _analyze_build_error(self, output: str) -> ValidationFailure:
        """
        Analyze build error output and return a single failure.

        Args:
            output: Combined stdout and stderr from build command

        Returns:
            ValidationFailure representing the build error
        """
        failures = self._parse_build_errors(output)
        # Return the first failure (most relevant)
        return failures[0] if failures else self._create_failure(
            error_message="Build failed",
            raw_output=output[:2000],
            suggested_fix="Check the build output for error details",
        )

    def _parse_build_errors(self, output: str) -> list[ValidationFailure]:
        """Parse build output into structured failures."""
        failures = []

        # Check for common error patterns
        error_patterns = [
            # Vite/Rollup errors
            (r'error during build:[\s\S]*?(?=\n\n|\Z)', 'bundler'),
            # Module resolution errors
            (r"Cannot find module '([^']+)'", 'module'),
            (r"Module not found: .*?'([^']+)'", 'module'),
            # TypeScript errors embedded in build
            (r'TS\d+:.*', 'typescript'),
            # ESBuild errors
            (r'✘ \[ERROR\] (.+)', 'esbuild'),
            # Webpack errors
            (r'ERROR in (.+)', 'webpack'),
        ]

        for pattern, error_type in error_patterns:
            for match in re.finditer(pattern, output, re.MULTILINE):
                error_text = match.group(0)

                # Create appropriate failure
                failure = self._create_failure_from_error(
                    error_text,
                    error_type,
                    output
                )

                # Avoid duplicates
                if not any(f.error_message == failure.error_message for f in failures):
                    failures.append(failure)

        # If no specific errors found, create generic failure
        if not failures:
            failures.append(self._create_failure(
                error_message="Build failed with unknown error",
                raw_output=output[:2000],
                suggested_fix="Check the build output for specific error messages",
            ))

        return failures

    def _create_failure_from_error(
        self,
        error_text: str,
        error_type: str,
        full_output: str
    ) -> ValidationFailure:
        """Create a failure from a parsed error."""

        suggested_fix = None
        related_files = []
        file_path = None

        if error_type == 'module':
            # Extract module name
            match = re.search(r"'([^']+)'", error_text)
            module_name = match.group(1) if match else "unknown"

            if module_name == 'electron':
                suggested_fix = (
                    "Add 'electron' to external array in bundler config. "
                    "For electron-vite: external: ['electron'] in rollupOptions"
                )
                related_files = ["electron-vite.config.ts", "vite.config.ts"]
            else:
                suggested_fix = f"Install missing module: npm install {module_name}"

            return self._create_failure(
                error_message=f"Cannot find module: {module_name}",
                suggested_fix=suggested_fix,
                related_files=related_files,
            )

        elif error_type == 'typescript':
            return self._create_failure(
                error_message=error_text[:200],
                suggested_fix="Fix TypeScript error and rebuild",
            )

        elif error_type == 'bundler':
            # Try to extract more specific error
            if "electron" in error_text.lower():
                suggested_fix = (
                    "Electron must be externalized in bundler config. "
                    "Check that electron-vite.config.ts has electron in external array."
                )
                related_files = ["electron-vite.config.ts"]

            return self._create_failure(
                error_message="Bundler error during build",
                raw_output=error_text[:1000],
                suggested_fix=suggested_fix,
                related_files=related_files,
            )

        else:
            return self._create_failure(
                error_message=error_text[:200],
                raw_output=error_text,
            )


class DependencyValidator(BaseValidator):
    """
    Validator that checks project dependencies.

    Verifies:
    1. package.json exists and is valid
    2. node_modules exists (dependencies installed)
    3. No obvious missing dependencies
    """

    @property
    def name(self) -> str:
        return "Dependencies"

    @property
    def check_type(self) -> str:
        return "dependencies"

    def is_applicable(self) -> bool:
        """Check if this is a Node.js project."""
        return (self.project_dir / "package.json").exists()

    async def validate(self) -> ValidationResult:
        """
        Validate project dependencies.

        Returns:
            ValidationResult with any dependency issues
        """
        result = self._create_result()

        # Check package.json
        pkg_json = self.project_dir / "package.json"
        if not pkg_json.exists():
            result.add_failure(self._create_failure(
                error_message="package.json not found",
                suggested_fix="Initialize project with 'npm init'",
            ))
            return result

        # Parse package.json
        try:
            with open(pkg_json) as f:
                pkg = json.load(f)
        except json.JSONDecodeError as e:
            result.add_failure(self._create_failure(
                error_message=f"Invalid package.json: {e}",
                file_path="package.json",
                suggested_fix="Fix JSON syntax in package.json",
            ))
            return result

        # Check node_modules exists
        node_modules = self.project_dir / "node_modules"
        if not node_modules.exists():
            result.add_failure(self._create_failure(
                error_message="node_modules not found - dependencies not installed",
                suggested_fix="Run 'npm install' to install dependencies",
            ))
            return result

        # Verify critical dependencies exist
        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }

        missing = []
        for dep_name in all_deps:
            dep_path = node_modules / dep_name
            if not dep_path.exists():
                missing.append(dep_name)

        if missing:
            result.add_failure(self._create_failure(
                error_message=f"Missing installed packages: {', '.join(missing[:10])}",
                severity=ValidationSeverity.WARNING,
                suggested_fix="Run 'npm install' to install missing packages",
            ))
        else:
            result.checks_passed.append(self.check_type)

        return result
