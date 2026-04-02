"""
General Runtime Validator - Tests any project's runtime behavior using Claude CLI.

This validator:
1. Detects project type (Electron, Node, Python, Web, etc.)
2. Runs the appropriate start command
3. Captures any runtime errors
4. Uses Claude CLI to analyze errors and generate fixes
5. Applies fixes and re-tests
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import structlog

from .base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)

logger = structlog.get_logger(__name__)


class ProjectType(str, Enum):
    """Detected project types."""
    ELECTRON = "electron"
    ELECTRON_VITE = "electron-vite"
    NODE = "node"
    REACT = "react"
    VUE = "vue"
    NEXTJS = "nextjs"
    PYTHON = "python"
    PYTHON_FLASK = "flask"
    PYTHON_FASTAPI = "fastapi"
    RUST = "rust"
    UNKNOWN = "unknown"


@dataclass
class RuntimeResult:
    """Result from running a project."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timeout: bool = False
    project_type: ProjectType = ProjectType.UNKNOWN
    start_command: str = ""
    error_summary: str = ""

    @property
    def has_errors(self) -> bool:
        return not self.success or bool(self.stderr.strip()) or self.exit_code != 0


@dataclass
class FixSuggestion:
    """A fix suggestion from Claude CLI."""
    file_path: str
    original_content: str
    fixed_content: str
    explanation: str
    confidence: float = 0.0


@dataclass
class DebugAnalysis:
    """Analysis result from Claude CLI."""
    error_type: str
    root_cause: str
    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    additional_info: str = ""


