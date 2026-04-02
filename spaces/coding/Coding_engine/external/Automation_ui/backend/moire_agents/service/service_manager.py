"""
Cross-Platform Service Manager for Handoff MCP

Supports:
- Windows: Task Scheduler, NSSM, or native service
- Linux: systemd service units
- macOS: launchd plist

Provides unified interface for service installation, control, and monitoring.
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger('ServiceManager')


class Platform(Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "darwin"
    UNKNOWN = "unknown"


@dataclass
class ServiceConfig:
    """Configuration for a managed service"""
    name: str
    display_name: str
    description: str
    command: str
    args: list[str]
    working_dir: str
    auto_start: bool = True
    restart_on_failure: bool = True
    restart_delay_seconds: int = 5
    max_restarts: int = 3
    environment: Dict[str, str] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}


class ServiceManager:
    """
    Cross-platform service manager for Handoff MCP components.

    Usage:
        manager = ServiceManager()
        manager.install_service(ServiceConfig(...))
        manager.start_service("HandoffMCP")
        manager.status("HandoffMCP")
    """

    def __init__(self):
        self.platform = self._detect_platform()
        self.project_root = Path(__file__).parent.parent.parent
        self.python_root = Path(__file__).parent.parent

    def _detect_platform(self) -> Platform:
        """Detect the current operating system"""
        system = platform.system().lower()
        if system == "windows":
            return Platform.WINDOWS
        elif system == "linux":
            return Platform.LINUX
        elif system == "darwin":
            return Platform.MACOS
        return Platform.UNKNOWN

    # ==========================================
    # Public API
    # ==========================================

    def install_service(self, config: ServiceConfig) -> bool:
        """Install a service on the current platform"""
        logger.info(f"Installing service '{config.name}' on {self.platform.value}")

        if self.platform == Platform.WINDOWS:
            return self._install_windows(config)
        elif self.platform == Platform.LINUX:
            return self._install_linux_systemd(config)
        elif self.platform == Platform.MACOS:
            return self._install_macos_launchd(config)
        else:
            logger.error(f"Unsupported platform: {self.platform}")
            return False

    def uninstall_service(self, name: str) -> bool:
        """Uninstall a service"""
        logger.info(f"Uninstalling service '{name}'")

        if self.platform == Platform.WINDOWS:
            return self._uninstall_windows(name)
        elif self.platform == Platform.LINUX:
            return self._uninstall_linux_systemd(name)
        elif self.platform == Platform.MACOS:
            return self._uninstall_macos_launchd(name)
        return False

    def start_service(self, name: str) -> bool:
        """Start a service"""
        logger.info(f"Starting service '{name}'")

        if self.platform == Platform.WINDOWS:
            return self._run_command(["sc", "start", name])
        elif self.platform == Platform.LINUX:
            return self._run_command(["systemctl", "--user", "start", name])
        elif self.platform == Platform.MACOS:
            return self._run_command(["launchctl", "start", f"com.handoff.{name}"])
        return False

    def stop_service(self, name: str) -> bool:
        """Stop a service"""
        logger.info(f"Stopping service '{name}'")

        if self.platform == Platform.WINDOWS:
            return self._run_command(["sc", "stop", name])
        elif self.platform == Platform.LINUX:
            return self._run_command(["systemctl", "--user", "stop", name])
        elif self.platform == Platform.MACOS:
            return self._run_command(["launchctl", "stop", f"com.handoff.{name}"])
        return False

    def restart_service(self, name: str) -> bool:
        """Restart a service"""
        self.stop_service(name)
        return self.start_service(name)

    def status(self, name: str) -> Dict[str, Any]:
        """Get service status"""
        if self.platform == Platform.WINDOWS:
            return self._status_windows(name)
        elif self.platform == Platform.LINUX:
            return self._status_linux_systemd(name)
        elif self.platform == Platform.MACOS:
            return self._status_macos_launchd(name)
        return {"status": "unknown", "platform": "unsupported"}

    def is_running(self, name: str) -> bool:
        """Check if service is running"""
        status = self.status(name)
        return status.get("running", False)

    # ==========================================
    # Windows Implementation
    # ==========================================

    def _install_windows(self, config: ServiceConfig) -> bool:
        """Install service on Windows using Task Scheduler or NSSM"""
        # Check if NSSM is available (preferred for services)
        nssm_path = shutil.which("nssm")

        if nssm_path:
            return self._install_windows_nssm(config, nssm_path)
        else:
            # Fallback to Task Scheduler
            return self._install_windows_task_scheduler(config)

    def _install_windows_nssm(self, config: ServiceConfig, nssm_path: str) -> bool:
        """Install using NSSM (Non-Sucking Service Manager)"""
        try:
            # Install the service
            cmd = [nssm_path, "install", config.name, config.command]
            cmd.extend(config.args)

            if not self._run_command(cmd):
                return False

            # Set working directory
            self._run_command([nssm_path, "set", config.name, "AppDirectory", config.working_dir])

            # Set display name and description
            self._run_command([nssm_path, "set", config.name, "DisplayName", config.display_name])
            self._run_command([nssm_path, "set", config.name, "Description", config.description])

            # Set auto-start
            start_type = "SERVICE_AUTO_START" if config.auto_start else "SERVICE_DEMAND_START"
            self._run_command([nssm_path, "set", config.name, "Start", start_type])

            # Set restart on failure
            if config.restart_on_failure:
                self._run_command([nssm_path, "set", config.name, "AppExit", "Default", "Restart"])
                self._run_command([nssm_path, "set", config.name, "AppRestartDelay",
                                   str(config.restart_delay_seconds * 1000)])

            # Set environment variables
            if config.environment:
                env_str = " ".join([f"{k}={v}" for k, v in config.environment.items()])
                self._run_command([nssm_path, "set", config.name, "AppEnvironmentExtra", env_str])

            logger.info(f"Service '{config.name}' installed via NSSM")
            return True

        except Exception as e:
            logger.error(f"NSSM installation failed: {e}")
            return False

    def _install_windows_task_scheduler(self, config: ServiceConfig) -> bool:
        """Install using Windows Task Scheduler"""
        try:
            # Build the command
            full_command = f'"{config.command}" {" ".join(config.args)}'

            # Create task using schtasks
            cmd = [
                "schtasks", "/create",
                "/tn", config.name,
                "/tr", full_command,
                "/sc", "onlogon" if config.auto_start else "ondemand",
                "/rl", "limited",
                "/f"  # Force overwrite
            ]

            if not self._run_command(cmd):
                return False

            logger.info(f"Service '{config.name}' installed via Task Scheduler")
            return True

        except Exception as e:
            logger.error(f"Task Scheduler installation failed: {e}")
            return False

    def _uninstall_windows(self, name: str) -> bool:
        """Uninstall Windows service"""
        nssm_path = shutil.which("nssm")

        if nssm_path:
            self._run_command([nssm_path, "stop", name])
            return self._run_command([nssm_path, "remove", name, "confirm"])
        else:
            return self._run_command(["schtasks", "/delete", "/tn", name, "/f"])

    def _status_windows(self, name: str) -> Dict[str, Any]:
        """Get Windows service status"""
        try:
            result = subprocess.run(
                ["sc", "query", name],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                output = result.stdout
                running = "RUNNING" in output
                return {
                    "name": name,
                    "running": running,
                    "status": "running" if running else "stopped",
                    "platform": "windows"
                }
            else:
                # Try Task Scheduler
                result = subprocess.run(
                    ["schtasks", "/query", "/tn", name],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    running = "Running" in result.stdout
                    return {
                        "name": name,
                        "running": running,
                        "status": "running" if running else "ready",
                        "platform": "windows-task"
                    }

        except Exception as e:
            logger.error(f"Status check failed: {e}")

        return {"name": name, "running": False, "status": "not_found", "platform": "windows"}

    # ==========================================
    # Linux Implementation (systemd)
    # ==========================================

    def _install_linux_systemd(self, config: ServiceConfig) -> bool:
        """Install systemd user service on Linux"""
        try:
            # Create systemd user directory
            systemd_dir = Path.home() / ".config" / "systemd" / "user"
            systemd_dir.mkdir(parents=True, exist_ok=True)

            # Build environment string
            env_lines = "\n".join([f"Environment={k}={v}" for k, v in config.environment.items()])

            # Create service unit file
            service_content = f"""[Unit]
