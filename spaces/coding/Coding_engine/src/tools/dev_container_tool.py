"""
Development Container Tool - Docker container with VNC for live code generation viewing.

This tool provides a development environment that:
1. Mounts the output directory as a Docker volume (live file sync)
2. Starts VNC services for browser-based viewing
3. Watches for package.json and auto-runs npm install + dev server
4. Enables hot reload so changes appear instantly in the browser

Unlike SandboxTool which copies files once, DevContainerTool uses volume mounts
so files appear in the container as they're generated.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import structlog

logger = structlog.get_logger(__name__)


class ProjectType(str, Enum):
    """Supported project types for dev container."""
    REACT_VITE = "react_vite"
    ELECTRON = "electron"
    NODE_API = "node_api"
    PYTHON_FASTAPI = "python_fastapi"
    UNKNOWN = "unknown"


class DevContainerState(str, Enum):
    """State of the dev container."""
    STOPPED = "stopped"
    STARTING = "starting"
    VNC_READY = "vnc_ready"
    WAITING_FOR_PACKAGE_JSON = "waiting_for_package_json"
    INSTALLING_DEPS = "installing_deps"
    STARTING_DEV_SERVER = "starting_dev_server"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class DevContainerResult:
    """Result from dev container operations."""
    success: bool
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    vnc_url: Optional[str] = None
    dev_server_url: Optional[str] = None
    state: DevContainerState = DevContainerState.STOPPED
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "container_id": self.container_id,
            "container_name": self.container_name,
            "vnc_url": self.vnc_url,
            "dev_server_url": self.dev_server_url,
            "state": self.state.value,
            "error": self.error,
        }


class DevContainerTool:
    """
    Development container with VNC for live code generation viewing.

    Key differences from SandboxTool:
    - Uses Docker VOLUME MOUNT instead of copying files
    - Starts VNC immediately (before code generation)
    - Watches for package.json and auto-runs npm install
    - Runs dev server with hot reload
    - Files appear in real-time as they're generated

    Usage:
        tool = DevContainerTool(project_dir="./output")
        result = await tool.start()
        # VNC available at http://localhost:6080/vnc.html
        # Files generated to ./output appear live in browser
    """

    # Docker image with VNC support
    SANDBOX_IMAGE = "sandbox-test"

    # Default ports
    DEFAULT_VNC_PORT = 5900
    DEFAULT_NOVNC_PORT = 6080
    DEFAULT_DEV_PORT = 5173

    def __init__(
        self,
        project_dir: str,
        vnc_port: int = 6080,
        dev_port: int = 5173,
        container_name: Optional[str] = None,
        state_callback: Optional[Callable[[DevContainerState], None]] = None,
    ):
        """
        Initialize dev container tool.

        Args:
            project_dir: Path to project directory (will be mounted)
            vnc_port: noVNC web port (default 6080, access via http://localhost:6080/vnc.html)
            dev_port: Development server port (default 5173 for Vite)
            container_name: Optional container name (auto-generated if not provided)
            state_callback: Optional callback for state changes
        """
        self.project_dir = Path(project_dir).resolve()
        self.vnc_port = vnc_port
        self.dev_port = dev_port
        self.container_name = container_name or f"dev-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.state_callback = state_callback

        self.container_id: Optional[str] = None
        self._state = DevContainerState.STOPPED
        self._watcher_task: Optional[asyncio.Task] = None
        self._project_type: Optional[ProjectType] = None

        self.logger = logger.bind(
            component="dev_container_tool",
            project_dir=str(project_dir),
            container_name=self.container_name,
        )

    @property
    def state(self) -> DevContainerState:
        return self._state

    @state.setter
    def state(self, new_state: DevContainerState):
        old_state = self._state
        self._state = new_state
        self.logger.info("state_changed", old_state=old_state.value, new_state=new_state.value)
        if self.state_callback:
            try:
                self.state_callback(new_state)
            except Exception as e:
                self.logger.warning("state_callback_error", error=str(e))

    async def start(self) -> DevContainerResult:
        """
        Start dev container with mounted volume and VNC.

        Returns:
            DevContainerResult with container info and URLs
        """
        self.logger.info("starting_dev_container")
        self.state = DevContainerState.STARTING

        try:
            # Ensure project directory exists
            self.project_dir.mkdir(parents=True, exist_ok=True)

            # Check if Docker is available
            if not await self._check_docker():
                return DevContainerResult(
                    success=False,
                    state=DevContainerState.ERROR,
                    error="Docker is not available",
                )

            # Check if sandbox image exists
            if not await self._check_image():
                self.logger.warning("sandbox_image_not_found", image=self.SANDBOX_IMAGE)
                # Fall back to node image (less features but works)

            # Stop any existing container with same name
            await self._stop_existing()

            # Create container with volume mount
            container_id = await self._create_container()
            if not container_id:
                return DevContainerResult(
                    success=False,
                    state=DevContainerState.ERROR,
                    error="Failed to create container",
                )

            self.container_id = container_id

            # Start VNC services
            vnc_started = await self._start_vnc_services()
            if not vnc_started:
                return DevContainerResult(
                    success=False,
                    container_id=self.container_id,
                    state=DevContainerState.ERROR,
                    error="Failed to start VNC services",
                )

            self.state = DevContainerState.VNC_READY
            vnc_url = f"http://localhost:{self.vnc_port}/vnc.html"

            self.logger.info(
                "vnc_ready",
                vnc_url=vnc_url,
                container_id=self.container_id,
            )

            # Start background watcher for package.json
            self._watcher_task = asyncio.create_task(self._watch_and_start_dev_server())

            return DevContainerResult(
                success=True,
                container_id=self.container_id,
                container_name=self.container_name,
                vnc_url=vnc_url,
                dev_server_url=f"http://localhost:{self.dev_port}",
                state=self.state,
            )

        except Exception as e:
            self.logger.error("start_failed", error=str(e))
            self.state = DevContainerState.ERROR
            return DevContainerResult(
                success=False,
                state=DevContainerState.ERROR,
                error=str(e),
            )

    async def stop(self) -> bool:
        """Stop and remove the dev container."""
        self.logger.info("stopping_dev_container", container_id=self.container_id)

        # Cancel watcher task
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass
            self._watcher_task = None

        # Stop container
        if self.container_id:
            result = await self._run_command(
                ["docker", "rm", "-f", self.container_id],
                timeout=30,
            )
            self.container_id = None

        self.state = DevContainerState.STOPPED
        return True

    async def _check_docker(self) -> bool:
        """Check if Docker is available."""
        result = await self._run_command(["docker", "version"], timeout=10)
        return result.exit_code == 0

    async def _check_image(self) -> bool:
        """Check if sandbox image exists."""
        result = await self._run_command(
            ["docker", "images", "-q", self.SANDBOX_IMAGE],
            timeout=10,
        )
        return result.exit_code == 0 and result.stdout.strip() != ""

    async def _stop_existing(self):
        """Stop existing container with same name."""
        await self._run_command(
            ["docker", "rm", "-f", self.container_name],
            timeout=30,
        )

    async def _create_container(self) -> Optional[str]:
        """Create Docker container with volume mount."""
        # Convert Windows path to Docker-compatible format
        mount_path = str(self.project_dir)
        if mount_path[1:3] == ":\\":
            # Convert C:\path to /c/path for Docker on Windows
            mount_path = "/" + mount_path[0].lower() + mount_path[2:].replace("\\", "/")

        cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "-v", f"{mount_path}:/app",  # VOLUME MOUNT - live sync
            "-w", "/app",
            "-p", f"{self.vnc_port}:6080",
            "-p", f"{self.DEFAULT_VNC_PORT}:{self.DEFAULT_VNC_PORT}",
            "-p", f"{self.dev_port}:5173",
            "-e", "DISPLAY=:99",
            "-e", "CHOKIDAR_USEPOLLING=true",  # For hot reload in Docker
            "-e", "WATCHPACK_POLLING=true",    # Webpack polling
            self.SANDBOX_IMAGE,
            "sleep", "infinity",
        ]

        self.logger.debug("creating_container", cmd=" ".join(cmd))

        result = await self._run_command(cmd, timeout=60)

        if result.exit_code == 0:
            container_id = result.stdout.strip()[:12]
            self.logger.info("container_created", container_id=container_id)
            return container_id

        self.logger.error("container_creation_failed", stderr=result.stderr)
        return None

    async def _start_vnc_services(self) -> bool:
        """Start VNC services (Xvfb, x11vnc, websockify) in container."""
        self.logger.info("starting_vnc_services")

        # Start Xvfb (virtual framebuffer)
        await self._exec_in_container(
            ["bash", "-c", "Xvfb :99 -screen 0 1280x800x24 &"],
            timeout=10,
        )
        await asyncio.sleep(1)

        # Start x11vnc (VNC server)
        await self._exec_in_container(
            ["bash", "-c", f"x11vnc -display :99 -nopw -forever -shared -rfbport {self.DEFAULT_VNC_PORT} -bg"],
            timeout=15,
        )
        await asyncio.sleep(1)

        # Start websockify/noVNC (web interface)
        await self._exec_in_container(
            ["bash", "-c", f"websockify --web=/usr/share/novnc 6080 localhost:{self.DEFAULT_VNC_PORT} &"],
            timeout=10,
        )
        await asyncio.sleep(1)

        # Verify services are running
        check = await self._exec_in_container(
            ["bash", "-c", "pgrep -f 'Xvfb|x11vnc|websockify' | wc -l"],
            timeout=5,
        )

        services_count = int(check.stdout.strip() or "0")
        success = services_count >= 2

        self.logger.info(
            "vnc_services_status",
            services_running=services_count,
            success=success,
        )

        return success

    async def _watch_and_start_dev_server(self):
        """
        Background task that watches for package.json and starts dev server.

        Workflow:
        1. Wait for package.json to appear
        2. Run npm install
        3. Run npm run dev
        4. Open browser in VNC
        """
        self.state = DevContainerState.WAITING_FOR_PACKAGE_JSON
        self.logger.info("watching_for_package_json")

        max_wait = 600  # 10 minutes
        check_interval = 2  # Check every 2 seconds
        waited = 0

        # Wait for package.json
        while waited < max_wait:
            check = await self._exec_in_container(
                ["bash", "-c", "test -f /app/package.json && echo 'exists'"],
                timeout=5,
            )

            if "exists" in check.stdout:
                self.logger.info("package_json_found")
                break

            await asyncio.sleep(check_interval)
            waited += check_interval

        if waited >= max_wait:
            self.logger.warning("package_json_not_found_timeout")
            return

        # Detect project type
        self._project_type = await self._detect_project_type()
        self.logger.info("project_type_detected", type=self._project_type.value)

        # Install dependencies
        self.state = DevContainerState.INSTALLING_DEPS
        self.logger.info("installing_dependencies")

        install_result = await self._exec_in_container(
            ["npm", "install", "--legacy-peer-deps"],
            timeout=300,  # 5 minutes for npm install
        )

        if install_result.exit_code != 0:
            self.logger.error("npm_install_failed", stderr=install_result.stderr[:500])
            self.state = DevContainerState.ERROR
            return

        self.logger.info("dependencies_installed")

        # Start dev server
        self.state = DevContainerState.STARTING_DEV_SERVER
        await self._start_dev_server()

        # Wait for dev server to be ready
        await asyncio.sleep(5)

        # Open browser in VNC
        await self._open_browser_in_vnc()

        self.state = DevContainerState.RUNNING
        self.logger.info("dev_container_fully_running")

    async def _detect_project_type(self) -> ProjectType:
        """Detect project type from package.json."""
        check = await self._exec_in_container(
            ["cat", "/app/package.json"],
            timeout=5,
        )

        if check.exit_code != 0:
            return ProjectType.UNKNOWN

        content = check.stdout.lower()

        if "electron" in content:
            return ProjectType.ELECTRON
        elif "vite" in content or "@vitejs" in content:
            return ProjectType.REACT_VITE
        elif "express" in content or "fastify" in content:
            return ProjectType.NODE_API
        elif "fastapi" in content:
            return ProjectType.PYTHON_FASTAPI

        return ProjectType.REACT_VITE  # Default to Vite for web projects

    async def _start_dev_server(self):
        """Start the appropriate dev server based on project type."""
        if self._project_type == ProjectType.ELECTRON:
            # Electron dev mode
            cmd = "DISPLAY=:99 npm run dev &"
        elif self._project_type == ProjectType.REACT_VITE:
            # Vite dev server with host binding
            cmd = "npm run dev -- --host 0.0.0.0 --port 5173 &"
        elif self._project_type == ProjectType.NODE_API:
            # Node API server
            cmd = "npm run dev &"
        else:
            # Fallback to npm run dev
            cmd = "npm run dev -- --host 0.0.0.0 --port 5173 &"

        self.logger.info("starting_dev_server", command=cmd)

        await self._exec_in_container(
            ["bash", "-c", cmd],
            timeout=10,
        )

    async def _open_browser_in_vnc(self):
        """Open Chromium browser in VNC to display the app."""
        # Determine URL based on project type
        if self._project_type == ProjectType.ELECTRON:
            # Electron apps display directly, no browser needed
            self.logger.info("electron_app_displays_directly")
            return
        elif self._project_type == ProjectType.NODE_API:
            url = "http://localhost:3000"
        else:
            url = "http://localhost:5173"

        self.logger.info("opening_browser", url=url)

        await self._exec_in_container(
            ["bash", "-c", f"""
                DISPLAY=:99 chromium \
                    --no-sandbox \
                    --disable-gpu \
                    --disable-software-rasterizer \
                    --disable-dev-shm-usage \
                    --disable-extensions \
                    --window-size=1280,800 \
                    --window-position=0,0 \
                    --start-maximized \
                    --kiosk \
                    --app='{url}' &
            """],
            timeout=15,
        )

        await asyncio.sleep(2)

        # Verify browser started
        check = await self._exec_in_container(
            ["bash", "-c", "pgrep -f chromium | head -1"],
            timeout=5,
        )

        browser_started = check.exit_code == 0 and check.stdout.strip()
        self.logger.info("browser_status", started=browser_started)

    async def _exec_in_container(
        self,
        command: List[str],
        timeout: int = 60,
    ):
        """Execute command in container."""
        if not self.container_id:
            return type('Result', (), {
                'exit_code': -1,
                'stdout': '',
                'stderr': 'No container ID',
            })()

        cmd = ["docker", "exec", self.container_id] + command
        return await self._run_command(cmd, timeout=timeout)

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
            })()

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the dev container."""
        return {
            "state": self.state.value,
            "container_id": self.container_id,
            "container_name": self.container_name,
            "project_dir": str(self.project_dir),
            "vnc_url": f"http://localhost:{self.vnc_port}/vnc.html" if self.container_id else None,
            "dev_server_url": f"http://localhost:{self.dev_port}" if self.container_id else None,
            "project_type": self._project_type.value if self._project_type else None,
        }


async def start_dev_container(
    project_dir: str,
    vnc_port: int = 6080,
    dev_port: int = 5173,
) -> DevContainerResult:
    """
    Convenience function to start a dev container.

    Args:
        project_dir: Path to project directory (will be mounted)
        vnc_port: noVNC web port (default 6080)
        dev_port: Development server port (default 5173)

    Returns:
        DevContainerResult with container info and URLs

    Example:
        result = await start_dev_container("./output")
        print(f"VNC: {result.vnc_url}")
        # Files generated to ./output appear live in VNC browser
    """
    tool = DevContainerTool(
        project_dir=project_dir,
        vnc_port=vnc_port,
        dev_port=dev_port,
    )
    return await tool.start()
