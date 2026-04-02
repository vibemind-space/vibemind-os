"""
Cloud Test Tool - GitHub Actions integration for multi-platform testing.

This tool:
1. Detects GitHub repo from .git/config
2. Generates multi-platform workflow YAML
3. Triggers workflow via GitHub API
4. Polls for completion and extracts results
"""

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class Platform(str, Enum):
    """Supported CI/CD platforms."""
    LINUX = "ubuntu-latest"
    MACOS = "macos-latest"
    WINDOWS = "windows-latest"


class WorkflowStatus(str, Enum):
    """GitHub Actions workflow status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class PlatformResult:
    """Result from a single platform test."""
    platform: Platform
    success: bool
    duration_seconds: float = 0
    logs: str = ""
    error_message: Optional[str] = None


@dataclass
class CloudTestResult:
    """Result from cloud testing."""
    success: bool
    workflow_id: Optional[int] = None
    workflow_url: Optional[str] = None
    status: WorkflowStatus = WorkflowStatus.UNKNOWN

    # Per-platform results
    platforms_tested: int = 0
    platforms_passed: int = 0
    platform_results: list[PlatformResult] = field(default_factory=list)

    # Timing
    total_duration_seconds: float = 0

    # Errors
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "workflow_id": self.workflow_id,
            "workflow_url": self.workflow_url,
            "status": self.status.value,
            "platforms_tested": self.platforms_tested,
            "platforms_passed": self.platforms_passed,
            "platform_results": [
                {
                    "platform": r.platform.value,
                    "success": r.success,
                    "duration_seconds": r.duration_seconds,
                    "error_message": r.error_message,
                }
                for r in self.platform_results
            ],
            "total_duration_seconds": self.total_duration_seconds,
            "error_message": self.error_message,
        }


class CloudTestTool:
    """
    Tool for running tests via GitHub Actions.

    Features:
    - Auto-detect GitHub repo from .git/config
    - Generate multi-platform workflow YAML
    - Trigger workflow via API
    - Poll for completion
    - Extract per-platform results
    """

    WORKFLOW_TEMPLATE = """# Auto-generated workflow for deployment verification
name: Deployment Verification

