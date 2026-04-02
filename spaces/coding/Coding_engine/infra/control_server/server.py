"""
FastAPI Control Server for Coding Engine Container.
Provides REST API and WebSocket streaming for engine control.
"""

import asyncio
import json
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    StartRequest, StopRequest, EngineState, StatusResponse,
    HealthResponse, EventType, WebSocketEvent, EngineStatus,
    ProjectType, LogEntry, LogsResponse,
    GitConfig, GitResult, GitStatusResponse,
    CLICallRecord, CLIStatsResponse, CLIHistoryResponse
)
from git_service import GitService

# ============ Configuration ===========

DATA_DIR = Path("/data")
REQUIREMENTS_DIR = DATA_DIR / "requirements"
OUTPUT_DIR = DATA_DIR / "output"
ENGINE_DIR = Path("/app/src")

VNC_PORT = 6080
PREVIEW_BASE_URL = "http://localhost"

# Import preview service
try:
    from preview_service import create_preview_router, get_preview_service
    PREVIEW_SERVICE_AVAILABLE = True
except ImportError:
    PREVIEW_SERVICE_AVAILABLE = False

# ============ Application Setup ============

app = FastAPI(
    title="Coding Engine Control Server",
    description="Control API for autonomous code generation engine",
    version="1.0.0"
)

# CORS for Widget-Embedding
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Preview Service Router
if PREVIEW_SERVICE_AVAILABLE:
    app.include_router(create_preview_router(), prefix="/api/preview")

# ============ Global State ============

engine_state = EngineState()
active_websockets: list[WebSocket] = []
log_history: list[LogEntry] = []
engine_process: Optional[subprocess.Popen] = None
git_service = GitService()  # Initialize Git service
current_git_config: Optional[GitConfig] = None

# CLI Monitoring state
cli_call_history: list[CLICallRecord] = []
CLI_HISTORY_MAX_SIZE = 500

# ============ Helper Functions ============

def add_log(level: str, source: str, message: str, data: dict = None):
    """Add log entry and broadcast to websockets."""
    entry = LogEntry(
        timestamp=datetime.now(),
        level=level,
        source=source,
        message=message,
        data=data
    )
    log_history.append(entry)
    # Keep last 1000 entries
    if len(log_history) > 1000:
        log_history.pop(0)


async def broadcast_event(event: WebSocketEvent):
    """Send event to all connected websockets."""
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(event.model_dump(mode='json'))
        except Exception:
            disconnected.append(ws)
    
    for ws in disconnected:
        active_websockets.remove(ws)


def detect_project_type(output_path: Path) -> ProjectType:
    """Detect what type of project was generated."""
    if not output_path.exists():
        return ProjectType.UNKNOWN
    
    # Check for package.json
    pkg_json = output_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            all_deps = {**deps, **dev_deps}
            
            if "electron" in all_deps:
                return ProjectType.ELECTRON
            if "@tauri-apps/cli" in all_deps or "tauri" in all_deps:
                return ProjectType.TAURI
            if "react" in all_deps or "vue" in all_deps or "svelte" in all_deps:
                return ProjectType.WEBAPP
            return ProjectType.NODEJS
        except:
            return ProjectType.NODEJS
    
    # Check for Python
    if (output_path / "requirements.txt").exists() or (output_path / "setup.py").exists():
        # Check for web frameworks
        try:
            req_txt = (output_path / "requirements.txt").read_text()
            if any(fw in req_txt.lower() for fw in ["flask", "django", "fastapi", "streamlit"]):
                return ProjectType.PYTHON_WEB
        except:
            pass
        return ProjectType.PYTHON_CLI
    
    # Check for Rust
    if (output_path / "Cargo.toml").exists():
        return ProjectType.RUST_CLI
    
    # Check for Go
    if (output_path / "go.mod").exists():
        return ProjectType.GO_CLI
    
    # Check for plain HTML
    if (output_path / "index.html").exists():
        return ProjectType.WEBAPP
    
    return ProjectType.UNKNOWN


