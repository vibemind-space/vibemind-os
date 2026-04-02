"""Shell Service for TRAE Backend

Provides shell command execution, session management, and security features.
"""

import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

from ..logger_config import get_logger

logger = get_logger("shell_service")


class ShellService:
    """Service for managing shell operations and sessions"""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.max_sessions = 10
        self.session_timeout = 3600  # 1 hour
        self.max_command_length = 10000
        self.max_output_length = 100000

        # Security patterns for dangerous commands
        self.dangerous_commands = {
            "powershell": [
                r"Remove-Item.*-Recurse.*-Force",
                r"Format-Volume",
                r"Clear-Disk",
                r"Remove-Computer",
                r"Stop-Computer",
                r"Restart-Computer",
                r"Disable-ComputerRestore",
                r"Get-Credential",
                r"ConvertTo-SecureString",
                r"Invoke-Expression.*\$",
                r"iex.*\$",
                r"Start-Process.*-Verb.*RunAs",
            ],
            "cmd": [
                r"del.*\/s.*\/q",
                r"rmdir.*\/s.*\/q",
                r"format.*\/q",
                r"diskpart",
                r"shutdown",
                r"restart",
                r"net user.*\/add",
                r"net localgroup.*administrators.*\/add",
                r"reg delete.*\/f",
                r"schtasks.*\/create",
            ],
            "bash": [
                r"rm.*-rf.*\/",
                r"sudo.*rm.*-rf",
                r"dd.*if=.*of=\/dev",
                r"mkfs\.",
                r"fdisk",
                r"parted",
                r"shutdown",
                r"reboot",
                r"halt",
                r"init.*0",
                r"kill.*-9.*1",
            ],
        }

        logger.info("Shell service initialized")

    def check_command_security(
        self, command: str, shell_type: str, force: bool = False
    ) -> Tuple[bool, str]:
        """Check if command is potentially dangerous"""
        if force:
            logger.warning(f"Forced execution enabled for command: {command[:50]}...")
            return True, "Forced execution enabled"

        dangerous_patterns = self.dangerous_commands.get(shell_type, [])

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning(
                    f"Dangerous command detected: {command[:50]}... (pattern: {pattern})"
                )
                return False, f"Potentially dangerous command detected: {pattern}"

        return True, "Command appears safe"

    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        current_time = datetime.now()
        expired_sessions = []

        for session_id, session_data in self.active_sessions.items():
            if current_time - session_data["last_activity"] > timedelta(
                seconds=session_data["timeout"]
            ):
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            logger.info(f"Cleaning up expired session: {session_id}")
            self.active_sessions.pop(session_id, None)

        return len(expired_sessions)

    def get_shell_command(self, shell_type: str, command: str) -> List[str]:
        """Get shell command array based on shell type"""
        if shell_type == "powershell":
            return ["powershell", "-Command", command]
        elif shell_type == "cmd":
            return ["cmd", "/c", command]
        elif shell_type == "bash":
            # For WSL or Git Bash
            return ["bash", "-c", command]
        else:
            raise ValueError(f"Unsupported shell type: {shell_type}")

    def test_shell_availability(self) -> Dict[str, bool]:
        """Test availability of different shell types"""
        shell_availability = {}

        # Test PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-Command", 'echo "test"'],
                capture_output=True,
                timeout=5,
            )
            shell_availability["powershell"] = result.returncode == 0
        except Exception as e:
            logger.debug(f"PowerShell test failed: {e}")
            shell_availability["powershell"] = False

        # Test CMD
        try:
            result = subprocess.run(
                ["cmd", "/c", "echo test"], capture_output=True, timeout=5
            )
            shell_availability["cmd"] = result.returncode == 0
        except Exception as e:
            logger.debug(f"CMD test failed: {e}")
            shell_availability["cmd"] = False

        # Test Bash (WSL or Git Bash)
        try:
            result = subprocess.run(
                ["bash", "-c", "echo test"], capture_output=True, timeout=5
            )
            shell_availability["bash"] = result.returncode == 0
        except Exception as e:
            logger.debug(f"Bash test failed: {e}")
            shell_availability["bash"] = False

        return shell_availability

    def execute_command(
        self,
        command: str,
        shell_type: str,
        session_id: Optional[str] = None,
        working_directory: Optional[str] = None,
        timeout: int = 30,
        environment: Optional[Dict[str, str]] = None,
        force_execution: bool = False,
    ) -> Dict[str, Any]:
        """Execute shell command with security checks"""

        # Security check
        is_safe, security_msg = self.check_command_security(
            command, shell_type, force_execution
        )
        if not is_safe:
            raise ValueError(f"Security violation: {security_msg}")

        # Prepare environment
        env = os.environ.copy()
        if environment:
            env.update(environment)

        # Get session environment if session exists
        if session_id and session_id in self.active_sessions:
            session_env = self.active_sessions[session_id]["environment"]
            env.update(session_env)

        # Set working directory
        cwd = working_directory
        if session_id and session_id in self.active_sessions:
            cwd = cwd or self.active_sessions[session_id]["working_directory"]
        cwd = cwd or os.getcwd()

        if not os.path.exists(cwd):
            raise ValueError(f"Working directory does not exist: {cwd}")

        logger.info(f"Executing {shell_type} command: {command[:100]}...")

        # Execute command
        start_time = datetime.now()
        try:
            shell_cmd = self.get_shell_command(shell_type, command)
            result = subprocess.run(
                shell_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            execution_time = (datetime.now() - start_time).total_seconds()

            # Truncate output if too long
            stdout = result.stdout[: self.max_output_length] if result.stdout else ""
            stderr = result.stderr[: self.max_output_length] if result.stderr else ""

            # Update session if provided
            if session_id and session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                session["last_activity"] = datetime.now()
                session["command_history"].append(
                    {
                        "command": command,
                        "timestamp": start_time.isoformat(),
                        "exit_code": result.returncode,
                        "execution_time": execution_time,
                        "shell_type": shell_type,
                    }
                )

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "execution_time": execution_time,
                "command": command,
                "shell_type": shell_type,
                "security_check": security_msg,
                "working_directory": cwd,
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"{shell_type} command timed out: {command[:100]}...")
            raise TimeoutError("Command execution timed out")
        except Exception as e:
            logger.error(f"{shell_type} execution error: {e}", exc_info=True)
            raise

    def create_session(
        self,
        shell_type: str,
        name: Optional[str] = None,
        working_directory: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout: int = 3600,
    ) -> Dict[str, Any]:
        """Create new shell session"""

        self.cleanup_expired_sessions()

        if len(self.active_sessions) >= self.max_sessions:
            raise ValueError(f"Maximum sessions ({self.max_sessions}) reached")

        if shell_type not in ["powershell", "cmd", "bash"]:
            raise ValueError("Shell type must be powershell, cmd, or bash")

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Validate working directory
        working_directory = working_directory or os.getcwd()
        if not os.path.exists(working_directory):
            raise ValueError(f"Working directory does not exist: {working_directory}")

        # Create session data
        session_data = {
            "session_id": session_id,
            "name": name or f"Session {session_id[:8]}",
            "shell_type": shell_type,
            "created_at": datetime.now(),
            "last_activity": datetime.now(),
            "working_directory": working_directory,
            "environment": environment or {},
            "timeout": timeout,
            "command_history": [],
        }

        self.active_sessions[session_id] = session_data

        logger.info(f"Created shell session: {session_id} ({shell_type})")

        return {
            "session_id": session_id,
            "name": session_data["name"],
            "shell_type": shell_type,
            "working_directory": working_directory,
            "created_at": session_data["created_at"].isoformat(),
        }

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        self.cleanup_expired_sessions()

        sessions_info = []
        for session_id, session_data in self.active_sessions.items():
            sessions_info.append(
                {
                    "session_id": session_id,
                    "name": session_data.get("name", f"Session {session_id[:8]}"),
                    "shell_type": session_data["shell_type"],
                    "created_at": session_data["created_at"].isoformat(),
                    "last_activity": session_data["last_activity"].isoformat(),
                    "working_directory": session_data["working_directory"],
                    "command_count": len(session_data["command_history"]),
                    "status": "active",
                }
            )

        return sessions_info

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete shell session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")

        session_data = self.active_sessions.pop(session_id)

        logger.info(f"Deleted shell session: {session_id}")

        return {
            "session_id": session_id,
            "name": session_data.get("name"),
            "shell_type": session_data["shell_type"],
            "command_count": len(session_data["command_history"]),
        }

    def get_session_history(self, session_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get command history for session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")

        session_data = self.active_sessions[session_id]
        command_history = session_data["command_history"]

        # Limit results
        if limit > 0:
            command_history = command_history[-limit:]

        return {
            "session_id": session_id,
            "history": command_history,
            "total_commands": len(session_data["command_history"]),
            "returned_commands": len(command_history),
        }

    def get_environment_variables(
        self, session_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get environment variables"""
        if session_id and session_id in self.active_sessions:
            # Get session-specific environment
            session_env = self.active_sessions[session_id]["environment"]
            env_vars = {**os.environ, **session_env}
        else:
            # Get system environment
            env_vars = dict(os.environ)

        # Filter sensitive variables
        sensitive_patterns = ["PASSWORD", "SECRET", "KEY", "TOKEN", "CREDENTIAL"]
        filtered_env = {}

        for key, value in env_vars.items():
            is_sensitive = any(pattern in key.upper() for pattern in sensitive_patterns)
            if is_sensitive:
                filtered_env[key] = "[HIDDEN]"
            else:
                filtered_env[key] = value

        return filtered_env

    def set_environment_variables(
        self, variables: Dict[str, str], session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Set environment variables"""
        if session_id:
            # Set session-specific environment
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session_data = self.active_sessions[session_id]
            session_data["environment"].update(variables)
            session_data["last_activity"] = datetime.now()

            logger.info(
                f"Updated environment for session {session_id}: {list(variables.keys())}"
            )
        else:
            # Set system environment (for current process only)
            os.environ.update(variables)
            logger.info(f"Updated system environment: {list(variables.keys())}")

        return {
            "message": f"Set {len(variables)} environment variables",
            "variables": list(variables.keys()),
            "session_id": session_id,
        }

    def change_directory(
        self, path: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Change working directory"""
        # Validate path
        if not os.path.exists(path):
            raise ValueError(f"Directory does not exist: {path}")

        if not os.path.isdir(path):
            raise ValueError(f"Path is not a directory: {path}")

        # Resolve absolute path
        abs_path = os.path.abspath(path)

        if session_id:
            # Change directory for session
            if session_id not in self.active_sessions:
                raise ValueError(f"Session {session_id} not found")

            session_data = self.active_sessions[session_id]
            old_path = session_data["working_directory"]
            session_data["working_directory"] = abs_path
            session_data["last_activity"] = datetime.now()

            logger.info(
                f"Changed directory for session {session_id}: {old_path} -> {abs_path}"
            )
        else:
            # Change directory for current process
            old_path = os.getcwd()
            os.chdir(abs_path)
            logger.info(f"Changed system directory: {old_path} -> {abs_path}")

        return {"old_path": old_path, "new_path": abs_path, "session_id": session_id}

    def get_processes(self, name_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get running processes"""
        processes = []

        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                proc_info = proc.info

                # Apply name filter if provided
                if name_filter and name_filter.lower() not in proc_info["name"].lower():
                    continue

                processes.append(
                    {
                        "pid": proc_info["pid"],
                        "name": proc_info["name"],
                        "cpu_percent": proc_info["cpu_percent"],
                        "memory_percent": proc_info["memory_percent"],
                        "status": proc_info["status"],
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by CPU usage
        processes.sort(key=lambda x: x["cpu_percent"] or 0, reverse=True)

        return processes

    def manage_process(
        self,
        process_id: Optional[int] = None,
        process_name: Optional[str] = None,
        action: str = "kill",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Manage processes (kill, suspend, resume)"""

        if action not in ["kill", "suspend", "resume"]:
            raise ValueError("Action must be kill, suspend, or resume")

        # Find process
        target_proc = None

        if process_id:
            try:
                target_proc = psutil.Process(process_id)
            except psutil.NoSuchProcess:
                raise ValueError(f"Process with PID {process_id} not found")
        elif process_name:
            # Find by name (first match)
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"].lower() == process_name.lower():
                        target_proc = proc
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if not target_proc:
                raise ValueError(f"Process '{process_name}' not found")
        else:
            raise ValueError("Either process_id or process_name must be provided")

        # Perform action
        result = {"action": action, "pid": target_proc.pid, "name": target_proc.name()}

        try:
            if action == "kill":
                if force:
                    target_proc.kill()  # SIGKILL
                else:
                    target_proc.terminate()  # SIGTERM
                result["message"] = (
                    f"Process {target_proc.pid} {'killed' if force else 'terminated'}"
                )

            elif action == "suspend":
                target_proc.suspend()
                result["message"] = f"Process {target_proc.pid} suspended"

            elif action == "resume":
                target_proc.resume()
                result["message"] = f"Process {target_proc.pid} resumed"

        except psutil.AccessDenied:
            raise PermissionError("Access denied - insufficient privileges")
        except psutil.NoSuchProcess:
            raise ValueError("Process no longer exists")

        logger.info(f"Process action completed: {result['message']}")

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get shell service status"""
        self.cleanup_expired_sessions()

        return {
            "service_healthy": True,
            "active_sessions": len(self.active_sessions),
            "max_sessions": self.max_sessions,
            "shell_availability": self.test_shell_availability(),
            "security_enabled": True,
            "session_timeout": self.session_timeout,
        }


# Global shell service instance
_shell_service = None


def get_shell_service() -> ShellService:
    """Get shell service instance"""
    global _shell_service
    if _shell_service is None:
        _shell_service = ShellService()
    return _shell_service