class GeneralRuntimeValidator(BaseValidator):
    """
    General-purpose runtime validator that works with any project type.

    Uses Claude CLI to intelligently analyze errors and generate fixes.
    """

    # Project type detection rules
    PROJECT_DETECTION = [
        # (check_func, project_type, priority)
        ("_is_electron_vite", ProjectType.ELECTRON_VITE, 10),
        ("_is_electron", ProjectType.ELECTRON, 9),
        ("_is_nextjs", ProjectType.NEXTJS, 8),
        ("_is_react", ProjectType.REACT, 7),
        ("_is_vue", ProjectType.VUE, 7),
        ("_is_fastapi", ProjectType.PYTHON_FASTAPI, 6),
        ("_is_flask", ProjectType.PYTHON_FLASK, 6),
        ("_is_python", ProjectType.PYTHON, 5),
        ("_is_rust", ProjectType.RUST, 5),
        ("_is_node", ProjectType.NODE, 4),
    ]

    # Start commands for each project type
    START_COMMANDS = {
        ProjectType.ELECTRON_VITE: "npm run dev",
        ProjectType.ELECTRON: "npm start",
        ProjectType.NEXTJS: "npm run dev",
        ProjectType.REACT: "npm start",
        ProjectType.VUE: "npm run dev",
        ProjectType.NODE: "npm start",
        ProjectType.PYTHON_FASTAPI: "uvicorn main:app --reload",
        ProjectType.PYTHON_FLASK: "flask run",
        ProjectType.PYTHON: "python main.py",
        ProjectType.RUST: "cargo run",
        ProjectType.UNKNOWN: "",
    }

    def __init__(
        self,
        project_dir: str,
        timeout: float = 30.0,
        startup_wait: float = 5.0,
        clean_env: bool = True,
    ):
        """
        Initialize the general runtime validator.

        Args:
            project_dir: Path to the project
            timeout: Maximum time to wait for the app to start
            startup_wait: Time to wait after start to check for errors
            clean_env: Whether to clean problematic env vars
        """
        super().__init__(project_dir)
        self.timeout = timeout
        self.startup_wait = startup_wait
        self.clean_env = clean_env
        self.logger = logger.bind(component="general_runtime_validator")
        self._detected_type: Optional[ProjectType] = None
        self._package_json: Optional[dict] = None

    @property
    def name(self) -> str:
        return "General Runtime Validator"

    @property
    def check_type(self) -> str:
        return "runtime"

    def is_applicable(self) -> bool:
        """Check if this project can be runtime-tested."""
        return self.detect_project_type() != ProjectType.UNKNOWN

    def detect_project_type(self) -> ProjectType:
        """Detect the project type based on files and dependencies."""
        if self._detected_type is not None:
            return self._detected_type

        # Load package.json if exists
        self._load_package_json()

        # Try each detection method
        for method_name, project_type, _ in sorted(
            self.PROJECT_DETECTION, key=lambda x: -x[2]
        ):
            method = getattr(self, method_name)
            if method():
                self._detected_type = project_type
                self.logger.info("project_type_detected", type=project_type.value)
                return project_type

        self._detected_type = ProjectType.UNKNOWN
        return ProjectType.UNKNOWN

    def get_start_command(self) -> str:
        """Get the appropriate start command for this project."""
        project_type = self.detect_project_type()

        # Check package.json scripts first
        if self._package_json and "scripts" in self._package_json:
            scripts = self._package_json["scripts"]
            # Prefer 'dev' for development
            if "dev" in scripts:
                return "npm run dev"
            if "start" in scripts:
                return "npm start"

        return self.START_COMMANDS.get(project_type, "")

    async def validate(self) -> ValidationResult:
        """
        Run runtime validation.

        Returns:
            ValidationResult with any runtime failures
        """
        import time
        start_time = time.time()
        result = self._create_result()

        project_type = self.detect_project_type()
        if project_type == ProjectType.UNKNOWN:
            result.add_failure(self._create_failure(
                "Unable to detect project type",
                severity=ValidationSeverity.WARNING,
                error_code="PROJECT_TYPE_UNKNOWN",
            ))
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

        start_command = self.get_start_command()
        if not start_command:
            result.add_failure(self._create_failure(
                f"No start command found for {project_type.value}",
                severity=ValidationSeverity.ERROR,
                error_code="NO_START_COMMAND",
            ))
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

        # Run the project
        runtime_result = await self._run_project(start_command, project_type)

        if runtime_result.has_errors:
            # Create a failure for the error
            error_msg = runtime_result.stderr or runtime_result.error_summary or "Runtime error"
            result.add_failure(self._create_failure(
                error_msg[:500],
                severity=ValidationSeverity.ERROR,
                error_code="RUNTIME_ERROR",
                raw_output=f"stdout:\n{runtime_result.stdout[:1000]}\n\nstderr:\n{runtime_result.stderr[:1000]}",
            ))
        else:
            result.checks_passed.append(self.check_type)

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    async def run_and_debug(self) -> tuple[RuntimeResult, Optional[DebugAnalysis]]:
        """
        Run the project and if errors occur, analyze with Claude CLI.

        Returns:
            Tuple of (RuntimeResult, Optional[DebugAnalysis])
        """
        project_type = self.detect_project_type()
        start_command = self.get_start_command()

        if not start_command:
            return RuntimeResult(
                success=False,
                error_summary="No start command found",
                project_type=project_type,
            ), None

        # Run the project
        runtime_result = await self._run_project(start_command, project_type)

        # If errors, analyze with Claude
        analysis = None
        if runtime_result.has_errors:
            analysis = await self._analyze_with_claude(runtime_result)

        return runtime_result, analysis

    async def _run_project(
        self,
        start_command: str,
        project_type: ProjectType,
    ) -> RuntimeResult:
        """
        Run the project and capture output.

        Args:
            start_command: Command to run
            project_type: Detected project type

        Returns:
            RuntimeResult with captured output
        """
        self.logger.info(
            "running_project",
            command=start_command,
            type=project_type.value,
        )

        # Prepare environment
        env = os.environ.copy()
        if self.clean_env:
            # Remove vars that can cause issues
            for var in ['ELECTRON_RUN_AS_NODE', 'ELECTRON_NO_ATTACH_CONSOLE']:
                env.pop(var, None)

        # Parse command
        if sys.platform == 'win32':
            shell = True
            cmd = start_command
        else:
            shell = True
            cmd = start_command

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
                env=env,
            )

            try:
                # Wait for startup_wait seconds to catch immediate errors
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.startup_wait,
                )

                return RuntimeResult(
                    success=process.returncode == 0,
                    stdout=stdout.decode('utf-8', errors='replace'),
                    stderr=stderr.decode('utf-8', errors='replace'),
                    exit_code=process.returncode or 0,
                    project_type=project_type,
                    start_command=start_command,
                )

            except asyncio.TimeoutError:
                # Process is still running - this is often good (server started)
                # Kill it and return success if no stderr
                process.terminate()
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    stdout, stderr = b"", b""

                stdout_str = stdout.decode('utf-8', errors='replace')
                stderr_str = stderr.decode('utf-8', errors='replace')

                # Check for error indicators in output
                has_errors = self._check_for_errors(stdout_str, stderr_str)

                return RuntimeResult(
                    success=not has_errors,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=0,
                    timeout=True,
                    project_type=project_type,
                    start_command=start_command,
                    error_summary="Process still running (server mode)" if not has_errors else "Errors detected",
                )

        except Exception as e:
            return RuntimeResult(
                success=False,
                stderr=str(e),
                project_type=project_type,
                start_command=start_command,
                error_summary=f"Failed to start: {e}",
            )

    def _check_for_errors(self, stdout: str, stderr: str) -> bool:
        """Check output for error indicators."""
        error_patterns = [
            "Error:",
            "ERROR",
            "FATAL",
            "Exception",
            "Traceback",
            "Cannot find module",
            "Module not found",
            "SyntaxError",
            "TypeError",
            "ReferenceError",
            "ENOENT",
            "EACCES",
            "failed to",
            "Failed to",
        ]

        combined = stdout + stderr
        for pattern in error_patterns:
            if pattern in combined:
                return True
        return False

    async def _analyze_with_claude(self, runtime_result: RuntimeResult) -> DebugAnalysis:
        """
        Use Claude CLI to analyze runtime errors.

        Args:
            runtime_result: The runtime result with errors

        Returns:
            DebugAnalysis with fix suggestions
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        self.logger.info("analyzing_with_claude", project_type=runtime_result.project_type.value)

        # Gather relevant files for context
        context_files = self._get_relevant_files(runtime_result)

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(runtime_result)

        # Use Claude CLI to analyze
        tool = ClaudeCodeTool(working_dir=str(self.project_dir))

        try:
            result = await tool.execute(
                prompt=prompt,
                context=f"Project type: {runtime_result.project_type.value}\nStart command: {runtime_result.start_command}",
                agent_type="general",
                context_files=context_files,
            )

            if result.success and result.files:
                # Claude generated fix files
                suggestions = []
                for gen_file in result.files:
                    suggestions.append(FixSuggestion(
                        file_path=gen_file.path,
                        original_content="",  # Will be filled when applying
                        fixed_content=gen_file.content,
                        explanation=f"Fix for {gen_file.path}",
                    ))

                return DebugAnalysis(
                    error_type="runtime_error",
                    root_cause=result.output[:500] if result.output else "Unknown",
                    fix_suggestions=suggestions,
                    additional_info=result.output,
                )
            else:
                return DebugAnalysis(
                    error_type="runtime_error",
                    root_cause=runtime_result.error_summary or "Unknown error",
                    additional_info=result.error or result.output,
                )

        except Exception as e:
            self.logger.error("claude_analysis_failed", error=str(e))
            return DebugAnalysis(
                error_type="analysis_failed",
                root_cause=str(e),
            )

    def _build_analysis_prompt(self, runtime_result: RuntimeResult) -> str:
        """Build a prompt for Claude to analyze the error."""
        return f"""Analyze this runtime error and fix it.

