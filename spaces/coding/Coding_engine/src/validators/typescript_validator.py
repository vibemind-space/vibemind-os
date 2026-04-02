"""
TypeScript Validator - Validates TypeScript compilation.

Runs tsc --noEmit to check for type errors without generating output.
Parses compiler output to create structured ValidationFailure objects.
"""

import re
from pathlib import Path
from typing import Optional

from .base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)


class TypeScriptValidator(BaseValidator):
    """
    Validator that checks TypeScript compilation.

    Runs the TypeScript compiler in check-only mode and parses
    the output to create structured failure objects.
    """

    @property
    def name(self) -> str:
        return "TypeScript Compiler"

    @property
    def check_type(self) -> str:
        return "typescript"

    def is_applicable(self) -> bool:
        """Check if project has TypeScript configuration."""
        tsconfig = self.project_dir / "tsconfig.json"
        return tsconfig.exists()

    async def validate(self) -> ValidationResult:
        """
        Run TypeScript compiler and collect errors.

        Returns:
            ValidationResult with any compilation errors
        """
        result = self._create_result()

        # Check for tsconfig.json
        tsconfig = self.project_dir / "tsconfig.json"
        if not tsconfig.exists():
            result.checks_skipped.append(self.check_type)
            return result

        # Try using npx tsc with shell=True on Windows for better compatibility
        exit_code, stdout, stderr = await self._run_command(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            timeout=120.0,
            use_shell=True,  # Force shell mode for npm/npx commands
        )

        # Parse the output
        combined_output = stdout + stderr

        # Check for command not found errors
        if exit_code == -1 or "Command not found" in combined_output or "nicht finden" in combined_output:
            result.add_failure(self._create_failure(
                error_message="TypeScript compiler (npx tsc) not available",
                raw_output=combined_output[:2000],
                suggested_fix="Ensure Node.js and npm are installed and in PATH. "
                             "Run 'npm install' in the project directory first.",
                error_code="TOOL_NOT_FOUND",
            ))
            return result

        if exit_code == 0:
            result.checks_passed.append(self.check_type)
        else:
            # Parse TypeScript errors
            failures = self._parse_tsc_output(combined_output)

            if failures:
                for failure in failures:
                    result.add_failure(failure)
            else:
                # Couldn't parse specific errors, add generic failure
                result.add_failure(self._create_failure(
                    error_message="TypeScript compilation failed",
                    raw_output=combined_output[:2000],
                    suggested_fix="Run 'npx tsc --noEmit' to see full error output",
                ))

        return result

    def _parse_tsc_output(self, output: str) -> list[ValidationFailure]:
        """
        Parse TypeScript compiler output into structured failures.

        TypeScript error format:
        src/file.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.
        """
        failures = []

        # Pattern: file(line,col): error TSxxxx: message
        error_pattern = re.compile(
            r'^(.+?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)$',
            re.MULTILINE
        )

        for match in error_pattern.finditer(output):
            file_path = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            severity_str = match.group(4)
            error_code = match.group(5)
            message = match.group(6)

            # Determine severity
            severity = (
                ValidationSeverity.ERROR
                if severity_str == "error"
                else ValidationSeverity.WARNING
            )

            # Make file path relative to project if it's absolute
            if Path(file_path).is_absolute():
                try:
                    file_path = str(Path(file_path).relative_to(self.project_dir))
                except ValueError:
                    pass  # Keep absolute path if not under project

            # Get suggested fix based on error code
            suggested_fix = self._get_suggested_fix(error_code, message)

            failures.append(ValidationFailure(
                check_type=self.check_type,
                error_message=message,
                severity=severity,
                file_path=file_path,
                line_number=line_num,
                column_number=col_num,
                error_code=error_code,
                suggested_fix=suggested_fix,
            ))

        return failures

    def _get_suggested_fix(self, error_code: str, message: str) -> Optional[str]:
        """Get suggested fix based on error code."""
        suggestions = {
            "TS2307": "Check that the module exists and is properly installed. "
                      "May need to install @types package or add to tsconfig paths.",
            "TS2304": "The name is not defined. Check imports or declare the variable.",
            "TS2322": "Type mismatch. Check the types being assigned.",
            "TS2339": "Property doesn't exist on type. Check spelling or add to interface.",
            "TS2345": "Argument type mismatch. Check function signature.",
            "TS2532": "Object is possibly undefined. Add null check or use optional chaining.",
            "TS2531": "Object is possibly null. Add null check.",
            "TS7006": "Parameter implicitly has 'any' type. Add type annotation.",
            "TS7016": "Could not find declaration file. Install @types package or declare module.",
            "TS1259": "Module can only be default-imported with esModuleInterop. "
                      "Enable esModuleInterop in tsconfig.json.",
            "TS2354": "This syntax requires an imported helper. Enable importHelpers in tsconfig.",
        }

        # Check for specific patterns in message
        if "Cannot find module" in message:
            if "'electron'" in message:
                return ("Electron module not found at compile time. "
                        "Ensure electron is externalized in bundler config.")
            return suggestions.get("TS2307", "Check module installation and paths.")

        return suggestions.get(error_code)