def get_cli_error_hint(error_type: str) -> str:
    """Get a helpful hint message for CLI errors."""
    hints = {
        "AUTH": "Claude CLI not authenticated. Run 'claude login' on your host system or set ANTHROPIC_API_KEY environment variable.",
        "NOT_INSTALLED": "Claude CLI not installed in container. Check Dockerfile npm installation.",
        "RATE_LIMIT": "API rate limit exceeded. Wait a few minutes before trying again.",
        "SILENT_FAILURE": "CLI returned error without details. This usually means missing authentication - set ANTHROPIC_API_KEY.",
        "UNKNOWN": "Unknown CLI error. Check container logs for details."
    }
    return hints.get(error_type, hints["UNKNOWN"])


async def run_engine(request: StartRequest):
    """Run the coding engine in background."""
    global engine_process, engine_state, current_git_config
    
    try:
        engine_state.status = EngineStatus.STARTING
        engine_state.started_at = datetime.now()
        
        # Store git config for completion
        current_git_config = request.git_config
        
        await broadcast_event(WebSocketEvent(
            type=EventType.ENGINE_STARTED,
            message="Engine starting...",
            data={"requirements": request.requirements_file or "inline", "run_mode": request.run_mode}
        ))
        
        add_log("INFO", "engine", "Starting engine", {
            "requirements_file": request.requirements_file,
            "git_enabled": request.git_config is not None,
            "run_mode": request.run_mode,
            "slice_size": request.slice_size
        })
        
        # Prepare command - use run_mode to select the correct script
        if request.run_mode == "society_hybrid":
            cmd = ["python", "/app/run_society_hybrid.py"]
        else:
            cmd = ["python", "/app/run_hybrid.py"]
        
        if request.requirements_file:
            req_path = REQUIREMENTS_DIR / request.requirements_file
            cmd.append(str(req_path))
        elif request.requirements_json:
            # Write inline requirements to temp file
            temp_req = DATA_DIR / "temp_requirements.json"
            temp_req.write_text(json.dumps(request.requirements_json))
            cmd.append(str(temp_req))
        
        if request.output_dir:
            out_path = OUTPUT_DIR / request.output_dir
            cmd.extend(["--output-dir", str(out_path)])
            engine_state.output_dir = request.output_dir
        
        # Add slice-size parameter
        cmd.extend(["--slice-size", str(request.slice_size)])
        
        # No timeout option for run_hybrid.py - it runs until complete
        
        add_log("INFO", "engine", f"Running command: {' '.join(cmd)}")
        
        # Start engine process from /app directory
        engine_process = subprocess.Popen(
            cmd,
            cwd="/app",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        engine_state.status = EngineStatus.RUNNING
        engine_state.engine_running = True
        engine_state.engine_pid = engine_process.pid
        
        await broadcast_event(WebSocketEvent(
            type=EventType.ENGINE_STARTED,
            message=f"Engine running with PID {engine_process.pid}",
            data={"pid": engine_process.pid}
        ))
        
        # Stream output
        iteration = 0
        for line in engine_process.stdout:
            line = line.strip()
            if not line:
                continue
            
            add_log("INFO", "engine", line)
            
            # Parse engine output for events
            if "iteration" in line.lower():
                iteration += 1
                engine_state.iterations = iteration
                await broadcast_event(WebSocketEvent(
                    type=EventType.ITERATION_COMPLETE,
                    message=f"Iteration {iteration} complete",
                    data={"iteration": iteration}
                ))
            
            elif "file generated" in line.lower() or "created" in line.lower():
                engine_state.files_generated += 1
                await broadcast_event(WebSocketEvent(
                    type=EventType.FILE_GENERATED,
                    message=line,
                    data={"total_files": engine_state.files_generated}
                ))
            
            elif "test" in line.lower():
                if "passed" in line.lower():
                    engine_state.tests_passed += 1
                elif "failed" in line.lower():
                    engine_state.tests_failed += 1
                await broadcast_event(WebSocketEvent(
                    type=EventType.TEST_RESULT,
                    message=line,
                    data={
                        "passed": engine_state.tests_passed,
                        "failed": engine_state.tests_failed
                    }
                ))
            
            elif "confidence" in line.lower():
                try:
                    # Extract confidence score
                    import re
                    match = re.search(r'(\d+\.?\d*)%?', line)
                    if match:
                        score = float(match.group(1))
                        if score > 1:
                            score = score / 100
                        engine_state.confidence_score = score
                except:
                    pass
            
            # CLI Error detection - check for various error patterns
            elif "[CLI_ERROR]" in line or "cli_error" in line.lower():
                engine_state.cli_errors += 1
                error_type = "UNKNOWN"
                if "CLI_AUTH_ERROR" in line:
                    error_type = "AUTH"
                elif "CLI_NOT_INSTALLED" in line:
                    error_type = "NOT_INSTALLED"
                elif "CLI_RATE_LIMIT" in line:
                    error_type = "RATE_LIMIT"
                elif "CLI_SILENT_FAILURE" in line:
                    error_type = "SILENT_FAILURE"
                
                await broadcast_event(WebSocketEvent(
                    type=EventType.CLI_ERROR,
                    message=line,
                    data={
                        "error_type": error_type,
                        "total_cli_errors": engine_state.cli_errors,
                        "hint": get_cli_error_hint(error_type)
                    }
                ))
                add_log("ERROR", "cli", line)
            
            # Also catch structlog cli_error events
            elif "error" in line.lower() and ("exit_code" in line.lower() or "stderr" in line.lower()):
                engine_state.cli_errors += 1
                await broadcast_event(WebSocketEvent(
                    type=EventType.CLI_ERROR,
                    message=f"CLI Error detected: {line}",
                    data={
                        "total_cli_errors": engine_state.cli_errors
                    }
                ))
                add_log("ERROR", "cli", line)
        
        # Wait for completion
        return_code = engine_process.wait()
        
        engine_state.status = EngineStatus.STOPPED
        engine_state.engine_running = False
        engine_state.stopped_at = datetime.now()
        
        # Detect project type
        if engine_state.output_dir:
            out_path = OUTPUT_DIR / engine_state.output_dir
            engine_state.project_type = detect_project_type(out_path)
            
            # Git push on completion if configured
            if current_git_config and current_git_config.push_on_complete:
                await handle_git_push_on_complete(out_path, current_git_config)
        
        await broadcast_event(WebSocketEvent(
            type=EventType.ENGINE_STOPPED,
            message=f"Engine completed with code {return_code}",
            data={
                "return_code": return_code,
                "iterations": engine_state.iterations,
                "files_generated": engine_state.files_generated,
                "project_type": engine_state.project_type.value if engine_state.project_type else None,
                "git_pushed": engine_state.git_pushed,
                "git_repo_url": engine_state.git_repo_url
            }
        ))
        
        add_log("INFO", "engine", f"Engine completed with code {return_code}")
        
    except Exception as e:
        engine_state.status = EngineStatus.ERROR
        engine_state.engine_running = False
        engine_state.last_error = str(e)
        
        await broadcast_event(WebSocketEvent(
            type=EventType.ENGINE_ERROR,
            message=f"Engine error: {str(e)}",
            data={"error": str(e)}
        ))
        
        add_log("ERROR", "engine", f"Engine error: {str(e)}")


async def handle_git_push_on_complete(output_path: Path, git_config: GitConfig):
    """Handle git operations when engine completes."""
    global engine_state
    
    try:
        await broadcast_event(WebSocketEvent(
            type=EventType.GIT_PUSH_STARTED,
            message="Starting Git operations...",
            data={"repo_name": git_config.repo_name or output_path.name}
        ))
        
        result = await git_service.init_and_push(str(output_path), git_config)
        
        if result.success:
            engine_state.git_pushed = True
            engine_state.git_repo_url = result.repo_url
            
            await broadcast_event(WebSocketEvent(
                type=EventType.GIT_PUSH_COMPLETE,
                message="Code pushed to GitHub!",
                data={
                    "repo_url": result.repo_url,
                    "clone_url": result.clone_url
                }
            ))
            add_log("INFO", "git", f"Pushed to {result.repo_url}")
        else:
            await broadcast_event(WebSocketEvent(
                type=EventType.GIT_ERROR,
                message=f"Git error: {result.error}",
                data={"error": result.error}
            ))
            add_log("ERROR", "git", f"Git error: {result.error}")
            
    except Exception as e:
        await broadcast_event(WebSocketEvent(
            type=EventType.GIT_ERROR,
            message=f"Git exception: {str(e)}",
            data={"error": str(e)}
        ))
        add_log("ERROR", "git", f"Git exception: {str(e)}")


# ============ REST API Endpoints ============

@app.get("/")
async def root():
    """Root endpoint."""
    endpoints = {
        "status": "/api/status",
        "health": "/api/health",
        "start": "/api/start",
        "stop": "/api/stop",
        "logs": "/api/logs",
        "git_status": "/api/git/status",
        "git_push": "/api/git/push",
        "websocket": "/ws"
    }
    
    # Add preview endpoints if available
    if PREVIEW_SERVICE_AVAILABLE:
        endpoints["preview"] = "/api/preview/"
        endpoints["preview_create"] = "/api/preview/create"
        endpoints["preview_health"] = "/api/preview/{project_id}/health"
    
    return {
        "name": "Coding Engine Control Server",
        "version": "1.0.0",
        "status": engine_state.status.value,
        "preview_service": PREVIEW_SERVICE_AVAILABLE,
        "endpoints": endpoints
    }


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    services = {
        "api": True,
        "engine": engine_state.engine_running,
        "vnc": os.path.exists("/tmp/.X11-unix/X99"),
        "novnc": True,  # Assume running via supervisord
        "git": git_service.is_configured
    }
    
    return HealthResponse(
        healthy=all([services["api"], services["vnc"]]),
        services=services,
        timestamp=datetime.now()
    )


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get current engine status."""
    uptime = 0
    if engine_state.started_at:
        end_time = engine_state.stopped_at or datetime.now()
        uptime = (end_time - engine_state.started_at).total_seconds()
    
    return StatusResponse(
        state=engine_state,
        uptime_seconds=uptime,
        vnc_url=f"/vnc/vnc.html",
        preview_url=None,  # Dynamic based on project type
        git_configured=git_service.is_configured
    )


@app.post("/api/start")
async def start_engine(request: StartRequest, background_tasks: BackgroundTasks):
    """Start the coding engine."""
    if engine_state.engine_running:
        raise HTTPException(status_code=409, detail="Engine already running")
    
    # Validate requirements
    if request.requirements_file:
        req_path = REQUIREMENTS_DIR / request.requirements_file
        if not req_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Requirements file not found: {request.requirements_file}"
            )
    elif not request.requirements_json:
        raise HTTPException(
            status_code=400,
            detail="Either requirements_file or requirements_json required"
        )
    
    # Check git config
    if request.git_config and request.git_config.create_repo:
        if not git_service.is_configured:
            raise HTTPException(
                status_code=400,
                detail="Git enabled but GITHUB_TOKEN not configured"
            )
    
    # Reset state
    engine_state.status = EngineStatus.IDLE
    engine_state.iterations = 0
    engine_state.files_generated = 0
    engine_state.tests_passed = 0
    engine_state.tests_failed = 0
    engine_state.cli_errors = 0  # Reset CLI error counter
    engine_state.build_success = None
    engine_state.confidence_score = 0.0
    engine_state.last_error = None
    engine_state.git_pushed = False
    engine_state.git_repo_url = None
    
    # Start engine in background
    background_tasks.add_task(run_engine, request)
    
    return {
        "status": "starting",
        "message": "Engine starting in background",
        "git_enabled": request.git_config is not None
    }


@app.post("/api/stop")
async def stop_engine(request: StopRequest):
    """Stop the coding engine."""
    global engine_process
    
    if not engine_state.engine_running:
        raise HTTPException(status_code=409, detail="Engine not running")
    
    try:
        if engine_process:
            if request.graceful:
                engine_process.send_signal(signal.SIGINT)
                try:
                    engine_process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    engine_process.kill()
            else:
                engine_process.kill()
        
        engine_state.status = EngineStatus.STOPPED
        engine_state.engine_running = False
        engine_state.stopped_at = datetime.now()
        
        await broadcast_event(WebSocketEvent(
            type=EventType.ENGINE_STOPPED,
            message="Engine stopped by user"
        ))
        
        add_log("INFO", "api", "Engine stopped by user request")
        
        return {
            "status": "stopped",
            "graceful": request.graceful
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs", response_model=LogsResponse)
async def get_logs(offset: int = 0, limit: int = 100):
    """Get engine logs."""
    total = len(log_history)
    logs = log_history[offset:offset + limit]
    
    return LogsResponse(
        logs=logs,
        total=total,
        offset=offset,
        limit=limit
    )


# ============ Git API Endpoints ============

@app.get("/api/git/status", response_model=GitStatusResponse)
async def git_status():
    """Check Git/GitHub configuration status."""
    if git_service.is_configured:
        username = await git_service.get_username()
        return GitStatusResponse(
            configured=True,
            username=username,
            message=f"GitHub configured for user: {username}" if username else "GitHub configured"
        )
    else:
        return GitStatusResponse(
            configured=False,
            username=None,
            message="GITHUB_TOKEN not set. Set environment variable to enable Git integration."
        )


@app.post("/api/git/create", response_model=GitResult)
async def git_create_repo(config: GitConfig):
    """Create a new GitHub repository."""
    if not git_service.is_configured:
        raise HTTPException(
            status_code=400,
            detail="GITHUB_TOKEN not configured"
        )
    
    result = await git_service.create_repo(config)
    
    if result.success:
        await broadcast_event(WebSocketEvent(
            type=EventType.GIT_REPO_CREATED,
            message=f"Repository created: {result.repo_url}",
            data={"repo_url": result.repo_url, "clone_url": result.clone_url}
        ))
        add_log("INFO", "git", f"Created repo: {result.repo_url}")
    else:
        add_log("ERROR", "git", f"Failed to create repo: {result.error}")
    
    return result


@app.post("/api/git/push", response_model=GitResult)
async def git_push(config: GitConfig, output_dir: Optional[str] = None):
    """Push code to GitHub repository."""
    if not git_service.is_configured:
        raise HTTPException(
            status_code=400,
            detail="GITHUB_TOKEN not configured"
        )
    
    # Use provided output_dir or current from state
    dir_name = output_dir or engine_state.output_dir
    if not dir_name:
        raise HTTPException(
            status_code=400,
            detail="No output directory specified or available from engine state"
        )
    
    output_path = OUTPUT_DIR / dir_name
    if not output_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Output directory not found: {dir_name}"
        )
    
    await broadcast_event(WebSocketEvent(
        type=EventType.GIT_PUSH_STARTED,
        message="Starting Git push...",
        data={"directory": dir_name}
    ))
    
    result = await git_service.init_and_push(str(output_path), config)
    
    if result.success:
        engine_state.git_pushed = True
        engine_state.git_repo_url = result.repo_url
        
        await broadcast_event(WebSocketEvent(
            type=EventType.GIT_PUSH_COMPLETE,
            message="Code pushed successfully!",
            data={"repo_url": result.repo_url, "clone_url": result.clone_url}
        ))
        add_log("INFO", "git", f"Pushed to {result.repo_url}")
    else:
        await broadcast_event(WebSocketEvent(
            type=EventType.GIT_ERROR,
            message=f"Push failed: {result.error}",
            data={"error": result.error}
        ))
        add_log("ERROR", "git", f"Push failed: {result.error}")
    
    return result


# ============ CLI Monitoring API Endpoints ============

@app.get("/api/cli/stats", response_model=CLIStatsResponse)
async def get_cli_stats():
    """Get aggregated CLI statistics."""
    if not cli_call_history:
        return CLIStatsResponse()
    
    total_calls = len(cli_call_history)
    successful_calls = sum(1 for c in cli_call_history if c.success)
    failed_calls = total_calls - successful_calls
    
    total_tokens_in = sum(c.tokens_in for c in cli_call_history)
    total_tokens_out = sum(c.tokens_out for c in cli_call_history)
    
    latencies = [c.latency_ms for c in cli_call_history if c.latency_ms > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0
    
    success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0.0
    
    # Calculate calls per minute
    if len(cli_call_history) >= 2:
        first_call = cli_call_history[0].timestamp
        last_call = cli_call_history[-1].timestamp
        duration_minutes = (last_call - first_call).total_seconds() / 60
        calls_per_minute = total_calls / duration_minutes if duration_minutes > 0 else 0.0
    else:
        calls_per_minute = 0.0
    
    # Per-agent breakdown
    calls_by_agent = {}
    tokens_by_agent = {}
    for call in cli_call_history:
        agent = call.agent
        calls_by_agent[agent] = calls_by_agent.get(agent, 0) + 1
        tokens_by_agent[agent] = tokens_by_agent.get(agent, 0) + call.tokens_in + call.tokens_out
    
    return CLIStatsResponse(
        total_calls=total_calls,
        successful_calls=successful_calls,
        failed_calls=failed_calls,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        avg_latency_ms=avg_latency,
        max_latency_ms=max_latency,
        success_rate=success_rate,
        calls_per_minute=calls_per_minute,
        calls_by_agent=calls_by_agent,
        tokens_by_agent=tokens_by_agent
    )


@app.get("/api/cli/history", response_model=CLIHistoryResponse)
async def get_cli_history(offset: int = 0, limit: int = 50, agent: Optional[str] = None):
    """Get CLI call history."""
    # Filter by agent if specified
    calls = cli_call_history
    if agent:
        calls = [c for c in calls if c.agent == agent]
    
    total = len(calls)
    
    # Reverse to get most recent first
    calls = list(reversed(calls))
    
    # Apply pagination
    paginated = calls[offset:offset + limit]
    
    # Get current stats
    stats = await get_cli_stats()
    
    return CLIHistoryResponse(
        calls=paginated,
        total=total,
        offset=offset,
        limit=limit,
        stats=stats
    )


@app.post("/api/cli/record")
async def record_cli_call(call: CLICallRecord):
    """Record a CLI call (called by engine internals)."""
    global cli_call_history
    
    cli_call_history.append(call)
    
    # Keep history bounded
    if len(cli_call_history) > CLI_HISTORY_MAX_SIZE:
        cli_call_history = cli_call_history[-CLI_HISTORY_MAX_SIZE:]
    
    # Broadcast event via WebSocket
    event_type = EventType.CLI_RESPONSE_RECEIVED if call.success else EventType.CLI_ERROR
    await broadcast_event(WebSocketEvent(
        type=event_type,
        message=f"CLI call from {call.agent}: {'success' if call.success else 'failed'}",
        data={
            "call_id": call.id,
            "agent": call.agent,
            "tokens_in": call.tokens_in,
            "tokens_out": call.tokens_out,
            "latency_ms": call.latency_ms,
            "success": call.success,
            "error": call.error
        }
    ))
    
    add_log(
        "INFO" if call.success else "ERROR",
        f"cli:{call.agent}",
        f"CLI call: {call.tokens_in}+{call.tokens_out} tokens, {call.latency_ms}ms"
    )
    
    return {"status": "recorded", "call_id": call.id}


@app.delete("/api/cli/history")
async def clear_cli_history():
    """Clear CLI call history."""
    global cli_call_history
    cli_call_history = []
    
    add_log("INFO", "api", "CLI history cleared")
    
    return {"status": "cleared"}


# ============ WebSocket Endpoint ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    active_websockets.append(websocket)
    
    add_log("INFO", "ws", "Client connected")
    
    # Send current state
    await websocket.send_json({
        "type": "connected",
        "state": engine_state.model_dump(mode='json'),
        "git_configured": git_service.is_configured
    })
    
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
            
            # Handle commands via websocket
            try:
                msg = json.loads(data)
                if msg.get("command") == "status":
                    await websocket.send_json({
                        "type": "status",
                        "state": engine_state.model_dump(mode='json'),
                        "git_configured": git_service.is_configured
                    })
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
        add_log("INFO", "ws", "Client disconnected")


# ============ Static Files ============

# Serve noVNC files
if os.path.exists("/usr/share/novnc"):
    app.mount("/vnc", StaticFiles(directory="/usr/share/novnc"), name="novnc")

# Serve widget files - mounted at /app/widget in container
WIDGET_DIR = Path("/app/widget")
if WIDGET_DIR.exists():
    app.mount("/widget", StaticFiles(directory=str(WIDGET_DIR), html=True), name="widget")
else:
    # Fallback for local development
    LOCAL_WIDGET_DIR = Path(__file__).parent.parent / "widget"
    if LOCAL_WIDGET_DIR.exists():
        app.mount("/widget", StaticFiles(directory=str(LOCAL_WIDGET_DIR), html=True), name="widget")


# ============ Startup/Shutdown ============

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    add_log("INFO", "server", "Control server starting")
    
    # Ensure directories exist
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check git configuration
    if git_service.is_configured:
        add_log("INFO", "git", "GITHUB_TOKEN configured - Git integration enabled")
    else:
        add_log("INFO", "git", "GITHUB_TOKEN not set - Git integration disabled")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global engine_process
    
    if engine_process and engine_state.engine_running:
        engine_process.kill()
        engine_process = None
    
    # Shutdown preview service
    if PREVIEW_SERVICE_AVAILABLE:
        preview_service = get_preview_service()
        await preview_service.shutdown()
    
    add_log("INFO", "server", "Control server shutting down")


# ============ Main ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)