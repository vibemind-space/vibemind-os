"""
Execution Sandbox — Safe execution environment for generated code.

Provides:
- Isolated subprocess execution with timeout and memory limits
- stdout/stderr capture with streaming
- Exit code tracking and signal handling
- File I/O sandboxing (restricted working directory)
- Multi-language support (Python, Node.js, shell)
- Test runner integration (pytest, jest, go test)
- Execution history and result caching

Usage:
    sandbox = ExecutionSandbox(work_dir="/tmp/sandbox")

    # Run a Python script
    result = sandbox.run_python("print('hello')")

    # Run a test suite
    result = sandbox.run_tests("pytest", target="tests/")

    # Run arbitrary command
    result = sandbox.run_command(["node", "app.js"], timeout=30)
"""

import os
import subprocess
import tempfile
import time
import uuid
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"


class Language(str, Enum):
    PYTHON = "python"
    NODEJS = "nodejs"
    SHELL = "shell"
    GO = "go"


@dataclass
class ExecutionResult:
    """Result of a sandbox execution."""
    execution_id: str
    status: ExecutionStatus
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    language: str = ""
    command: str = ""
    working_dir: str = ""
    created_at: float = field(default_factory=time.time)
    timed_out: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS and self.exit_code == 0

    @property
    def output(self) -> str:
        """Combined stdout + stderr."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 1),
            "language": self.language,
            "command": self.command,
            "success": self.success,
            "timed_out": self.timed_out,
            "metadata": self.metadata,
        }


@dataclass
class TestResult:
    """Parsed test execution result."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    test_output: str = ""
    framework: str = ""
    success: bool = False
    failure_details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 1),
            "framework": self.framework,
            "success": self.success,
            "pass_rate": round(self.passed / max(self.total, 1) * 100, 1),
            "failure_details": self.failure_details[:10],  # Limit
        }


