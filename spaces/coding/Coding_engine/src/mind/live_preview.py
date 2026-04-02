"""
Live Preview System - Real-time app preview as it evolves.

Provides:
1. File system watching with event emission
2. Automatic dev server management
3. Hot reload triggering
4. Screenshot capture for visual progress
"""

import asyncio
import os
import re
import socket
import subprocess
import signal
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from collections import deque
from typing import Optional, Callable, Any
import structlog

from .event_bus import EventBus, Event, EventType


logger = structlog.get_logger(__name__)


class PreviewStatus(Enum):
    """Status of the live preview system."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    REBUILDING = "rebuilding"
    ERROR = "error"


@dataclass
class PreviewState:
    """Current state of the live preview."""
    status: PreviewStatus = PreviewStatus.STOPPED
    url: Optional[str] = None
    port: int = 5173
    pid: Optional[int] = None
    last_rebuild: Optional[datetime] = None
    rebuild_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "url": self.url,
            "port": self.port,
            "pid": self.pid,
            "last_rebuild": self.last_rebuild.isoformat() if self.last_rebuild else None,
            "rebuild_count": self.rebuild_count,
            "error": self.error,
        }


class FileWatcher:
    """
    Watches a directory for file changes and emits events.

    Uses polling for cross-platform compatibility.
    """

    def __init__(
        self,
        watch_dir: str,
        event_bus: EventBus,
        ignore_patterns: Optional[list[str]] = None,
        poll_interval: float = 1.0,
    ):
        self.watch_dir = Path(watch_dir)
        self.event_bus = event_bus
        self.poll_interval = poll_interval

        # Default ignore patterns
        self.ignore_patterns = ignore_patterns or [
            "node_modules",
            ".git",
            "__pycache__",
            "*.pyc",
            ".DS_Store",
            "dist",
            "out",
            ".vite",
        ]

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._file_mtimes: dict[str, float] = {}

        self.logger = logger.bind(component="file_watcher", watch_dir=str(watch_dir))

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)
        for pattern in self.ignore_patterns:
            if pattern in path_str:
                return True
            if pattern.startswith("*") and path_str.endswith(pattern[1:]):
                return True
        return False

    def _scan_directory(self) -> dict[str, float]:
        """Scan directory and return file mtimes."""
        mtimes = {}
        if not self.watch_dir.exists():
            return mtimes

        try:
            for path in self.watch_dir.rglob("*"):
                if path.is_file() and not self._should_ignore(path):
                    try:
                        mtimes[str(path)] = path.stat().st_mtime
                    except (OSError, FileNotFoundError):
                        pass
        except Exception as e:
            self.logger.warning("scan_error", error=str(e))

        return mtimes

    def _has_git_changes(self, file_path: str) -> bool:
        """
        Check if a file has actual content changes using git.

        More accurate than mtime-based detection because:
        1. Git compares actual content, not timestamps
        2. Avoids false positives from file touch operations

        Returns:
            True if file has changes (or git unavailable), False if unchanged
        """
        try:
            # Get the directory for git operations
            file_dir = os.path.dirname(file_path)
            if not file_dir:
                file_dir = str(self.watch_dir)

            # Check for changes compared to git index
            result = subprocess.run(
                ['git', 'diff', '--name-only', '--', file_path],
                cwd=file_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            # File appears in git diff = has changes
            if result.returncode == 0 and file_path in result.stdout:
                return True

            # Check for untracked/staged files
            result_status = subprocess.run(
                ['git', 'status', '--porcelain', '--', file_path],
                cwd=file_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Any status output means changes exist
            if result_status.returncode == 0 and result_status.stdout.strip():
                return True

            return False

        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            # Git not available - fall back to mtime (assume changed)
            return True

    async def _check_for_changes(self) -> None:
        """Check for file changes and emit events.

        Uses git-based detection to verify actual content changes
        before emitting FILE_MODIFIED events.
        """
        current_mtimes = self._scan_directory()

        # Find new and modified files
        for path, mtime in current_mtimes.items():
            if path not in self._file_mtimes:
                # New file
                await self.event_bus.publish(Event(
                    type=EventType.FILE_CREATED,
                    source="file_watcher",
                    file_path=path,
                    data={"mtime": mtime},
                ))
            elif mtime > self._file_mtimes[path]:
                # mtime changed - verify with git before emitting
                if self._has_git_changes(path):
                    await self.event_bus.publish(Event(
                        type=EventType.FILE_MODIFIED,
                        source="file_watcher",
                        file_path=path,
                        data={"mtime": mtime, "previous_mtime": self._file_mtimes[path]},
                    ))
                else:
                    self.logger.debug("mtime_changed_no_content_change", path=path)

        # Find deleted files
        for path in self._file_mtimes:
            if path not in current_mtimes:
                await self.event_bus.publish(Event(
                    type=EventType.FILE_DELETED,
                    source="file_watcher",
                    file_path=path,
                ))

        self._file_mtimes = current_mtimes

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        self.logger.info("watcher_started")

        # Initial scan
        self._file_mtimes = self._scan_directory()
        self.logger.info("initial_scan_complete", file_count=len(self._file_mtimes))

        while self._running:
            await asyncio.sleep(self.poll_interval)
            await self._check_for_changes()

    async def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        self.logger.info("file_watcher_started")

    async def stop(self) -> None:
        """Stop watching for file changes."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.logger.info("file_watcher_stopped")