class TypeScriptBuildValidator(BaseValidator):
    """
    Validator that runs the full TypeScript build.

    Unlike TypeScriptValidator which only checks types,
    this actually runs the build to catch bundler issues.
    """

    @property
    def name(self) -> str:
        return "TypeScript Build"

    @property
    def check_type(self) -> str:
        return "typescript_build"

    def is_applicable(self) -> bool:
        """Check if project has build script."""
        pkg_json = self.project_dir / "package.json"
        if not pkg_json.exists():
            return False

        try:
            import json
            with open(pkg_json) as f:
                pkg = json.load(f)
            scripts = pkg.get("scripts", {})
            return "build" in scripts or "compile" in scripts
        except Exception:
            return False

    async def validate(self) -> ValidationResult:
        """Run the build and check for errors."""
        result = self._create_result()

        # Try npm run build
        exit_code, stdout, stderr = await self._run_command(
            ["npm", "run", "build"],
            timeout=180.0,
        )

        combined_output = stdout + stderr

        if exit_code == 0:
            result.checks_passed.append(self.check_type)
        else:
            # Check for common build errors
            failure = self._analyze_build_error(combined_output)
            result.add_failure(failure)

        return result

    def _analyze_build_error(self, output: str) -> ValidationFailure:
        """Analyze build error output and create failure."""
        error_message = "Build failed"
        suggested_fix = None
        related_files = []

        # Check for common patterns
        if "Cannot find module 'electron'" in output:
            error_message = "Electron module not found during build"
            suggested_fix = ("Add 'electron' to external array in bundler config "
                           "(electron-vite.config.ts or vite.config.ts)")
            related_files = ["electron-vite.config.ts", "vite.config.ts"]

        elif "Module not found" in output or "Cannot resolve" in output:
            # Try to extract module name
            match = re.search(r"(?:Module not found|Cannot resolve)[^\n]*'([^']+)'", output)
            if match:
                module_name = match.group(1)
                error_message = f"Cannot resolve module: {module_name}"
                suggested_fix = f"Install {module_name} with 'npm install {module_name}'"

        elif "SyntaxError" in output:
            error_message = "JavaScript/TypeScript syntax error"
            suggested_fix = "Check the file for syntax errors"

        elif "ENOENT" in output:
            error_message = "File or directory not found"
            match = re.search(r"ENOENT[^\n]*'([^']+)'", output)
            if match:
                error_message = f"File not found: {match.group(1)}"

        return self._create_failure(
            error_message=error_message,
            raw_output=output[:2000],
            suggested_fix=suggested_fix,
            related_files=related_files,
        )
