"""Shell and PowerShell Router for TRAE Backend

Provides endpoints for shell command execution, session management,
and environment control with security measures.
"""

import asyncio
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from ..logger_config import get_logger, log_api_request
from ..services import get_service_manager

logger = get_logger("shell")

router = APIRouter()

# Security configuration
DANGEROUS_COMMANDS = {
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

MAX_SESSIONS = 10
SESSION_TIMEOUT = 3600  # 1 hour
MAX_COMMAND_LENGTH = 10000
MAX_OUTPUT_LENGTH = 100000

# Global session storage
active_sessions: Dict[str, Dict[str, Any]] = {}


class ShellCommandRequest(BaseModel):
    """Request model for shell command execution"""

    command: str = Field(
        ..., description="Command to execute", max_length=MAX_COMMAND_LENGTH
    )
    session_id: Optional[str] = Field(
        None, description="Session ID for command execution"
    )
    working_directory: Optional[str] = Field(
        None, description="Working directory for command"
    )
    timeout: Optional[int] = Field(
        30, description="Command timeout in seconds", ge=1, le=300
    )
    environment: Optional[Dict[str, str]] = Field(
        None, description="Environment variables"
    )
    force_execution: bool = Field(
        False, description="Force execution of potentially dangerous commands"
    )

    @validator("command")
    def validate_command(cls, v):
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")
        return v.strip()


class SessionCreateRequest(BaseModel):
    """Request model for creating shell sessions"""

    shell_type: str = Field(..., description="Shell type: powershell, cmd, or bash")
    name: Optional[str] = Field(None, description="Session name")
    working_directory: Optional[str] = Field(
        None, description="Initial working directory"
    )
    environment: Optional[Dict[str, str]] = Field(
        None, description="Environment variables"
    )
    timeout: Optional[int] = Field(3600, description="Session timeout in seconds")

    @validator("shell_type")
    def validate_shell_type(cls, v):
        if v not in ["powershell", "cmd", "bash"]:
            raise ValueError("Shell type must be powershell, cmd, or bash")
        return v


class EnvironmentRequest(BaseModel):
    """Request model for environment variable operations"""

    variables: Dict[str, str] = Field(..., description="Environment variables to set")
    session_id: Optional[str] = Field(None, description="Session ID")


class DirectoryChangeRequest(BaseModel):
    """Request model for changing working directory"""

    path: str = Field(..., description="New working directory path")
    session_id: Optional[str] = Field(None, description="Session ID")


class ProcessActionRequest(BaseModel):
    """Request model for process management"""

    process_id: Optional[int] = Field(None, description="Process ID")
    process_name: Optional[str] = Field(None, description="Process name")
    action: str = Field(..., description="Action: kill, suspend, resume")
    force: bool = Field(False, description="Force action")

    @validator("action")
    def validate_action(cls, v):
        if v not in ["kill", "suspend", "resume"]:
            raise ValueError("Action must be kill, suspend, or resume")
        return v


def check_command_security(
    command: str, shell_type: str, force: bool = False
) -> tuple[bool, str]:
    """Check if command is potentially dangerous"""
    if force:
        return True, "Forced execution enabled"

    dangerous_patterns = DANGEROUS_COMMANDS.get(shell_type, [])

    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Potentially dangerous command detected: {pattern}"

    return True, "Command appears safe"


def cleanup_expired_sessions():
    """Clean up expired sessions"""
    current_time = datetime.now()
    expired_sessions = []

    for session_id, session_data in active_sessions.items():
        if current_time - session_data["last_activity"] > timedelta(
            seconds=session_data["timeout"]
        ):
            expired_sessions.append(session_id)

    for session_id in expired_sessions:
        logger.info(f"Cleaning up expired session: {session_id}")
        active_sessions.pop(session_id, None)


def get_shell_command(shell_type: str, command: str) -> List[str]:
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


@router.get("/status")
@log_api_request(logger)
async def get_shell_status(request: Request):
    """Get shell service status"""
    try:
        cleanup_expired_sessions()

        # Test shell availability
        shell_availability = {}

        # Test PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-Command", 'echo "test"'],
                capture_output=True,
                timeout=5,
            )
            shell_availability["powershell"] = result.returncode == 0
        except:
            shell_availability["powershell"] = False

        # Test CMD
        try:
            result = subprocess.run(
                ["cmd", "/c", "echo test"], capture_output=True, timeout=5
            )
            shell_availability["cmd"] = result.returncode == 0
        except:
            shell_availability["cmd"] = False

        # Test Bash (WSL or Git Bash)
        try:
            result = subprocess.run(
                ["bash", "-c", "echo test"], capture_output=True, timeout=5
            )
            shell_availability["bash"] = result.returncode == 0
        except:
            shell_availability["bash"] = False

        return JSONResponse(
            content={
                "success": True,
                "status": {
                    "service_healthy": True,
                    "active_sessions": len(active_sessions),
                    "max_sessions": MAX_SESSIONS,
                    "shell_availability": shell_availability,
                    "security_enabled": True,
                    "session_timeout": SESSION_TIMEOUT,
                },
            }
        )

    except Exception as e:
        logger.error(f"Shell status error: {e}", exc_info=True)
        return JSONResponse(content={"success": False, "error": str(e)})