Description={config.description}
After=network.target

[Service]
Type=simple
WorkingDirectory={config.working_dir}
ExecStart={config.command} {' '.join(config.args)}
Restart={'always' if config.restart_on_failure else 'no'}
RestartSec={config.restart_delay_seconds}
{env_lines}

[Install]
WantedBy=default.target
"""

            service_file = systemd_dir / f"{config.name}.service"
            service_file.write_text(service_content)

            # Reload systemd
            self._run_command(["systemctl", "--user", "daemon-reload"])

            # Enable if auto-start
            if config.auto_start:
                self._run_command(["systemctl", "--user", "enable", config.name])

            logger.info(f"Service '{config.name}' installed as systemd user service")
            return True

        except Exception as e:
            logger.error(f"systemd installation failed: {e}")
            return False

    def _uninstall_linux_systemd(self, name: str) -> bool:
        """Uninstall systemd user service"""
        try:
            self._run_command(["systemctl", "--user", "stop", name])
            self._run_command(["systemctl", "--user", "disable", name])

            service_file = Path.home() / ".config" / "systemd" / "user" / f"{name}.service"
            if service_file.exists():
                service_file.unlink()

            self._run_command(["systemctl", "--user", "daemon-reload"])
            return True

        except Exception as e:
            logger.error(f"systemd uninstall failed: {e}")
            return False

    def _status_linux_systemd(self, name: str) -> Dict[str, Any]:
        """Get systemd service status"""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", name],
                capture_output=True,
                text=True
            )
            active = result.stdout.strip() == "active"

            result2 = subprocess.run(
                ["systemctl", "--user", "is-enabled", name],
                capture_output=True,
                text=True
            )
            enabled = result2.stdout.strip() == "enabled"

            return {
                "name": name,
                "running": active,
                "status": "active" if active else "inactive",
                "enabled": enabled,
                "platform": "linux-systemd"
            }

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {"name": name, "running": False, "status": "error", "platform": "linux"}

    # ==========================================
    # macOS Implementation (launchd)
    # ==========================================

    def _install_macos_launchd(self, config: ServiceConfig) -> bool:
        """Install launchd service on macOS"""
        try:
            # Create LaunchAgents directory
            launch_dir = Path.home() / "Library" / "LaunchAgents"
            launch_dir.mkdir(parents=True, exist_ok=True)

            label = f"com.handoff.{config.name}"

            # Build environment dict for plist
            env_dict = "\n".join([
                f"        <key>{k}</key>\n        <string>{v}</string>"
                for k, v in config.environment.items()
            ])

            # Create plist file
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{config.command}</string>
        {"".join([f"<string>{arg}</string>" for arg in config.args])}
    </array>
    <key>WorkingDirectory</key>
    <string>{config.working_dir}</string>
    <key>RunAtLoad</key>
    <{'true' if config.auto_start else 'false'}/>
    <key>KeepAlive</key>
    <{'true' if config.restart_on_failure else 'false'}/>
    <key>EnvironmentVariables</key>
    <dict>
{env_dict}
    </dict>
</dict>
</plist>
"""

            plist_file = launch_dir / f"{label}.plist"
            plist_file.write_text(plist_content)

            # Load the service
            self._run_command(["launchctl", "load", str(plist_file)])

            logger.info(f"Service '{config.name}' installed as launchd agent")
            return True

        except Exception as e:
            logger.error(f"launchd installation failed: {e}")
            return False

    def _uninstall_macos_launchd(self, name: str) -> bool:
        """Uninstall launchd service"""
        try:
            label = f"com.handoff.{name}"
            plist_file = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

            if plist_file.exists():
                self._run_command(["launchctl", "unload", str(plist_file)])
                plist_file.unlink()

            return True

        except Exception as e:
            logger.error(f"launchd uninstall failed: {e}")
            return False

    def _status_macos_launchd(self, name: str) -> Dict[str, Any]:
        """Get launchd service status"""
        try:
            label = f"com.handoff.{name}"
            result = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True,
                text=True
            )

            running = result.returncode == 0
            return {
                "name": name,
                "running": running,
                "status": "running" if running else "not_running",
                "platform": "macos-launchd"
            }

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {"name": name, "running": False, "status": "error", "platform": "macos"}

    # ==========================================
    # Utility Methods
    # ==========================================

    def _run_command(self, cmd: list) -> bool:
        """Run a command and return success status"""
        try:
            logger.debug(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"Command failed: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return False

    def get_default_configs(self) -> list[ServiceConfig]:
        """Get default service configurations for Handoff MCP"""
        python_exe = sys.executable

        return [
            ServiceConfig(
                name="HandoffMCP",
                display_name="Handoff MCP Desktop Automation",
                description="MCP server for desktop automation with Claude Code",
                command=python_exe,
                args=[str(self.python_root / "mcp_server_handoff.py")],
                working_dir=str(self.python_root),
                auto_start=True,
                restart_on_failure=True,
                environment={
                    "PYTHONUNBUFFERED": "1"
                }
            ),
            ServiceConfig(
                name="MoireServer",
                display_name="Moire OCR Server",
                description="WebSocket server for screen capture and OCR",
                command="npm" if self.platform != Platform.WINDOWS else "npm.cmd",
                args=["run", "dev"],
                working_dir=str(self.project_root),
                auto_start=True,
                restart_on_failure=True
            )
        ]


def main():
    """CLI for service management"""
    import argparse
    import json

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Handoff MCP Service Manager")
    parser.add_argument("action", choices=["install", "uninstall", "start", "stop", "restart", "status", "info"])
    parser.add_argument("--service", "-s", default="all", help="Service name (default: all)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    manager = ServiceManager()
    results = {
        "platform": manager.platform.value,
        "project_root": str(manager.project_root),
        "services": [],
        "success": True
    }

    if not args.json:
        print(f"Platform: {manager.platform.value}")
        print(f"Project Root: {manager.project_root}")
        print()

    if args.action == "info":
        configs = manager.get_default_configs()
        results["services"] = [
            {
                "name": c.name,
                "display_name": c.display_name,
                "description": c.description,
                "command": c.command,
                "working_dir": c.working_dir,
                "auto_start": c.auto_start
            }
            for c in configs
        ]

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("Default Services:")
            for config in configs:
                print(f"  - {config.name}: {config.description}")
        return

    services = manager.get_default_configs()
    if args.service != "all":
        services = [s for s in services if s.name == args.service]

    for config in services:
        service_result = {
            "name": config.name,
            "action": args.action,
            "success": False
        }

        if not args.json:
            print(f"\n=== {config.name} ===")

        if args.action == "install":
            success = manager.install_service(config)
            service_result["success"] = success
            if not args.json:
                print(f"Install: {'OK' if success else 'FAILED'}")

        elif args.action == "uninstall":
            success = manager.uninstall_service(config.name)
            service_result["success"] = success
            if not args.json:
                print(f"Uninstall: {'OK' if success else 'FAILED'}")

        elif args.action == "start":
            success = manager.start_service(config.name)
            service_result["success"] = success
            if not args.json:
                print(f"Start: {'OK' if success else 'FAILED'}")

        elif args.action == "stop":
            success = manager.stop_service(config.name)
            service_result["success"] = success
            if not args.json:
                print(f"Stop: {'OK' if success else 'FAILED'}")

        elif args.action == "restart":
            success = manager.restart_service(config.name)
            service_result["success"] = success
            if not args.json:
                print(f"Restart: {'OK' if success else 'FAILED'}")

        elif args.action == "status":
            status = manager.status(config.name)
            service_result["success"] = True
            service_result["status"] = status
            if not args.json:
                print(f"Status: {status}")

        results["services"].append(service_result)

        if not service_result["success"] and args.action != "status":
            results["success"] = False

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
