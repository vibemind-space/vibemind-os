"""
Sandbox Tool - Docker-based isolated testing for any app type.

This tool:
1. Auto-detects project type (Electron, React, Node.js, Python)
2. Spins up a Docker container with appropriate runtime
3. Copies project and runs build/test/start verification
4. Returns structured results for deployment validation
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


class ProjectType(str, Enum):
    """Supported project types for sandbox testing."""
    ELECTRON = "electron"
    REACT_VITE = "react_vite"
    NODE_API = "node_api"
    PYTHON_FASTAPI = "python_fastapi"
    PYTHON_FLASK = "python_flask"
    UNKNOWN = "unknown"


@dataclass
class SandboxStep:
    """Single step in sandbox testing."""
    name: str
    command: str
    success: bool
    stdout: str
    stderr: str
    duration_ms: int
    exit_code: int = 0
    error_message: Optional[str] = None


@dataclass
class ContinuousSandboxCycle:
    """Result of a single cycle in continuous sandbox testing."""
    cycle_number: int
    timestamp: datetime
    success: bool
    app_started: bool
    app_responsive: bool
    duration_ms: int
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "cycle_number": self.cycle_number,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "app_started": self.app_started,
            "app_responsive": self.app_responsive,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


@dataclass
class SandboxResult:
    """Result of sandbox testing."""
    success: bool
    project_type: ProjectType
    container_id: Optional[str] = None
    steps: List[SandboxStep] = field(default_factory=list)
    total_duration_ms: int = 0
    app_started: bool = False
    app_responsive: bool = False
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    # VNC Screen streaming
    vnc_enabled: bool = False
    vnc_url: Optional[str] = None
    vnc_port: int = 6080

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "success": self.success,
            "project_type": self.project_type.value,
            "container_id": self.container_id,
            "steps": [
                {
                    "name": s.name,
                    "command": s.command,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "exit_code": s.exit_code,
                    "error_message": s.error_message,
                }
                for s in self.steps
            ],
            "total_duration_ms": self.total_duration_ms,
            "app_started": self.app_started,
            "app_responsive": self.app_responsive,
            "error_message": self.error_message,
            "logs": self.logs[-50:] if self.logs else [],
        }
        # Add VNC streaming info if enabled
        if self.vnc_enabled:
            result["vnc_streaming"] = {
                "enabled": self.vnc_enabled,
                "url": self.vnc_url,
                "port": self.vnc_port,
            }
        return result


class SandboxTool:
    """
    Docker-based sandbox for isolated project testing.

    Workflow:
    1. Detect project type from package.json / requirements.txt
    2. Select appropriate Docker image
    3. Create container and copy project
    4. Run: install → build → test → start → health check
    5. Collect logs and cleanup

    VNC Streaming:
    When enable_vnc=True, apps can be viewed via browser at
    http://localhost:6080/vnc.html (noVNC web interface).
    - Electron apps: Direct display via Xvfb
    - Web apps: Chromium browser automatically opens the app URL

    Continuous Testing Mode:
    Use run_continuous_tests() for a 30-second cycle loop that:
    - Creates container once at start
    - Every cycle: starts app → health check → kills app → reports status
    - Keeps running until stopped or convergence reached
    """

    # Custom sandbox image with VNC support
    SANDBOX_IMAGE = "sandbox-test"

    # Fallback Docker images for different project types (if custom image not built)
    IMAGES = {
        ProjectType.ELECTRON: "node:20-slim",
        ProjectType.REACT_VITE: "node:20-slim",
        ProjectType.NODE_API: "node:20-slim",
        ProjectType.PYTHON_FASTAPI: "python:3.11-slim",
        ProjectType.PYTHON_FLASK: "python:3.11-slim",
        ProjectType.UNKNOWN: "node:20-slim",
    }

    # Default VNC ports
    DEFAULT_VNC_PORT = 5900
    DEFAULT_NOVNC_PORT = 6080

    def __init__(
        self,
        project_dir: str,
        timeout: int = 300,
        cleanup: bool = True,
        enable_vnc: bool = False,
        vnc_port: int = 6080,
        cycle_interval: int = 30,
        enable_database_setup: bool = True,  # Run prisma generate/db push/seed
    ):
        """
        Initialize sandbox tool.

        Args:
            project_dir: Path to project directory
            timeout: Timeout for sandbox tests in seconds
            cleanup: Whether to cleanup container after tests
            enable_vnc: Enable VNC streaming for all app types (Electron, React, Node API, Python)
            vnc_port: noVNC web port (default 6080, access via http://localhost:6080/vnc.html)
            cycle_interval: Interval in seconds for continuous testing mode (default 30)
            enable_database_setup: Run Prisma database setup if prisma schema exists
        """
        self.project_dir = Path(project_dir)
        self.timeout = timeout
        self.cleanup = cleanup
        self.enable_vnc = enable_vnc
        self.vnc_port = vnc_port
        self.cycle_interval = cycle_interval
        self.enable_database_setup = enable_database_setup
        self.container_id: Optional[str] = None
        self._continuous_running = False
        self._project_type: Optional[ProjectType] = None
        self._deps_installed = False
        self._build_complete = False
        self._database_setup_complete = False
        self.logger = logger.bind(component="sandbox_tool", project_dir=project_dir)

    def detect_project_type(self) -> ProjectType:
        """Detect project type from project files."""
        package_json = self.project_dir / "package.json"
        requirements_txt = self.project_dir / "requirements.txt"
        pyproject_toml = self.project_dir / "pyproject.toml"

        # Check for Python projects
        if requirements_txt.exists() or pyproject_toml.exists():
            # Check for FastAPI or Flask
            req_content = ""
            if requirements_txt.exists():
                req_content = requirements_txt.read_text().lower()
            if pyproject_toml.exists():
                req_content += pyproject_toml.read_text().lower()

            if "fastapi" in req_content:
                return ProjectType.PYTHON_FASTAPI
            elif "flask" in req_content:
                return ProjectType.PYTHON_FLASK

        # Check for Node.js projects
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                deps = {
                    **pkg.get("dependencies", {}),
                    **pkg.get("devDependencies", {}),
                }

                # Check for Electron
                if "electron" in deps or "electron-vite" in deps:
                    return ProjectType.ELECTRON

                # Check for React/Vue/Vite
                if any(k in deps for k in ["react", "vue", "vite", "@vitejs/plugin-react"]):
                    return ProjectType.REACT_VITE

                # Check for Node.js API (Express, Fastify, etc.)
                if any(k in deps for k in ["express", "fastify", "koa", "hapi"]):
                    return ProjectType.NODE_API

                # Default to React/Vite for web projects
                return ProjectType.REACT_VITE

            except (json.JSONDecodeError, IOError):
                pass

        return ProjectType.UNKNOWN

    async def check_docker_available(self) -> bool:
        """Check if Docker is available."""
        result = await self._run_command(["docker", "version"], timeout=10)
        return result.exit_code == 0

    async def check_sandbox_image_available(self) -> bool:
        """Check if custom sandbox image is available."""
        result = await self._run_command(
            ["docker", "images", "-q", self.SANDBOX_IMAGE],
            timeout=10,
        )
        return result.exit_code == 0 and result.stdout.strip() != ""

    async def run_sandbox_tests(
        self,
        env_vars: Optional[dict[str, str]] = None,
        persistent: bool = False,
    ) -> SandboxResult:
        """
        Run project in sandbox and execute verification tests.

        Args:
            env_vars: Additional environment variables to inject (e.g., secrets)
            persistent: If True, keep container running indefinitely for viewing

        Returns:
            SandboxResult with test outcomes
        """
        # Store env_vars and persistent mode for use in container creation
        self._extra_env_vars = env_vars or {}
        self._persistent_mode = persistent
        start_time = datetime.now()
        project_type = self.detect_project_type()
        result = SandboxResult(
            success=False,
            project_type=project_type,
        )

        self.logger.info(
            "sandbox_test_starting",
            project_type=result.project_type.value,
            vnc_enabled=self.enable_vnc,
        )

        try:
            # Check Docker is available
            if not await self.check_docker_available():
                result.error_message = "Docker is not available"
                self.logger.error("docker_not_available")
                return result

            # Create container
            container_step = await self._create_container(result.project_type)
            result.steps.append(container_step)
            if not container_step.success:
                result.error_message = "Failed to create container"
                return result

            result.container_id = container_step.stdout.strip()[:12]

            # Set VNC info if enabled (for ALL project types)
            if self.enable_vnc:
                result.vnc_enabled = True
                result.vnc_port = self.vnc_port
                result.vnc_url = f"http://localhost:{self.vnc_port}/vnc.html"
                self.logger.info(
                    "vnc_stream_available",
                    vnc_url=result.vnc_url,
                    container_id=result.container_id,
                    project_type=project_type.value,
                )

            # Copy project to container
            copy_step = await self._copy_project()
            result.steps.append(copy_step)
            if not copy_step.success:
                result.error_message = "Failed to copy project to container"
                return result

            # Run project-specific test sequence
            if result.project_type in [ProjectType.ELECTRON, ProjectType.REACT_VITE, ProjectType.NODE_API]:
                test_result = await self._test_node_project(result.project_type)
            else:
                test_result = await self._test_python_project(result.project_type)

            result.steps.extend(test_result["steps"])
            result.app_started = test_result.get("app_started", False)
            result.app_responsive = test_result.get("app_responsive", False)

            # Collect logs
            result.logs = await self._collect_logs()

            # Determine overall success
            result.success = all(s.success for s in result.steps)

        except Exception as e:
            self.logger.error("sandbox_test_error", error=str(e))
            result.error_message = str(e)

        finally:
            # Don't cleanup in persistent mode or if cleanup is disabled
            if self.cleanup and self.container_id and not self._persistent_mode:
                await self._cleanup()

            result.total_duration_ms = int(
                (datetime.now() - start_time).total_seconds() * 1000
            )

        self.logger.info(
            "sandbox_test_complete",
            success=result.success,
            duration_ms=result.total_duration_ms,
            vnc_url=result.vnc_url if result.vnc_enabled else None,
        )

        return result

    async def run_continuous_tests(
        self,
        max_cycles: Optional[int] = None,
        stop_on_success: bool = False,
    ):
        """
        Run continuous sandbox tests in a loop (30-second default interval).
        
        This is an async generator that yields ContinuousSandboxCycle results.
        Container is created once, then each cycle:
        1. Starts the app
        2. Performs health check
        3. Kills the app process
        4. Yields cycle result
        5. Waits for next interval
        
        Args:
            max_cycles: Maximum number of cycles (None = infinite)
            stop_on_success: Stop after first successful cycle
            
        Yields:
            ContinuousSandboxCycle for each test cycle
            
        Example:
            async for cycle in sandbox.run_continuous_tests():
                print(f"Cycle {cycle.cycle_number}: {'✓' if cycle.success else '✗'}")
                if cycle.success:
                    break
        """
        self._continuous_running = True
        cycle_number = 0
        
        self.logger.info(
            "continuous_sandbox_starting",
            interval_seconds=self.cycle_interval,
            max_cycles=max_cycles,
            vnc_enabled=self.enable_vnc,
        )
        
        try:
            # Phase 1: Setup (only once)
            setup_result = await self._setup_continuous_container()
            if not setup_result["success"]:
                yield ContinuousSandboxCycle(
                    cycle_number=0,
                    timestamp=datetime.now(),
                    success=False,
                    app_started=False,
                    app_responsive=False,
                    duration_ms=0,
                    error_message=setup_result.get("error", "Setup failed"),
                )
                return
            
            # Phase 2: Continuous test loop
            while self._continuous_running:
                cycle_number += 1
                cycle_start = datetime.now()
                
                self.logger.info(
                    "continuous_cycle_starting",
                    cycle=cycle_number,
                )
                
                # Run single test cycle
                cycle_result = await self._run_single_cycle(cycle_number)
                
                yield cycle_result
                
                # Check stop conditions
                if max_cycles and cycle_number >= max_cycles:
                    self.logger.info("max_cycles_reached", cycles=cycle_number)
                    break
                    
                if stop_on_success and cycle_result.success:
                    self.logger.info("success_reached_stopping", cycle=cycle_number)
                    break
                
                # Wait for next interval
                elapsed = (datetime.now() - cycle_start).total_seconds()
                wait_time = max(0, self.cycle_interval - elapsed)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    
        finally:
            self._continuous_running = False
            if self.cleanup:
                await self._cleanup()

    async def _run_single_cycle(self, cycle_number: int) -> ContinuousSandboxCycle:
        """
        Run a single test cycle: start → check → kill.
        """
        cycle_start = datetime.now()
        app_started = False
        app_responsive = False
        error_message = None
        
        try:
            # Step 1: Start app
            if self._project_type == ProjectType.ELECTRON:
                start_result = await self._cycle_start_electron()
            elif self._project_type == ProjectType.REACT_VITE:
                start_result = await self._cycle_start_vite()
            elif self._project_type == ProjectType.NODE_API:
                start_result = await self._cycle_start_node_api()
            elif self._project_type == ProjectType.PYTHON_FASTAPI:
                start_result = await self._cycle_start_fastapi()
            else:
                start_result = await self._cycle_start_flask()
            
            app_started = start_result.get("started", False)
            
            # Step 2: Health check
            if app_started:
                health_result = await self._cycle_health_check()
                app_responsive = health_result.get("responsive", False)

                # Log health check details for debugging
                self.logger.debug(
                    "health_check_result",
                    cycle=cycle_number,
                    responsive=app_responsive,
                    check_stdout=health_result.get("stdout", "")[:200],
                    check_stderr=health_result.get("stderr", "")[:200],
                )

                # Step 2.5: Start browser for VNC display if app is responsive
                if app_responsive and self.enable_vnc:
                    await self._start_browser_for_vnc()
            else:
                # Log why app didn't start
                self.logger.warning(
                    "app_not_started",
                    cycle=cycle_number,
                    start_stdout=start_result.get("stdout", "")[:200],
                    start_stderr=start_result.get("stderr", "")[:200],
                )
            
            # Step 3: Kill app process (only if not VNC mode - keep running for viewing)
            if not self.enable_vnc:
                await self._cycle_kill_app()
            
        except Exception as e:
            error_message = str(e)
            self.logger.error("cycle_error", cycle=cycle_number, error=error_message)
        
        # Collect brief logs
        logs = await self._collect_logs()
        
        duration_ms = int((datetime.now() - cycle_start).total_seconds() * 1000)
        success = app_started and app_responsive
        
        self.logger.info(
            "continuous_cycle_complete",
            cycle=cycle_number,
            success=success,
            app_started=app_started,
            app_responsive=app_responsive,
            duration_ms=duration_ms,
        )
        
        return ContinuousSandboxCycle(
            cycle_number=cycle_number,
            timestamp=datetime.now(),
            success=success,
            app_started=app_started,
            app_responsive=app_responsive,
            duration_ms=duration_ms,
            error_message=error_message,
            logs=logs[-20:] if logs else [],
        )

    async def _start_browser_for_vnc(self) -> Dict[str, Any]:
        """
        Start Chromium browser to display the app in VNC.
        """
        # Determine app URL based on project type
        if self._project_type == ProjectType.REACT_VITE:
            app_url = "http://localhost:4173"
        elif self._project_type == ProjectType.NODE_API:
            app_url = "http://localhost:3000"
        elif self._project_type == ProjectType.PYTHON_FASTAPI:
            app_url = "http://localhost:8000"
        elif self._project_type == ProjectType.PYTHON_FLASK:
            app_url = "http://localhost:5000"
        else:
            app_url = "http://localhost:3000"
        
        self.logger.info(
            "starting_browser_for_vnc",
            app_url=app_url,
            container_id=self.container_id,
        )
        
        try:
            # Start Chromium in kiosk mode
            browser_result = await self._exec_in_container(
                "start_browser",
                [
                    "bash", "-c",
                    f"DISPLAY=:99 chromium --no-sandbox --disable-gpu --disable-software-rasterizer "
                    f"--disable-dev-shm-usage --disable-extensions --window-size=1280,800 "
                    f"--window-position=0,0 --start-maximized --kiosk --app='{app_url}' &"
                ],
                timeout=15,
            )
            
            await asyncio.sleep(2)
            
            # Verify browser started
            check_result = await self._exec_in_container(
                "check_browser",
                ["bash", "-c", "pgrep -f chromium | head -1"],
                timeout=5,
            )
            
            browser_started = check_result.exit_code == 0 and check_result.stdout.strip()
            
            self.logger.info(
                "browser_started_for_vnc",
                app_url=app_url,
                browser_started=browser_started,
            )
            
            return {"success": browser_started, "app_url": app_url}
            
        except Exception as e:
            self.logger.warning("browser_start_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def _setup_continuous_container(self) -> Dict[str, Any]:
        """
        Setup container for continuous testing. Called once at start.
        Creates container, copies project, installs deps, builds, and starts VNC if enabled.
        """
        self._project_type = self.detect_project_type()
        
        self.logger.info(
            "continuous_setup_starting",
            project_type=self._project_type.value,
            vnc_enabled=self.enable_vnc,
        )
        
        try:
            # Step 1: Create container
            container_step = await self._create_container(self._project_type)
            if not container_step.success:
                return {"success": False, "error": f"Container creation failed: {container_step.error_message}"}
            
            self.container_id = container_step.stdout.strip()[:12]
            
            # Step 2: Start VNC services if enabled (BEFORE copying project)
            if self.enable_vnc:
                vnc_result = await self._start_vnc_services()
                if not vnc_result.get("success", False):
                    self.logger.warning("vnc_services_start_failed", error=vnc_result.get("error"))
            
            # Step 3: Copy project
            copy_step = await self._copy_project()
            if not copy_step.success:
                return {"success": False, "error": f"Project copy failed: {copy_step.error_message}"}
            
            # Step 4: Install dependencies
            install_step = await self._install_dependencies()
            if not install_step.success:
                return {"success": False, "error": f"Dependency install failed: {install_step.error_message}"}

            self._deps_installed = True

            # Step 4.5: Database setup (if prisma exists and enabled)
            if self.enable_database_setup and self._project_type in [
                ProjectType.ELECTRON, ProjectType.REACT_VITE, ProjectType.NODE_API
            ]:
                db_steps = await self._run_database_setup()
                if db_steps and not all(s.success for s in db_steps):
                    self.logger.warning("database_setup_partial_failure")
                # Database setup failure is not fatal

            # Step 5: Build project
            build_step = await self._build_project()
            if not build_step.success:
                # Build failure is not fatal for continuous testing
                self.logger.warning("initial_build_failed", error=build_step.error_message)
            else:
                self._build_complete = True

            self.logger.info(
                "continuous_setup_complete",
                container_id=self.container_id,
                deps_installed=self._deps_installed,
                build_complete=self._build_complete,
                database_setup=self._database_setup_complete,
                vnc_enabled=self.enable_vnc,
            )
            
            return {"success": True, "container_id": self.container_id}
            
        except Exception as e:
            self.logger.error("continuous_setup_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def _start_vnc_services(self) -> Dict[str, Any]:
        """
        Start VNC services inside the container: Xvfb, x11vnc, noVNC.
        This is called after container creation when enable_vnc=True.
        """
        self.logger.info("starting_vnc_services", container_id=self.container_id)
        
        try:
            # Step 1: Start Xvfb (virtual framebuffer)
            xvfb_result = await self._exec_in_container(
                "start_xvfb",
                ["bash", "-c", "Xvfb :99 -screen 0 1280x800x24 &"],
                timeout=10,
            )
            await asyncio.sleep(1)
            
            # Step 2: Start x11vnc (VNC server)
            x11vnc_result = await self._exec_in_container(
                "start_x11vnc",
                ["bash", "-c", f"x11vnc -display :99 -nopw -forever -shared -rfbport {self.DEFAULT_VNC_PORT} -bg"],
                timeout=15,
            )
            await asyncio.sleep(1)
            
            # Step 3: Start websockify/noVNC (web interface)
            novnc_result = await self._exec_in_container(
                "start_novnc",
                ["bash", "-c", f"websockify --web=/usr/share/novnc {self.vnc_port} localhost:{self.DEFAULT_VNC_PORT} &"],
                timeout=10,
            )
            await asyncio.sleep(1)
            
            # Verify services are running
            check_result = await self._exec_in_container(
                "check_vnc_services",
                ["bash", "-c", "pgrep -f 'Xvfb|x11vnc|websockify' | wc -l"],
                timeout=5,
            )
            
            services_running = int(check_result.stdout.strip() or "0") >= 2
            
            self.logger.info(
                "vnc_services_started",
                xvfb=xvfb_result.success,
                x11vnc=x11vnc_result.success,
                novnc=novnc_result.success,
                services_running=services_running,
                vnc_url=f"http://localhost:{self.vnc_port}/vnc.html",
            )
            
            return {
                "success": services_running,
                "vnc_url": f"http://localhost:{self.vnc_port}/vnc.html",
            }
            
        except Exception as e:
            self.logger.error("vnc_services_start_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def _install_dependencies(self) -> SandboxStep:
        """Install project dependencies."""
        if self._project_type in [ProjectType.ELECTRON, ProjectType.REACT_VITE, ProjectType.NODE_API]:
            return await self._exec_in_container(
                "install_deps",
                ["npm", "install", "--legacy-peer-deps"],
                timeout=180,
            )
        else:
            return await self._exec_in_container(
                "install_deps",
                ["pip", "install", "-r", "requirements.txt"],
                timeout=180,
            )

    async def _build_project(self) -> SandboxStep:
        """Build the project."""
        if self._project_type in [ProjectType.ELECTRON, ProjectType.REACT_VITE, ProjectType.NODE_API]:
            return await self._exec_in_container(
                "build",
                ["npm", "run", "build"],
                timeout=120,
            )
        else:
            # Python projects don't need build
            return SandboxStep(
                name="build",
                command="N/A (Python)",
                success=True,
                stdout="Python project - no build required",
                stderr="",
                duration_ms=0,
                exit_code=0,
            )

    async def _run_database_setup(self) -> List[SandboxStep]:
        """
        Run Prisma database setup commands if prisma schema exists.

        Steps:
        1. npx prisma generate - Generate Prisma client
        2. npx prisma db push - Push schema to database
        3. npx prisma db seed - Seed with initial data (if seed script exists)

        Returns:
            List of SandboxStep results
        """
        steps = []

        # Check if prisma schema exists
        check_prisma = await self._exec_in_container(
            "check_prisma_schema",
            ["bash", "-c", "test -f prisma/schema.prisma && echo 'exists' || echo 'missing'"],
            timeout=5,
        )

        if "missing" in check_prisma.stdout:
            self.logger.info("prisma_schema_not_found", message="Skipping database setup")
            return steps

        self.logger.info("database_setup_starting", message="Found prisma/schema.prisma")

        # Step 1: Generate Prisma client
        generate_step = await self._exec_in_container(
            "prisma_generate",
            ["npx", "prisma", "generate"],
            timeout=60,
        )
        steps.append(generate_step)

        if not generate_step.success:
            self.logger.warning(
                "prisma_generate_failed",
                error=generate_step.error_message,
            )
            return steps

        self.logger.info("prisma_generate_complete")

        # Step 2: Push schema to database
        # Using --accept-data-loss for dev environments to auto-reset if needed
        db_push_step = await self._exec_in_container(
            "prisma_db_push",
            ["npx", "prisma", "db", "push", "--accept-data-loss"],
            timeout=120,
        )
        steps.append(db_push_step)

        if not db_push_step.success:
            self.logger.warning(
                "prisma_db_push_failed",
                error=db_push_step.error_message,
            )
            return steps

        self.logger.info("prisma_db_push_complete")

        # Step 3: Check if seed script exists in package.json
        check_seed = await self._exec_in_container(
            "check_seed_script",
            ["bash", "-c", "grep -q '\"seed\"' package.json && echo 'has_seed' || echo 'no_seed'"],
            timeout=5,
        )

        if "has_seed" in check_seed.stdout:
            # Run seed script
            seed_step = await self._exec_in_container(
                "prisma_db_seed",
                ["npx", "prisma", "db", "seed"],
                timeout=120,
            )
            steps.append(seed_step)

            if seed_step.success:
                self.logger.info("prisma_db_seed_complete")
            else:
                self.logger.warning(
                    "prisma_db_seed_failed",
                    error=seed_step.error_message,
                )
        else:
            self.logger.info("prisma_seed_script_not_found", message="Skipping seed")

        self._database_setup_complete = True
        self.logger.info(
            "database_setup_complete",
            steps_run=len(steps),
            all_success=all(s.success for s in steps),
        )

        return steps

    async def _collect_logs(self) -> List[str]:
        """Collect container logs."""
        if not self.container_id:
            return []
            
        try:
            result = await self._run_command(
                ["docker", "logs", "--tail", "100", self.container_id],
                timeout=10,
            )
            if result.exit_code == 0:
                return result.stdout.split('\n')[-100:]
            return []
        except Exception as e:
            self.logger.warning("log_collection_failed", error=str(e))
            return []

    async def _cleanup(self) -> None:
        """Remove container."""
        if self.container_id:
            self.logger.info("cleaning_up_container", container_id=self.container_id)
            await self._run_command(
                ["docker", "rm", "-f", self.container_id],
                timeout=30,
            )
            self.container_id = None

    async def _create_container(self, project_type: ProjectType) -> SandboxStep:
        """Create Docker container for sandbox testing."""
        start = datetime.now()
        
        # Check if custom sandbox image is available
        use_sandbox_image = await self.check_sandbox_image_available()
        
        if use_sandbox_image:
            image = self.SANDBOX_IMAGE
        else:
            image = self.IMAGES.get(project_type, self.IMAGES[ProjectType.UNKNOWN])
        
        container_name = f"sandbox-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Build docker run command
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-w", "/app",
        ]
        
        # Add port mappings based on project type
        if project_type == ProjectType.REACT_VITE:
            cmd.extend(["-p", "4173:4173"])
        elif project_type == ProjectType.NODE_API:
            cmd.extend(["-p", "3000:3000"])
        elif project_type == ProjectType.PYTHON_FASTAPI:
            cmd.extend(["-p", "8000:8000"])
        elif project_type == ProjectType.PYTHON_FLASK:
            cmd.extend(["-p", "5000:5000"])
        
        # Add VNC port if enabled
        if self.enable_vnc:
            cmd.extend([
                "-p", f"{self.vnc_port}:{self.vnc_port}",
                "-p", f"{self.DEFAULT_VNC_PORT}:{self.DEFAULT_VNC_PORT}",
                "-e", "DISPLAY=:99",
            ])

        # Add extra environment variables (for secrets injection)
        if hasattr(self, '_extra_env_vars') and self._extra_env_vars:
            for key, value in self._extra_env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

        # For persistent mode, use infinite sleep; otherwise timeout after 1 hour
        if hasattr(self, '_persistent_mode') and self._persistent_mode:
            cmd.extend([image, "sleep", "infinity"])
        else:
            cmd.extend([image, "sleep", "3600"])
        
        result = await self._run_command(cmd, timeout=60)
        duration = int((datetime.now() - start).total_seconds() * 1000)
        
        if result.exit_code == 0:
            self.container_id = result.stdout.strip()[:12]
            self.logger.info(
                "container_created",
                container_id=self.container_id,
                image=image,
                project_type=project_type.value,
            )
        
        return SandboxStep(
            name="create_container",
            command=" ".join(cmd[-4:]),
            success=result.exit_code == 0,
            stdout=result.stdout[:200],
            stderr=result.stderr[:500],
            duration_ms=duration,
            exit_code=result.exit_code,
            error_message=result.stderr[:500] if result.exit_code != 0 else None,
        )

    async def _copy_project(self) -> SandboxStep:
        """Copy project files to container."""
        start = datetime.now()
        
        if not self.container_id:
            return SandboxStep(
                name="copy_project",
                command="N/A",
                success=False,
                stdout="",
                stderr="No container ID",
                duration_ms=0,
                exit_code=1,
                error_message="No container ID available",
            )
        
        # Copy project directory to container
        cmd = ["docker", "cp", f"{self.project_dir}/.", f"{self.container_id}:/app/"]
        result = await self._run_command(cmd, timeout=120)
        duration = int((datetime.now() - start).total_seconds() * 1000)
        
        if result.exit_code == 0:
            self.logger.info(
                "project_copied",
                container_id=self.container_id,
                source=str(self.project_dir),
            )
        
        return SandboxStep(
            name="copy_project",
            command=f"docker cp {self.project_dir}/. {self.container_id}:/app/",
            success=result.exit_code == 0,
            stdout=result.stdout[:200],
            stderr=result.stderr[:500],
            duration_ms=duration,
            exit_code=result.exit_code,
            error_message=result.stderr[:500] if result.exit_code != 0 else None,
        )

    async def _test_node_project(self, project_type: ProjectType) -> Dict[str, Any]:
        """Run test sequence for Node.js projects (Electron, React/Vite, Node API)."""
        steps = []
        app_started = False
        app_responsive = False

        # Step 1: Install dependencies
        install_step = await self._exec_in_container(
            "install_deps",
            ["npm", "install", "--legacy-peer-deps"],
            timeout=180,
        )
        steps.append(install_step)
        if not install_step.success:
            return {"steps": steps, "app_started": False, "app_responsive": False}

        # Step 1.5: Database setup (if prisma exists and enabled)
        if self.enable_database_setup:
            db_steps = await self._run_database_setup()
            steps.extend(db_steps)
            # Database setup failure is not fatal - continue with build

        # Step 2: Build
        build_step = await self._exec_in_container(
            "build",
            ["npm", "run", "build"],
            timeout=120,
        )
        steps.append(build_step)
        # Build failure is not fatal - continue for dev server testing
        
        # Step 3: Start and test based on project type
        if project_type == ProjectType.ELECTRON:
            # Start Electron app
            start_step = await self._exec_in_container(
                "start_app",
                ["bash", "-c", "DISPLAY=:99 npm run start &"],
                timeout=10,
            )
            steps.append(start_step)
            await asyncio.sleep(5)
            
            # Check if Electron process is running
            check_step = await self._exec_in_container(
                "check_running",
                ["bash", "-c", "pgrep -f electron || pgrep -f 'npm run start'"],
                timeout=5,
            )
            steps.append(check_step)
            app_started = check_step.exit_code == 0
            app_responsive = app_started
            
        elif project_type == ProjectType.REACT_VITE:
            # Start Vite preview server
            start_step = await self._exec_in_container(
                "start_app",
                ["bash", "-c", "npm run preview -- --host 0.0.0.0 --port 4173 &"],
                timeout=10,
            )
            steps.append(start_step)
            await asyncio.sleep(3)
            
            # Health check
            health_step = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:4173 || echo '000'"],
                timeout=10,
            )
            steps.append(health_step)
            app_started = True
            app_responsive = "200" in health_step.stdout
            
        else:  # NODE_API
            # Start Node server
            start_step = await self._exec_in_container(
                "start_app",
                ["bash", "-c", "npm start &"],
                timeout=10,
            )
            steps.append(start_step)
            await asyncio.sleep(3)
            
            # Health check
            health_step = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000 || echo '000'"],
                timeout=10,
            )
            steps.append(health_step)
            app_started = True
            app_responsive = "200" in health_step.stdout or health_step.exit_code == 0
        
        return {
            "steps": steps,
            "app_started": app_started,
            "app_responsive": app_responsive,
        }

    async def _test_python_project(self, project_type: ProjectType) -> Dict[str, Any]:
        """Run test sequence for Python projects (FastAPI, Flask)."""
        steps = []
        app_started = False
        app_responsive = False
        
        # Step 1: Install dependencies
        install_step = await self._exec_in_container(
            "install_deps",
            ["pip", "install", "-r", "requirements.txt"],
            timeout=180,
        )
        steps.append(install_step)
        if not install_step.success:
            return {"steps": steps, "app_started": False, "app_responsive": False}
        
        # Step 2: Start and test based on project type
        if project_type == ProjectType.PYTHON_FASTAPI:
            # Start FastAPI server
            start_step = await self._exec_in_container(
                "start_app",
                ["bash", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 &"],
                timeout=10,
            )
            steps.append(start_step)
            await asyncio.sleep(3)
            
            # Health check
            health_step = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000 || echo '000'"],
                timeout=10,
            )
            steps.append(health_step)
            app_started = True
            app_responsive = "200" in health_step.stdout
            
        else:  # Flask
            # Start Flask server
            start_step = await self._exec_in_container(
                "start_app",
                ["bash", "-c", "gunicorn --bind 0.0.0.0:5000 app:app &"],
                timeout=10,
            )
            steps.append(start_step)
            await asyncio.sleep(3)
            
            # Health check
            health_step = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000 || echo '000'"],
                timeout=10,
            )
            steps.append(health_step)
            app_started = True
            app_responsive = "200" in health_step.stdout
        
        return {
            "steps": steps,
            "app_started": app_started,
            "app_responsive": app_responsive,
        }

    # =========================================================================
    # Cycle Methods for Continuous Testing
    # =========================================================================

    async def _cycle_start_electron(self) -> Dict[str, Any]:
        """Start Electron app for a single cycle."""
        result = await self._exec_in_container(
            "start_electron",
            ["bash", "-c", "DISPLAY=:99 npm run start &"],
            timeout=10,
        )
        await asyncio.sleep(3)
        
        # Check if process started
        check = await self._exec_in_container(
            "check_electron",
            ["bash", "-c", "pgrep -f electron"],
            timeout=5,
        )
        
        return {"started": check.exit_code == 0}

    async def _cycle_start_vite(self) -> Dict[str, Any]:
        """Start Vite preview server for a single cycle."""
        result = await self._exec_in_container(
            "start_vite",
            ["bash", "-c", "npm run preview -- --host 0.0.0.0 --port 4173 &"],
            timeout=10,
        )
        await asyncio.sleep(3)

        # Check if server is listening
        check = await self._exec_in_container(
            "check_vite",
            ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:4173"],
            timeout=5,
        )

        started = "200" in check.stdout
        return {
            "started": started,
            "stdout": check.stdout,
            "stderr": check.stderr if not started else "",
        }

    async def _cycle_start_node_api(self) -> Dict[str, Any]:
        """Start Node API server for a single cycle."""
        result = await self._exec_in_container(
            "start_node",
            ["bash", "-c", "npm start &"],
            timeout=10,
        )
        await asyncio.sleep(3)
        
        # Check if server is listening
        check = await self._exec_in_container(
            "check_node",
            ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000"],
            timeout=5,
        )
        
        return {"started": "200" in check.stdout or check.exit_code == 0}

    async def _cycle_start_fastapi(self) -> Dict[str, Any]:
        """Start FastAPI server for a single cycle."""
        result = await self._exec_in_container(
            "start_fastapi",
            ["bash", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 &"],
            timeout=10,
        )
        await asyncio.sleep(3)
        
        # Check if server is listening
        check = await self._exec_in_container(
            "check_fastapi",
            ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000"],
            timeout=5,
        )
        
        return {"started": "200" in check.stdout}

    async def _cycle_start_flask(self) -> Dict[str, Any]:
        """Start Flask server for a single cycle."""
        result = await self._exec_in_container(
            "start_flask",
            ["bash", "-c", "gunicorn --bind 0.0.0.0:5000 app:app &"],
            timeout=10,
        )
        await asyncio.sleep(3)
        
        # Check if server is listening
        check = await self._exec_in_container(
            "check_flask",
            ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000"],
            timeout=5,
        )
        
        return {"started": "200" in check.stdout}

    async def _cycle_health_check(self) -> Dict[str, Any]:
        """Perform health check based on project type. Returns responsive status and diagnostic info."""
        if self._project_type == ProjectType.ELECTRON:
            check = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "pgrep -f electron"],
                timeout=5,
            )
            responsive = check.exit_code == 0
            return {"responsive": responsive, "stdout": check.stdout, "stderr": check.stderr}

        elif self._project_type == ProjectType.REACT_VITE:
            check = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:4173"],
                timeout=5,
            )
            responsive = "200" in check.stdout
            return {"responsive": responsive, "stdout": check.stdout, "stderr": check.stderr}

        elif self._project_type == ProjectType.NODE_API:
            check = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/health || curl -s -o /dev/null -w '%{http_code}' http://localhost:3000"],
                timeout=5,
            )
            responsive = "200" in check.stdout
            return {"responsive": responsive, "stdout": check.stdout, "stderr": check.stderr}

        elif self._project_type == ProjectType.PYTHON_FASTAPI:
            check = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000"],
                timeout=5,
            )
            responsive = "200" in check.stdout
            return {"responsive": responsive, "stdout": check.stdout, "stderr": check.stderr}

        else:  # Flask
            check = await self._exec_in_container(
                "health_check",
                ["bash", "-c", "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000"],
                timeout=5,
            )
            responsive = "200" in check.stdout
            return {"responsive": responsive, "stdout": check.stdout, "stderr": check.stderr}

    async def _cycle_kill_app(self) -> None:
        """Kill app process after cycle."""
        if self._project_type == ProjectType.ELECTRON:
            await self._exec_in_container("kill_app", ["bash", "-c", "pkill -f electron || true"], timeout=5)
        elif self._project_type == ProjectType.REACT_VITE:
            await self._exec_in_container("kill_app", ["bash", "-c", "pkill -f vite || true"], timeout=5)
        elif self._project_type == ProjectType.NODE_API:
            await self._exec_in_container("kill_app", ["bash", "-c", "pkill -f node || true"], timeout=5)
        elif self._project_type == ProjectType.PYTHON_FASTAPI:
            await self._exec_in_container("kill_app", ["bash", "-c", "pkill -f uvicorn || true"], timeout=5)
        else:
            await self._exec_in_container("kill_app", ["bash", "-c", "pkill -f gunicorn || true"], timeout=5)

    def stop_continuous_tests(self) -> None:
        """Signal continuous testing to stop."""
        self._continuous_running = False
        self.logger.info("continuous_testing_stop_requested")

    async def _exec_in_container(
        self,
        name: str,
        command: List[str],
        timeout: int = 60,
    ) -> SandboxStep:
        """Execute command in container."""
        start = datetime.now()
        cmd = ["docker", "exec", self.container_id] + command

        result = await self._run_command(cmd, timeout=timeout)
        duration = int((datetime.now() - start).total_seconds() * 1000)

        return SandboxStep(
            name=name,
            command=" ".join(command),
            success=result.exit_code == 0,
            stdout=result.stdout[:2000],
            stderr=result.stderr[:2000],
            duration_ms=duration,
            exit_code=result.exit_code,
            error_message=result.stderr[:500] if result.exit_code != 0 else None,
        )

    async def _run_command(
        self,
        cmd: List[str],
        timeout: int = 60,
    ):
        """Run command and return result."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                return type('Result', (), {
                    'exit_code': process.returncode,
                    'stdout': stdout.decode('utf-8', errors='replace'),
                    'stderr': stderr.decode('utf-8', errors='replace'),
                })()

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return type('Result', (), {
                    'exit_code': -1,
                    'stdout': '',
                    'stderr': f'Timeout after {timeout}s',
                })()

        except Exception as e:
            return type('Result', (), {
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e),
            })