@router.post("/powershell")
@log_api_request(logger)
async def execute_powershell_command(request: ShellCommandRequest):
    """Execute PowerShell command"""
    try:
        # Security check
        is_safe, security_msg = check_command_security(
            request.command, "powershell", request.force_execution
        )
        if not is_safe:
            raise HTTPException(
                status_code=400, detail=f"Security violation: {security_msg}"
            )

        # Prepare environment
        env = os.environ.copy()
        if request.environment:
            env.update(request.environment)

        # Set working directory
        cwd = request.working_directory or os.getcwd()
        if not os.path.exists(cwd):
            raise HTTPException(
                status_code=400, detail=f"Working directory does not exist: {cwd}"
            )

        logger.info(f"Executing PowerShell command: {request.command[:100]}...")

        # Execute command
        start_time = datetime.now()
        result = subprocess.run(
            ["powershell", "-Command", request.command],
            capture_output=True,
            text=True,
            timeout=request.timeout,
            cwd=cwd,
            env=env,
        )
        execution_time = (datetime.now() - start_time).total_seconds()

        # Truncate output if too long
        stdout = result.stdout[:MAX_OUTPUT_LENGTH] if result.stdout else ""
        stderr = result.stderr[:MAX_OUTPUT_LENGTH] if result.stderr else ""

        # Update session if provided
        if request.session_id and request.session_id in active_sessions:
            session = active_sessions[request.session_id]
            session["last_activity"] = datetime.now()
            session["command_history"].append(
                {
                    "command": request.command,
                    "timestamp": start_time.isoformat(),
                    "exit_code": result.returncode,
                    "execution_time": execution_time,
                }
            )

        return JSONResponse(
            content={
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "execution_time": execution_time,
                "command": request.command,
                "shell_type": "powershell",
                "security_check": security_msg,
            }
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"PowerShell command timed out: {request.command[:100]}...")
        raise HTTPException(status_code=408, detail="Command execution timed out")
    except Exception as e:
        logger.error(f"PowerShell execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cmd")