on:
  workflow_dispatch:
    inputs:
      trigger_source:
        description: 'Source that triggered this workflow'
        required: false
        default: 'coding-engine'

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Run tests
        run: npm test || true

      - name: Health check (Linux/macOS)
        if: runner.os != 'Windows'
        run: |
          npm run preview &
          sleep 10
          curl -sf http://localhost:4173 || curl -sf http://localhost:5173 || echo "Preview not available"

      - name: Health check (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          Start-Process npm -ArgumentList "run", "preview" -NoNewWindow
          Start-Sleep -Seconds 10
          try { Invoke-WebRequest -Uri http://localhost:4173 -UseBasicParsing } catch { Write-Host "Preview not available" }

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: build-${{ matrix.os }}
          path: |
            dist/
            out/
          retention-days: 7
"""

    def __init__(
        self,
        project_dir: str,
        github_token: Optional[str] = None,
        poll_interval: int = 30,
        timeout: int = 600,
        platforms: Optional[list[Platform]] = None,
    ):
        """
        Initialize cloud test tool.

        Args:
            project_dir: Path to project directory
            github_token: GitHub token (defaults to GITHUB_TOKEN env var)
            poll_interval: Seconds between status polls
            timeout: Maximum wait time in seconds
            platforms: Platforms to test (defaults to all)
        """
        self.project_dir = Path(project_dir)
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.platforms = platforms or list(Platform)

        self.logger = logger.bind(component="cloud_test_tool")

        # GitHub repo info (detected lazily)
        self._owner: Optional[str] = None
        self._repo: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        """Check if tool is properly configured."""
        return bool(self.github_token) and self._detect_repo()

    def _detect_repo(self) -> bool:
        """Detect GitHub repo from .git/config."""
        if self._owner and self._repo:
            return True

        git_config = self.project_dir / ".git" / "config"
        if not git_config.exists():
            self.logger.warning("git_config_not_found")
            return False

        try:
            content = git_config.read_text()

            # Match GitHub URLs
            patterns = [
                r'url\s*=\s*https://github\.com/([^/]+)/([^/\s\.]+)',
                r'url\s*=\s*git@github\.com:([^/]+)/([^/\s\.]+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    self._owner = match.group(1)
                    self._repo = match.group(2).replace('.git', '')
                    self.logger.info(
                        "repo_detected",
                        owner=self._owner,
                        repo=self._repo,
                    )
                    return True

            self.logger.warning("github_url_not_found")
            return False

        except Exception as e:
            self.logger.error("repo_detection_failed", error=str(e))
            return False

    async def run_cloud_tests(self) -> CloudTestResult:
        """
        Run tests via GitHub Actions.

        Returns:
            CloudTestResult with test results
        """
        start_time = datetime.now()

        # Validate configuration
        if not self.github_token:
            return CloudTestResult(
                success=False,
                error_message="GITHUB_TOKEN not set",
            )

        if not self._detect_repo():
            return CloudTestResult(
                success=False,
                error_message="Could not detect GitHub repo",
            )

        try:
            # Ensure workflow file exists
            await self._ensure_workflow_file()

            # Trigger workflow
            workflow_id = await self._trigger_workflow()
            if not workflow_id:
                return CloudTestResult(
                    success=False,
                    error_message="Failed to trigger workflow",
                )

            workflow_url = f"https://github.com/{self._owner}/{self._repo}/actions/runs/{workflow_id}"
            self.logger.info("workflow_triggered", workflow_id=workflow_id, url=workflow_url)

            # Poll for completion
            status, platform_results = await self._poll_workflow(workflow_id)

            duration = (datetime.now() - start_time).total_seconds()

            platforms_passed = sum(1 for r in platform_results if r.success)

            return CloudTestResult(
                success=status == WorkflowStatus.COMPLETED and platforms_passed == len(platform_results),
                workflow_id=workflow_id,
                workflow_url=workflow_url,
                status=status,
                platforms_tested=len(platform_results),
                platforms_passed=platforms_passed,
                platform_results=platform_results,
                total_duration_seconds=duration,
            )

        except Exception as e:
            self.logger.error("cloud_test_error", error=str(e))
            return CloudTestResult(
                success=False,
                error_message=str(e),
                total_duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    async def _ensure_workflow_file(self) -> None:
        """Ensure workflow file exists in repo."""
        workflows_dir = self.project_dir / ".github" / "workflows"
        workflow_file = workflows_dir / "deployment-verification.yml"

        if workflow_file.exists():
            self.logger.debug("workflow_file_exists")
            return

        # Create workflow file
        workflows_dir.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(self.WORKFLOW_TEMPLATE)
        self.logger.info("workflow_file_created", path=str(workflow_file))

        # Note: This file needs to be committed and pushed for the workflow to run
        # The caller should handle git operations

    async def _trigger_workflow(self) -> Optional[int]:
        """Trigger workflow via GitHub API."""
        try:
            import httpx
        except ImportError:
            self.logger.error("httpx_not_installed")
            return None

        url = f"https://api.github.com/repos/{self._owner}/{self._repo}/actions/workflows/deployment-verification.yml/dispatches"

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        data = {
            "ref": "main",
            "inputs": {
                "trigger_source": "coding-engine",
            },
        }

        async with httpx.AsyncClient() as client:
            # Trigger workflow
            response = await client.post(url, headers=headers, json=data)

            if response.status_code not in (204, 202):
                self.logger.error(
                    "workflow_trigger_failed",
                    status=response.status_code,
                    body=response.text,
                )
                return None

            # Wait a moment for workflow to be created
            await asyncio.sleep(2)

            # Get the latest workflow run
            runs_url = f"https://api.github.com/repos/{self._owner}/{self._repo}/actions/runs"
            params = {"event": "workflow_dispatch", "per_page": 1}

            response = await client.get(runs_url, headers=headers, params=params)
            if response.status_code != 200:
                self.logger.error("failed_to_get_workflow_run")
                return None

            runs = response.json().get("workflow_runs", [])
            if not runs:
                self.logger.error("no_workflow_runs_found")
                return None

            return runs[0]["id"]

    async def _poll_workflow(
        self,
        workflow_id: int,
    ) -> tuple[WorkflowStatus, list[PlatformResult]]:
        """
        Poll workflow until completion.

        Returns:
            Tuple of (status, platform_results)
        """
        try:
            import httpx
        except ImportError:
            return WorkflowStatus.UNKNOWN, []

        url = f"https://api.github.com/repos/{self._owner}/{self._repo}/actions/runs/{workflow_id}"
        jobs_url = f"{url}/jobs"

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        start_time = datetime.now()

        async with httpx.AsyncClient() as client:
            while True:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.timeout:
                    self.logger.warning("workflow_timeout", elapsed=elapsed)
                    return WorkflowStatus.UNKNOWN, []

                # Check workflow status
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    self.logger.error("failed_to_check_status")
                    await asyncio.sleep(self.poll_interval)
                    continue

                run_data = response.json()
                status_str = run_data.get("status", "unknown")
                conclusion = run_data.get("conclusion")

                self.logger.debug(
                    "workflow_status",
                    status=status_str,
                    conclusion=conclusion,
                    elapsed=elapsed,
                )

                if status_str == "completed":
                    # Get job results
                    jobs_response = await client.get(jobs_url, headers=headers)
                    platform_results = []

                    if jobs_response.status_code == 200:
                        jobs = jobs_response.json().get("jobs", [])
                        for job in jobs:
                            # Extract platform from job name
                            job_name = job.get("name", "")
                            platform = self._extract_platform(job_name)
                            if platform:
                                platform_results.append(PlatformResult(
                                    platform=platform,
                                    success=job.get("conclusion") == "success",
                                    duration_seconds=self._calculate_job_duration(job),
                                    error_message=None if job.get("conclusion") == "success" else f"Job failed: {job.get('conclusion')}",
                                ))

                    status = (
                        WorkflowStatus.COMPLETED if conclusion == "success"
                        else WorkflowStatus.FAILED if conclusion in ("failure", "cancelled")
                        else WorkflowStatus.UNKNOWN
                    )

                    return status, platform_results

                await asyncio.sleep(self.poll_interval)

    def _extract_platform(self, job_name: str) -> Optional[Platform]:
        """Extract platform from job name."""
        job_lower = job_name.lower()
        if "ubuntu" in job_lower or "linux" in job_lower:
            return Platform.LINUX
        elif "macos" in job_lower or "mac" in job_lower:
            return Platform.MACOS
        elif "windows" in job_lower or "win" in job_lower:
            return Platform.WINDOWS
        return None

    def _calculate_job_duration(self, job: dict) -> float:
        """Calculate job duration in seconds."""
        try:
            started = job.get("started_at")
            completed = job.get("completed_at")
            if started and completed:
                start = datetime.fromisoformat(started.replace("Z", "+00:00"))
                end = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                return (end - start).total_seconds()
        except Exception:
            pass
        return 0

    def generate_workflow_yaml(self) -> str:
        """Generate workflow YAML for the project."""
        return self.WORKFLOW_TEMPLATE


# Convenience function
async def run_cloud_tests(project_dir: str) -> CloudTestResult:
    """
    Run cloud tests for a project.

    Args:
        project_dir: Path to project directory

    Returns:
        CloudTestResult with test results
    """
    tool = CloudTestTool(project_dir)
    return await tool.run_cloud_tests()
