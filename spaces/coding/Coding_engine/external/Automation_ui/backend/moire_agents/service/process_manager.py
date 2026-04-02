"""
Process Manager for Handoff MCP Production Deployment

Handles process lifecycle management including:
- Starting and stopping MoireServer and MCP processes
- Process monitoring and auto-restart
- Graceful shutdown handling
- PID file management
"""

import os
import sys
import signal
import subprocess
import asyncio
import psutil
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

from ..config import get_config


@dataclass
class ProcessInfo:
    """Information about a managed process"""
    name: str
    pid: Optional[int]
    started_at: Optional[datetime]
    restart_count: int = 0
    last_restart: Optional[datetime] = None


class ProcessManager:
    """
    Manages Handoff MCP processes with auto-restart and health monitoring.

    Handles:
    - MoireServer (TypeScript/Node.js) - WebSocket server for OCR
    - MCP Server (Python) - Main automation server
    """

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger('ProcessManager')

        # Process tracking
        self.processes: dict[str, ProcessInfo] = {}
        self.subprocess_handles: dict[str, subprocess.Popen] = {}

        # Control flags
        self._running = False
        self._shutdown_requested = False

        # Callbacks
        self._on_process_started: Optional[Callable] = None
        self._on_process_stopped: Optional[Callable] = None
        self._on_process_crashed: Optional[Callable] = None

        # PID file directory
        self.pid_dir = Path(self.config.python_root) / "run"
        self.pid_dir.mkdir(parents=True, exist_ok=True)

        # Setup signal handlers
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        if sys.platform == 'win32':
            # Windows doesn't have SIGTERM, use SIGINT and SIGBREAK
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGBREAK, self._signal_handler)
        else:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
        asyncio.create_task(self.stop_all())

    def _write_pid_file(self, name: str, pid: int):
        """Write PID to file for external monitoring"""
        pid_file = self.pid_dir / f"{name}.pid"
        pid_file.write_text(str(pid))
        self.logger.debug(f"Wrote PID {pid} to {pid_file}")

    def _remove_pid_file(self, name: str):
        """Remove PID file"""
        pid_file = self.pid_dir / f"{name}.pid"
        if pid_file.exists():
            pid_file.unlink()
            self.logger.debug(f"Removed PID file {pid_file}")

    def _read_pid_file(self, name: str) -> Optional[int]:
        """Read PID from file"""
        pid_file = self.pid_dir / f"{name}.pid"
        if pid_file.exists():
            try:
                return int(pid_file.read_text().strip())
            except (ValueError, IOError):
                pass
        return None

    async def start_moire_server(self) -> bool:
        """
        Start the MoireServer TypeScript/Node.js process.

        Returns:
            bool: True if started successfully
        """
        name = "moire_server"

        if name in self.subprocess_handles and self.subprocess_handles[name].poll() is None:
            self.logger.info("MoireServer is already running")
            return True

        moire_path = Path(self.config.project_root)

        try:
            # Start MoireServer using npm
            proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(moire_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )

            self.subprocess_handles[name] = proc
            self.processes[name] = ProcessInfo(
                name=name,
                pid=proc.pid,
                started_at=datetime.now()
            )

            self._write_pid_file(name, proc.pid)
            self.logger.info(f"MoireServer started with PID {proc.pid}")

            if self._on_process_started:
                self._on_process_started(name, proc.pid)

            # Wait briefly to check if it started successfully
            await asyncio.sleep(2)

            if proc.poll() is not None:
                self.logger.error("MoireServer failed to start")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Failed to start MoireServer: {e}")
            return False

    async def start_mcp_server(self) -> bool:
        """
        Start the MCP Server Python process.

        Note: In production, this is typically started by Claude Code as an MCP server.
        This method is for standalone/testing scenarios.

        Returns:
            bool: True if started successfully
        """
        name = "mcp_server"

        if name in self.subprocess_handles and self.subprocess_handles[name].poll() is None:
            self.logger.info("MCP Server is already running")
            return True

        mcp_script = Path(self.config.python_root) / "mcp_server_handoff.py"

        if not mcp_script.exists():
            self.logger.error(f"MCP Server script not found: {mcp_script}")
            return False

        try:
            proc = subprocess.Popen(
                [sys.executable, str(mcp_script)],
                cwd=self.config.python_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )

            self.subprocess_handles[name] = proc
            self.processes[name] = ProcessInfo(
                name=name,
                pid=proc.pid,
                started_at=datetime.now()
            )

            self._write_pid_file(name, proc.pid)
            self.logger.info(f"MCP Server started with PID {proc.pid}")

            if self._on_process_started:
                self._on_process_started(name, proc.pid)

            return True

        except Exception as e:
            self.logger.error(f"Failed to start MCP Server: {e}")
            return False

    async def stop_process(self, name: str, timeout: float = 10.0) -> bool:
        """
        Stop a managed process gracefully.

        Args:
            name: Process name
            timeout: Seconds to wait for graceful shutdown before force kill

        Returns:
            bool: True if stopped successfully
        """
        if name not in self.subprocess_handles:
            self.logger.warning(f"Process {name} not found")
            return True

        proc = self.subprocess_handles[name]

        if proc.poll() is not None:
            self.logger.info(f"Process {name} already stopped")
            self._cleanup_process(name)
            return True

        self.logger.info(f"Stopping process {name} (PID {proc.pid})...")

        try:
            # Try graceful shutdown first
            if sys.platform == 'win32':
                # Send CTRL+BREAK on Windows
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()

            # Wait for graceful shutdown
            try:
                proc.wait(timeout=timeout)
                self.logger.info(f"Process {name} stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                self.logger.warning(f"Process {name} didn't stop gracefully, forcing kill...")
                proc.kill()
                proc.wait(timeout=5)

            self._cleanup_process(name)

            if self._on_process_stopped:
                self._on_process_stopped(name, proc.returncode)

            return True

        except Exception as e:
            self.logger.error(f"Error stopping process {name}: {e}")
            return False

    def _cleanup_process(self, name: str):
        """Clean up process tracking data"""
        self._remove_pid_file(name)
        if name in self.processes:
            del self.processes[name]
        if name in self.subprocess_handles:
            del self.subprocess_handles[name]

    async def stop_all(self):
        """Stop all managed processes"""
        self.logger.info("Stopping all managed processes...")

        for name in list(self.subprocess_handles.keys()):
            await self.stop_process(name)

        self._running = False
        self.logger.info("All processes stopped")

    def is_process_running(self, name: str) -> bool:
        """Check if a process is running"""
        if name not in self.subprocess_handles:
            return False
        return self.subprocess_handles[name].poll() is None

    async def restart_process(self, name: str) -> bool:
        """Restart a process"""
        await self.stop_process(name)

        if name == "moire_server":
            return await self.start_moire_server()
        elif name == "mcp_server":
            return await self.start_mcp_server()
        else:
            self.logger.error(f"Unknown process type: {name}")
            return False

    async def monitor_processes(self, check_interval: float = 5.0):
        """
        Monitor processes and auto-restart if configured.

        Args:
            check_interval: Seconds between checks
        """
        self._running = True

        while self._running and not self._shutdown_requested:
            for name, proc in list(self.subprocess_handles.items()):
                if proc.poll() is not None:
                    # Process has exited
                    exit_code = proc.returncode
                    self.logger.warning(f"Process {name} exited with code {exit_code}")

                    if self._on_process_crashed:
                        self._on_process_crashed(name, exit_code)

                    # Auto-restart if configured
                    if self.config.auto_restart_on_failure:
                        info = self.processes.get(name)
                        if info and info.restart_count < self.config.max_restart_attempts:
                            self.logger.info(f"Auto-restarting {name} (attempt {info.restart_count + 1}/{self.config.max_restart_attempts})")

                            if await self.restart_process(name):
                                if name in self.processes:
                                    self.processes[name].restart_count += 1
                                    self.processes[name].last_restart = datetime.now()
                        else:
                            self.logger.error(f"Max restart attempts reached for {name}")
                            self._cleanup_process(name)

            await asyncio.sleep(check_interval)

    def get_status(self) -> dict:
        """Get status of all managed processes"""
        status = {}
        for name, info in self.processes.items():
            running = self.is_process_running(name)
            status[name] = {
                "running": running,
                "pid": info.pid if running else None,
                "started_at": info.started_at.isoformat() if info.started_at else None,
                "restart_count": info.restart_count,
                "last_restart": info.last_restart.isoformat() if info.last_restart else None
            }
        return status

    def kill_orphaned_processes(self):
        """Kill any orphaned processes from previous runs"""
        for name in ["moire_server", "mcp_server"]:
            pid = self._read_pid_file(name)
            if pid:
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        self.logger.warning(f"Killing orphaned {name} process (PID {pid})")
                        proc.terminate()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                    pass
                finally:
                    self._remove_pid_file(name)

    # Event callbacks
    def on_process_started(self, callback: Callable[[str, int], None]):
        """Set callback for when a process starts"""
        self._on_process_started = callback

    def on_process_stopped(self, callback: Callable[[str, int], None]):
        """Set callback for when a process stops"""
        self._on_process_stopped = callback

    def on_process_crashed(self, callback: Callable[[str, int], None]):
        """Set callback for when a process crashes"""
        self._on_process_crashed = callback


async def main():
    """Test the process manager"""
    logging.basicConfig(level=logging.INFO)

    manager = ProcessManager()
    manager.kill_orphaned_processes()

    print("Starting MoireServer...")
    if await manager.start_moire_server():
        print("MoireServer started successfully")
    else:
        print("Failed to start MoireServer")

    print("\nProcess Status:")
    print(manager.get_status())

    print("\nPress Ctrl+C to stop...")
    try:
        await manager.monitor_processes()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