@log_api_request(logger)
async def execute_cmd_command(request: ShellCommandRequest):
    """Execute CMD command"""
    try:
        # Security check
        is_safe, security_msg = check_command_security(
            request.command, "cmd", request.force_execution
        )
        if not is_safe:
            raise HTTPException(
                status_code=400, detail=f"Security violation: {security_msg}"
            )

        # Prepare environment
        env = os.environ.copy()
        if request.environment:
            env.update(request.environment)

        # Set working directory
        cwd = request.working_directory or os.getcwd()
        if not os.path.exists(cwd):
            raise HTTPException(
                status_code=400, detail=f"Working directory does not exist: {cwd}"
            )

        logger.info(f"Executing CMD command: {request.command[:100]}...")

        # Execute command
        start_time = datetime.now()
        result = subprocess.run(
            ["cmd", "/c", request.command],
            capture_output=True,
            text=True,
            timeout=request.timeout,
            cwd=cwd,
            env=env,
        )
        execution_time = (datetime.now() - start_time).total_seconds()

        # Truncate output if too long
        stdout = result.stdout[:MAX_OUTPUT_LENGTH] if result.stdout else ""
        stderr = result.stderr[:MAX_OUTPUT_LENGTH] if result.stderr else ""

        # Update session if provided
        if request.session_id and request.session_id in active_sessions:
            session = active_sessions[request.session_id]
            session["last_activity"] = datetime.now()
            session["command_history"].append(
                {
                    "command": request.command,
                    "timestamp": start_time.isoformat(),
                    "exit_code": result.returncode,
                    "execution_time": execution_time,
                }
            )

        return JSONResponse(
            content={
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "execution_time": execution_time,
                "command": request.command,
                "shell_type": "cmd",
                "security_check": security_msg,
            }
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"CMD command timed out: {request.command[:100]}...")
        raise HTTPException(status_code=408, detail="Command execution timed out")
    except Exception as e:
        logger.error(f"CMD execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bash")