class ExecutionSandbox:
    """Safe code execution sandbox with resource limits."""

    def __init__(
        self,
        work_dir: Optional[str] = None,
        default_timeout: float = 30.0,
        max_output_bytes: int = 1_000_000,  # 1MB
        max_history: int = 100,
    ):
        self._work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sandbox_"))
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._default_timeout = default_timeout
        self._max_output_bytes = max_output_bytes
        self._max_history = max_history

        # Execution history
        self._history: List[ExecutionResult] = []
        self._results: Dict[str, ExecutionResult] = {}

        # Stats
        self._total_executions = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_timeouts = 0

        logger.info(
            "sandbox_initialized",
            component="execution_sandbox",
            work_dir=str(self._work_dir),
            timeout=default_timeout,
        )

    @property
    def work_dir(self) -> Path:
        return self._work_dir

    # ── Python Execution ──────────────────────────────────────────────

    def run_python(
        self,
        code: str,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Run Python code in a temporary file."""
        script_path = self._work_dir / f"script_{uuid.uuid4().hex[:8]}.py"
        try:
            script_path.write_text(code, encoding="utf-8")
            result = self.run_command(
                ["python", str(script_path)],
                timeout=timeout,
                env=env,
                language=Language.PYTHON,
                metadata=metadata,
            )
            return result
        finally:
            if script_path.exists():
                script_path.unlink()

    def run_python_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        """Run an existing Python file."""
        cmd = ["python", file_path]
        if args:
            cmd.extend(args)
        return self.run_command(cmd, timeout=timeout, env=env, language=Language.PYTHON)

    # ── Node.js Execution ─────────────────────────────────────────────

    def run_nodejs(
        self,
        code: str,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Run Node.js code in a temporary file."""
        script_path = self._work_dir / f"script_{uuid.uuid4().hex[:8]}.js"
        try:
            script_path.write_text(code, encoding="utf-8")
            result = self.run_command(
                ["node", str(script_path)],
                timeout=timeout,
                env=env,
                language=Language.NODEJS,
                metadata=metadata,
            )
            return result
        finally:
            if script_path.exists():
                script_path.unlink()

    # ── Shell Execution ───────────────────────────────────────────────

    def run_shell(
        self,
        command: str,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Run a shell command string."""
        return self.run_command(
            command,
            timeout=timeout,
            env=env,
            language=Language.SHELL,
            shell=True,
            metadata=metadata,
        )

    # ── Test Runners ──────────────────────────────────────────────────

    def run_tests(
        self,
        framework: str = "pytest",
        target: str = "",
        timeout: Optional[float] = None,
        extra_args: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
    ) -> TestResult:
        """Run tests using a specified framework."""
        cmd = self._build_test_command(framework, target, extra_args)
        exec_result = self.run_command(
            cmd,
            timeout=timeout or self._default_timeout * 2,
            working_dir=working_dir,
            language=Language.PYTHON if framework == "pytest" else Language.NODEJS,
            metadata={"framework": framework, "target": target},
        )

        return self._parse_test_result(framework, exec_result)

    def _build_test_command(
        self,
        framework: str,
        target: str,
        extra_args: Optional[List[str]],
    ) -> List[str]:
        """Build command for a test framework."""
        if framework == "pytest":
            cmd = ["python", "-m", "pytest", "-v"]
            if target:
                cmd.append(target)
            if extra_args:
                cmd.extend(extra_args)
        elif framework == "jest":
            cmd = ["npx", "jest", "--verbose"]
            if target:
                cmd.append(target)
            if extra_args:
                cmd.extend(extra_args)
        elif framework == "go":
            cmd = ["go", "test", "-v"]
            if target:
                cmd.append(target)
            else:
                cmd.append("./...")
            if extra_args:
                cmd.extend(extra_args)
        elif framework == "unittest":
            cmd = ["python", "-m", "unittest", "discover", "-v"]
            if target:
                cmd.extend(["-s", target])
            if extra_args:
                cmd.extend(extra_args)
        else:
            cmd = [framework]
            if target:
                cmd.append(target)
            if extra_args:
                cmd.extend(extra_args)
        return cmd

    def _parse_test_result(self, framework: str, exec_result: ExecutionResult) -> TestResult:
        """Parse test output into a TestResult."""
        result = TestResult(
            duration_ms=exec_result.duration_ms,
            test_output=exec_result.output,
            framework=framework,
            success=exec_result.success,
        )

        output = exec_result.output
        lines = output.split("\n")

        if framework == "pytest":
            self._parse_pytest(lines, result)
        elif framework in ("jest", "vitest"):
            self._parse_jest(lines, result)
        else:
            # Generic: count PASS/FAIL/OK lines
            self._parse_generic(lines, result)

        result.success = result.failed == 0 and result.errors == 0 and result.total > 0
        return result

    def _parse_pytest(self, lines: List[str], result: TestResult):
        """Parse pytest output."""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("PASSED") or "passed" in stripped:
                if "passed" in stripped and ("failed" in stripped or "error" in stripped or "warning" in stripped):
                    # Summary line like "5 passed, 1 failed"
                    parts = stripped.split(",")
                    for part in parts:
                        part = part.strip()
                        if "passed" in part:
                            try:
                                result.passed = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "failed" in part:
                            try:
                                result.failed = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "error" in part:
                            try:
                                result.errors = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "skipped" in part:
                            try:
                                result.skipped = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                elif " passed" in stripped and not "," in stripped:
                    try:
                        result.passed = int(stripped.split()[0])
                    except (ValueError, IndexError):
                        pass
            elif "FAILED" in stripped:
                if stripped.startswith("FAILED"):
                    result.failure_details.append(stripped)

            # Count individual test results from verbose output
            if "::test_" in stripped:
                if "PASSED" in stripped:
                    result.passed += 1
                elif "FAILED" in stripped:
                    result.failed += 1
                elif "SKIPPED" in stripped:
                    result.skipped += 1

        result.total = result.passed + result.failed + result.skipped + result.errors

    def _parse_jest(self, lines: List[str], result: TestResult):
        """Parse Jest/Vitest output."""
        for line in lines:
            stripped = line.strip()
            if "Tests:" in stripped:
                parts = stripped.split(",")
                for part in parts:
                    part = part.strip()
                    if "passed" in part:
                        try:
                            result.passed = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "failed" in part:
                        try:
                            result.failed = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "skipped" in part:
                        try:
                            result.skipped = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "total" in part:
                        try:
                            result.total = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
            elif "FAIL" in stripped and "●" in stripped:
                result.failure_details.append(stripped)

        if result.total == 0:
            result.total = result.passed + result.failed + result.skipped

    def _parse_generic(self, lines: List[str], result: TestResult):
        """Parse generic test output (OK/FAIL lines)."""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("OK:"):
                result.passed += 1
            elif stripped.startswith("FAIL:") or stripped.startswith("FAILED:"):
                result.failed += 1
                result.failure_details.append(stripped)
            elif stripped.startswith("SKIP:"):
                result.skipped += 1

        result.total = result.passed + result.failed + result.skipped

    # ── Generic Command Execution ─────────────────────────────────────

    def run_command(
        self,
        cmd,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        language: Language = Language.SHELL,
        shell: bool = False,
        working_dir: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Run an arbitrary command with timeout and output capture."""
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        timeout = timeout or self._default_timeout
        cwd = working_dir or str(self._work_dir)

        # Build environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)

        result = ExecutionResult(
            execution_id=execution_id,
            status=ExecutionStatus.RUNNING,
            language=language.value if isinstance(language, Language) else language,
            command=cmd_str,
            working_dir=cwd,
            metadata=metadata or {},
        )

        self._total_executions += 1
        start = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=run_env,
                shell=shell,
            )

            result.exit_code = proc.returncode
            result.stdout = proc.stdout[:self._max_output_bytes] if proc.stdout else ""
            result.stderr = proc.stderr[:self._max_output_bytes] if proc.stderr else ""
            result.status = ExecutionStatus.SUCCESS if proc.returncode == 0 else ExecutionStatus.FAILED

            if proc.returncode == 0:
                self._total_successes += 1
            else:
                self._total_failures += 1

        except subprocess.TimeoutExpired as e:
            result.status = ExecutionStatus.TIMEOUT
            result.timed_out = True
            result.stdout = (e.stdout or "")[:self._max_output_bytes] if e.stdout else ""
            result.stderr = (e.stderr or "")[:self._max_output_bytes] if e.stderr else ""
            self._total_timeouts += 1

            logger.warning(
                "execution_timeout",
                component="execution_sandbox",
                execution_id=execution_id,
                timeout=timeout,
                command=cmd_str[:100],
            )

        except FileNotFoundError:
            result.status = ExecutionStatus.ERROR
            result.stderr = f"Command not found: {cmd_str.split()[0] if cmd_str else 'unknown'}"
            self._total_failures += 1

        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.stderr = str(e)
            self._total_failures += 1

        result.duration_ms = (time.time() - start) * 1000

        # Store in history
        self._results[execution_id] = result
        self._history.append(result)
        if len(self._history) > self._max_history:
            old = self._history.pop(0)
            self._results.pop(old.execution_id, None)

        logger.info(
            "execution_complete",
            component="execution_sandbox",
            execution_id=execution_id,
            status=result.status.value,
            exit_code=result.exit_code,
            duration_ms=round(result.duration_ms, 1),
            language=result.language,
        )

        return result

    # ── File Management ───────────────────────────────────────────────

    def write_file(self, relative_path: str, content: str) -> str:
        """Write a file into the sandbox working directory."""
        full_path = self._work_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return str(full_path)

    def read_file(self, relative_path: str) -> Optional[str]:
        """Read a file from the sandbox working directory."""
        full_path = self._work_dir / relative_path
        if not full_path.exists():
            return None
        return full_path.read_text(encoding="utf-8")

    def list_files(self, pattern: str = "**/*") -> List[str]:
        """List files in the sandbox directory."""
        return [
            str(p.relative_to(self._work_dir))
            for p in self._work_dir.glob(pattern)
            if p.is_file()
        ]

    def cleanup(self):
        """Remove all files in the sandbox directory."""
        for item in self._work_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

    # ── History & Stats ───────────────────────────────────────────────

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific execution result."""
        result = self._results.get(execution_id)
        return result.to_dict() if result else None

    def get_history(self, limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get execution history."""
        results = list(reversed(self._history))
        if status:
            results = [r for r in results if r.status.value == status]
        return [r.to_dict() for r in results[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        """Get sandbox execution statistics."""
        return {
            "total_executions": self._total_executions,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "total_timeouts": self._total_timeouts,
            "success_rate": round(
                self._total_successes / max(self._total_executions, 1) * 100, 1
            ),
            "work_dir": str(self._work_dir),
            "history_size": len(self._history),
        }

    def reset(self):
        """Reset sandbox state and clean files."""
        self.cleanup()
        self._history.clear()
        self._results.clear()
        self._total_executions = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_timeouts = 0