class DevServerManager:
    """
    Manages development server processes.

    Supports various dev server types:
    - Vite (electron-vite, vite)
    - Next.js
    - Webpack dev server
    - Custom commands
    """

    def __init__(
        self,
        working_dir: str,
        event_bus: EventBus,
        port: int = 5173,
    ):
        self.working_dir = Path(working_dir)
        self.event_bus = event_bus
        self.port = port
        self._port_detected = False  # Track if we've already detected and published the port

        self._process: Optional[subprocess.Popen] = None
        self._output_task: Optional[asyncio.Task] = None
        self._dependency_subscription: Optional[asyncio.Task] = None
        self.state = PreviewState(port=port)

        # Track port from multi-line error messages (e.g., EADDRINUSE)
        self._last_eaddrinuse_port: Optional[int] = None
        self._last_eaddrinuse_time: float = 0  # Timestamp of last EADDRINUSE detection
        self._eaddrinuse_cooldown: float = 5.0  # Seconds to ignore duplicate EADDRINUSE

        # Event deduplication cache: {error_hash: expiry_timestamp}
        # Prevents flooding with repeated error messages
        self._error_cache: dict[str, float] = {}
        self._error_cache_ttl: float = 30.0  # Seconds before same error can be re-published
        self._last_cache_cleanup: float = 0

        # Backend server management (separate from Vite frontend)
        self._backend_process: Optional[subprocess.Popen] = None
        self._backend_port: int = self._read_backend_port_from_env()
        self._backend_auto_start_enabled: bool = True
        self._backend_start_attempts: int = 0
        self._max_backend_start_attempts: int = 3
        self._backend_output_task: Optional[asyncio.Task] = None

        # Circular buffer for recent server output (for 500 error debugging)
        self._recent_logs: deque[str] = deque(maxlen=100)

        self.logger = logger.bind(component="dev_server", working_dir=str(working_dir))

        # Subscribe to dependency updates for auto-restart
        self._subscribe_to_dependency_updates()

        # Subscribe to browser errors for backend auto-start on 503
        self._subscribe_to_backend_errors()

    def _read_backend_port_from_env(self) -> int:
        """Read backend port from project's .env file or use default."""
        # First try to read from project's .env file
        env_file = self.working_dir / ".env"
        if env_file.exists():
            try:
                content = env_file.read_text()
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('PORT='):
                        port_str = line.split('=', 1)[1].strip().strip('"\'')
                        if port_str.isdigit():
                            return int(port_str)
                    elif line.startswith('BACKEND_PORT='):
                        port_str = line.split('=', 1)[1].strip().strip('"\'')
                        if port_str.isdigit():
                            return int(port_str)
            except Exception:
                pass

        # Fallback to environment variables
        return int(os.getenv("BACKEND_PORT", os.getenv("PORT", "3001")))

    def _should_publish_error(self, error_type: str, raw_error: str) -> bool:
        """
        Check if error should be published (deduplication).

        Uses TTL-based cache to prevent flooding with repeated errors.
        Returns True if error should be published, False if duplicate.
        """
        import time
        import hashlib

        now = time.time()

        # Periodic cache cleanup (every 60 seconds)
        if now - self._last_cache_cleanup > 60.0:
            expired = [k for k, v in self._error_cache.items() if v < now]
            for k in expired:
                del self._error_cache[k]
            self._last_cache_cleanup = now

        # Create hash from error type + normalized error message
        # Normalize by removing timestamps, line numbers, memory addresses
        normalized = re.sub(r'\b\d+\b', 'N', raw_error[:200])  # Replace numbers
        normalized = re.sub(r'0x[0-9a-f]+', 'ADDR', normalized)  # Replace addresses
        error_hash = hashlib.md5(f"{error_type}:{normalized}".encode()).hexdigest()[:16]

        # Check cache
        if error_hash in self._error_cache:
            if self._error_cache[error_hash] > now:
                # Still in TTL window - skip (log at debug level to avoid log flooding)
                self.logger.debug(
                    "error_deduplicated",
                    error_type=error_type,
                    remaining_ttl=round(self._error_cache[error_hash] - now, 1),
                )
                return False

        # Add to cache with TTL
        self._error_cache[error_hash] = now + self._error_cache_ttl
        self.logger.debug(
            "error_cache_added",
            error_type=error_type,
            cache_size=len(self._error_cache),
        )
        return True

    async def _cleanup_port(self, port: int) -> bool:
        """Kill any process using the specified port."""
        try:
            if os.name == 'nt':
                # Windows: Find and kill process on port
                result = subprocess.run(
                    ['netstat', '-ano', '-p', 'tcp'],
                    capture_output=True, text=True
                )
                for line in result.stdout.split('\n'):
                    if f':{port}' in line and 'LISTENING' in line:
                        parts = line.strip().split()
                        if parts:
                            pid = parts[-1]
                            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                            self.logger.info("port_cleanup_killed", port=port, pid=pid)
                            await asyncio.sleep(0.5)  # Wait for release
                            return True
            else:
                # Unix: Use lsof
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True, text=True
                )
                if result.stdout.strip():
                    for pid in result.stdout.strip().split('\n'):
                        subprocess.run(['kill', '-9', pid], capture_output=True)
                        self.logger.info("port_cleanup_killed", port=port, pid=pid)
                    await asyncio.sleep(0.5)
                    return True
            return False
        except Exception as e:
            self.logger.warning("port_cleanup_failed", port=port, error=str(e))
            return False

    def _is_port_available(self, port: int) -> bool:
        """Check if port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return True
        except OSError:
            return False

    def _find_available_port(self, start_port: int, max_attempts: int = 10) -> int:
        """Find next available port starting from start_port."""
        for offset in range(max_attempts):
            port = start_port + offset
            if self._is_port_available(port):
                return port
        raise RuntimeError(f"No available port found starting from {start_port}")

    def _detect_dev_command(self) -> Optional[list[str]]:
        """Detect the appropriate dev command from package.json."""
        package_json = self.working_dir / "package.json"
        if not package_json.exists():
            return None

        try:
            import json
            with open(package_json) as f:
                pkg = json.load(f)

            scripts = pkg.get("scripts", {})

            # Priority order for dev commands
            dev_commands = ["dev", "start", "serve", "develop"]
            for cmd in dev_commands:
                if cmd in scripts:
                    return ["npm", "run", cmd]

            # Check for electron-vite specifically
            if "electron-vite" in scripts.get("dev", ""):
                return ["npm", "run", "dev"]

        except Exception as e:
            self.logger.warning("package_json_parse_error", error=str(e))

        return None

    def _subscribe_to_backend_errors(self) -> None:
        """Subscribe to BROWSER_ERROR events to detect backend-down scenarios (503)."""
        def sync_callback(event: Event) -> None:
            # Run async handler in event loop
            asyncio.create_task(self._handle_backend_error(event))

        self.event_bus.subscribe(EventType.BROWSER_ERROR, sync_callback)
        self.logger.debug("subscribed_to_backend_errors")

    async def _handle_backend_error(self, event: Event) -> None:
        """Handle browser errors - auto-start backend on 503/ECONNREFUSED."""
        if not self._backend_auto_start_enabled:
            return

        error_data = event.data or {}
        error_type = error_data.get("error_type")
        message = error_data.get("message", "")

        # Detect 503 / backend unavailable patterns
        is_backend_down = (
            error_type == "network_error" and
            ("503" in message or "Service Unavailable" in message or
             "API server unavailable" in message or "ECONNREFUSED" in message or
             "socket hang up" in message)
        )

        if is_backend_down and self._backend_start_attempts < self._max_backend_start_attempts:
            self.logger.info(
                "backend_unavailable_detected",
                message=message[:100],
                attempt=self._backend_start_attempts + 1,
            )
            await self._start_backend_server()

    def _detect_backend_command(self) -> Optional[list[str]]:
        """Detect the backend server command from package.json."""
        package_json = self.working_dir / "package.json"
        if not package_json.exists():
            return None

        try:
            import json
            with open(package_json) as f:
                pkg = json.load(f)

            scripts = pkg.get("scripts", {})

            # Priority order for backend commands
            backend_commands = ["dev:backend", "server", "start:backend", "start:server", "backend"]
            for cmd in backend_commands:
                if cmd in scripts:
                    return ["npm", "run", cmd]

            # Fallback: check if dev uses concurrently with tsx/node server
            dev_script = scripts.get("dev", "")
            if "tsx" in dev_script and "server" in dev_script:
                # The dev script runs both, but we need just backend
                # Try to find server.ts or similar
                server_file = self.working_dir / "src" / "server.ts"
                if server_file.exists():
                    return ["npx", "tsx", "watch", "src/server.ts"]

            return None
        except Exception as e:
            self.logger.warning("backend_command_detection_failed", error=str(e))
            return None

    async def _start_backend_server(self) -> bool:
        """Start the backend server separately from the frontend."""
        # Check if already running
        if self._backend_process and self._backend_process.poll() is None:
            self.logger.info("backend_server_already_running", pid=self._backend_process.pid)
            return True

        self._backend_start_attempts += 1
        self.logger.info(
            "starting_backend_server",
            attempt=self._backend_start_attempts,
            port=self._backend_port,
        )

        # Cleanup port first
        if not self._is_port_available(self._backend_port):
            self.logger.info("backend_port_in_use_cleaning", port=self._backend_port)
            await self._cleanup_port(self._backend_port)

        cmd = self._detect_backend_command()
        if not cmd:
            self.logger.warning("no_backend_command_found")
            return False

        try:
            use_shell = os.name == 'nt'

            self._backend_process = subprocess.Popen(
                cmd,
                cwd=str(self.working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                env={**os.environ, "PORT": str(self._backend_port), "FORCE_COLOR": "1"},
            )

            self.logger.info(
                "backend_server_started",
                command=" ".join(cmd),
                port=self._backend_port,
                pid=self._backend_process.pid,
            )

            # Start output reader for backend
            self._backend_output_task = asyncio.create_task(
                self._read_backend_output()
            )

            # Publish event
            await self.event_bus.publish(Event(
                type=EventType.BUILD_STARTED,
                source="dev_server_backend",
                data={
                    "command": cmd,
                    "port": self._backend_port,
                    "pid": self._backend_process.pid,
                    "is_backend": True,
                },
            ))

            # Reset attempts on successful start
            self._backend_start_attempts = 0
            return True

        except Exception as e:
            self.logger.error("backend_server_start_error", error=str(e))
            return False

    # Database error patterns for auto-detection
    DATABASE_ERROR_PATTERNS = [
        r"Database connection failed",
        r"ECONNREFUSED.*5432",
        r"P1001.*Can't reach database",
        r"Authentication failed.*database",
        r"Can't reach database server",
        r"error: password authentication failed",
        r"Connection refused.*PostgreSQL",
        r"connect ECONNREFUSED.*:5432",
        r"provide valid database credentials",  # Prisma credential error
        r"PrismaClientInitializationError",  # Prisma init error
    ]

    async def _read_backend_output(self) -> None:
        """Read and log backend server output, detecting database errors."""
        if not self._backend_process or not self._backend_process.stdout:
            return

        try:
            while self._backend_process.poll() is None:
                line = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._backend_process.stdout.readline
                )
                if not line:
                    break

                try:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:
                        self.logger.debug(
                            "backend_server_output",
                            line=decoded[:200],
                        )

                        # Check for database connection errors
                        for pattern in self.DATABASE_ERROR_PATTERNS:
                            if re.search(pattern, decoded, re.IGNORECASE):
                                self.logger.warning(
                                    "database_connection_error",
                                    message=decoded[:200],
                                )

                                await self.event_bus.publish(Event(
                                    type=EventType.VALIDATION_ERROR,
                                    source="dev_server_backend",
                                    error_message="Database connection failed",
                                    data={
                                        "error_type": "database_error",
                                        "raw_error": decoded,
                                        "action_required": "start_database",
                                    },
                                ))
                                break

                except Exception:
                    pass

        except Exception as e:
            self.logger.debug("backend_output_reader_error", error=str(e))

    async def start(self, command: Optional[list[str]] = None) -> bool:
        """
        Start the development server.

        Args:
            command: Custom command to run. Auto-detects if not provided.

        Returns:
            True if server started successfully
        """
        if self._process and self._process.poll() is None:
            self.logger.warning("dev_server_already_running")
            return True

        # Cleanup ports before starting to prevent EADDRINUSE
        # NOTE: Port 3000 excluded - often used by other projects
        common_ports = [self.port, 3001, 8080]  # Frontend + backend ports (3000 excluded)
        for port in common_ports:
            if not self._is_port_available(port):
                self.logger.info("port_in_use_cleaning", port=port)
                await self._cleanup_port(port)

        cmd = command or self._detect_dev_command()
        if not cmd:
            self.logger.error("no_dev_command_found")
            self.state.status = PreviewStatus.ERROR
            self.state.error = "No dev command found in package.json"
            return False

        self.state.status = PreviewStatus.STARTING

        try:
            # Use shell=True on Windows for npm commands
            use_shell = os.name == 'nt'

            self._process = subprocess.Popen(
                cmd,
                cwd=str(self.working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                env={**os.environ, "FORCE_COLOR": "1"},
            )

            self.state.pid = self._process.pid
            self.state.url = f"http://localhost:{self.port}"
            self.state.status = PreviewStatus.RUNNING

            # Start output reader
            self._output_task = asyncio.create_task(self._read_output())

            # Register log buffer with SharedState for 500 error debugging
            try:
                from .shared_state import SharedState
                SharedState().register_vite_log_source(self.get_recent_logs)
            except Exception as e:
                self.logger.debug("shared_state_registration_failed", error=str(e))

            self.logger.info(
                "dev_server_started",
                command=" ".join(cmd),
                pid=self._process.pid,
            )

            # Publish event
            await self.event_bus.publish(Event(
                type=EventType.BUILD_STARTED,
                source="dev_server",
                data={"command": cmd, "pid": self._process.pid},
            ))

            return True

        except Exception as e:
            self.state.status = PreviewStatus.ERROR
            self.state.error = str(e)
            self.logger.error("dev_server_start_error", error=str(e))
            return False

    # Patterns for auto-detecting server port from output
    PORT_DETECTION_PATTERNS = [
        r"listening on (?:port )?:?(\d{4,5})",  # listening on :3000, listening on port 3000
        r"[Ss]erver (?:running|started|listening) on (?:port )?:?(\d{4,5})",  # server running on port 3001
        r"http://(?:localhost|127\.0\.0\.1):(\d{4,5})",  # http://localhost:3000
        r"Local:\s+http://.*:(\d{4,5})",  # Vite: Local:   http://localhost:5173
        r"running at.*:(\d{4,5})",  # express running at http://...:3000
    ]

    # Port ranges for frontend vs backend classification
    # Frontend: Can be debugged with Playwright (renders HTML/JS in browser)
    # Backend: API servers (JSON responses, not debuggable with Playwright)
    FRONTEND_PORT_RANGES = [
        (5173, 5199),  # Vite default range
        (3000, 3000),  # Create React App default
        (8080, 8080),  # Webpack dev server
        (4200, 4200),  # Angular CLI
        (4000, 4000),  # Gatsby
    ]
    BACKEND_PORT_RANGES = [
        (3001, 3099),  # Express common range
        (8000, 8001),  # FastAPI/Django
        (5000, 5000),  # Flask
    ]

    @classmethod
    def classify_port(cls, port: int) -> str:
        """
        Classify a port as 'frontend' or 'backend'.

        Frontend ports serve HTML/JS that can be debugged with Playwright.
        Backend ports serve APIs (JSON) that cannot be browser-debugged.

        Args:
            port: The port number to classify

        Returns:
            'frontend' or 'backend'
        """
        for start, end in cls.FRONTEND_PORT_RANGES:
            if start <= port <= end:
                return "frontend"
        for start, end in cls.BACKEND_PORT_RANGES:
            if start <= port <= end:
                return "backend"
        # Default: assume frontend for unknown ports (safer for monitoring)
        return "frontend"

    # Patterns for detecting missing module errors
    MODULE_NOT_FOUND_PATTERNS = [
        r"Cannot find (?:package|module) ['\"]([^'\"]+)['\"]",
        r"ERR_MODULE_NOT_FOUND.*['\"]([^'\"]+)['\"]",
        r"Module not found.*['\"]([^'\"]+)['\"]",
        r"Error: Cannot find module ['\"]([^'\"]+)['\"]",
        r"error TS2307:.*['\"]([^'\"]+)['\"]",  # TypeScript module error
        r"Cannot resolve ['\"]([^'\"]+)['\"]",
    ]

    # Patterns for code-level errors (missing exports, syntax, etc.)
    # Returns (pattern, error_type, group_for_module, group_for_export)
    CODE_ERROR_PATTERNS = [
        # Missing export: "The requested module 'X' does not provide an export named 'Y'" (Vite/browser format)
        (r"The requested module ['\"]([^'\"]+)['\"] does not provide an export named ['\"]([^'\"]+)['\"]",
         "missing_export", 1, 2),
        # Missing export: "module 'X' does not provide an export named 'Y'"
        (r"module ['\"]([^'\"]+)['\"] does not provide an export named ['\"]([^'\"]+)['\"]",
         "missing_export", 1, 2),
        (r"does not provide an export named ['\"]([^'\"]+)['\"]",
         "missing_export", None, 1),
        # Circular dependency
        (r"Circular dependency.*['\"]([^'\"]+)['\"]",
         "circular_dependency", 1, None),
        # TypeScript specific errors
        (r"error TS2305:.*['\"]([^'\"]+)['\"].*['\"]([^'\"]+)['\"]",
         "missing_export", 2, 1),  # Module 'X' has no exported member 'Y'
        # Duplicate identifier: "Identifier 'X' has already been declared"
        (r"Identifier ['\"]?([^'\"]+)['\"]? has already been declared",
         "duplicate_identifier", None, 1),
        # require is not defined (CommonJS in ESM context)
        (r"ReferenceError:\s*require is not defined",
         "require_not_defined", None, None),
        (r"require is not defined",
         "require_not_defined", None, None),
        # Syntax errors
        (r"SyntaxError:\s*(.+)",
         "syntax_error", None, None),
        # Import path errors
        (r"Cannot find module ['\"]([^'\"]+)['\"]",
         "import_path_error", 1, None),
        (r"Module not found.*['\"]([^'\"]+)['\"]",
         "import_path_error", 1, None),
    ]

    async def _read_output(self) -> None:
        """Read and process server output."""
        if not self._process or not self._process.stdout:
            return

        try:
            while self._process.poll() is None:
                line = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._process.stdout.readline
                )
                if line:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:
                        # Sanitize for Windows console (replace non-ASCII chars)
                        safe_decoded = decoded.encode('ascii', errors='replace').decode('ascii')
                        # Log output
                        self.logger.debug("server_output", line=safe_decoded)

                        # Store in recent logs buffer (for 500 error context)
                        self._recent_logs.append(decoded)

                        # Strip ANSI escape codes for pattern matching
                        # Vite's output has ANSI codes like [1m5176[22m around the port number
                        ansi_stripped = re.sub(r'\x1b\[[0-9;]*m', '', decoded)

                        # Cache port from Node.js error objects for multi-line EADDRINUSE detection
                        # Node.js errors span multiple lines: "code: 'EADDRINUSE'" on one line,
                        # "port: 3000" on a separate line - we need to cache and use later
                        port_cache_match = re.search(r'\bport:\s*(\d{4,5})\b', decoded)
                        if port_cache_match:
                            self._last_eaddrinuse_port = int(port_cache_match.group(1))

                        # Auto-detect server port from output
                        if not self._port_detected:
                            for pattern in self.PORT_DETECTION_PATTERNS:
                                match = re.search(pattern, ansi_stripped, re.IGNORECASE)
                                if match:
                                    detected_port = int(match.group(1))
                                    # Only update if different from default
                                    if detected_port != self.port:
                                        old_port = self.port
                                        self.port = detected_port
                                        self.state.port = detected_port
                                        self.state.url = f"http://localhost:{detected_port}"
                                        self._port_detected = True

                                        self.logger.info(
                                            "server_port_auto_detected",
                                            old_port=old_port,
                                            detected_port=detected_port,
                                        )

                                        # Classify port as frontend or backend
                                        port_type = self.classify_port(detected_port)

                                        # Publish event for health monitor to update
                                        await self.event_bus.publish(Event(
                                            type=EventType.SERVER_PORT_DETECTED,
                                            source="dev_server",
                                            data={
                                                "port": detected_port,
                                                "port_type": port_type,  # "frontend" or "backend"
                                                "old_port": old_port,
                                                "working_dir": str(self.working_dir),
                                            },
                                        ))

                                        self.logger.info(
                                            "port_classified",
                                            port=detected_port,
                                            port_type=port_type,
                                        )
                                    else:
                                        self._port_detected = True  # Port matches, no update needed
                                    break

                        # Check for ready signals
                        if "ready" in decoded.lower() or "listening" in decoded.lower():
                            await self.event_bus.publish(Event(
                                type=EventType.BUILD_COMPLETED,
                                source="dev_server",
                                success=True,
                                data={"message": decoded},
                            ))

                        # Check for code-level errors FIRST (missing exports, circular deps)
                        # These often contain "module" but need different handling than module_not_found
                        elif ("does not provide an export" in decoded.lower() or
                              "circular dependency" in decoded.lower() or
                              ("export" in decoded.lower() and "error" in decoded.lower())):
                            code_error_found = False
                            for pattern, error_type, module_group, export_group in self.CODE_ERROR_PATTERNS:
                                match = re.search(pattern, decoded, re.IGNORECASE)
                                if match:
                                    # Extract source file from earlier line if available
                                    source_file = None
                                    file_match = re.search(r'([^\s:]+\.(ts|tsx|js|jsx)):', decoded)
                                    if file_match:
                                        source_file = file_match.group(1)

                                    # Extract module and export names
                                    target_module = match.group(module_group) if module_group else None
                                    missing_export = match.group(export_group) if export_group else None

                                    self.logger.warning(
                                        "code_error_detected",
                                        error_type=error_type,
                                        target_module=target_module,
                                        missing_export=missing_export,
                                        source_file=source_file,
                                    )

                                    await self.event_bus.publish(Event(
                                        type=EventType.VALIDATION_ERROR,
                                        source="dev_server",
                                        error_message=f"Code error: {error_type}",
                                        data={
                                            "error_type": "code_error",
                                            "code_error_type": error_type,
                                            "target_module": target_module,
                                            "missing_export": missing_export,
                                            "source_file": source_file,
                                            "raw_error": decoded,
                                            "action_required": "fix_code",
                                        },
                                    ))
                                    code_error_found = True
                                    break

                            # Fall back to generic if no pattern matched - still send to BugFixer
                            if not code_error_found:
                                # Try to extract source file from error
                                source_file = None
                                file_match = re.search(r'([^\s:]+\.(ts|tsx|js|jsx)):', decoded)
                                if file_match:
                                    source_file = file_match.group(1)

                                await self.event_bus.publish(Event(
                                    type=EventType.VALIDATION_ERROR,
                                    source="dev_server",
                                    error_message=decoded,
                                    data={
                                        "error_type": "code_error",
                                        "code_error_type": "generic",
                                        "source_file": source_file,
                                        "raw_error": decoded,
                                        "action_required": "fix_code",
                                    },
                                ))

                        # Check for module not found errors (specific, actionable)
                        elif "module" in decoded.lower() or "cannot find" in decoded.lower():
                            module_found = False
                            for pattern in self.MODULE_NOT_FOUND_PATTERNS:
                                match = re.search(pattern, decoded, re.IGNORECASE)
                                if match:
                                    module_name = match.group(1)
                                    # Clean up module name (remove paths, get package name)
                                    if "/" in module_name:
                                        module_name = module_name.split("/")[0]
                                    if module_name.startswith("@"):
                                        # Scoped package like @types/node
                                        parts = match.group(1).split("/")
                                        if len(parts) >= 2:
                                            module_name = f"{parts[0]}/{parts[1]}"

                                    self.logger.warning(
                                        "module_not_found_detected",
                                        module=module_name,
                                        raw_error=safe_decoded,
                                    )
                                    await self.event_bus.publish(Event(
                                        type=EventType.VALIDATION_ERROR,
                                        source="dev_server",
                                        error_message=f"Missing module: {module_name}",
                                        data={
                                            "error_type": "module_not_found",
                                            "module_name": module_name,
                                            "raw_error": decoded,
                                            "action_required": "npm_install",
                                        },
                                    ))
                                    module_found = True
                                    break

                            # Generic error if no module pattern matched - WITH DEDUPLICATION
                            if not module_found and "error" in decoded.lower():
                                if self._should_publish_error("module_generic", decoded):
                                    await self.event_bus.publish(Event(
                                        type=EventType.VALIDATION_ERROR,
                                        source="dev_server",
                                        error_message=decoded,
                                        data={
                                            "error_type": "generic",
                                            "raw_error": decoded,
                                        },
                                    ))

                        # Check for Vite proxy errors (backend not running)
                        elif "proxy error" in decoded.lower() or "[vite proxy]" in decoded.lower() or "socket hang up" in decoded.lower():
                            # This usually means the backend server is not running
                            self.logger.warning(
                                "vite_proxy_error_detected",
                                message=decoded[:200],
                            )
                            # Trigger backend auto-start
                            if self._backend_auto_start_enabled and self._backend_start_attempts < self._max_backend_start_attempts:
                                asyncio.create_task(self._start_backend_server())

                        # Check for EADDRINUSE (port already in use) - auto-cleanup and restart
                        elif "EADDRINUSE" in decoded or "address already in use" in decoded.lower():
                            import time as time_module
                            now = time_module.time()

                            # Deduplicate EADDRINUSE within cooldown window (Node.js outputs multiple lines)
                            if now - self._last_eaddrinuse_time < self._eaddrinuse_cooldown:
                                self.logger.debug(
                                    "eaddrinuse_deduplicated",
                                    message=decoded[:100],
                                    cooldown_remaining=round(self._eaddrinuse_cooldown - (now - self._last_eaddrinuse_time), 1),
                                )
                            else:
                                # Extract the port from the error message (try multiple patterns)
                                blocked_port = None

                                # Try :::3000 format first (most reliable)
                                port_match = re.search(r':::(\d{4,5})', decoded)
                                if port_match:
                                    blocked_port = int(port_match.group(1))

                                # Try "address already in use" followed by port
                                if not blocked_port:
                                    port_match = re.search(r'address already in use[^\d]*(\d{4,5})', decoded)
                                    if port_match:
                                        blocked_port = int(port_match.group(1))

                                # Fallback to cached port from previous lines (Node.js multi-line errors)
                                used_cached = False
                                if not blocked_port and self._last_eaddrinuse_port:
                                    blocked_port = self._last_eaddrinuse_port
                                    used_cached = True
                                    self._last_eaddrinuse_port = None  # Clear after use

                                # Cache port for subsequent lines (if we found one)
                                if blocked_port and not used_cached:
                                    self._last_eaddrinuse_port = blocked_port

                                self.logger.warning(
                                    "eaddrinuse_detected",
                                    port=blocked_port,
                                    cached_port_used=used_cached,
                                    message=decoded[:150],
                                )

                                # Update timestamp for deduplication
                                self._last_eaddrinuse_time = now

                                # Cleanup the blocked port
                                if blocked_port:
                                    await self._cleanup_port(blocked_port)

                                await self.event_bus.publish(Event(
                                    type=EventType.VALIDATION_ERROR,
                                    source="dev_server",
                                    error_message=f"Port {blocked_port or 'unknown'} already in use - cleaned up",
                                    data={
                                        "error_type": "eaddrinuse",
                                        "port": blocked_port,
                                        "action_taken": "port_cleanup",
                                        "action_required": "restart_server",
                                    },
                                ))

                        # Check for database errors BEFORE generic error check
                        elif any(re.search(p, decoded, re.IGNORECASE) for p in self.DATABASE_ERROR_PATTERNS):
                            self.logger.warning(
                                "database_error_detected_in_output",
                                message=decoded[:200],
                            )
                            await self.event_bus.publish(Event(
                                type=EventType.VALIDATION_ERROR,
                                source="dev_server",
                                error_message="Database connection failed",
                                data={
                                    "error_type": "database_error",
                                    "raw_error": decoded,
                                    "action_required": "start_database",
                                },
                            ))

                        # Check for other errors (generic fallback) - WITH DEDUPLICATION
                        elif "error" in decoded.lower():
                            # Only publish if not a duplicate (prevents event flooding)
                            if self._should_publish_error("generic", decoded):
                                await self.event_bus.publish(Event(
                                    type=EventType.VALIDATION_ERROR,
                                    source="dev_server",
                                    error_message=decoded,
                                    data={
                                        "error_type": "generic",
                                        "raw_error": decoded,
                                    },
                                ))

        except Exception as e:
            self.logger.error("output_read_error", error=str(e))

    async def stop(self) -> None:
        """Stop the development server."""
        if not self._process:
            return

        try:
            if os.name == 'nt':
                # Windows: use taskkill for process tree
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(self._process.pid)],
                    capture_output=True
                )
            else:
                # Unix: send SIGTERM then SIGKILL
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                await asyncio.sleep(2)
                if self._process.poll() is None:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)

            self._process = None
            self.state.status = PreviewStatus.STOPPED
            self.state.pid = None

            self.logger.info("dev_server_stopped")

        except Exception as e:
            self.logger.error("dev_server_stop_error", error=str(e))

        # Cancel output reader
        if self._output_task:
            self._output_task.cancel()
            try:
                await self._output_task
            except asyncio.CancelledError:
                pass
            self._output_task = None

        # Stop backend server if running
        await self._stop_backend_server()

    async def _stop_backend_server(self) -> None:
        """Stop the backend server if running."""
        if not self._backend_process:
            return

        try:
            if os.name == 'nt':
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(self._backend_process.pid)],
                    capture_output=True
                )
            else:
                self._backend_process.terminate()
                try:
                    self._backend_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._backend_process.kill()

            self.logger.info("backend_server_stopped", pid=self._backend_process.pid)
            self._backend_process = None

        except Exception as e:
            self.logger.warning("backend_server_stop_error", error=str(e))

        # Cancel backend output reader
        if self._backend_output_task:
            self._backend_output_task.cancel()
            try:
                await self._backend_output_task
            except asyncio.CancelledError:
                pass
            self._backend_output_task = None

        # Reset attempt counter
        self._backend_start_attempts = 0

    async def restart(self, full_cleanup: bool = True) -> bool:
        """Restart the development server with optional port cleanup.

        Args:
            full_cleanup: If True, cleanup all common ports before restart
        """
        self.logger.info("dev_server_restarting", full_cleanup=full_cleanup)
        await self.stop()
        await asyncio.sleep(1)

        # Reset port detection flag so we can detect new ports
        self._port_detected = False

        if full_cleanup:
            await self.cleanup_all_ports()

        return await self.start()

    async def cleanup_all_ports(self) -> dict[int, bool]:
        """Aggressively cleanup ALL common development ports.

        Useful when restarting or when EADDRINUSE errors occur.

        Returns:
            Dict mapping port -> whether cleanup was performed
        """
        # All ports that might be used by frontend or backend
        # NOTE: Port 3000 excluded - often used by other projects
        all_dev_ports = [
            5173, 5174, 5175, 5176, 5177, 5178, 5179,  # Vite range
            3001, 3002, 3003,  # Express range (3000 excluded - external project)
            8080, 8000, 8001,  # Other common ports
            self.port,  # Current configured port
        ]
        # Deduplicate
        all_dev_ports = list(set(all_dev_ports))

        results = {}
        for port in all_dev_ports:
            if not self._is_port_available(port):
                self.logger.info("cleaning_occupied_port", port=port)
                success = await self._cleanup_port(port)
                results[port] = success
            else:
                results[port] = False  # No cleanup needed

        cleaned_count = sum(1 for v in results.values() if v)
        if cleaned_count > 0:
            self.logger.info("ports_cleaned", count=cleaned_count, ports=[p for p, v in results.items() if v])

        return results

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._process is not None and self._process.poll() is None

    def get_recent_logs(self, count: int = 50) -> list[str]:
        """
        Get recent server output lines for debugging context.

        Used by BrowserErrorDetector to provide Vite logs when 500 errors occur.

        Args:
            count: Maximum number of lines to return (newest last)

        Returns:
            List of recent log lines, newest last
        """
        return list(self._recent_logs)[-count:]

    def _subscribe_to_dependency_updates(self) -> None:
        """Subscribe to DEPENDENCY_UPDATED events for auto-restart."""
        try:
            self.event_bus.subscribe(  # Synchronous - no await needed
                EventType.DEPENDENCY_UPDATED,
                self._on_dependency_updated
            )
            self.logger.debug("subscribed_to_dependency_updates")
        except Exception as e:
            self.logger.warning("dependency_subscription_failed", error=str(e))

    async def _on_dependency_updated(self, event: Event) -> None:
        """Handle dependency update events - restart server if needed."""
        if not self.is_running():
            self.logger.debug("dependency_updated_but_server_not_running")
            return

        event_data = event.data or {}
        action = event_data.get("action")
        module = event_data.get("module", "unknown")

        if action == "installed":
            self.logger.info(
                "dependency_installed_restarting",
                module=module,
            )
            # Brief pause for npm to finish writing files
            await asyncio.sleep(1)
            await self.restart()


class LivePreviewSystem:
    """
    Complete live preview system integrating file watching and dev server.

    Provides real-time preview of the evolving application.
    """

    def __init__(
        self,
        working_dir: str,
        event_bus: EventBus,
        port: int = 5173,
        auto_restart_on_change: bool = True,
        restart_debounce_ms: int = 500,
        open_browser: bool = True,
    ):
        self.working_dir = working_dir
        self.event_bus = event_bus
        self.auto_restart = auto_restart_on_change
        self.restart_debounce_ms = restart_debounce_ms
        self.open_browser = open_browser
        self._browser_opened = False

        # Components
        self.file_watcher = FileWatcher(working_dir, event_bus)
        self.dev_server = DevServerManager(working_dir, event_bus, port)

        # Debounce state
        self._restart_task: Optional[asyncio.Task] = None
        self._pending_restart = False

        self.logger = logger.bind(component="live_preview")

        # Subscribe to file change events
        event_bus.subscribe(EventType.FILE_CREATED, self._on_file_change)
        event_bus.subscribe(EventType.FILE_MODIFIED, self._on_file_change)

    async def _on_file_change(self, event: Event) -> None:
        """Handle file changes that may require server restart."""
        if not self.auto_restart or not self.dev_server.is_running():
            return

        # Only restart for relevant file changes
        file_path = event.file_path or ""
        relevant_extensions = [".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".css", ".scss"]

        if not any(file_path.endswith(ext) for ext in relevant_extensions):
            return

        # Ignore node_modules and build output
        if "node_modules" in file_path or "dist" in file_path:
            return

        # Debounced restart
        await self._schedule_restart()

    async def _schedule_restart(self) -> None:
        """Schedule a debounced restart."""
        self._pending_restart = True

        if self._restart_task:
            return  # Already scheduled

        async def _delayed_restart():
            await asyncio.sleep(self.restart_debounce_ms / 1000)
            if self._pending_restart:
                self._pending_restart = False
                self.dev_server.state.status = PreviewStatus.REBUILDING
                self.dev_server.state.rebuild_count += 1
                self.dev_server.state.last_rebuild = datetime.now()

                # For Vite/esbuild, hot reload should handle most cases
                # Only full restart for config changes
                self.logger.info("hot_reload_triggered")

            self._restart_task = None

        self._restart_task = asyncio.create_task(_delayed_restart())

    async def start(self, wait_for_ready: bool = True, timeout: float = 60.0) -> bool:
        """
        Start the live preview system.

        Args:
            wait_for_ready: Wait for server to be ready
            timeout: Timeout in seconds

        Returns:
            True if started successfully
        """
        self.logger.info("starting_live_preview")

        # Start file watcher
        await self.file_watcher.start()

        # Start dev server
        if not await self.dev_server.start():
            return False

        # Wait for server to be ready
        if wait_for_ready:
            ready_event = asyncio.Event()

            async def on_ready(event: Event):
                if event.type == EventType.BUILD_COMPLETED and event.success:
                    ready_event.set()

            self.event_bus.subscribe(EventType.BUILD_COMPLETED, on_ready)

            try:
                await asyncio.wait_for(ready_event.wait(), timeout=timeout)
                self.logger.info("live_preview_ready", url=self.dev_server.state.url)
            except asyncio.TimeoutError:
                self.logger.warning("server_ready_timeout")

        # Publish preview ready event
        await self.event_bus.publish(Event(
            type=EventType.SYSTEM_READY,
            source="live_preview",
            data={
                "url": self.dev_server.state.url,
                "port": self.dev_server.state.port,
            },
        ))

        # Auto-open browser if enabled
        if self.open_browser and not self._browser_opened and self.dev_server.state.url:
            try:
                webbrowser.open(self.dev_server.state.url)
                self._browser_opened = True
                self.logger.info("browser_opened", url=self.dev_server.state.url)
            except Exception as e:
                self.logger.warning("browser_open_failed", error=str(e))

        return True

    async def stop(self) -> None:
        """Stop the live preview system."""
        self.logger.info("stopping_live_preview")

        await self.file_watcher.stop()
        await self.dev_server.stop()

    def get_state(self) -> dict:
        """Get current preview state."""
        return {
            "server": self.dev_server.state.to_dict(),
            "watcher": {
                "running": self.file_watcher._running,
                "watched_files": len(self.file_watcher._file_mtimes),
            },
        }


async def create_live_preview(
    working_dir: str,
    event_bus: Optional[EventBus] = None,
    port: int = 5173,
    open_browser: bool = True,
) -> LivePreviewSystem:
    """
    Convenience function to create and start a live preview system.

    Args:
        working_dir: Project working directory
        event_bus: Optional event bus (creates new if not provided)
        port: Dev server port
        open_browser: Whether to auto-open browser when ready

    Returns:
        Running LivePreviewSystem instance
    """
    bus = event_bus or EventBus()
    preview = LivePreviewSystem(working_dir, bus, port, open_browser=open_browser)
    await preview.start()
    return preview
