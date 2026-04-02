"""
Test Runner Tool - Executes tests and returns structured results.

This tool runs pytest for Python and jest for TypeScript/JavaScript.
It provides structured output that agents can use for decision-making.
"""
import asyncio
import subprocess
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import structlog

logger = structlog.get_logger()


@dataclass
class TestFailure:
    """Details of a single test failure."""
    test_name: str
    file_path: str
    line_number: Optional[int] = None
    error_message: str = ""
    error_type: str = ""
    traceback: str = ""

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "traceback": self.traceback[:500] if self.traceback else "",
        }


@dataclass
class TestResult:
    """Result from running tests."""
    success: bool
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    output: str = ""
    execution_time_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "failures": [f.to_dict() for f in self.failures],
            "execution_time_ms": self.execution_time_ms,
        }


class TestRunnerTool:
    """
    Tool for running tests in the generated codebase.

    Supports:
    - pytest for Python
    - jest for TypeScript/JavaScript

    Returns structured results that agents can use for fixing failures.
    """

    # Tool definition for Agent SDK
    TOOL_DEFINITION = {
        "name": "run_tests",
        "description": """Run tests in the codebase and return results.
Use this to verify that generated code works correctly.
Returns detailed failure information that can be used for debugging.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_type": {
                    "type": "string",
                    "enum": ["pytest", "jest", "auto"],
                    "description": "Type of test runner to use. 'auto' will detect based on project."
                },
                "path": {
                    "type": "string",
                    "description": "Specific test file or directory to run. If not provided, runs all tests."
                },
                "pattern": {
                    "type": "string",
                    "description": "Pattern to filter test names (e.g., 'test_auth*')"
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Whether to include verbose output"
                }
            },
            "required": []
        }
    }

    def __init__(self, working_dir: Optional[str] = None, timeout: int = 300):
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.timeout = timeout
        self.logger = logger.bind(tool="test_runner")

    async def execute(
        self,
        test_type: str = "auto",
        path: Optional[str] = None,
        pattern: Optional[str] = None,
        verbose: bool = True,
    ) -> TestResult:
        """
        Run tests and return structured results.

        Args:
            test_type: 'pytest', 'jest', or 'auto'
            path: Specific path to test
            pattern: Pattern to filter tests
            verbose: Include verbose output

        Returns:
            TestResult with pass/fail details
        """
        # Auto-detect test type if needed
        if test_type == "auto":
            test_type = self._detect_test_type()

        self.logger.info(
            "running_tests",
            test_type=test_type,
            path=path,
            pattern=pattern,
        )

        if test_type == "pytest":
            return await self._run_pytest(path, pattern, verbose)
        elif test_type == "jest":
            return await self._run_jest(path, pattern, verbose)
        else:
            return TestResult(
                success=False,
                output=f"Unknown test type: {test_type}",
            )

    def _detect_test_type(self) -> str:
        """Detect which test runner to use based on project files."""
        # Check for Python tests
        if (self.working_dir / "pytest.ini").exists():
            return "pytest"
        if (self.working_dir / "pyproject.toml").exists():
            return "pytest"
        if list(self.working_dir.glob("**/test_*.py")):
            return "pytest"
        if list(self.working_dir.glob("**/*_test.py")):
            return "pytest"

        # Check for JavaScript/TypeScript tests
        if (self.working_dir / "jest.config.js").exists():
            return "jest"
        if (self.working_dir / "jest.config.ts").exists():
            return "jest"
        if list(self.working_dir.glob("**/*.test.ts")):
            return "jest"
        if list(self.working_dir.glob("**/*.test.tsx")):
            return "jest"

        # Default to pytest
        return "pytest"

    async def _run_pytest(
        self,
        path: Optional[str],
        pattern: Optional[str],
        verbose: bool,
    ) -> TestResult:
        """Run pytest and parse results."""
        import time
        start_time = time.time()

        cmd = ["python", "-m", "pytest"]

        # Add JSON output for parsing
        cmd.extend(["--tb=short", "-q"])

        if verbose:
            cmd.append("-v")

        if path:
            cmd.append(path)

        if pattern:
            cmd.extend(["-k", pattern])

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                cwd=str(self.working_dir),
            )

            execution_time = int((time.time() - start_time) * 1000)

            # Parse pytest output
            return self._parse_pytest_output(
                result.stdout,
                result.stderr,
                result.returncode,
                execution_time,
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                success=False,
                output="Test execution timed out",
                execution_time_ms=self.timeout * 1000,
            )
        except Exception as e:
            return TestResult(
                success=False,
                output=f"Error running tests: {str(e)}",
            )

    def _parse_pytest_output(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        execution_time: int,
    ) -> TestResult:
        """Parse pytest output into structured result."""
        failures = []

        # Parse summary line (e.g., "5 passed, 2 failed, 1 skipped")
        total = passed = failed = skipped = errors = 0

        output = stdout + "\n" + stderr

        # Look for summary line
        import re
        summary_match = re.search(
            r"(\d+) passed|(\d+) failed|(\d+) skipped|(\d+) error",
            output,
        )

        # Count results from output
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        skipped_match = re.search(r"(\d+) skipped", output)
        error_match = re.search(r"(\d+) error", output)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if skipped_match:
            skipped = int(skipped_match.group(1))
        if error_match:
            errors = int(error_match.group(1))

        total = passed + failed + skipped + errors

        # Parse individual failures
        failure_blocks = re.findall(
            r"FAILED ([^\s]+)::([^\s]+).*?\n(.*?)(?=FAILED|$)",
            output,
            re.DOTALL,
        )

        for file_path, test_name, traceback in failure_blocks:
            # Extract error message from traceback
            error_lines = traceback.strip().split("\n")
            error_message = error_lines[-1] if error_lines else ""

            failures.append(TestFailure(
                test_name=test_name,
                file_path=file_path,
                error_message=error_message,
                traceback=traceback.strip(),
            ))

        return TestResult(
            success=returncode == 0,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            failures=failures,
            output=output,
            execution_time_ms=execution_time,
        )

    async def _run_jest(
        self,
        path: Optional[str],
        pattern: Optional[str],
        verbose: bool,
    ) -> TestResult:
        """Run jest and parse results."""
        import time
        start_time = time.time()

        cmd = ["npx", "jest", "--json"]

        if verbose:
            cmd.append("--verbose")

        if path:
            cmd.append(path)

        if pattern:
            cmd.extend(["-t", pattern])

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                cwd=str(self.working_dir),
                shell=True,  # Required for npx on Windows
            )

            execution_time = int((time.time() - start_time) * 1000)

            # Try to parse JSON output
            try:
                json_output = json.loads(result.stdout)
                return self._parse_jest_json(json_output, execution_time)
            except json.JSONDecodeError:
                # Fallback to basic parsing
                return TestResult(
                    success=result.returncode == 0,
                    output=result.stdout + "\n" + result.stderr,
                    execution_time_ms=execution_time,
                )

        except subprocess.TimeoutExpired:
            return TestResult(
                success=False,
                output="Test execution timed out",
                execution_time_ms=self.timeout * 1000,
            )
        except Exception as e:
            return TestResult(
                success=False,
                output=f"Error running tests: {str(e)}",
            )

    def _parse_jest_json(self, json_output: dict, execution_time: int) -> TestResult:
        """Parse jest JSON output into structured result."""
        failures = []

        # Extract test results
        test_results = json_output.get("testResults", [])

        total = passed = failed = 0

        for test_file in test_results:
            for assertion in test_file.get("assertionResults", []):
                total += 1
                if assertion.get("status") == "passed":
                    passed += 1
                elif assertion.get("status") == "failed":
                    failed += 1
                    failures.append(TestFailure(
                        test_name=assertion.get("title", "unknown"),
                        file_path=test_file.get("name", "unknown"),
                        error_message="\n".join(assertion.get("failureMessages", [])),
                    ))

        return TestResult(
            success=json_output.get("success", False),
            total_tests=total,
            passed=passed,
            failed=failed,
            failures=failures,
            execution_time_ms=execution_time,
        )


# Convenience function for direct tool use
async def test_runner_tool(
    test_type: str = "auto",
    path: Optional[str] = None,
    pattern: Optional[str] = None,
    verbose: bool = True,
    working_dir: Optional[str] = None,
) -> TestResult:
    """
    Convenience function to run tests.

    Args:
        test_type: 'pytest', 'jest', or 'auto'
        path: Specific test path
        pattern: Test name pattern
        verbose: Verbose output
        working_dir: Working directory

    Returns:
        TestResult with details
    """
    tool = TestRunnerTool(working_dir=working_dir)
    return await tool.execute(test_type, path, pattern, verbose)