@log_api_request(logger)
async def execute_bash_command(request: ShellCommandRequest):
    """Execute Bash command (WSL support)"""
    try:
        # Security check
        is_safe, security_msg = check_command_security(
            request.command, "bash", request.force_execution
        )
        if not is_safe:
            raise HTTPException(
                status_code=400, detail=f"Security violation: {security_msg}"
            )

        # Prepare environment
        env = os.environ.copy()
        if request.environment:
            env.update(request.environment)

        # Set working directory
        cwd = request.working_directory or os.getcwd()
        if not os.path.exists(cwd):
            raise HTTPException(
                status_code=400, detail=f"Working directory does not exist: {cwd}"
            )

        logger.info(f"Executing Bash command: {request.command[:100]}...")

        # Execute command
        start_time = datetime.now()
        result = subprocess.run(
            ["bash", "-c", request.command],
            capture_output=True,
            text=True,
            timeout=request.timeout,
            cwd=cwd,
            env=env,
        )
        execution_time = (datetime.now() - start_time).total_seconds()

        # Truncate output if too long
        stdout = result.stdout[:MAX_OUTPUT_LENGTH] if result.stdout else ""
        stderr = result.stderr[:MAX_OUTPUT_LENGTH] if result.stderr else ""

        # Update session if provided
        if request.session_id and request.session_id in active_sessions:
            session = active_sessions[request.session_id]
            session["last_activity"] = datetime.now()
            session["command_history"].append(
                {
                    "command": request.command,
                    "timestamp": start_time.isoformat(),
                    "exit_code": result.returncode,
                    "execution_time": execution_time,
                }
            )

        return JSONResponse(
            content={
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "execution_time": execution_time,
                "command": request.command,
                "shell_type": "bash",
                "security_check": security_msg,
            }
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"Bash command timed out: {request.command[:100]}...")
        raise HTTPException(status_code=408, detail="Command execution timed out")
    except Exception as e:
        logger.error(f"Bash execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
@log_api_request(logger)
async def get_shell_sessions(request: Request):
    """Get all active shell sessions"""
    try:
        cleanup_expired_sessions()

        sessions_info = []
        for session_id, session_data in active_sessions.items():
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

        return JSONResponse(
            content={
                "success": True,
                "sessions": sessions_info,
                "total_sessions": len(sessions_info),
                "max_sessions": MAX_SESSIONS,
            }
        )

    except Exception as e:
        logger.error(f"Get sessions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions")
@log_api_request(logger)
async def create_shell_session(request: SessionCreateRequest):
    """Create new shell session"""
    try:
        cleanup_expired_sessions()

        if len(active_sessions) >= MAX_SESSIONS:
            raise HTTPException(
                status_code=429, detail=f"Maximum sessions ({MAX_SESSIONS}) reached"
            )

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Validate working directory
        working_directory = request.working_directory or os.getcwd()
        if not os.path.exists(working_directory):
            raise HTTPException(
                status_code=400,
                detail=f"Working directory does not exist: {working_directory}",
            )

        # Create session data
        session_data = {
            "session_id": session_id,
            "name": request.name or f"Session {session_id[:8]}",
            "shell_type": request.shell_type,
            "created_at": datetime.now(),
            "last_activity": datetime.now(),
            "working_directory": working_directory,
            "environment": request.environment or {},
            "timeout": request.timeout,
            "command_history": [],
        }

        active_sessions[session_id] = session_data

        logger.info(f"Created shell session: {session_id} ({request.shell_type})")

        return JSONResponse(
            content={
                "success": True,
                "session_id": session_id,
                "name": session_data["name"],
                "shell_type": request.shell_type,
                "working_directory": working_directory,
                "created_at": session_data["created_at"].isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Create session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
@log_api_request(logger)
async def delete_shell_session(session_id: str, request: Request):
    """Delete shell session"""
    try:
        if session_id not in active_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        session_data = active_sessions.pop(session_id)

        logger.info(f"Deleted shell session: {session_id}")

        return JSONResponse(
            content={
                "success": True,
                "message": f"Session {session_id} deleted",
                "session_info": {
                    "session_id": session_id,
                    "name": session_data.get("name"),
                    "shell_type": session_data["shell_type"],
                    "command_count": len(session_data["command_history"]),
                },
            }
        )

    except Exception as e:
        logger.error(f"Delete session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}")
@log_api_request(logger)
async def get_shell_history(session_id: str, request: Request, limit: int = 50):
    """Get shell command history for session"""
    try:
        if session_id not in active_sessions:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        session_data = active_sessions[session_id]
        command_history = session_data["command_history"]

        # Limit results
        if limit > 0:
            command_history = command_history[-limit:]

        return JSONResponse(
            content={
                "success": True,
                "session_id": session_id,
                "history": command_history,
                "total_commands": len(session_data["command_history"]),
                "returned_commands": len(command_history),
            }
        )

    except Exception as e:
        logger.error(f"Get history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/env")
@log_api_request(logger)
async def get_environment_variables(request: Request, session_id: Optional[str] = None):
    """Get environment variables"""
    try:
        if session_id and session_id in active_sessions:
            # Get session-specific environment
            session_env = active_sessions[session_id]["environment"]
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

        return JSONResponse(
            content={
                "success": True,
                "environment": filtered_env,
                "session_id": session_id,
                "variable_count": len(filtered_env),
            }
        )

    except Exception as e:
        logger.error(f"Get environment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/env")
@log_api_request(logger)
async def set_environment_variables(request: EnvironmentRequest):
    """Set environment variables"""
    try:
        if request.session_id:
            # Set session-specific environment
            if request.session_id not in active_sessions:
                raise HTTPException(
                    status_code=404, detail=f"Session {request.session_id} not found"
                )

            session_data = active_sessions[request.session_id]
            session_data["environment"].update(request.variables)
            session_data["last_activity"] = datetime.now()

            logger.info(
                f"Updated environment for session {request.session_id}: {list(request.variables.keys())}"
            )
        else:
            # Set system environment (for current process only)
            os.environ.update(request.variables)
            logger.info(f"Updated system environment: {list(request.variables.keys())}")

        return JSONResponse(
            content={
                "success": True,
                "message": f"Set {len(request.variables)} environment variables",
                "variables": list(request.variables.keys()),
                "session_id": request.session_id,
            }
        )

    except Exception as e:
        logger.error(f"Set environment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cd")
@log_api_request(logger)
async def change_directory(request: DirectoryChangeRequest):
    """Change working directory"""
    try:
        # Validate path
        if not os.path.exists(request.path):
            raise HTTPException(
                status_code=400, detail=f"Directory does not exist: {request.path}"
            )

        if not os.path.isdir(request.path):
            raise HTTPException(
                status_code=400, detail=f"Path is not a directory: {request.path}"
            )

        # Resolve absolute path
        abs_path = os.path.abspath(request.path)

        if request.session_id:
            # Change directory for session
            if request.session_id not in active_sessions:
                raise HTTPException(
                    status_code=404, detail=f"Session {request.session_id} not found"
                )

            session_data = active_sessions[request.session_id]
            old_path = session_data["working_directory"]
            session_data["working_directory"] = abs_path
            session_data["last_activity"] = datetime.now()

            logger.info(
                f"Changed directory for session {request.session_id}: {old_path} -> {abs_path}"
            )
        else:
            # Change directory for current process
            old_path = os.getcwd()
            os.chdir(abs_path)
            logger.info(f"Changed system directory: {old_path} -> {abs_path}")

        return JSONResponse(
            content={
                "success": True,
                "old_path": old_path,
                "new_path": abs_path,
                "session_id": request.session_id,
            }
        )

    except Exception as e:
        logger.error(f"Change directory error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processes")
@log_api_request(logger)
async def get_processes(request: Request, name_filter: Optional[str] = None):
    """Get running processes"""
    try:
        import psutil

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

        return JSONResponse(
            content={
                "success": True,
                "processes": processes,
                "total_processes": len(processes),
                "filter": name_filter,
            }
        )

    except Exception as e:
        logger.error(f"Get processes error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/processes")
@log_api_request(logger)
async def manage_process(request: ProcessActionRequest):
    """Manage processes (kill, suspend, resume)"""
    try:
        import psutil

        # Find process
        target_proc = None

        if request.process_id:
            try:
                target_proc = psutil.Process(request.process_id)
            except psutil.NoSuchProcess:
                raise HTTPException(
                    status_code=404,
                    detail=f"Process with PID {request.process_id} not found",
                )
        elif request.process_name:
            # Find by name (first match)
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"].lower() == request.process_name.lower():
                        target_proc = proc
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if not target_proc:
                raise HTTPException(
                    status_code=404,
                    detail=f"Process '{request.process_name}' not found",
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="Either process_id or process_name must be provided",
            )

        # Perform action
        result = {
            "success": False,
            "action": request.action,
            "pid": target_proc.pid,
            "name": target_proc.name(),
        }

        try:
            if request.action == "kill":
                if request.force:
                    target_proc.kill()  # SIGKILL
                else:
                    target_proc.terminate()  # SIGTERM
                result["success"] = True
                result["message"] = (
                    f"Process {target_proc.pid} {'killed' if request.force else 'terminated'}"
                )

            elif request.action == "suspend":
                target_proc.suspend()
                result["success"] = True
                result["message"] = f"Process {target_proc.pid} suspended"

            elif request.action == "resume":
                target_proc.resume()
                result["success"] = True
                result["message"] = f"Process {target_proc.pid} resumed"

        except psutil.AccessDenied:
            raise HTTPException(
                status_code=403, detail="Access denied - insufficient privileges"
            )
        except psutil.NoSuchProcess:
            raise HTTPException(status_code=404, detail="Process no longer exists")

        logger.info(f"Process action completed: {result['message']}")

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Process management error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/processes/{process_id}")
@log_api_request(logger)
async def kill_process(process_id: int, request: Request, force: bool = False):
    """Kill specific process by PID"""
    try:
        import psutil

        try:
            proc = psutil.Process(process_id)
            proc_name = proc.name()

            if force:
                proc.kill()  # SIGKILL
                action = "killed"
            else:
                proc.terminate()  # SIGTERM
                action = "terminated"

            logger.info(f"Process {process_id} ({proc_name}) {action}")

            return JSONResponse(
                content={
                    "success": True,
                    "message": f"Process {process_id} ({proc_name}) {action}",
                    "pid": process_id,
                    "name": proc_name,
                    "action": action,
                }
            )

        except psutil.NoSuchProcess:
            raise HTTPException(
                status_code=404, detail=f"Process with PID {process_id} not found"
            )
        except psutil.AccessDenied:
            raise HTTPException(
                status_code=403, detail="Access denied - insufficient privileges"
            )

    except Exception as e:
        logger.error(f"Kill process error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