## Error Output

**Command:** `{runtime_result.start_command}`
**Exit code:** {runtime_result.exit_code}

### stdout:
```
{runtime_result.stdout[:2000]}
```

### stderr:
```
{runtime_result.stderr[:2000]}
```

## Task

1. Identify the root cause of this error
2. Generate fixed versions of the problematic files
3. Focus on the most likely fix based on the error message

Create the fixed file(s) that will resolve this runtime error.
"""

    def _get_relevant_files(self, runtime_result: RuntimeResult) -> list[str]:
        """Get relevant files for context based on error output."""
        files = []

        # Always include package.json if exists
        package_json = self.project_dir / "package.json"
        if package_json.exists():
            files.append(str(package_json))

        # Include main entry files
        for main_file in ["main.js", "main.ts", "index.js", "index.ts", "src/main.ts", "src/main.js"]:
            path = self.project_dir / main_file
            if path.exists():
                files.append(str(path))

        # Parse error output to find mentioned files
        error_text = runtime_result.stdout + runtime_result.stderr
        import re
        # Match file paths in error messages
        file_patterns = [
            r'at\s+.*?\(([^:]+):',  # Node.js stack traces
            r'File "([^"]+)"',  # Python stack traces
            r'in\s+([^\s:]+):',  # General patterns
            r'([a-zA-Z0-9_/\\.-]+\.(js|ts|py|jsx|tsx)):',  # Explicit file extensions
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, error_text)
            for match in matches:
                file_path = match[0] if isinstance(match, tuple) else match
                full_path = self.project_dir / file_path
                if full_path.exists() and str(full_path) not in files:
                    files.append(str(full_path))

        return files[:10]  # Limit to 10 files

    # Project detection methods
    def _load_package_json(self) -> None:
        """Load package.json if exists."""
        package_json = self.project_dir / "package.json"
        if package_json.exists():
            try:
                with open(package_json) as f:
                    self._package_json = json.load(f)
            except Exception:
                self._package_json = None

    def _get_deps(self) -> dict:
        """Get all dependencies from package.json."""
        if not self._package_json:
            return {}
        deps = {}
        deps.update(self._package_json.get("dependencies", {}))
        deps.update(self._package_json.get("devDependencies", {}))
        return deps

    def _is_electron_vite(self) -> bool:
        return "electron-vite" in self._get_deps()

    def _is_electron(self) -> bool:
        return "electron" in self._get_deps()

    def _is_nextjs(self) -> bool:
        return "next" in self._get_deps()

    def _is_react(self) -> bool:
        deps = self._get_deps()
        return "react" in deps and "next" not in deps

    def _is_vue(self) -> bool:
        return "vue" in self._get_deps()

    def _is_node(self) -> bool:
        return (self.project_dir / "package.json").exists()

    def _is_fastapi(self) -> bool:
        req = self.project_dir / "requirements.txt"
        if req.exists():
            content = req.read_text()
            return "fastapi" in content.lower()
        return False

    def _is_flask(self) -> bool:
        req = self.project_dir / "requirements.txt"
        if req.exists():
            content = req.read_text()
            return "flask" in content.lower()
        return False

    def _is_python(self) -> bool:
        return (
            (self.project_dir / "requirements.txt").exists() or
            (self.project_dir / "pyproject.toml").exists() or
            (self.project_dir / "main.py").exists()
        )

    def _is_rust(self) -> bool:
        return (self.project_dir / "Cargo.toml").exists()
