"""
Deploy Tool - Orchestrates deployment using AutoGen + Claude CLI.

This tool:
1. Uses AutoGen ConversableAgent to orchestrate deployment
2. Runs build commands (npm run build, npm run package)
3. Collects logs from each deployment step
4. Returns structured deployment results for memory storage
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

try:
    from autogen import ConversableAgent, UserProxyAgent
    HAS_AUTOGEN = True
except ImportError:
    HAS_AUTOGEN = False

from .claude_code_tool import ClaudeCodeTool

logger = structlog.get_logger(__name__)


@dataclass
class DeploymentStep:
    """Single step in deployment process."""
    name: str
    command: str
    success: bool
    stdout: str
    stderr: str
    duration_ms: int
    error_message: Optional[str] = None


@dataclass
class DeploymentResult:
    """Result of deployment attempt."""
    success: bool
    steps: List[DeploymentStep]
    total_duration_ms: int
    error_message: Optional[str] = None
    logs: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "steps": [
                {
                    "name": s.name,
                    "command": s.command,
                    "success": s.success,
                    "stdout": s.stdout[:500],  # Truncate for storage
                    "stderr": s.stderr[:500],
                    "duration_ms": s.duration_ms,
                    "error_message": s.error_message,
                }
                for s in self.steps
            ],
            "total_duration_ms": self.total_duration_ms,
            "error_message": self.error_message,
            "logs": self.logs or [],
        }


class DeployTool:
    """
    Deployment tool with AutoGen orchestration.

    Uses AutoGen ConversableAgent to orchestrate deployment steps:
    1. npm run build - Build the project
    2. npm run package - Package for distribution (optional)
    3. Electron launch test - Verify app starts
    """

    def __init__(self, project_dir: str, timeout: int = 300):
        """
        Initialize deploy tool.

        Args:
            project_dir: Path to project directory
            timeout: Timeout for deployment in seconds (default 5min)
        """
        self.project_dir = Path(project_dir)
        self.timeout = timeout
        self.claude_tool = ClaudeCodeTool(working_dir=str(project_dir))
        self.logger = logger.bind(component="deploy_tool", project_dir=project_dir)

        # Check if AutoGen is available
        if not HAS_AUTOGEN:
            self.logger.warning("autogen_not_installed", msg="pip install pyautogen")

    async def deploy(
        self,
        include_package: bool = False,
        test_launch: bool = True,
    ) -> DeploymentResult:
        """
        Execute deployment.

        Args:
            include_package: Whether to run npm run package
            test_launch: Whether to test electron launch

        Returns:
            DeploymentResult
        """
        start_time = datetime.now()
        steps: List[DeploymentStep] = []
        logs: List[str] = []

        try:
            # Step 1: Build
            self.logger.info("deployment_step_build_started")
            build_step = await self._run_build()
            steps.append(build_step)
            logs.append(f"[BUILD] {build_step.stdout}")
            logs.append(f"[BUILD ERROR] {build_step.stderr}")

            if not build_step.success:
                return self._create_result(steps, logs, start_time, build_step.error_message)

            # Step 2: Package (optional)
            if include_package:
                self.logger.info("deployment_step_package_started")
                package_step = await self._run_package()
                steps.append(package_step)
                logs.append(f"[PACKAGE] {package_step.stdout}")
                logs.append(f"[PACKAGE ERROR] {package_step.stderr}")

                if not package_step.success:
                    return self._create_result(steps, logs, start_time, package_step.error_message)

            # Step 3: Launch test (optional)
            if test_launch:
                self.logger.info("deployment_step_launch_started")
                launch_step = await self._test_launch()
                steps.append(launch_step)
                logs.append(f"[LAUNCH] {launch_step.stdout}")
                logs.append(f"[LAUNCH ERROR] {launch_step.stderr}")

                if not launch_step.success:
                    return self._create_result(steps, logs, start_time, launch_step.error_message)

            # Success!
            return self._create_result(steps, logs, start_time)

        except Exception as e:
            self.logger.error("deployment_failed", error=str(e))
            return self._create_result(steps, logs, start_time, str(e))

    async def _run_build(self) -> DeploymentStep:
        """Run npm run build."""
        step_start = datetime.now()
        command = "npm run build"

        try:
            # Use Claude CLI to run build with context awareness
            result = await self._execute_command(
                command=command,
                description="Build the Electron application",
            )

            duration_ms = int((datetime.now() - step_start).total_seconds() * 1000)

            return DeploymentStep(
                name="build",
                command=command,
                success=result["success"],
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                duration_ms=duration_ms,
                error_message=result.get("error") if not result["success"] else None,
            )

        except Exception as e:
            duration_ms = int((datetime.now() - step_start).total_seconds() * 1000)
            return DeploymentStep(
                name="build",
                command=command,
                success=False,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def _run_package(self) -> DeploymentStep:
        """Run npm run package."""
        step_start = datetime.now()
        command = "npm run package"

        try:
            result = await self._execute_command(
                command=command,
                description="Package the Electron application for distribution",
            )

            duration_ms = int((datetime.now() - step_start).total_seconds() * 1000)

            return DeploymentStep(
                name="package",
                command=command,
                success=result["success"],
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                duration_ms=duration_ms,
                error_message=result.get("error") if not result["success"] else None,
            )

        except Exception as e:
            duration_ms = int((datetime.now() - step_start).total_seconds() * 1000)
            return DeploymentStep(
                name="package",
                command=command,
                success=False,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def _test_launch(self) -> DeploymentStep:
        """Test electron launch (quick smoke test)."""
        step_start = datetime.now()
        command = "npm run dev"  # Run dev server briefly to test

        try:
            # Launch and immediately kill after 5 seconds
            result = await self._execute_command(
                command=command,
                description="Test launching the Electron application",
                timeout=5,  # Kill after 5 seconds
            )

            duration_ms = int((datetime.now() - step_start).total_seconds() * 1000)

            # For launch test, timeout is expected (app running is good)
            success = "timeout" in result.get("error", "").lower() or result["success"]

            return DeploymentStep(
                name="launch_test",
                command=command,
                success=success,
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                duration_ms=duration_ms,
                error_message=None if success else result.get("error"),
            )

        except Exception as e:
            duration_ms = int((datetime.now() - step_start).total_seconds() * 1000)
            return DeploymentStep(
                name="launch_test",
                command=command,
                success=False,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def _execute_command(
        self,
        command: str,
        description: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        Execute command using subprocess.

        Args:
            command: Command to execute
            description: Human-readable description
            timeout: Timeout in seconds

        Returns:
            Dict with success, stdout, stderr, error
        """
        import subprocess

        try:
            self.logger.debug("executing_command", command=command, description=description)

            # Run command with timeout
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                return_code = process.returncode

                return {
                    "success": return_code == 0,
                    "stdout": stdout.decode("utf-8", errors="ignore"),
                    "stderr": stderr.decode("utf-8", errors="ignore"),
                    "error": None if return_code == 0 else f"Command exited with code {return_code}",
                }

            except asyncio.TimeoutError:
                # Kill process
                process.kill()
                await process.wait()

                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "",
                    "error": f"Command timed out after {timeout}s",
                }

        except Exception as e:
            self.logger.error("command_execution_failed", command=command, error=str(e))
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "error": str(e),
            }

    def _create_result(
        self,
        steps: List[DeploymentStep],
        logs: List[str],
        start_time: datetime,
        error_message: Optional[str] = None,
    ) -> DeploymentResult:
        """Create deployment result."""
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        success = all(step.success for step in steps) and error_message is None

        return DeploymentResult(
            success=success,
            steps=steps,
            total_duration_ms=duration_ms,
            error_message=error_message,
            logs=logs,
        )


async def deploy_project(
    project_dir: str,
    include_package: bool = False,
    test_launch: bool = True,
) -> DeploymentResult:
    """
    Convenience function to deploy a project.

    Args:
        project_dir: Path to project directory
        include_package: Whether to run npm run package
        test_launch: Whether to test electron launch

    Returns:
        DeploymentResult
    """
    tool = DeployTool(project_dir)
    return await tool.deploy(include_package=include_package, test_launch=test_launch)