async def run_sandbox_test(
    project_dir: str,
    enable_vnc: bool = False,
    vnc_port: int = 6080,
) -> SandboxResult:
    """
    Convenience function to run sandbox tests.

    Args:
        project_dir: Path to project directory
        enable_vnc: Enable VNC streaming for all app types (Electron, React, Node API, Python)
        vnc_port: noVNC web port (default 6080)

    Returns:
        SandboxResult with vnc_url if VNC is enabled
    """
    tool = SandboxTool(
        project_dir,
        enable_vnc=enable_vnc,
        vnc_port=vnc_port,
    )
    return await tool.run_sandbox_tests()


async def run_continuous_sandbox_tests(
    project_dir: str,
    cycle_interval: int = 30,
    max_cycles: Optional[int] = None,
    enable_vnc: bool = False,
    vnc_port: int = 6080,
):
    """
    Convenience async generator for continuous sandbox testing.
    
    Args:
        project_dir: Path to project directory
        cycle_interval: Seconds between test cycles (default 30)
        max_cycles: Maximum cycles to run (None = infinite)
        enable_vnc: Enable VNC streaming for GUI apps
        vnc_port: noVNC web port
        
    Yields:
        ContinuousSandboxCycle for each test cycle
        
    Example:
        async for cycle in run_continuous_sandbox_tests("./my-project", cycle_interval=30):
            print(f"Cycle {cycle.cycle_number}: {'✓' if cycle.success else '✗'}")
            if cycle.success:
                break
    """
    tool = SandboxTool(
        project_dir,
        enable_vnc=enable_vnc,
        vnc_port=vnc_port,
        cycle_interval=cycle_interval,
        cleanup=not enable_vnc,  # Keep container for VNC viewing
    )
    
    async for cycle in tool.run_continuous_tests(max_cycles=max_cycles):
        yield cycle
