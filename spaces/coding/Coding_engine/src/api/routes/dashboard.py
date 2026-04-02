"""
FastAPI routes for real-time dashboard endpoints.
Provides timeline, metrics, and process monitoring APIs.
Also provides Docker/project management APIs for web dashboard.
"""

from datetime import datetime
from typing import Any, Optional, List
import asyncio
import json
import subprocess
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.secrets import get_secret
from src.models.dashboard_models import (
    TimelineResponse,
    DashboardMetrics,
    DashboardOverview,
    ProcessListResponse,
    EventFilter,
    PerformanceMetrics,
    HealthStatus,
)
from src.services.dashboard_service import DashboardService
from src.models.base import get_db
from src.mind.shared_state import SharedState
from src.mind.event_bus import EventBus, Event, EventType
from src.mind.event_payloads import BuildFailurePayload, SandboxTestPayload
import structlog


# ============================================================================
# Pydantic models for Docker management
# ============================================================================

class DockerStatusResponse(BaseModel):
    running: bool
    services: List[str] = []

class ProjectStartRequest(BaseModel):
    projectId: str
    outputDir: str
    vncPort: int
    appPort: int

class ProjectStopRequest(BaseModel):
    projectId: str

class GenerateRequest(BaseModel):
    requirementsPath: str
    outputDir: str = ""

class ReviewResumeRequest(BaseModel):
    feedback: Optional[str] = None


class SandboxErrorReport(BaseModel):
    """Error report from Docker sandbox container."""
    project_id: str
    container_name: Optional[str] = None
    error_type: str  # "build_failed", "runtime_error", "test_failed"
    build_output: str  # Full error log
    exit_code: int = 1
    working_dir: Optional[str] = None
    project_type: Optional[str] = None  # "react", "node_fullstack", etc.

class SuccessResponse(BaseModel):
    success: bool
    error: Optional[str] = None

class ProjectStatusResponse(BaseModel):
    running: bool
    vncPort: Optional[int] = None
    appPort: Optional[int] = None
    health: Optional[str] = None

class LogsResponse(BaseModel):
    logs: str


# Project container tracking
_project_containers: dict = {}

# Generation state tracking (keyed by projectId)
# Stores: { phase, progress_pct, completed, failed, total, started_at, error }
_generation_state: dict = {}

# ── Parallel Generation Registry ──
# Tracks all running generation processes: {project_id: {pid, started_at, output_dir, db_schema, ...}}
_active_generations: dict = {}

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def get_dashboard_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    """Dependency to get dashboard service instance."""
    return DashboardService(db)


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types to filter"),
    severity: Optional[str] = Query(None, description="Comma-separated severity levels (info,warning,error,success)"),
    process_id: Optional[int] = Query(None, description="Filter by process ID"),
    port: Optional[int] = Query(None, description="Filter by port number"),
    since: Optional[datetime] = Query(None, description="Events since timestamp (ISO format)"),
    until: Optional[datetime] = Query(None, description="Events until timestamp (ISO format)"),
    service: DashboardService = Depends(get_dashboard_service)
) -> TimelineResponse:
    """
    Get connection events timeline with filtering and pagination.

    Returns the last N connection events with timestamp, event type, and affected resource.
    Supports filtering by event type, severity, process, port, and time range.

    **REQ-ea7004-015**: Displays real-time timeline of last 100 connection events.
    """
    try:
        # Build filter
        event_filter = EventFilter(
            event_types=event_types.split(",") if event_types else None,
            severity=severity.split(",") if severity else None,
            process_id=process_id,
            port=port,
            since=since,
            until=until,
            limit=limit,
            offset=offset
        )

        timeline = await service.get_timeline(
            limit=limit,
            offset=offset,
            event_filter=event_filter
        )

        logger.info(
            "timeline_fetched",
            returned_count=timeline.returned_count,
            total_count=timeline.total_count,
            page=timeline.page
        )

        return timeline

    except Exception as e:
        logger.error("timeline_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch timeline: {str(e)}")


@router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics(
    service: DashboardService = Depends(get_dashboard_service)
) -> DashboardMetrics:
    """
    Get current dashboard metrics including process and connection stats.

    Returns real-time metrics for processes, connections, and recent event activity.
    """
    try:
        metrics = await service.get_dashboard_metrics()

        logger.info(
            "metrics_fetched",
            active_processes=metrics.process_metrics.active_processes,
            active_connections=metrics.connection_metrics.active_connections,
            recent_events=metrics.recent_events_count
        )

        return metrics

    except Exception as e:
        logger.error("metrics_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {str(e)}")


@router.get("/overview", response_model=DashboardOverview)
async def get_overview(
    timeline_limit: int = Query(100, ge=1, le=1000, description="Number of timeline events"),
    event_types: Optional[str] = Query(None, description="Filter timeline by event types"),
    severity: Optional[str] = Query(None, description="Filter timeline by severity"),
    service: DashboardService = Depends(get_dashboard_service)
) -> DashboardOverview:
    """
    Get complete dashboard overview with timeline and metrics.

    Provides a comprehensive view of system state including:
    - Process and connection metrics
    - Recent connection events timeline
    - Performance statistics

    **REQ-ea7004-016**: Loads within 2 seconds for up to 500 active processes.

    Returns:
        DashboardOverview with metrics, timeline, and load time
    """
    try:
        # Build filter if provided
        event_filter = None
        if event_types or severity:
            event_filter = EventFilter(
                event_types=event_types.split(",") if event_types else None,
                severity=severity.split(",") if severity else None,
                limit=timeline_limit
            )

        overview, performance = await service.get_dashboard_overview(
            timeline_limit=timeline_limit,
            timeline_filter=event_filter
        )

        logger.info(
            "overview_fetched",
            load_time_ms=overview.load_time_ms,
            active_processes=performance.active_processes_count,
            meets_sla=performance.meets_sla,
            timeline_events=overview.timeline.returned_count
        )

        # Log warning if SLA not met
        if not performance.meets_sla:
            logger.warning(
                "dashboard_sla_exceeded",
                load_time_ms=overview.load_time_ms,
                active_processes=performance.active_processes_count,
                sla_threshold_ms=2000
            )

        return overview

    except Exception as e:
        logger.error("overview_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch overview: {str(e)}")


@router.get("/processes", response_model=ProcessListResponse)
async def get_processes(
    sort_by: str = Query("cpu", regex="^(cpu|memory|name|pid)$", description="Sort field"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum processes to return"),
    service: DashboardService = Depends(get_dashboard_service)
) -> ProcessListResponse:
    """
    Get list of active processes with detailed information.

    Returns process details including CPU/memory usage, ports, and thread count.
    Optimized for fast retrieval with up to 500 active processes.
    """
    try:
        process_list = await service.get_process_list(
            sort_by=sort_by,
            limit=limit
        )

        logger.info(
            "process_list_fetched",
            total_count=process_list.total_count,
            returned_count=len(process_list.processes),
            load_time_ms=process_list.load_time_ms
        )

        return process_list

    except Exception as e:
        logger.error("process_list_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch process list: {str(e)}")


@router.get("/health", response_model=HealthStatus)
async def get_health(
    service: DashboardService = Depends(get_dashboard_service)
) -> HealthStatus:
    """
    Get dashboard health status.

    Returns overall system health, WebSocket status, and event processing metrics.
    """
    try:
        # Get recent events to check activity
        recent_events = await service.get_recent_events_count(minutes=5)

        # Get latest event timestamp
        timeline = await service.get_timeline(limit=1)
        last_event_timestamp = timeline.events[0].timestamp if timeline.events else None

        # Calculate event processing lag
        event_lag_ms = 0.0
        if last_event_timestamp:
            lag = datetime.utcnow() - last_event_timestamp
            event_lag_ms = lag.total_seconds() * 1000

        # Determine health status
        status = "healthy"
        if event_lag_ms > 5000:  # More than 5 seconds lag
            status = "degraded"
        if recent_events == 0:  # No events in last 5 minutes
            status = "degraded"

        health = HealthStatus(
            status=status,
            websocket_connected=True,  # Will be updated by WebSocket handler
            active_connections=0,  # Will be updated by WebSocket handler
            last_event_timestamp=last_event_timestamp,
            event_processing_lag_ms=event_lag_ms,
            metrics_update_interval_ms=1000.0
        )

        logger.info(
            "health_check",
            status=status,
            recent_events=recent_events,
            event_lag_ms=event_lag_ms
        )

        return health

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return HealthStatus(
            status="unhealthy",
            websocket_connected=False,
            active_connections=0,
            event_processing_lag_ms=0.0
        )


# ============================================================================
# Docker Management Routes (for web dashboard)
# ============================================================================

async def run_command(cmd: str, cwd: str = None) -> tuple[str, str, int]:
    """Run a command asynchronously and return stdout, stderr, returncode."""
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    stdout, stderr = await process.communicate()
    return (
        stdout.decode('utf-8', errors='replace'),
        stderr.decode('utf-8', errors='replace'),
        process.returncode
    )


@router.get("/docker/status", response_model=DockerStatusResponse)
async def get_docker_status() -> DockerStatusResponse:
    """
    Get Docker engine status - check if relevant containers are running.
    """
    try:
        stdout, stderr, rc = await run_command('docker ps --format "{{.Names}}"')
        if rc != 0:
            return DockerStatusResponse(running=False, services=[])

        services = [
            name.strip() for name in stdout.strip().split('\n')
            if name.strip() and any(x in name for x in ['coding-engine', 'postgres', 'redis'])
        ]

        return DockerStatusResponse(running=len(services) > 0, services=services)
    except Exception as e:
        logger.error("docker_status_check_failed", error=str(e))
        return DockerStatusResponse(running=False, services=[])


@router.post("/docker/start", response_model=SuccessResponse)
async def start_docker_engine() -> SuccessResponse:
    """
    Start the Coding Engine Docker stack.
    """
    try:
        engine_root = Path(__file__).parent.parent.parent.parent
        compose_file = engine_root / "infra" / "docker" / "docker-compose.dashboard.yml"

        if not compose_file.exists():
            return SuccessResponse(success=False, error=f"Compose file not found: {compose_file}")

        stdout, stderr, rc = await run_command(
            f'docker-compose -f "{compose_file}" up -d',
            cwd=str(engine_root)
        )

        if rc != 0:
            return SuccessResponse(success=False, error=stderr or stdout)

        logger.info("docker_engine_started")
        return SuccessResponse(success=True)
    except Exception as e:
        logger.error("docker_start_failed", error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.post("/docker/stop", response_model=SuccessResponse)
async def stop_docker_engine() -> SuccessResponse:
    """
    Stop the Coding Engine Docker stack.
    """
    try:
        engine_root = Path(__file__).parent.parent.parent.parent
        compose_file = engine_root / "infra" / "docker" / "docker-compose.dashboard.yml"

        stdout, stderr, rc = await run_command(
            f'docker-compose -f "{compose_file}" down',
            cwd=str(engine_root)
        )

        if rc != 0:
            return SuccessResponse(success=False, error=stderr or stdout)

        logger.info("docker_engine_stopped")
        return SuccessResponse(success=True)
    except Exception as e:
        logger.error("docker_stop_failed", error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.post("/project/start", response_model=SuccessResponse)
async def start_project_container(request: ProjectStartRequest) -> SuccessResponse:
    """
    Start the sandbox container via docker-compose for live preview with VNC.
    Gracefully handles sandbox not being available (does not block generation).
    """
    try:
        container_name = f"project-{request.projectId}"

        # Check if already running
        if request.projectId in _project_containers:
            info = _project_containers[request.projectId]
            if info.get('status') == 'running':
                return SuccessResponse(success=True)

        engine_root = Path(__file__).parent.parent.parent.parent
        compose_file = engine_root / "docker-compose.yml"

        # Start sandbox service via docker-compose
        cmd = (
            f'docker-compose -f "{compose_file}" up -d sandbox'
        )
        stdout, stderr, rc = await run_command(cmd, cwd=str(engine_root))

        if rc != 0:
            # Sandbox failed to start — log but don't block generation
            logger.warning(
                "sandbox_start_failed_non_blocking",
                projectId=request.projectId,
                error=stderr or stdout,
            )
            return SuccessResponse(
                success=False,
                error=f"Sandbox unavailable (generation continues): {stderr or stdout}",
            )

        _project_containers[request.projectId] = {
            'id': 'coding-engine-sandbox',
            'vncPort': request.vncPort,
            'appPort': request.appPort,
            'status': 'running'
        }

        logger.info("project_container_started", projectId=request.projectId, vncPort=request.vncPort)
        return SuccessResponse(success=True)
    except Exception as e:
        # Sandbox errors must not block the generation pipeline
        logger.warning("project_start_failed_non_blocking", projectId=request.projectId, error=str(e))
        return SuccessResponse(success=False, error=f"Sandbox unavailable: {str(e)}")


@router.post("/project/stop", response_model=SuccessResponse)
async def stop_project_container(request: ProjectStopRequest) -> SuccessResponse:
    """
    Stop a project container.
    """
    try:
        container_name = f"project-{request.projectId}"

        await run_command(f'docker stop {container_name}')
        await run_command(f'docker rm {container_name}')

        if request.projectId in _project_containers:
            del _project_containers[request.projectId]

        logger.info("project_container_stopped", projectId=request.projectId)
        return SuccessResponse(success=True)
    except Exception as e:
        logger.error("project_stop_failed", projectId=request.projectId, error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.get("/project/status")
def _load_epics_from_files(project_path: str) -> list:
    """Load epic info from task files on disk. Works even when generation is idle."""
    import json as _json
    epics = []
    tasks_dir = Path(project_path) / "tasks"
    if not tasks_dir.exists():
        return epics
    for tf in sorted(tasks_dir.glob("epic-*-tasks-enriched.json")):
        try:
            with open(tf) as f:
                td = _json.load(f)
            tasks = td.get("tasks", [])
            epic_id = td.get("epic_id", tf.stem.split("-tasks")[0].upper())
            if not epic_id:
                # Extract from filename: epic-001-tasks-enriched.json → EPIC-001
                parts = tf.stem.replace("-tasks-enriched", "").upper()
                epic_id = parts
            epics.append({
                "id": epic_id,
                "name": td.get("epic_name", td.get("name", epic_id)),
                "tasks_total": len(tasks),
                "tasks_complete": sum(1 for t in tasks if t.get("status") == "completed"),
                "progress_pct": 0,
            })
        except Exception:
            pass
    # Calculate progress from DB if possible (task_id prefix matching)
    return epics


async def _enrich_epics_from_db(epics: list, job_id: int = None) -> list:
    """Enrich epic progress from DB task statuses."""
    try:
        import asyncpg
        db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(db_url.split("?")[0] if "?" in db_url else db_url)
        job_clause = "job_id=%d" % job_id if job_id else "job_id=(SELECT MAX(id) FROM jobs)"
        rows = await conn.fetch(
            "SELECT task_id, status FROM tasks WHERE %s" % job_clause
        )
        await conn.close()

        # Group by epic prefix
        epic_stats = {}  # epic_id → {completed, failed, total}
        for row in rows:
            tid = row["task_id"] or ""
            # Extract epic: EPIC-001-SETUP-xxx → EPIC-001
            parts = tid.split("-")
            if len(parts) >= 2 and parts[0] == "EPIC":
                eid = "EPIC-%s" % parts[1]
            else:
                eid = "UNKNOWN"
            if eid not in epic_stats:
                epic_stats[eid] = {"completed": 0, "failed": 0, "pending": 0, "total": 0}
            epic_stats[eid]["total"] += 1
            status = (row["status"] or "").upper()
            if status == "COMPLETED":
                epic_stats[eid]["completed"] += 1
            elif status == "FAILED":
                epic_stats[eid]["failed"] += 1
            else:
                epic_stats[eid]["pending"] += 1

        # Merge into epics list
        for e in epics:
            eid = e["id"].upper()
            if eid in epic_stats:
                s = epic_stats[eid]
                e["tasks_total"] = s["total"]
                e["tasks_complete"] = s["completed"]
                e["tasks_failed"] = s.get("failed", 0)
                e["progress_pct"] = int(s["completed"] * 100 / max(s["total"], 1))
    except Exception:
        pass
    return epics


async def get_project_status(projectId: str = Query(..., description="Project ID")):
    """
    Get project generation status. Returns generation phase, progress, and task counts
    when generation is active. Falls back to container status otherwise.
    """
    # Check generation state first
    gen = _generation_state.get(projectId)
    if gen and gen.get("phase") not in (None, "idle"):
        # Lazy-load epics from project if not cached
        if not gen.get("epics") and gen.get("project_path"):
            try:
                from mcp_plugins.servers.grpc_host.epic_task_generator import EpicTaskGenerator
                etg = EpicTaskGenerator(gen["project_path"])
                raw_epics = etg.get_epic_list()
                epic_infos = []
                for e in raw_epics:
                    epic_infos.append({
                        "id": e.get("id", ""),
                        "name": e.get("name", ""),
                        "progress_pct": e.get("progress_percent", 0),
                        "tasks_total": 0,
                        "tasks_complete": 0,
                    })
                gen["epics"] = epic_infos
            except Exception:
                # Fallback: try reading tasks files for epic IDs
                import glob as _glob
                import json as _json
                epic_infos = []
                tasks_dir = Path(gen["project_path"]) / "tasks"
                for tf in sorted(tasks_dir.glob("epic-*-tasks.json")):
                    try:
                        with open(tf) as f:
                            td = _json.load(f)
                        tasks = td.get("tasks", [])
                        completed = sum(1 for t in tasks if t.get("status") == "completed")
                        total = len(tasks)
                        epic_id = td.get("epic_id", tf.stem.split("-tasks")[0].upper())
                        epic_infos.append({
                            "id": epic_id,
                            "name": td.get("epic_name", epic_id),
                            "progress_pct": int(completed * 100 / max(total, 1)),
                            "tasks_total": total,
                            "tasks_complete": completed,
                        })
                    except Exception:
                        pass
                gen["epics"] = epic_infos

        return {
            "phase": gen.get("phase", "idle"),
            "progress_pct": gen.get("progress_pct", 0),
            "agents": gen.get("agents", []),
            "epics": gen.get("epics", []),
            "service_count": gen.get("service_count", 0),
            "endpoint_count": gen.get("endpoint_count", 0),
            "completed": gen.get("completed", 0),
            "failed": gen.get("failed", 0),
            "total": gen.get("total", 0),
            "running": True,
        }

    # Fallback 1: Check subprocess generation via .generation_status.json + log file
    output_base = Path("/app/output")
    output_dir = output_base / projectId
    if not output_dir.exists() and output_base.exists():
        # Try finding by prefix match
        for d in output_base.iterdir():
            if d.is_dir() and (projectId in d.name or d.name.startswith(projectId)):
                output_dir = d
                break

    gen_status_file = output_dir / ".generation_status.json"
    gen_log_file = output_dir / "generation.log"

    if gen_log_file.exists():
        try:
            import time as _time
            log_mtime = gen_log_file.stat().st_mtime
            log_age = _time.time() - log_mtime

            # If log was modified in last 60s, generation is running
            is_running = log_age < 60

            # Read last few lines for progress info
            log_lines = gen_log_file.read_text(encoding="utf-8", errors="replace").strip().split("\n")
            last_lines = log_lines[-10:] if len(log_lines) > 10 else log_lines

            # Count executing/completed/failed from log
            total_executing = sum(1 for l in log_lines if "Executing task" in l)
            total_completed_log = sum(1 for l in log_lines if "epic_task_completed" in l)
            total_failed_log = sum(1 for l in log_lines if "epic_task_failed" in l)

            # Get DB stats via direct SQL
            db_stats = {"completed": 0, "failed": 0, "pending": 0, "total": 0}
            try:
                import asyncpg
                db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "postgresql://")
                if "asyncpg" in db_url:
                    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
                conn = await asyncpg.connect(db_url.split("?")[0] if "?" in db_url else db_url)
                rows = await conn.fetch(
                    "SELECT status, COUNT(*) as cnt FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) GROUP BY status"
                )
                for row in rows:
                    db_stats[row["status"].lower()] = row["cnt"]
                db_stats["total"] = sum(db_stats.values())
                await conn.close()
            except Exception:
                pass

            total = db_stats.get("total", 0) or (total_executing + 1)
            completed = db_stats.get("completed", 0) or total_completed_log
            failed = db_stats.get("failed", 0) or total_failed_log
            pending = db_stats.get("pending", 0)
            progress = int((completed + failed) * 100 / max(total, 1))

            # Current task from last log line
            current_task = ""
            for l in reversed(last_lines):
                if "Executing task" in l:
                    import re as _re
                    m = _re.search(r"Executing task (\S+?):", l)
                    if m:
                        current_task = m.group(1)
                    break

            if is_running or (gen_status_file.exists() and "running" in gen_status_file.read_text()):
                # Load epics from task files
                req_path = None
                try:
                    from src.engine_settings import get_project
                    _p = get_project()
                    req_path = _p.get("requirements_path") if _p else None
                except Exception:
                    pass
                _epics = _load_epics_from_files(req_path) if req_path else []
                _epics = await _enrich_epics_from_db(_epics)

                return {
                    "phase": "generating",
                    "progress_pct": progress,
                    "agents": [{"name": "EpicOrchestrator", "status": "running", "current_task": current_task}] if is_running else [],
                    "epics": _epics,
                    "service_count": 0,
                    "endpoint_count": 0,
                    "completed": completed,
                    "failed": failed,
                    "pending": pending,
                    "total": total,
                    "running": is_running,
                    "last_activity": last_lines[-1][:200] if last_lines else "",
                }
        except Exception:
            pass

    # Always try to get DB task counts (even when idle)
    db_stats = {"completed": 0, "failed": 0, "pending": 0, "total": 0, "cancelled": 0, "running": 0}
    try:
        import asyncpg
        db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(db_url.split("?")[0] if "?" in db_url else db_url)
        rows = await conn.fetch(
            "SELECT status, COUNT(*) as cnt FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) GROUP BY status"
        )
        for row in rows:
            db_stats[row["status"].lower()] = row["cnt"]
        db_stats["total"] = sum(v for k, v in db_stats.items() if k != "total")
        await conn.close()
    except Exception:
        pass

    if db_stats["total"] > 0:
        progress = int((db_stats["completed"] + db_stats["failed"]) * 100 / max(db_stats["total"], 1))
        # Load epics from task files + DB stats
        req_path = None
        try:
            from src.engine_settings import get_project
            _p = get_project()
            req_path = _p.get("requirements_path") if _p else None
        except Exception:
            pass
        _epics = _load_epics_from_files(req_path) if req_path else []
        _epics = await _enrich_epics_from_db(_epics)

        return {
            "phase": "idle",
            "progress_pct": progress,
            "agents": [],
            "epics": _epics,
            "service_count": 0,
            "endpoint_count": 0,
            "completed": db_stats["completed"],
            "failed": db_stats["failed"],
            "pending": db_stats["pending"],
            "cancelled": db_stats.get("cancelled", 0),
            "total": db_stats["total"],
            "running": False,
        }

    # Fallback 2: container status
    try:
        container_name = f"project-{projectId}"
        stdout, stderr, rc = await run_command(
            f"docker inspect --format='{{{{.State.Status}}}}' {container_name}"
        )
        if rc != 0:
            return {"phase": "idle", "progress_pct": 0, "agents": [], "epics": [],
                    "service_count": 0, "endpoint_count": 0, "running": False}

        status = stdout.strip().strip("'")
        info = _project_containers.get(projectId, {})
        return {"phase": "idle", "progress_pct": 0, "agents": [], "epics": [],
                "service_count": 0, "endpoint_count": 0,
                "running": (status == 'running'),
                "vncPort": info.get('vncPort'), "appPort": info.get('appPort'),
                "health": status}
    except Exception:
        return {"phase": "idle", "progress_pct": 0, "agents": [], "epics": [],
                "service_count": 0, "endpoint_count": 0, "running": False}


@router.get("/project/logs", response_model=LogsResponse)
async def get_project_logs(
    projectId: str = Query(..., description="Project ID"),
    tail: int = Query(100, description="Number of lines to return")
) -> LogsResponse:
    """
    Get project container logs.
    """
    try:
        container_name = f"project-{projectId}"

        stdout, stderr, rc = await run_command(f'docker logs --tail {tail} {container_name}')

        if rc != 0:
            return LogsResponse(logs=f"Error: {stderr or 'Container not found'}")

        return LogsResponse(logs=stdout + stderr)
    except Exception as e:
        return LogsResponse(logs=f"Error: {str(e)}")


@router.post("/generate", response_model=SuccessResponse)
async def start_generation(request: GenerateRequest) -> SuccessResponse:
    """
    Start a code generation job. Returns immediately, spawns in background thread.
    Lock check happens synchronously before thread spawn.
    """
    import threading
    import time

    # Resolve project_id and output_dir for lock check
    req_path = Path(request.requirementsPath)
    project_id = getattr(request, "projectId", "") or (req_path.name if req_path.is_dir() or not req_path.suffix else req_path.parent.name)
    output_dir = request.outputDir or "/app/output/%s" % project_id

    # ── Lock check (synchronous — before thread) ──
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    lock_file = Path(output_dir) / ".generation_running"
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text())
            elapsed = int(time.time() - lock_data.get("started_at", 0))
            if elapsed < 7200:  # Valid for 2 hours max
                return SuccessResponse(success=False, error="Generation already running for '%s' (started %ds ago)" % (project_id, elapsed))
        except Exception:
            pass
        lock_file.unlink(missing_ok=True)

    # ── Write lock BEFORE spawning thread ──
    lock_file.write_text(json.dumps({"project_id": project_id, "started_at": time.time()}))

    def _launch():
        try:
            import traceback
            logger.info("generation_thread_started project=%s", project_id)
            _start_generation_sync(request)
            logger.info("generation_thread_completed project=%s", project_id)
        except Exception as e:
            logger.error("generation_launch_failed error=%s\n%s", str(e), traceback.format_exc())
            lock_file.unlink(missing_ok=True)

    t = threading.Thread(target=_launch, daemon=True)
    t.start()
    return SuccessResponse(success=True)


def _start_generation_sync(request):
    """Synchronous generation launcher — runs in background thread. Supports parallel projects."""
    try:
        engine_root = Path(__file__).parent.parent.parent.parent

        req_path = Path(request.requirementsPath)
        if req_path.is_dir() or (not req_path.suffix and not req_path.exists()):
            project_path_resolved = req_path
        else:
            project_path_resolved = req_path.parent

        project_id = getattr(request, "projectId", "") or project_path_resolved.name
        output_dir = request.outputDir or "/app/output/%s" % project_id

        # Lock already checked in start_generation() — clean stale registry
        if project_id in _active_generations:
            del _active_generations[project_id]

        # ── Resolve project config from engine_settings ──
        proj_config = {}
        try:
            from src.engine_settings import get_project
            proj_config = get_project(project_id) or {}
        except Exception:
            pass

        db_schema = proj_config.get("db_schema", project_id.replace("-", "_").replace(" ", "_"))
        vnc_port = proj_config.get("vnc_port", 6090)
        app_port = proj_config.get("app_port", 3100)

        # Load generation settings
        gen_settings = {}
        try:
            from src.engine_settings import load_settings
            all_settings = load_settings()
            gen_settings = all_settings.get("generation", {})
        except Exception:
            pass

        # ── Auto-create project database ──
        try:
            subprocess.run(
                ["psql", "-U", "postgres", "-h", "postgres", "-c",
                 "CREATE DATABASE %s" % db_schema],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass  # May already exist

        # ── Generate MCP config ──
        try:
            from src.mcp.project_config import (
                generate_project_mcp_config,
                save_project_mcp_config,
                generate_cli_mcp_config,
            )
            mcp_config = generate_project_mcp_config(
                project_id=project_id,
                project_path=str(project_path_resolved),
                output_dir=output_dir,
            )
            save_project_mcp_config(mcp_config)
            generate_cli_mcp_config(working_dir=output_dir)
        except Exception as e:
            logger.warning("mcp_config_generation_failed", error=str(e))

        # ── Build command with project-specific params ──
        project_path = str(project_path_resolved)
        cmd = [
            "python", "run_generation.py",
            "--project-path", project_path,
            "--output-dir", output_dir,
            "--project-id", project_id,
            "--db-schema", db_schema,
            "--vnc-port", str(vnc_port),
            "--app-port", str(app_port),
            "--parallelism", str(gen_settings.get("max_parallel_epics", 3)),
        ]

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        # ── Spawn as truly detached subprocess ──
        log_path = Path(output_dir) / "generation.log"
        log_file = open(str(log_path), "a")

        process = subprocess.Popen(
            cmd,
            cwd=str(engine_root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,  # Detach from parent process group
        )
        pid = process.pid
        log_file.close()  # Popen has its own fd now

        # ── Register in active generations ──
        _active_generations[project_id] = {
            "pid": pid,
            "started_at": time.time(),
            "output_dir": output_dir,
            "db_schema": db_schema,
            "vnc_port": vnc_port,
            "app_port": app_port,
            "log_path": log_path,
        }

        logger.info("generation_started",
                     project_id=project_id,
                     output=output_dir,
                     db_schema=db_schema,
                     vnc_port=vnc_port,
                     app_port=app_port,
                     pid=pid)
        return SuccessResponse(success=True)
    except Exception as e:
        logger.error("generation_start_failed", error=str(e))
        return SuccessResponse(success=False, error=str(e))


# ============================================================================
# Parallel Generation Management
# ============================================================================


@router.get("/active-generations")
async def get_active_generations():
    """List all currently running generation processes."""
    result = {}
    for pid, info in list(_active_generations.items()):
        alive = False
        try:
            os.kill(info.get("pid", 0), 0)
            alive = True
        except (OSError, TypeError):
            pass

        last_line = ""
        try:
            log = Path(info.get("log_path", info.get("output_dir", "") + "/generation.log"))
            if log.exists():
                content = log.read_text(encoding="utf-8", errors="replace")
                lines = content.strip().split("\n")
                last_line = lines[-1][:200] if lines else ""
        except Exception:
            pass

        result[pid] = {
            **info,
            "status": "running" if alive else "completed",
            "last_log": last_line,
            "elapsed_seconds": round(time.time() - info.get("started_at", time.time()), 1),
        }
    return {"generations": result, "count": len(result)}


class GenerationCompleteRequest(BaseModel):
    project_id: str


@router.post("/generation-complete")
async def generation_complete(request: GenerationCompleteRequest):
    """Called by run_generation.py when a generation process finishes."""
    pid = request.project_id
    if pid in _active_generations:
        info = _active_generations.pop(pid)
        logger.info("generation_complete_cleanup", project_id=pid, elapsed=round(time.time() - info.get("started_at", 0), 1))
        return {"success": True, "cleaned_up": True}
    return {"success": True, "cleaned_up": False}


# ============================================================================
# Sandbox exec — run commands in sandbox or API container
# ============================================================================


class SandboxExecRequest(BaseModel):
    command: str
    container: str = "coding-engine-sandbox"
    timeout: int = 30


@router.post("/sandbox/exec")
async def sandbox_exec(request: SandboxExecRequest):
    """Execute a command in the API container (has access to /app/output)."""
    import asyncio as _aio

    # Rewrite /workspace/app paths to /app/output (API container has the files)
    cmd = request.command.replace("/workspace/app", "/app/output")

    try:
        proc = await _aio.create_subprocess_shell(
            cmd,
            stdout=_aio.subprocess.PIPE,
            stderr=_aio.subprocess.PIPE,
            cwd="/app/output",
        )
        stdout, stderr = await _aio.wait_for(
            proc.communicate(), timeout=request.timeout
        )
        return {
            "stdout": (stdout or b"").decode("utf-8", errors="replace"),
            "stderr": (stderr or b"").decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


# ============================================================================
# Single-file code generation via LLM
# ============================================================================

class GenerateCodeRequest(BaseModel):
    """Request to generate code for a single file via OpenRouter LLM."""
    file_path: str  # e.g. "src/components/Login.tsx"
    task_description: str  # What the code should do
    task_id: str = ""  # Optional task ID for MCMP context
    model: str = ""  # Override model (empty = use config default)
    backend: str = "openrouter"  # "openrouter" | "kilo" | "claude"
    max_tokens: int = 4000

class GenerateCodeResponse(BaseModel):
    success: bool
    file_path: str = ""
    code_length: int = 0
    deployed: bool = False
    build_result: str = ""
    error: str = ""

@router.post("/generate-code", response_model=GenerateCodeResponse)
async def generate_code(request: GenerateCodeRequest):
    """
    Generate code for a single file via LLM, write to sandbox, verify build.

    Pipeline: Prompt -> MCMP context -> LLM -> Write file -> Build check
    """
    import httpx

    try:
        # 1. Get MCMP context enrichment
        mcmp_context = ""
        try:
            from src.services.mcmp_prerun import get_prerun
            prerun = get_prerun()
            ctx = await prerun.get_task_context(
                task_id=request.task_id or request.file_path,
                task_name=request.file_path.split("/")[-1],
                task_description=request.task_description[:300],
                file_path=request.file_path,
            )
            mcmp_context = ctx.get("enriched_prompt", "")
        except Exception:
            pass  # Continue without MCMP

        # 2. Build prompt
        prompt = (
            "You are a senior TypeScript/React developer.\n"
            "Generate the complete file for: %s\n"
            "Task: %s\n"
            "%s"
            "Reply with ONLY the complete file content (no markdown fences, no explanation). "
            "Use TypeScript, React functional components, proper types."
            % (request.file_path, request.task_description, mcmp_context)
        )

        # 3. Call LLM based on backend
        code = ""
        if request.backend == "kilo":
            try:
                from src.autogen.kilo_cli_wrapper import KiloCLI
                kilo = KiloCLI()
                result = await kilo.generate(prompt)
                code = result.get("code", "")
            except Exception as e:
                code = ""
                logger.warning("kilo_backend_failed", error=str(e))

        if request.backend == "claude":
            try:
                from src.tools.claude_code_tool import ClaudeCodeTool
                tool = ClaudeCodeTool()
                result = await tool.execute(prompt)
                code = result.get("output", "") if isinstance(result, dict) else str(result)
            except Exception as e:
                code = ""
                logger.warning("claude_backend_failed", error=str(e))

        if not code:  # Default: OpenRouter
            from src.llm_config import get_model, get_api_key
            model = request.model or get_model("primary")
            api_key = get_api_key("primary")

            if not api_key:
                return GenerateCodeResponse(success=False, error="No OPENROUTER_API_KEY configured")

            async with httpx.AsyncClient(timeout=60) as client:
                for attempt in range(3):
                    resp = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": "Bearer %s" % api_key,
                            "HTTP-Referer": "https://coding-engine.local",
                            "X-Title": "DaveFelix Coding Engine",
                        },
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": request.max_tokens,
                        },
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep((attempt + 1) * 10)
                        continue
                    if resp.status_code == 200:
                        code = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        break
                    else:
                        return GenerateCodeResponse(
                            success=False, error="LLM API error %d: %s" % (resp.status_code, resp.text[:200])
                        )

        if not code:
            return GenerateCodeResponse(success=False, error="LLM returned empty response")

        # Strip markdown code fences
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        # 4. Write to shared Data volume (API → /app/Data/generated/, Sandbox → /workspace/data/generated/)
        gen_dir = Path("/app/Data/generated") / str(Path(request.file_path).parent)
        gen_file = Path("/app/Data/generated") / request.file_path
        try:
            gen_dir.mkdir(parents=True, exist_ok=True)
            gen_file.write_text(code, encoding="utf-8")
            deployed = True
            logger.info("code_written_to_shared_volume", path=str(gen_file), size=len(code))
        except Exception as e:
            return GenerateCodeResponse(
                success=True, file_path=request.file_path,
                code_length=len(code), deployed=False,
                build_result="Write failed: %s" % str(e)[:100],
            )

        # 5. Build check via HTTP to sandbox health
        build_result = "skipped"
        if deployed:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get("http://coding-engine-sandbox:3100")
                    build_result = "OK (sandbox HTTP %d)" % resp.status_code
            except Exception:
                build_result = "sandbox unreachable"

        return GenerateCodeResponse(
            success=True,
            file_path=request.file_path,
            code_length=len(code),
            deployed=deployed,
            build_result=build_result,
        )

    except Exception as e:
        logger.error("generate_code_failed", error=str(e))
        return GenerateCodeResponse(success=False, error=str(e)[:300])


class StopGenerationRequest(BaseModel):
    """Request to stop any running generation."""
    project_id: str


@router.post("/stop-generation", response_model=SuccessResponse)
async def stop_generation(request: StopGenerationRequest):
    """
    Gracefully stop any running generation (epic or legacy).

    Pauses all running EpicOrchestrators so they finish the current task
    before stopping. The checkpoint is preserved for later resume.
    """
    try:
        paused_count = 0
        for key, orch in _epic_orchestrators.items():
            try:
                if orch.is_running() and not orch.is_paused():
                    orch.pause()
                    paused_count += 1
                    logger.info("epic_orchestrator_paused", key=key, project_id=request.project_id)
            except Exception as e:
                logger.warning("epic_orchestrator_pause_failed", key=key, error=str(e))

        # Publish stop event to dashboard
        if _event_bus:
            try:
                from src.mind.event_bus import Event, EventType
                await _event_bus.publish(Event(
                    type=EventType.TASK_PROGRESS_UPDATE,
                    source="stop_generation",
                    data={
                        "type": "generation_stopped",
                        "project_id": request.project_id,
                        "paused_orchestrators": paused_count,
                    }
                ))
            except Exception:
                pass

        logger.info("generation_stopped", project_id=request.project_id, paused=paused_count)
        return SuccessResponse(success=True)
    except Exception as e:
        logger.error("generation_stop_failed", error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.delete("/events/cleanup")
async def cleanup_old_events(
    days: int = Query(7, ge=1, le=365, description="Delete events older than N days"),
    service: DashboardService = Depends(get_dashboard_service)
) -> dict:
    """
    Clean up old connection events from the database.

    Deletes events older than the specified number of days to maintain performance.

    Args:
        days: Number of days to retain (default: 7)

    Returns:
        Count of deleted events
    """
    try:
        deleted_count = await service.cleanup_old_events(days=days)

        logger.info(
            "events_cleaned_up",
            deleted_count=deleted_count,
            retention_days=days
        )

        return {
            "success": True,
            "deleted_count": deleted_count,
            "retention_days": days,
            "message": f"Deleted {deleted_count} events older than {days} days"
        }

    except Exception as e:
        logger.error("cleanup_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to clean up events: {str(e)}")


# ============================================================================
# Review Gate Endpoints (Pause/Resume Generation for User Review)
# ============================================================================

# Global instances - these will be set by the main API module
_shared_state: Optional[SharedState] = None
_event_bus: Optional[EventBus] = None


def set_review_gate_dependencies(shared_state: SharedState, event_bus: EventBus) -> None:
    """Set the global SharedState and EventBus instances for review gate."""
    global _shared_state, _event_bus
    _shared_state = shared_state
    _event_bus = event_bus


def set_event_bus(event_bus: EventBus) -> None:
    """Set the EventBus for dashboard routes (used by run_engine.py).

    This allows external callers to inject a shared EventBus without
    requiring a SharedState instance (which is only available in the
    full Society of Mind pipeline).
    """
    global _event_bus
    _event_bus = event_bus


@router.post("/generation/{project_id}/pause")
async def pause_generation(project_id: str):
    """
    Pause generation for user review.

    The generation will pause after the current batch completes.
    """
    if not _shared_state:
        raise HTTPException(status_code=503, detail="SharedState not initialized")

    try:
        await _shared_state.pause_for_review()

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.REVIEW_PAUSE_REQUESTED,
                source="dashboard",
                data={"project_id": project_id}
            ))

        logger.info("pause_requested", project_id=project_id)
        return {"success": True, "status": "pause_requested"}

    except Exception as e:
        logger.error("pause_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to pause: {str(e)}")


@router.post("/generation/{project_id}/resume")
async def resume_generation(project_id: str, request: ReviewResumeRequest):
    """
    Resume generation after user review.

    Optionally include feedback to inject into the next generation iteration.
    """
    if not _shared_state:
        raise HTTPException(status_code=503, detail="SharedState not initialized")

    try:
        await _shared_state.resume_from_review(request.feedback)

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.REVIEW_RESUME_REQUESTED,
                source="dashboard",
                data={
                    "project_id": project_id,
                    "has_feedback": bool(request.feedback)
                }
            ))

        logger.info(
            "resume_requested",
            project_id=project_id,
            has_feedback=bool(request.feedback)
        )
        return {"success": True, "status": "resumed"}

    except Exception as e:
        logger.error("resume_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to resume: {str(e)}")


@router.get("/generation/{project_id}/review-status")
async def get_review_status(project_id: str):
    """Get the current review gate status."""
    if not _shared_state:
        raise HTTPException(status_code=503, detail="SharedState not initialized")

    return _shared_state.get_review_status()


@router.post("/generation/{project_id}/feedback")
async def submit_review_feedback(project_id: str, request: ReviewResumeRequest):
    """
    Submit additional feedback during pause.

    This allows the user to add multiple feedback items before resuming.
    """
    if not _shared_state:
        raise HTTPException(status_code=503, detail="SharedState not initialized")

    if not request.feedback:
        raise HTTPException(status_code=400, detail="Feedback is required")

    try:
        await _shared_state.submit_review_feedback(request.feedback)

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.REVIEW_FEEDBACK_SUBMITTED,
                source="dashboard",
                data={
                    "project_id": project_id,
                    "feedback_length": len(request.feedback)
                }
            ))

        logger.info(
            "feedback_submitted",
            project_id=project_id,
            feedback_length=len(request.feedback)
        )
        return {"success": True, "feedback_accepted": True}

    except Exception as e:
        logger.error("feedback_submit_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(e)}")


# =============================================================================
# Clarification API (Tier 1 Core Intelligence)
# =============================================================================

# Pydantic models for clarification
class ClarificationChoice(BaseModel):
    """Single choice submission for a clarification question."""
    ambiguity_id: str
    interpretation_id: str


class ClarificationSubmitRequest(BaseModel):
    """Request to submit clarification choices."""
    choices: List[ClarificationChoice]
    use_defaults_for_remaining: bool = False


class ClarificationQuestionOption(BaseModel):
    """Option for a clarification question."""
    id: str
    label: str
    description: str
    is_recommended: bool = False


class ClarificationQuestion(BaseModel):
    """Single clarification question."""
    ambiguity_id: str
    description: str
    requirement_text: str
    severity: str
    options: List[ClarificationQuestionOption]


class ClarificationStatusResponse(BaseModel):
    """Response for clarification status."""
    has_pending: bool
    request_id: Optional[str] = None
    questions: List[ClarificationQuestion] = []
    answered: int = 0
    total: int = 0
    is_complete: bool = False


# Global clarification gate reference (set by initialize_event_systems)
_clarification_gate = None


def set_clarification_gate(gate):
    """Set the clarification gate instance."""
    global _clarification_gate
    _clarification_gate = gate


@router.get("/generation/{project_id}/clarifications")
async def get_clarification_status(project_id: str) -> ClarificationStatusResponse:
    """
    Get the current clarification status.

    Returns pending clarification questions if any exist.
    """
    if not _clarification_gate:
        return ClarificationStatusResponse(has_pending=False)

    pending_requests = _clarification_gate.get_pending_requests()
    if not pending_requests:
        return ClarificationStatusResponse(has_pending=False)

    # Get the first pending request
    request = pending_requests[0]

    questions = []
    for iset in request.interpretation_sets:
        options = [
            ClarificationQuestionOption(
                id=interp.id,
                label=interp.label,
                description=interp.description,
                is_recommended=interp.is_recommended,
            )
            for interp in iset.interpretations
        ]
        questions.append(
            ClarificationQuestion(
                ambiguity_id=iset.ambiguity.id,
                description=iset.ambiguity.description,
                requirement_text=iset.ambiguity.requirement_text[:200],
                severity=iset.ambiguity.severity.value,
                options=options,
            )
        )

    return ClarificationStatusResponse(
        has_pending=True,
        request_id=request.id,
        questions=questions,
        answered=request.answered_questions,
        total=request.total_questions,
        is_complete=request.is_complete,
    )


@router.post("/generation/{project_id}/clarifications/submit")
async def submit_clarification_choices(
    project_id: str,
    request: ClarificationSubmitRequest,
):
    """
    Submit clarification choices.

    Can submit one or more choices at a time.
    Set use_defaults_for_remaining=true to use recommended defaults for unanswered questions.
    """
    if not _clarification_gate:
        raise HTTPException(status_code=503, detail="ClarificationGate not initialized")

    pending_requests = _clarification_gate.get_pending_requests()
    if not pending_requests:
        raise HTTPException(status_code=404, detail="No pending clarification request")

    clar_request = pending_requests[0]

    try:
        # Submit each choice
        for choice in request.choices:
            success = await _clarification_gate.submit_choice(
                request_id=clar_request.id,
                ambiguity_id=choice.ambiguity_id,
                interpretation_id=choice.interpretation_id,
            )
            if not success:
                logger.warning(
                    "clarification_choice_rejected",
                    ambiguity_id=choice.ambiguity_id,
                    interpretation_id=choice.interpretation_id,
                )

        # Use defaults for remaining if requested
        if request.use_defaults_for_remaining:
            await _clarification_gate.use_defaults(clar_request.id)

        # Get updated status
        updated_request = _clarification_gate.get_request(clar_request.id)

        if _event_bus and updated_request:
            await _event_bus.publish(Event(
                type=EventType.CLARIFICATION_CHOICE_SUBMITTED,
                source="dashboard",
                data={
                    "project_id": project_id,
                    "request_id": clar_request.id,
                    "choices_submitted": len(request.choices),
                    "is_complete": updated_request.is_complete,
                }
            ))

        logger.info(
            "clarification_choices_submitted",
            project_id=project_id,
            choices=len(request.choices),
            is_complete=updated_request.is_complete if updated_request else False,
        )

        return {
            "success": True,
            "is_complete": updated_request.is_complete if updated_request else False,
            "remaining": updated_request.total_questions - updated_request.answered_questions
            if updated_request else 0,
        }

    except Exception as e:
        logger.error("clarification_submit_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to submit clarifications: {str(e)}")


@router.post("/generation/{project_id}/clarifications/use-defaults")
async def use_default_clarifications(project_id: str):
    """
    Use recommended defaults for all pending clarification questions.

    This allows the generation to proceed without manual choices.
    """
    if not _clarification_gate:
        raise HTTPException(status_code=503, detail="ClarificationGate not initialized")

    pending_requests = _clarification_gate.get_pending_requests()
    if not pending_requests:
        raise HTTPException(status_code=404, detail="No pending clarification request")

    clar_request = pending_requests[0]

    try:
        await _clarification_gate.use_defaults(clar_request.id)

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.CLARIFICATION_RESOLVED,
                source="dashboard",
                data={
                    "project_id": project_id,
                    "request_id": clar_request.id,
                    "used_defaults": True,
                }
            ))

        logger.info(
            "clarification_defaults_used",
            project_id=project_id,
            request_id=clar_request.id,
        )

        return {"success": True, "used_defaults": True}

    except Exception as e:
        logger.error("clarification_defaults_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to use defaults: {str(e)}")


@router.post("/generation/{project_id}/clarifications/cancel")
async def cancel_clarification(project_id: str):
    """
    Cancel the current clarification request.

    This will cancel the clarification and may cause generation to fail
    or use defaults.
    """
    if not _clarification_gate:
        raise HTTPException(status_code=503, detail="ClarificationGate not initialized")

    pending_requests = _clarification_gate.get_pending_requests()
    if not pending_requests:
        raise HTTPException(status_code=404, detail="No pending clarification request")

    clar_request = pending_requests[0]

    try:
        _clarification_gate.cancel_request(clar_request.id)

        logger.info(
            "clarification_cancelled",
            project_id=project_id,
            request_id=clar_request.id,
        )

        return {"success": True, "cancelled": True}

    except Exception as e:
        logger.error("clarification_cancel_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to cancel: {str(e)}")


# =============================================================================
# Clarification Queue Notifications (Non-Blocking Mode)
# =============================================================================


@router.get("/notifications/clarifications")
async def get_pending_clarifications():
    """
    Get all pending clarification notifications from the queue.

    In queue mode, clarifications are collected without blocking generation.
    This endpoint returns all pending clarifications that need user attention.

    Returns:
        List of pending clarifications with:
        - id: Unique clarification ID
        - ambiguity_id: ID of the detected ambiguity
        - description: Human-readable description
        - requirement_text: Original requirement text
        - interpretations: List of possible interpretations
        - priority: 1=high, 2=medium, 3=low
        - severity: high, medium, low
        - queued_at: When it was added to queue
        - timeout_at: When it will auto-resolve
    """
    if not _clarification_gate:
        return {"pending": [], "queue_mode": False}

    if not _clarification_gate.queue_mode:
        # Not in queue mode, return empty
        return {"pending": [], "queue_mode": False}

    pending = _clarification_gate.get_pending_from_queue()

    return {
        "pending": pending,
        "queue_mode": True,
        "count": len(pending),
        "statistics": _clarification_gate._queue.get_statistics() if _clarification_gate._queue else {},
    }


@router.post("/notifications/clarifications/{clarification_id}/resolve")
async def resolve_queued_clarification(
    clarification_id: str,
    choice: ClarificationChoice,
):
    """
    Resolve a specific clarification from the queue.

    Args:
        clarification_id: The queue item ID (CLARQ-XXXX)
        choice: Contains interpretation_id to select

    Returns:
        Success status and remaining pending count
    """
    if not _clarification_gate:
        raise HTTPException(status_code=503, detail="ClarificationGate not initialized")

    if not _clarification_gate.queue_mode:
        raise HTTPException(status_code=400, detail="Not in queue mode")

    success = await _clarification_gate.resolve_from_queue(
        clarification_id,
        choice.interpretation_id
    )

    if not success:
        raise HTTPException(status_code=404, detail="Clarification not found or invalid interpretation")

    pending = _clarification_gate.get_pending_from_queue()

    return {
        "success": True,
        "clarification_id": clarification_id,
        "interpretation_id": choice.interpretation_id,
        "pending_count": len(pending),
    }


@router.post("/notifications/clarifications/resolve-all-defaults")
async def resolve_all_clarifications_with_defaults():
    """
    Auto-resolve all pending clarifications with recommended defaults.

    Use this when the user wants to accept all default interpretations
    and continue generation without reviewing each one.

    Returns:
        Number of clarifications resolved
    """
    if not _clarification_gate:
        raise HTTPException(status_code=503, detail="ClarificationGate not initialized")

    if not _clarification_gate.queue_mode:
        raise HTTPException(status_code=400, detail="Not in queue mode")

    count = await _clarification_gate.resolve_all_defaults_from_queue()

    return {
        "success": True,
        "resolved_count": count,
        "pending_count": len(_clarification_gate.get_pending_from_queue()),
    }


@router.get("/notifications/clarifications/statistics")
async def get_clarification_statistics():
    """
    Get statistics about the clarification queue.

    Returns:
        - total: Total clarifications ever queued
        - pending: Currently pending
        - resolved: Already resolved
        - auto_resolved: Resolved by timeout
        - by_priority: Breakdown by priority level
        - by_severity: Breakdown by severity level
    """
    if not _clarification_gate or not _clarification_gate._queue:
        return {
            "queue_mode": False,
            "statistics": {},
        }

    return {
        "queue_mode": _clarification_gate.queue_mode,
        "statistics": _clarification_gate._queue.get_statistics(),
    }


# =============================================================================
# Sandbox Error Reporting (for auto-fix integration)
# =============================================================================

@router.post("/sandbox/report-error")
async def report_sandbox_error(report: SandboxErrorReport):
    """
    Receive error reports from Docker sandbox containers.

    When a sandbox container encounters a build failure or runtime error,
    it POSTs the error details here. This endpoint parses the error
    and publishes BUILD_FAILED or SANDBOX_TEST_FAILED events to the EventBus,
    which triggers the ContinuousDebugAgent to auto-fix the code.

    This enables the "auto-fix on error" loop:
    1. Sandbox builds/runs code -> fails
    2. Sandbox POSTs error to this endpoint
    3. This endpoint publishes BUILD_FAILED event
    4. ContinuousDebugAgent receives event
    5. Agent analyzes error, generates fix
    6. Agent syncs fix to container via docker cp
    7. Sandbox rebuilds -> repeat until success
    """
    if not _event_bus:
        logger.warning("sandbox_error_received_but_eventbus_not_initialized",
                      project_id=report.project_id)
        return {"success": False, "error": "EventBus not initialized"}

    try:
        # Parse build output into structured payload
        payload = BuildFailurePayload.from_build_output(
            output=report.build_output,
            exit_code=report.exit_code
        )
        payload.failing_command = f"{report.project_type} build" if report.project_type else "build"

        # Determine event type based on error type
        if report.error_type == "build_failed":
            event_type = EventType.BUILD_FAILED
        elif report.error_type == "test_failed":
            event_type = EventType.SANDBOX_TEST_FAILED
        elif report.error_type in ("database_migration_failed", "database_runtime_error"):
            event_type = EventType.VALIDATION_ERROR
            # Mark as database error for DatabaseDockerAgent to pick up
            payload.is_database_error = True
        else:
            event_type = EventType.BUILD_FAILED  # Default to build failed

        # Publish event to trigger auto-fix
        await _event_bus.publish(Event(
            type=event_type,
            source="sandbox",
            data={
                "project_id": report.project_id,
                "container_name": report.container_name,
                "working_dir": report.working_dir,
                "project_type": report.project_type,
                **payload.to_dict()
            }
        ))

        logger.info(
            "sandbox_error_published",
            project_id=report.project_id,
            error_type=report.error_type,
            error_count=payload.error_count,
            is_type_error=payload.is_type_error,
            is_import_error=payload.is_import_error,
            is_database_error=payload.is_database_error,
            affected_files=payload.affected_files[:5]  # Log first 5 files
        )

        return {
            "success": True,
            "event_published": event_type.value,
            "error_count": payload.error_count,
            "affected_files": payload.affected_files
        }

    except Exception as e:
        logger.error("sandbox_error_report_failed",
                    project_id=report.project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process error report: {str(e)}")


# =============================================================================
# Epic-based Task Management API
# =============================================================================

# Pydantic models for Epic management
class EpicResponse(BaseModel):
    """Single Epic response."""
    id: str
    name: str
    description: str
    status: str
    progress_percent: float
    user_stories: List[str]
    requirements: List[str]
    entities: List[str]
    api_endpoints: List[str]
    last_run_at: Optional[str] = None
    run_count: int = 0


class EpicListResponse(BaseModel):
    """Response for listing all epics."""
    project_path: str
    total_epics: int
    epics: List[EpicResponse]


class LocalProjectResponse(BaseModel):
    """Response for a local project found in Data/all_services."""
    project_id: str
    project_name: str
    project_path: str
    has_user_stories: bool
    has_api_docs: bool
    has_data_dictionary: bool
    epic_count: int = 0
    user_story_count: int = 0
    created_at: Optional[str] = None


class LocalProjectsResponse(BaseModel):
    """Response for local projects scan."""
    projects: List[LocalProjectResponse]
    total: int
    scan_path: str


@router.get("/local-projects", response_model=LocalProjectsResponse)
async def scan_local_projects(
    base_path: str = Query("Data/all_services", description="Base path to scan for projects")
):
    """
    Scan for local projects in the Data/all_services folder.

    Returns all project folders that contain user_stories.md or other spec files.
    This allows the dashboard to display projects without needing the req-orchestrator.
    """
    try:
        engine_root = Path(__file__).parent.parent.parent.parent
        scan_path = engine_root / base_path

        if not scan_path.exists():
            raise HTTPException(status_code=404, detail=f"Path does not exist: {scan_path}")

        projects = []

        for project_dir in sorted(scan_path.iterdir()):
            if not project_dir.is_dir():
                continue

            # Check for spec files
            user_stories_path = project_dir / "user_stories" / "user_stories.md"
            api_docs_path = project_dir / "api" / "api_documentation.md"
            data_dict_path = project_dir / "data" / "data_dictionary.md"

            has_user_stories = user_stories_path.exists()
            has_api_docs = api_docs_path.exists()
            has_data_dict = data_dict_path.exists()

            # Skip folders without any spec files
            if not (has_user_stories or has_api_docs or has_data_dict):
                continue

            # Count epics and user stories if user_stories.md exists
            epic_count = 0
            user_story_count = 0

            if has_user_stories:
                try:
                    content = user_stories_path.read_text(encoding='utf-8')
                    import re
                    epic_count = len(re.findall(r'## EPIC-\d+:', content))
                    user_story_count = len(re.findall(r'### US-\d+:', content))
                except Exception:
                    pass

            # Get creation time
            try:
                created_at = datetime.fromtimestamp(project_dir.stat().st_ctime).isoformat()
            except Exception:
                created_at = None

            # Generate readable name from folder name
            folder_name = project_dir.name
            if folder_name.startswith("unnamed_project_"):
                # "unnamed_project_20260204_165411" -> "Project (Feb 04, 2026)"
                parts = folder_name.replace("unnamed_project_", "").split("_")
                if len(parts) >= 1 and len(parts[0]) == 8:
                    date_str = parts[0]
                    try:
                        date = datetime.strptime(date_str, "%Y%m%d")
                        project_name = f"Project ({date.strftime('%b %d, %Y')})"
                    except ValueError:
                        project_name = folder_name
                else:
                    project_name = folder_name
            else:
                project_name = folder_name.replace("_", " ").replace("-", " ").title()

            projects.append(LocalProjectResponse(
                project_id=folder_name,
                project_name=project_name,
                project_path=str(project_dir),
                has_user_stories=has_user_stories,
                has_api_docs=has_api_docs,
                has_data_dictionary=has_data_dict,
                epic_count=epic_count,
                user_story_count=user_story_count,
                created_at=created_at,
            ))

        return LocalProjectsResponse(
            projects=projects,
            total=len(projects),
            scan_path=str(scan_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("local_projects_scan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to scan projects: {str(e)}")


class EpicTaskResponse(BaseModel):
    """Single task response."""
    id: str
    epic_id: str
    type: str
    title: str
    description: str
    status: str
    dependencies: List[str]
    estimated_minutes: int
    actual_minutes: Optional[int] = None
    error_message: Optional[str] = None
    output_files: List[str] = []
    related_requirements: List[str] = []
    related_user_stories: List[str] = []
    tested: bool = False
    user_fix_instructions: Optional[str] = None


class EpicTaskListResponse(BaseModel):
    """Task list response for an epic."""
    epic_id: str
    epic_name: str
    tasks: List[EpicTaskResponse]
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    progress_percent: float
    estimated_total_minutes: int
    run_count: int
    last_run_at: Optional[str] = None


class RunEpicRequest(BaseModel):
    """Request to run an epic."""
    project_path: str
    max_parallel_tasks: int = 1  # 1=sequential (default), 2-5=parallel


class TaskRerunRequest(BaseModel):
    """Request to rerun a single task."""
    project_path: str
    fix_instructions: Optional[str] = None


class FixTaskRequest(BaseModel):
    """Request to fix a failed task using CLI (Kilo/Claude)."""
    task_id: str
    epic_id: str = ""
    error_message: str = ""
    project_path: str = "/data/projects/whatsapp-messaging-service"
    create_pr: bool = True  # Auto-create PR after successful fix


class CreatePRRequest(BaseModel):
    """Request to create a GitHub PR from generated/fixed code."""
    project_path: str = "/data/projects/whatsapp-messaging-service"
    branch_name: str = ""  # Auto-generated if empty
    title: str = ""  # Auto-generated if empty
    body: str = ""
    base_branch: str = "main"
    max_retries: int = 3


class GenerateTaskListsRequest(BaseModel):
    """Request to generate task lists."""
    project_path: str


class ChatRequest(BaseModel):
    """Request for interactive Claude chat (Cursor-like)."""
    message: str
    project_path: str
    output_dir: str
    history: list = []


@router.get("/epics", response_model=EpicListResponse)
async def get_epics(project_path: str = Query(..., description="Path to the project")):
    """
    Get all epics from a project.

    Parses the user_stories.md file and extracts epic information.
    """
    try:
        # Import the epic parser
        import sys
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_parser import EpicParser

        parser = EpicParser(project_path)
        epics = parser.parse_all_epics()

        epic_responses = [
            EpicResponse(
                id=e.id,
                name=e.name,
                description=e.description[:500] if e.description else "",
                status=e.status,
                progress_percent=e.progress_percent,
                user_stories=e.user_stories,
                requirements=e.requirements,
                entities=e.entities,
                api_endpoints=e.api_endpoints,
                last_run_at=e.last_run_at,
                run_count=e.run_count,
            )
            for e in epics
        ]

        logger.info("epics_fetched", project_path=project_path, count=len(epics))

        return EpicListResponse(
            project_path=project_path,
            total_epics=len(epics),
            epics=epic_responses,
        )

    except FileNotFoundError as e:
        logger.error("epics_fetch_failed", project_path=project_path, error=str(e))
        raise HTTPException(status_code=404, detail=f"Project not found: {str(e)}")
    except Exception as e:
        logger.error("epics_fetch_failed", project_path=project_path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch epics: {str(e)}")


@router.get("/epic/{epic_id}/tasks", response_model=EpicTaskListResponse)
async def get_epic_tasks(
    epic_id: str,
    project_path: str = Query(..., description="Path to the project")
):
    """
    Get tasks for a specific epic.

    Returns the task list if it exists, or generates it on-demand.
    """
    try:
        import sys
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_task_generator import EpicTaskGenerator

        generator = EpicTaskGenerator(project_path)

        # Try to load existing tasks first
        task_list = generator.load_epic_tasks(epic_id)

        # If no existing tasks, generate them
        if not task_list:
            task_list = generator.generate_tasks_for_epic(epic_id)
            generator.save_epic_tasks(epic_id)

        task_responses = [
            EpicTaskResponse(
                id=t.id,
                epic_id=t.epic_id,
                type=t.type,
                title=t.title,
                description=t.description,
                status=t.status,
                dependencies=t.dependencies,
                estimated_minutes=t.estimated_minutes,
                actual_minutes=t.actual_minutes,
                error_message=t.error_message,
            )
            for t in task_list.tasks
        ]

        logger.info("epic_tasks_fetched", epic_id=epic_id, task_count=len(task_responses))

        return EpicTaskListResponse(
            epic_id=task_list.epic_id,
            epic_name=task_list.epic_name,
            tasks=task_responses,
            total_tasks=task_list.total_tasks,
            completed_tasks=task_list.completed_tasks,
            failed_tasks=task_list.failed_tasks,
            progress_percent=task_list.progress_percent,
            estimated_total_minutes=task_list.estimated_total_minutes,
            run_count=task_list.run_count,
            last_run_at=task_list.last_run_at,
        )

    except ValueError as e:
        logger.error("epic_tasks_fetch_failed", epic_id=epic_id, error=str(e))
        raise HTTPException(status_code=404, detail=f"Epic not found: {str(e)}")
    except Exception as e:
        logger.error("epic_tasks_fetch_failed", epic_id=epic_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch epic tasks: {str(e)}")


@router.post("/epic/{epic_id}/run", response_model=SuccessResponse)
async def run_epic(epic_id: str, request: RunEpicRequest):
    """
    Start running an epic with LLM code generation.

    This initiates the actual code generation process for all tasks in the epic
    using the EpicOrchestrator and TaskExecutor with Claude Code Tool.
    Progress updates are sent via WebSocket.
    """
    try:
        import sys
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_orchestrator import EpicOrchestrator

        # Load SoM bridge config from society_defaults.json
        som_config = {}
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "society_defaults.json"
        if config_path.exists():
            try:
                import json as _json
                som_config = _json.loads(config_path.read_text(encoding="utf-8")).get("som_bridge", {})
            except Exception:
                pass

        # Create orchestrator with event bus for WebSocket updates
        # max_parallel_tasks: 1=sequential (default), 2-5=parallel execution
        # enable_som=True activates convergence loop (validate→fix→re-run)
        orchestrator = EpicOrchestrator(
            project_path=request.project_path,
            event_bus=_event_bus,
            max_parallel_tasks=request.max_parallel_tasks,
            enable_som=True,
            som_config=som_config,
        )

        logger.info(
            "epic_orchestrator_created",
            epic_id=epic_id,
            max_parallel=request.max_parallel_tasks
        )

        # Store orchestrator reference for checkpoint approval
        global _epic_orchestrators
        if '_epic_orchestrators' not in globals():
            _epic_orchestrators = {}
        _epic_orchestrators[epic_id] = orchestrator

        # Run epic in background task
        asyncio.create_task(_run_epic_background(epic_id, orchestrator))

        logger.info("epic_run_started", epic_id=epic_id, project_path=request.project_path)

        return SuccessResponse(success=True)

    except Exception as e:
        logger.error("epic_run_failed", epic_id=epic_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


# Global orchestrator storage for checkpoint approval
_epic_orchestrators: dict = {}


async def _run_epic_background(epic_id: str, orchestrator):
    """Background task to run epic execution + MCMP post-epic verification."""
    try:
        result = await orchestrator.run_epic(epic_id)

        # Publish completion event
        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.GENERATION_COMPLETE if result.success else EventType.BUILD_FAILED,
                source="epic_orchestrator",
                data={
                    "epic_id": epic_id,
                    "success": result.success,
                    "completed_tasks": result.completed_tasks,
                    "failed_tasks": result.failed_tasks,
                    "duration_seconds": result.duration_seconds,
                    "error": result.error,
                }
            ))

        logger.info(
            "epic_run_completed",
            epic_id=epic_id,
            success=result.success,
            completed=result.completed_tasks,
            failed=result.failed_tasks,
        )

        # --- MCMP Post-Epic Verification ---
        try:
            await _mcmp_post_epic_verify(epic_id, result)
        except Exception as ve:
            logger.warning("mcmp_post_epic_verify_error", epic_id=epic_id, error=str(ve))

    except Exception as e:
        logger.error("epic_run_background_failed", epic_id=epic_id, error=str(e))

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.BUILD_FAILED,
                source="epic_orchestrator",
                data={"epic_id": epic_id, "error": str(e)}
            ))


async def _mcmp_post_epic_verify(epic_id: str, result):
    """Run MCMP 200-agent swarm to verify epic completeness, post to Discord."""
    from src.services.mcmp_prerun import get_prerun

    prerun = get_prerun()

    # Re-index project to pick up newly generated files
    doc_count = await prerun.index_project()
    logger.info("mcmp_post_verify_indexed", epic_id=epic_id, documents=doc_count)

    # Extract expected requirements from task names
    requirements = []
    if hasattr(result, 'task_results'):
        for tr in result.task_results:
            if hasattr(tr, 'task_name') and tr.task_name:
                requirements.append(tr.task_name)

    # Run completeness check
    verify = await prerun.verify_epic_completeness(
        epic_id=epic_id,
        requirements=requirements or None,
    )

    coverage = verify.get("coverage", 0)
    missing = verify.get("missing", [])
    is_complete = verify.get("complete", False)

    logger.info(
        "mcmp_post_verify_done",
        epic_id=epic_id,
        coverage=coverage,
        missing_count=len(missing),
        complete=is_complete,
    )

    # Post result to Discord
    try:
        from src.tools.discord_agent import DiscordAgent
        bot_token = get_secret("discord_bot_token")
        ch_done = os.environ.get("DISCORD_CH_DONE", "1484193417381679225")

        if bot_token:
            agent = DiscordAgent(bot_token=bot_token, channel_id=ch_done)

            if is_complete:
                msg = (
                    "**MCMP VERIFICATION PASSED**\n"
                    "Epic: `%s`\n"
                    "Coverage: **%.0f%%**\n"
                    "All requirements verified by 200-agent swarm."
                    % (epic_id, coverage * 100)
                )
            else:
                missing_list = "\n".join("- %s" % m for m in missing[:10])
                msg = (
                    "**MCMP VERIFICATION INCOMPLETE**\n"
                    "Epic: `%s`\n"
                    "Coverage: **%.0f%%**\n"
                    "Missing:\n%s\n"
                    "Action: Re-run generation for missing items."
                    % (epic_id, coverage * 100, missing_list)
                )

            await agent.send(msg)
            logger.info("mcmp_verify_posted_to_discord", epic_id=epic_id)

            # If incomplete, also post to #fixes for the fix agent to pick up
            if not is_complete and missing:
                ch_fixes = os.environ.get("DISCORD_CH_FIXES", "1484193412679733302")
                fix_agent = DiscordAgent(bot_token=bot_token, channel_id=ch_fixes)
                for m in missing[:5]:
                    fix_msg = (
                        "TYPE=FIX_NEEDED\n"
                        "EPIC=%s\n"
                        "TASK=VERIFY-%s\n"
                        "ERROR=Missing implementation: %s\n"
                        "ACTION=CODE"
                        % (epic_id, m.replace(" ", "-")[:30], m)
                    )
                    await fix_agent.send(fix_msg)
                logger.info("mcmp_missing_posted_to_fixes", count=min(5, len(missing)))
    except Exception as de:
        logger.warning("mcmp_discord_post_failed", error=str(de))


@router.post("/epic/{epic_id}/rerun", response_model=SuccessResponse)
async def rerun_epic(epic_id: str, request: RunEpicRequest):
    """
    Rerun an epic, resetting all tasks to pending first.

    This allows re-executing a previously completed or failed epic.
    """
    try:
        import sys
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_task_generator import EpicTaskGenerator

        generator = EpicTaskGenerator(request.project_path)

        # Reset tasks
        generator.reset_epic_tasks(epic_id)

        # Publish event to start epic generation
        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.GENERATION_REQUESTED,
                source="dashboard",
                data={
                    "epic_id": epic_id,
                    "project_path": request.project_path,
                    "action": "rerun_epic",
                }
            ))

        logger.info("epic_rerun_started", epic_id=epic_id, project_path=request.project_path)

        return SuccessResponse(success=True)

    except Exception as e:
        logger.error("epic_rerun_failed", epic_id=epic_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


# =============================================================================
# Single-Task Rerun
# =============================================================================

@router.post("/epic/{epic_id}/task/{task_id}/rerun", response_model=SuccessResponse)
async def rerun_task(epic_id: str, task_id: str, request: TaskRerunRequest):
    """
    Rerun a single task within an epic, optionally with user fix instructions.

    The fix_instructions are injected into the LLM prompt for the next execution.
    """
    try:
        import sys
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_orchestrator import EpicOrchestrator

        global _epic_orchestrators

        orchestrator = _epic_orchestrators.get(epic_id)

        if not orchestrator:
            # Load SoM config
            som_config = {}
            config_path = engine_root / "config" / "society_defaults.json"
            if config_path.exists():
                try:
                    import json as _json
                    som_config = _json.loads(config_path.read_text(encoding="utf-8")).get("som_bridge", {})
                except Exception:
                    pass

            orchestrator = EpicOrchestrator(
                project_path=request.project_path,
                enable_som=False,
                som_config=som_config,
            )
            _epic_orchestrators[epic_id] = orchestrator

        # Run single task rerun in background
        asyncio.create_task(
            _rerun_task_background(epic_id, task_id, orchestrator, request.fix_instructions)
        )

        logger.info("task_rerun_started", epic_id=epic_id, task_id=task_id,
                     has_fix_instructions=bool(request.fix_instructions))

        return SuccessResponse(success=True)

    except Exception as e:
        logger.error("task_rerun_failed", epic_id=epic_id, task_id=task_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


async def _rerun_task_background(
    epic_id: str, task_id: str, orchestrator, fix_instructions: str = None
):
    """Background task for single-task rerun."""
    try:
        result = await orchestrator.rerun_single_task(epic_id, task_id, fix_instructions)

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.GENERATION_COMPLETE,
                source="epic_orchestrator",
                data={
                    "epic_id": epic_id,
                    "task_id": task_id,
                    "action": "task_rerun",
                    "success": result.success,
                }
            ))
    except Exception as e:
        logger.error("task_rerun_background_failed", epic_id=epic_id,
                     task_id=task_id, error=str(e))


# =============================================================================
# Fix Task via CLI (Kilo/Claude) — reads files, writes fix, retests
# =============================================================================


@router.post("/fix-task")
async def fix_task(request: FixTaskRequest):
    """
    Fix a failed task using Kilo/Claude CLI with MCP tools.

    The CLI has filesystem access and can read the source code,
    understand the error, write the fix directly, and retest.
    """
    asyncio.create_task(_fix_task_loop(request))
    return SuccessResponse(success=True)


async def _fix_task_loop(request: FixTaskRequest):
    """Background: CLI fix → rebuild → retest, up to max_retries."""
    import shutil

    task_id = request.task_id
    epic_id = request.epic_id or _extract_epic_id(task_id)
    project_path = request.project_path
    error = request.error_message

    # Determine which CLI to use based on active backend
    backend = _active_backend.get("name", "openrouter")

    for attempt in range(1, request.max_retries + 1):
        logger.info("fix_task_attempt", task_id=task_id, attempt=attempt,
                     backend=backend, max=request.max_retries)

        # 1. Build fix prompt with full context
        fix_prompt = _build_fix_prompt(task_id, epic_id, error, project_path, attempt)

        # 2. Run CLI to apply fix
        try:
            fix_result = await _run_cli_fix(fix_prompt, project_path, backend)
        except Exception as e:
            logger.error("fix_cli_failed", task_id=task_id, error=str(e))
            error = "CLI fix failed: %s" % str(e)[:300]
            continue

        if not fix_result.get("success"):
            error = fix_result.get("error", "CLI returned failure")
            logger.warning("fix_attempt_failed", task_id=task_id,
                           attempt=attempt, error=error[:200])
            continue

        # 3. Verify fix: run build check
        verify_result = await _verify_fix(project_path)
        if verify_result.get("success"):
            logger.info("fix_task_success", task_id=task_id, attempt=attempt)

            # Post success to Discord
            await _post_fix_result(task_id, attempt, True)

            # Auto-create PR if enabled
            if request.create_pr:
                pr_url = await _create_pr_after_fix(task_id, project_path, attempt)
                if pr_url:
                    logger.info("fix_pr_created", task_id=task_id, pr_url=pr_url)
            return

        # Build still failing — use new error for next attempt
        error = verify_result.get("error", "Build verification failed")
        logger.warning("fix_verify_failed", task_id=task_id,
                       attempt=attempt, error=error[:200])

    # All retries exhausted
    logger.error("fix_task_exhausted", task_id=task_id,
                 attempts=request.max_retries)
    await _post_fix_result(task_id, request.max_retries, False, error)


async def _create_pr_after_fix(task_id: str, project_path: str, attempt: int):
    """Create a GitHub PR after a successful fix."""
    import asyncio as _asyncio
    import datetime

    branch_name = "fix/%s-%s" % (
        task_id.lower().replace(" ", "-"),
        datetime.datetime.now().strftime("%Y%m%d-%H%M"),
    )

    try:
        env = os.environ.copy()
        # Inject secrets from Docker /run/secrets/ if not in env
        for secret_name, env_key in [
            ("github_token", "GITHUB_TOKEN"),
            ("openai_api_key", "OPENAI_API_KEY"),
        ]:
            if not env.get(env_key):
                secret_path = f"/run/secrets/{secret_name}"
                if os.path.exists(secret_path):
                    env[env_key] = open(secret_path).read().strip()

        # Create branch + commit
        cmds = [
            (["git", "checkout", "-b", branch_name], "create branch"),
            (["git", "add", "-A"], "stage files"),
            (["git", "commit", "-m", "fix(%s): auto-fix after %d attempt(s)" % (task_id, attempt)], "commit"),
            (["git", "push", "-u", "origin", branch_name], "push"),
        ]

        for cmd, label in cmds:
            process = await _asyncio.create_subprocess_exec(
                *cmd,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.PIPE,
                cwd=project_path,
                env=env,
            )
            stdout, stderr = await _asyncio.wait_for(process.communicate(), timeout=30)
            if process.returncode != 0 and label != "commit":
                # commit may fail if nothing to commit — that's OK
                error_text = (stderr or stdout or b"").decode("utf-8", errors="replace")
                logger.warning("pr_git_%s_failed" % label, error=error_text[:200])
                if label == "push":
                    return None  # Can't create PR without push

        # Create PR via gh CLI
        title = "fix(%s): Auto-fix" % task_id
        body = (
            "## Auto-Fix PR\n\n"
            "**Task:** `%s`\n"
            "**Fixed after:** %d attempt(s)\n"
            "**Branch:** `%s`\n\n"
            "Generated by Coding Engine Fix Loop.\n"
        ) % (task_id, attempt, branch_name)

        process = await _asyncio.create_subprocess_exec(
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--base", "main",
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=project_path,
            env=env,
        )
        stdout, stderr = await _asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode == 0:
            pr_url = stdout.decode("utf-8", errors="replace").strip()
            logger.info("pr_created", task_id=task_id, url=pr_url)

            # Post to Discord #prs channel
            await _post_pr_notification(task_id, pr_url, branch_name, attempt)
            return pr_url
        else:
            error_text = (stderr or stdout or b"").decode("utf-8", errors="replace")
            logger.warning("gh_pr_create_failed", error=error_text[:300])
            return None

    except Exception as e:
        logger.error("create_pr_failed", task_id=task_id, error=str(e))
        return None


async def _post_pr_notification(task_id: str, pr_url: str, branch: str,
                                 attempts: int):
    """Post PR notification to Discord #prs channel."""
    try:
        from src.tools.discord_agent import DiscordAgent

        prs_channel = os.environ.get("DISCORD_CH_PRS", "")
        dev_channel = os.environ.get("DISCORD_CH_DEV_TASKS", "1484193408955322399")
        token = get_secret("discord_bot_token")
        if not token:
            return

        msg = (
            "**NEW PR** | `%s`\n"
            "Branch: `%s`\n"
            "Fixed after %d attempt(s)\n"
            "Link: %s\n"
            "**Action:** `REVIEW_NEEDED`"
        ) % (task_id, branch, attempts, pr_url)

        # Post to #prs channel if configured
        if prs_channel:
            discord_prs = DiscordAgent(bot_token=token, channel_id=prs_channel)
            await discord_prs.send(msg)

        # Also post to #dev-tasks
        discord_dev = DiscordAgent(bot_token=token, channel_id=dev_channel)
        await discord_dev.send(msg)

    except Exception as e:
        logger.error("post_pr_notification_failed", error=str(e))


def _extract_epic_id(task_id: str) -> str:
    """EPIC-003-SETUP-env → EPIC-003"""
    parts = task_id.split("-")
    if len(parts) >= 2 and parts[0] == "EPIC":
        return "%s-%s" % (parts[0], parts[1])
    return ""


def _build_fix_prompt(task_id: str, epic_id: str, error: str,
                      project_path: str, attempt: int) -> str:
    """Build a rich prompt for the CLI to fix the task."""
    return (
        "You are fixing a failed code generation task. "
        "Read the relevant source files, understand the error, "
        "and write the corrected code directly to the files.\n\n"
        "## Task\n"
        "ID: %s\n"
        "Epic: %s\n"
        "Project: %s\n"
        "Attempt: %d\n\n"
        "## Error\n"
        "```\n%s\n```\n\n"
        "## Instructions\n"
        "1. Read the files mentioned in the error\n"
        "2. Understand what went wrong\n"
        "3. Write the corrected code to the file(s)\n"
        "4. Make minimal changes — fix only the error\n"
        "5. Do NOT create new files unless absolutely necessary\n"
    ) % (task_id, epic_id, project_path, attempt, error[:2000])


async def _run_cli_fix(prompt: str, project_path: str, backend: str) -> dict:
    """Run fix via CLI or OpenAI API fallback."""
    import asyncio as _asyncio
    from src.config import get_settings

    settings = get_settings()

    # Try OpenAI API first (most reliable — no CLI dependency issues)
    openai_key = get_secret("openai_api_key")
    if openai_key and backend in ("openai", "openrouter", ""):
        result = await _run_openai_fix(prompt, project_path, openai_key)
        if result.get("success"):
            return result
        logger.warning("openai_fix_fallback", error=result.get("error", "")[:100])

    # Fallback to CLI
    if backend == "kilo":
        model = settings.kilo_model or "openrouter/openrouter/free"
        cmd = ["kilo", "run", "--auto", "--model", model, prompt]
    elif backend == "claude":
        cmd = ["claude", "--dangerously-skip-permissions",
               "--output-format", "json", "--max-turns", "10", "-p", prompt]
    else:
        # Kilo with free model
        cmd = ["kilo", "run", "--auto", "--model", "openrouter/qwen/qwen3-coder:free", prompt]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CLAUDECODE", None)

    timeout = 300  # 5 min per fix attempt

    try:
        process = await _asyncio.create_subprocess_exec(
            *cmd,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=project_path,
            env=env,
        )
        stdout, stderr = await _asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        if process.returncode == 0:
            return {"success": True, "output": stdout_text[:2000]}
        else:
            return {
                "success": False,
                "error": "Exit %d: %s" % (
                    process.returncode,
                    (stderr_text or stdout_text)[:500]
                ),
            }
    except _asyncio.TimeoutError:
        return {"success": False, "error": "CLI timeout after %ds" % timeout}
    except Exception as e:
        return {"success": False, "error": str(e)[:300]}


def _get_fix_model() -> str:
    """Get the model name for code fixing from engine_settings.yml."""
    try:
        from src.engine_settings import get_setting
        return get_setting("models.fixing.model", "gpt-5.4")
    except Exception:
        return "gpt-5.4"


async def _run_openai_fix(prompt: str, project_path: str, api_key: str) -> dict:
    """Fix task via OpenAI API (GPT-5.4) — writes files directly."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": "Bearer %s" % api_key},
                json={
                    "model": _get_fix_model(),
                    "messages": [
                        {"role": "system", "content": (
                            "You are a code fixer. Given an error and project context, "
                            "output ONLY a JSON array of file fixes: "
                            '[{"file": "path/to/file.ts", "content": "full corrected file content"}]. '
                            "No explanations, no markdown — just the JSON array."
                        )},
                        {"role": "user", "content": prompt[:8000]},
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.2,
                },
            )

            if resp.status_code != 200:
                return {"success": False, "error": "OpenAI %d: %s" % (resp.status_code, resp.text[:200])}

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse file fixes from response
            try:
                # Strip markdown fences if present
                clean = content.strip()
                if clean.startswith("```"):
                    clean = "\n".join(clean.split("\n")[1:])
                if clean.endswith("```"):
                    clean = clean.rsplit("```", 1)[0]
                fixes = json.loads(clean.strip())
            except (json.JSONDecodeError, ValueError):
                return {"success": False, "error": "Could not parse fix JSON: %s" % content[:200]}

            if not isinstance(fixes, list):
                fixes = [fixes]

            # Write fixes to disk
            files_written = 0
            for fix in fixes:
                file_path = fix.get("file", "")
                file_content = fix.get("content", "")
                if not file_path or not file_content:
                    continue

                full_path = Path(project_path) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(file_content, encoding="utf-8")
                files_written += 1
                logger.info("openai_fix_wrote", file=file_path)

            if files_written > 0:
                return {"success": True, "output": "Fixed %d files via OpenAI" % files_written}
            return {"success": False, "error": "No files to write from OpenAI response"}

    except Exception as e:
        return {"success": False, "error": "OpenAI fix error: %s" % str(e)[:200]}


async def _verify_fix(project_path: str) -> dict:
    """Run build check after fix to verify it works."""
    import asyncio as _asyncio

    # Try npm/pnpm build in the project
    for build_cmd in [
        ["npm", "run", "build", "--if-present"],
        ["npx", "tsc", "--noEmit"],
    ]:
        try:
            process = await _asyncio.create_subprocess_exec(
                *build_cmd,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.PIPE,
                cwd=project_path,
            )
            stdout, stderr = await _asyncio.wait_for(
                process.communicate(), timeout=120
            )
            if process.returncode != 0:
                error_text = (stderr or stdout or b"").decode("utf-8", errors="replace")
                return {"success": False, "error": error_text[:1000]}
        except _asyncio.TimeoutError:
            return {"success": False, "error": "Build timeout"}
        except FileNotFoundError:
            continue  # npm not found, try next

    return {"success": True}


async def _post_fix_result(task_id: str, attempts: int, success: bool,
                           error: str = ""):
    """Post fix result to Discord #dev-tasks."""
    import json
    try:
        from src.tools.discord_agent import DiscordAgent

        fixes_ch = os.environ.get("DISCORD_CH_DEV_TASKS", "1484193408955322399")
        token = get_secret("discord_bot_token")
        if not token:
            return

        discord = DiscordAgent(bot_token=token, channel_id=fixes_ch)

        if success:
            msg = (
                "**FIX_APPLIED** | `%s`\n"
                "Fixed after %d attempt(s)\n"
                "**Action:** `RETEST`\n"
                "||`%s`||"
            ) % (
                task_id, attempts,
                json.dumps({"type": "FIX_APPLIED", "task": task_id, "action": "RETEST"}),
            )
        else:
            msg = (
                "**FIX_FAILED** | `%s`\n"
                "All %d attempts exhausted\n"
                "```\n%s\n```\n"
                "**Action:** `MANUAL_REVIEW`\n"
                "||`%s`||"
            ) % (
                task_id, attempts, error[:500],
                json.dumps({"type": "FIX_FAILED", "task": task_id, "action": "MANUAL_REVIEW"}),
            )

        await discord.send(msg[:2000])
    except Exception as e:
        logger.error("post_fix_result_failed", error=str(e))


# =============================================================================
# Sync task results from generation subprocess to DB
# =============================================================================


class SyncTasksRequest(BaseModel):
    output_dir: str = ""


# ── Fix All (Smart Fix — same logic as Discord !fixall) ────

# ── Trigger Bot Command (UI → Discord Bot) ────────────────

class TriggerBotCommandRequest(BaseModel):
    command: str = "fixall"
    project_name: str = ""


@router.post("/trigger-bot-command")
async def trigger_bot_command(request: TriggerBotCommandRequest):
    """Send a !command to Discord channel so the bot picks it up."""
    import httpx

    bot_token = get_secret("discord_bot_token_analyzer")
    channel_id = os.environ.get("DISCORD_CH_DEV_TASKS", "")

    if not bot_token or not channel_id:
        return {"success": False, "error": "Missing DISCORD_BOT_TOKEN_ANALYZER or DISCORD_CH_DEV_TASKS env vars"}

    cmd = "!%s" % request.command
    if request.project_name:
        cmd += " %s" % request.project_name

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://discord.com/api/v10/channels/%s/messages" % channel_id,
                headers={"Authorization": "Bot %s" % bot_token},
                json={"content": cmd},
            )
            if resp.status_code in (200, 201):
                return {"success": True, "message": "Sent '%s' to Discord" % cmd}
            return {"success": False, "error": "Discord %d: %s" % (resp.status_code, resp.text[:200])}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


class FixAllRequest(BaseModel):
    project_name: str = ""


@router.post("/fixall")
async def fixall_endpoint(request: FixAllRequest, db: AsyncSession = Depends(get_db)):
    """Smart fix ALL failed tasks — groups by type, uses optimal strategy per group.
    Also dispatches to Orchestrator which notifies OpenClaw bots via Discord."""
    import asyncio as _aio

    # Notify orchestrator (posts to Discord channels)
    try:
        from src.services.orchestrator import get_orchestrator
        from src.engine_settings import load_settings
        orch = get_orchestrator(settings=load_settings())
        asyncio.create_task(orch.trigger_fixall(request.project_name or "", 0))
    except Exception as e:
        logger.warning("Orchestrator dispatch failed: %s", e)

    try:
        from src.engine_settings import get_project
        proj = get_project(request.project_name)
    except Exception:
        proj = {}

    # Get job_id
    job_id = proj.get("db_job_id", 24) if proj else 24
    output_dir = proj.get("output_dir", "/app/output") if proj else "/app/output"
    db_schema = proj.get("db_schema", "coding_engine") if proj else "coding_engine"

    # Get all failed tasks
    from sqlalchemy import text as sql_text
    result = await db.execute(
        sql_text("SELECT task_id, title, status_message, task_type FROM tasks WHERE job_id = :jid AND status = 'FAILED' ORDER BY task_id"),
        {"jid": job_id},
    )
    failed_tasks = [dict(r._mapping) for r in result.fetchall()]

    if not failed_tasks:
        return {"success": True, "message": "No failed tasks", "fixed": 0, "total": 0}

    # Group by type
    migrations = [t for t in failed_tasks if "migration" in t["task_id"].lower()]
    lint_tasks = [t for t in failed_tasks if "lint" in t["task_id"].lower() or "eslint" in t["task_id"].lower()]
    build_tasks = [t for t in failed_tasks if "build" in t["task_id"].lower() or "verify" in t["task_id"].lower()]
    code_tasks = [t for t in failed_tasks if t not in migrations and t not in lint_tasks and t not in build_tasks]

    fixed = 0
    errors = []
    db_url = "postgresql://postgres:postgres@postgres:5432/%s?schema=public" % db_schema

    # Phase 1: Prisma migrations
    if migrations:
        try:
            push_result = await _aio.create_subprocess_exec(
                "npx", "prisma", "db", "push", "--accept-data-loss",
                cwd=output_dir,
                env={**os.environ, "DATABASE_URL": db_url},
                stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.PIPE,
            )
            stdout, stderr = await _aio.wait_for(push_result.communicate(), timeout=120)
            if push_result.returncode == 0:
                # Mark all migration tasks as completed
                for t in migrations:
                    await db.execute(sql_text(
                        "UPDATE tasks SET status='COMPLETED', status_message='Fixed: prisma db push' WHERE task_id=:tid AND job_id=:jid"
                    ), {"tid": t["task_id"], "jid": job_id})
                fixed += len(migrations)
            else:
                err = (stderr or stdout or b"").decode("utf-8", errors="replace")[:300]
                errors.append("Prisma push failed: %s" % err)
        except Exception as e:
            errors.append("Prisma error: %s" % str(e)[:200])

    # Phase 2: ESLint
    if lint_tasks:
        try:
            lint_result = await _aio.create_subprocess_exec(
                "npx", "eslint", "--fix", "src/**/*.{ts,tsx}",
                cwd=output_dir,
                stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.PIPE,
            )
            await _aio.wait_for(lint_result.communicate(), timeout=60)
            for t in lint_tasks:
                await db.execute(sql_text(
                    "UPDATE tasks SET status='COMPLETED', status_message='Fixed: eslint --fix' WHERE task_id=:tid AND job_id=:jid"
                ), {"tid": t["task_id"], "jid": job_id})
            fixed += len(lint_tasks)
        except Exception as e:
            errors.append("ESLint error: %s" % str(e)[:200])

    # Phase 3: Build
    if build_tasks:
        try:
            build_result = await _aio.create_subprocess_exec(
                "npm", "run", "build",
                cwd=output_dir,
                env={**os.environ, "DATABASE_URL": db_url},
                stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.PIPE,
            )
            stdout, stderr = await _aio.wait_for(build_result.communicate(), timeout=120)
            if build_result.returncode == 0:
                for t in build_tasks:
                    await db.execute(sql_text(
                        "UPDATE tasks SET status='COMPLETED', status_message='Fixed: build passed' WHERE task_id=:tid AND job_id=:jid"
                    ), {"tid": t["task_id"], "jid": job_id})
                fixed += len(build_tasks)
            else:
                errors.append("Build failed")
        except Exception as e:
            errors.append("Build error: %s" % str(e)[:200])

    # Phase 4: Code tasks via GPT
    if code_tasks:
        for t in code_tasks:
            try:
                fix_result = await _run_openai_fix(
                    "Fix this failed task: %s\nError: %s" % (t["title"], t.get("status_message", "unknown")),
                    output_dir, get_secret("openai_api_key"),
                )
                if fix_result.get("success"):
                    await db.execute(sql_text(
                        "UPDATE tasks SET status='COMPLETED', status_message='Fixed: GPT code fix' WHERE task_id=:tid AND job_id=:jid"
                    ), {"tid": t["task_id"], "jid": job_id})
                    fixed += 1
            except Exception as e:
                errors.append("GPT fix failed for %s: %s" % (t["task_id"], str(e)[:100]))

    await db.commit()

    return {
        "success": True,
        "fixed": fixed,
        "total": len(failed_tasks),
        "breakdown": {
            "migrations": len(migrations),
            "lint": len(lint_tasks),
            "build": len(build_tasks),
            "code": len(code_tasks),
        },
        "errors": errors,
    }


class FixPrismaRequest(BaseModel):
    project_dir: str = ""
    db_url: str = ""
    max_attempts: int = 5


@router.post("/fix-prisma-schema")
async def fix_prisma_schema(request: FixPrismaRequest):
    """Autonomously fix Prisma schema: read → GPT fix → write → prisma push → repeat until success."""
    import asyncio as _aio

    # Resolve from engine_settings if not provided
    project_dir = request.project_dir
    db_url = request.db_url
    if not project_dir or not db_url:
        try:
            from src.engine_settings import get_project
            proj = get_project()
            if not project_dir:
                project_dir = proj.get("output_dir", "/app/output")
            if not db_url:
                db_schema = proj.get("db_schema", "coding_engine")
                db_url = "postgresql://postgres:postgres@postgres:5432/%s?schema=public" % db_schema
        except Exception:
            if not project_dir:
                project_dir = "/app/output"
            if not db_url:
                db_url = "postgresql://postgres:postgres@postgres:5432/coding_engine?schema=public"
    schema_path = Path(project_dir) / "prisma" / "schema.prisma"
    root_schema_path = Path(project_dir) / "schema.prisma"
    openai_key = get_secret("openai_api_key")

    if not openai_key:
        return {"success": False, "error": "No OPENAI_API_KEY"}

    for attempt in range(1, request.max_attempts + 1):
        # 1. Run prisma db push
        env = os.environ.copy()
        env["DATABASE_URL"] = db_url
        try:
            proc = await _aio.create_subprocess_exec(
                "npx", "prisma", "db", "push", "--accept-data-loss",
                cwd=project_dir, env=env,
                stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.STDOUT,
            )
            stdout, _ = await _aio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
        except Exception as e:
            output = str(e)

        if "in sync" in output or "already in sync" in output:
            # Also generate client
            try:
                gen_proc = await _aio.create_subprocess_exec(
                    "npx", "prisma", "generate",
                    cwd=project_dir, env=env,
                    stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.STDOUT,
                )
                await _aio.wait_for(gen_proc.communicate(), timeout=30)
            except Exception:
                pass
            return {"success": True, "attempt": attempt, "message": "Schema synced and client generated"}

        # 2. Push failed — read current schema
        current_schema = ""
        for sp in [schema_path, root_schema_path]:
            if sp.exists():
                current_schema = sp.read_text(encoding="utf-8")
                break

        if not current_schema:
            return {"success": False, "error": "No schema.prisma found", "attempt": attempt}

        # 3. GPT fix
        logger.info("prisma_fix_attempt", attempt=attempt, error=output[:200])
        import httpx
        try:
            async with httpx.AsyncClient(timeout=90) as gpt_client:
                gpt_resp = await gpt_client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % openai_key},
                    json={
                        "model": _get_fix_model(),
                        "messages": [
                            {"role": "developer", "content": (
                                "You are a Prisma schema expert. Fix ALL validation errors.\n\n"
                                "CRITICAL RULES for Prisma relations:\n"
                                "1. Every named @relation('X', fields: [...], references: [...]) on model A targeting model B "
                                "MUST have a reverse field on model B with @relation('X') (no fields/references on reverse side).\n"
                                "2. If model A has TWO fields pointing to model B, BOTH must be named relations with DIFFERENT names, "
                                "and model B must have TWO reverse fields with matching names.\n"
                                "3. Self-referencing relations (model message has reply_to -> message) MUST be named "
                                "and have a reverse array field on the same model.\n"
                                "4. Reverse fields for arrays use ModelName[], for optional use ModelName?.\n\n"
                                "Example of correct self-reference:\n"
                                "  reply_to    message? @relation('Replies', fields: [reply_to_id], references: [id])\n"
                                "  replies     message[] @relation('Replies')\n\n"
                                "Output ONLY the complete fixed schema.prisma. No markdown fences."
                            )},
                            {"role": "user", "content": (
                                "Fix this Prisma schema. Error:\n\n%s\n\nSchema:\n%s"
                            ) % (output[-3000:], current_schema)},
                        ],
                        "max_completion_tokens": 16000,
                    },
                )

            if gpt_resp.status_code != 200:
                return {"success": False, "error": "GPT API %d" % gpt_resp.status_code, "attempt": attempt}

            content = gpt_resp.json()["choices"][0]["message"]["content"]
            # Strip markdown fences
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:])
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()

            if "generator client" not in content:
                continue  # Bad response, retry

            # 4. Write fixed schema directly to disk
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(content, encoding="utf-8")
            if root_schema_path.exists():
                root_schema_path.write_text(content, encoding="utf-8")

            logger.info("prisma_schema_fixed_by_gpt", attempt=attempt, lines=len(content.splitlines()))

        except Exception as e:
            logger.warning("prisma_gpt_fix_error", attempt=attempt, error=str(e)[:200])
            continue

    return {"success": False, "error": "Failed after %d attempts" % request.max_attempts}


class BulkUpdateTaskStatusRequest(BaseModel):
    task_ids: list
    status: str = "COMPLETED"
    status_message: str = ""


@router.post("/bulk-update-task-status")
async def bulk_update_task_status(request: BulkUpdateTaskStatusRequest, db: AsyncSession = Depends(get_db)):
    """Update multiple tasks' status in one DB call."""
    try:
        from sqlalchemy import text
        count = 0
        for tid in request.task_ids:
            await db.execute(
                text("UPDATE tasks SET status = :status, status_message = :msg, updated_at = NOW() WHERE task_id = :tid"),
                {"status": request.status.upper(), "msg": request.status_message, "tid": tid},
            )
            count += 1
        await db.commit()
        return {"success": True, "updated": count}
    except Exception as e:
        return {"success": False, "error": str(e)[:200], "updated": 0}


class UpdateTaskStatusRequest(BaseModel):
    task_id: str
    status: str = "COMPLETED"
    status_message: str = ""


@router.post("/update-task-status")
async def update_task_status(request: UpdateTaskStatusRequest, db: AsyncSession = Depends(get_db)):
    """Update a single task's status in the DB."""
    try:
        from sqlalchemy import text
        await db.execute(
            text("UPDATE tasks SET status = :status, status_message = :msg, updated_at = NOW() WHERE task_id = :tid"),
            {"status": request.status.upper(), "msg": request.status_message, "tid": request.task_id},
        )
        await db.commit()
        return {"success": True, "task_id": request.task_id}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


@router.post("/sync-tasks")
async def sync_tasks(request: SyncTasksRequest, db: AsyncSession = Depends(get_db)):
    """
    Sync task results from generation subprocess (.task_results.json) to DB.
    Called automatically by run_generation.py after completion, or manually.
    """
    from sqlalchemy import text as sql_text

    output_dir = request.output_dir
    if not output_dir:
        try:
            from src.engine_settings import get_project
            proj = get_project()
            output_dir = proj.get("output_dir", "/app/output") if proj else "/app/output"
        except Exception:
            output_dir = "/app/output"

    task_results_file = Path(output_dir) / ".task_results.json"
    if not task_results_file.exists():
        return {"success": False, "error": "No .task_results.json found", "path": str(task_results_file)}

    try:
        results = json.loads(task_results_file.read_text(encoding="utf-8"))
        if not isinstance(results, list):
            return {"success": False, "error": "Invalid format — expected list"}

        # Map lowercase status to DB enum (UPPERCASE)
        STATUS_MAP = {
            "completed": "COMPLETED",
            "failed": "FAILED",
            "pending": "PENDING",
            "running": "RUNNING",
            "skipped": "CANCELLED",
            "blocked": "BLOCKED",
        }

        updated = 0
        for r in results:
            task_id = r.get("task_id", "")
            raw_status = r.get("status", "")
            error_msg = r.get("error_message", "")

            if not task_id or not raw_status:
                continue

            # Map to DB enum value
            db_status = STATUS_MAP.get(raw_status.lower(), raw_status.upper())

            # Update task in DB by task_id string
            result = await db.execute(
                sql_text(
                    "UPDATE tasks SET status = :status, status_message = :msg, "
                    "updated_at = NOW() "
                    "WHERE task_id = :task_id"
                ),
                {"status": db_status, "msg": error_msg[:500] if error_msg else None, "task_id": task_id},
            )
            if result.rowcount > 0:
                updated += 1

        await db.commit()
        logger.info("sync_tasks_complete", updated=updated, total=len(results))
        return {"success": True, "updated": updated, "total": len(results)}

    except Exception as e:
        logger.error("sync_tasks_failed", error=str(e))
        return {"success": False, "error": str(e)[:300]}


# =============================================================================
# Create PR (manual or from review-bot)
# =============================================================================


@router.post("/create-pr")
async def create_pr(request: CreatePRRequest):
    """Create a GitHub Pull Request from the current project state."""
    import datetime

    project_path = request.project_path
    branch = request.branch_name or "gen/%s" % datetime.datetime.now().strftime("%Y%m%d-%H%M")
    title = request.title or "Generated code: %s" % Path(project_path).name

    pr_url = await _create_pr_after_fix(
        task_id=Path(project_path).name,
        project_path=project_path,
        attempt=0,
    )

    if pr_url:
        return {"success": True, "pr_url": pr_url}
    return {"success": False, "error": "PR creation failed — check git setup and gh CLI"}


# =============================================================================
# Review PR (auto-review + merge)
# =============================================================================


@router.post("/review-pr")
async def review_pr(pr_url: str = "", project_path: str = "/data/projects/whatsapp-messaging-service"):
    """Auto-review a PR: run build + type-check, then approve/merge if passing."""
    import asyncio as _asyncio

    if not pr_url:
        return {"success": False, "error": "pr_url required"}

    # 1. Verify build passes
    verify_result = await _verify_fix(project_path)
    if not verify_result.get("success"):
        # Post review comment: failing
        await _post_review_result(pr_url, False, verify_result.get("error", ""))
        return {
            "success": False,
            "action": "changes_requested",
            "error": verify_result.get("error", "Build failed"),
        }

    # 2. Build passes → approve + merge
    try:
        # Approve PR
        env = os.environ.copy()
        process = await _asyncio.create_subprocess_exec(
            "gh", "pr", "review", pr_url, "--approve",
            "--body", "Auto-approved by Coding Engine Review Bot. Build and type-check passing.",
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=project_path,
            env=env,
        )
        await _asyncio.wait_for(process.communicate(), timeout=30)

        # Merge PR
        process = await _asyncio.create_subprocess_exec(
            "gh", "pr", "merge", pr_url, "--squash", "--delete-branch",
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=project_path,
            env=env,
        )
        stdout, stderr = await _asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode == 0:
            await _post_review_result(pr_url, True)
            return {"success": True, "action": "merged"}
        else:
            error_text = (stderr or stdout or b"").decode("utf-8", errors="replace")
            return {"success": False, "action": "merge_failed", "error": error_text[:300]}

    except Exception as e:
        return {"success": False, "action": "review_failed", "error": str(e)[:300]}


async def _post_review_result(pr_url: str, approved: bool, error: str = ""):
    """Post review result to Discord #prs channel."""
    try:
        from src.tools.discord_agent import DiscordAgent

        prs_channel = os.environ.get("DISCORD_CH_PRS", "")
        token = get_secret("discord_bot_token")
        if not token or not prs_channel:
            return

        if approved:
            msg = (
                "**PR MERGED** | %s\n"
                "Build + TypeCheck passing\n"
                "Auto-approved and squash-merged"
            ) % pr_url
        else:
            msg = (
                "**PR REJECTED** | %s\n"
                "Build failing:\n```\n%s\n```\n"
                "**Action:** `FIX_NEEDED`"
            ) % (pr_url, error[:500])

        discord = DiscordAgent(bot_token=token, channel_id=prs_channel)
        await discord.send(msg[:2000])
    except Exception as e:
        logger.error("post_review_result_failed", error=str(e))


# =============================================================================
# Claude Chat (Cursor-like interactive coding assistant)
# =============================================================================

@router.post("/chat")
async def claude_chat(request: ChatRequest):
    """Interactive chat with Claude during generation.

    Cursor-like flow: user message -> Claude CLI -> code suggestions -> response.
    Claude receives the user message plus project context (build errors, changed
    files) and can directly modify files in the output directory.
    """
    try:
        import sys as _sys
        engine_root = Path(__file__).parent.parent.parent.parent
        _sys.path.insert(0, str(engine_root))

        from src.tools.claude_code_tool import ClaudeCodeTool

        output_dir = request.output_dir
        if not Path(output_dir).is_absolute():
            output_dir = str(Path(request.project_path) / output_dir)

        tool = ClaudeCodeTool(working_dir=output_dir)

        # Build prompt with conversation history and context
        parts = []
        if request.history:
            parts.append("Conversation so far:")
            for msg in request.history[-10:]:  # Last 10 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                parts.append(f"  {role}: {content}")
            parts.append("")

        parts.append(f"User request: {request.message}")
        parts.append(f"\nWorking directory: {output_dir}")
        parts.append("Apply any code changes directly to the files.")

        prompt = "\n".join(parts)

        result = await tool.execute(
            prompt=prompt,
            agent_type="fixer",
        )

        # Extract modified/created file paths
        files_modified = []
        files_created = []
        for f in result.files:
            fp = f.path if hasattr(f, "path") else str(f)
            if Path(output_dir, fp).exists():
                files_modified.append(fp)
            else:
                files_created.append(fp)

        return {
            "success": result.success,
            "response": result.output or "",
            "files_modified": files_modified,
            "files_created": files_created,
            "error": result.error,
        }

    except Exception as e:
        logger.error("claude_chat_failed", error=str(e))
        return {
            "success": False,
            "response": "",
            "files_modified": [],
            "files_created": [],
            "error": str(e),
        }


# =============================================================================
# Debug Mode - Session Analysis & Fix-Task Generation
# =============================================================================

class DebugAnalyzeRequest(BaseModel):
    """Request to analyze a debug session and generate fix tasks."""
    project_id: str
    output_dir: str
    interactions: list = []  # List of {type, x, y, errorMessage, logContent, ...}


def _format_debug_errors(errors: list) -> str:
    """Format error interactions for the Claude analysis prompt."""
    if not errors:
        return "No errors recorded."
    lines = []
    for i, err in enumerate(errors, 1):
        msg = err.get("errorMessage") or err.get("logContent") or "Unknown error"
        src = err.get("sourceFile", "")
        ln = err.get("lineNumber", "")
        etype = err.get("errorType", err.get("logSource", "error"))
        loc = f" at {src}:{ln}" if src else ""
        lines.append(f"  {i}. [{etype}] {msg}{loc}")
    return "\n".join(lines)


def _format_debug_clicks(clicks: list) -> str:
    """Format click interactions for the Claude analysis prompt."""
    if not clicks:
        return "No click interactions recorded."
    lines = []
    for i, click in enumerate(clicks, 1):
        info = click.get("componentInfo", "")
        x = click.get("x", "?")
        y = click.get("y", "?")
        lines.append(f"  {i}. Click at ({x}%, {y}%) {info}")
    return "\n".join(lines)


def _parse_fix_tasks(output: str) -> list:
    """Parse Claude's response into fix task dicts."""
    import json as _json
    import re
    import uuid

    # Try to extract JSON array from the response
    # Claude may wrap it in markdown code blocks
    json_match = re.search(r'\[[\s\S]*?\]', output or "")
    if json_match:
        try:
            tasks = _json.loads(json_match.group())
            result = []
            for t in tasks:
                result.append({
                    "id": str(uuid.uuid4())[:8],
                    "title": t.get("title", "Fix task"),
                    "description": t.get("description", ""),
                    "error_type": t.get("error_type", t.get("errorType", "unknown")),
                    "affected_files": t.get("affected_files", t.get("affectedFiles", [])),
                    "suggested_fix": t.get("suggested_fix", t.get("suggestedFix", "")),
                    "severity": t.get("severity", "medium"),
                    "source_interactions": [],
                })
            return result
        except _json.JSONDecodeError:
            pass

    # Fallback: return a single generic task if we couldn't parse
    if output and output.strip():
        return [{
            "id": str(uuid.uuid4())[:8],
            "title": "Review debug session findings",
            "description": output[:500],
            "error_type": "analysis",
            "affected_files": [],
            "suggested_fix": output[:1000],
            "severity": "medium",
            "source_interactions": [],
        }]

    return []


@router.post("/debug/analyze")
async def analyze_debug_session(request: DebugAnalyzeRequest):
    """Analyze a debug session and generate fix tasks.

    Takes recorded interactions (clicks, errors, logs) and uses Claude
    to analyze patterns, identify root causes, and create actionable fix tasks.
    """
    try:
        import sys as _sys
        import uuid
        engine_root = Path(__file__).parent.parent.parent.parent
        _sys.path.insert(0, str(engine_root))

        from src.tools.claude_code_tool import ClaudeCodeTool

        output_dir = request.output_dir
        if not Path(output_dir).is_absolute():
            output_dir = str(Path(output_dir).resolve())

        # Separate errors/logs from clicks
        errors = [i for i in request.interactions if i.get("type") in ("error", "log")]
        clicks = [i for i in request.interactions if i.get("type") == "click"]

        if not errors and not clicks:
            return {"success": True, "fix_tasks": []}

        # Build analysis prompt
        prompt = f"""Analyze these debug session recordings from a web application and generate fix tasks.

ERRORS CAPTURED ({len(errors)}):
{_format_debug_errors(errors)}

USER INTERACTIONS ({len(clicks)} clicks on VNC preview):
{_format_debug_clicks(clicks)}

Based on these errors and user interactions, generate a JSON array of fix tasks.
Each task should be a JSON object with these fields:
- title: short description of the fix
- description: detailed explanation
- error_type: category (e.g. "runtime_error", "type_error", "api_error", "ui_bug")
- affected_files: array of file paths that likely need changes
- suggested_fix: approach to fix the issue
- severity: "critical", "high", "medium", or "low"

Return ONLY a JSON array, no other text."""

        tool = ClaudeCodeTool(working_dir=output_dir)
        result = await tool.execute(prompt=prompt, agent_type="fixer")

        fix_tasks = _parse_fix_tasks(result.output if result else "")

        logger.info(
            "debug_session_analyzed",
            project_id=request.project_id,
            errors=len(errors),
            clicks=len(clicks),
            fix_tasks=len(fix_tasks),
        )

        return {"success": True, "fix_tasks": fix_tasks}

    except Exception as e:
        logger.error("debug_analyze_failed", error=str(e))
        return {"success": False, "fix_tasks": [], "error": str(e)}


# =============================================================================
# Checkpoint Approval Endpoints
# =============================================================================

class CheckpointApprovalRequest(BaseModel):
    """Request to approve a checkpoint."""
    task_id: str
    response: Optional[str] = None


class CheckpointRejectRequest(BaseModel):
    """Request to reject a checkpoint."""
    task_id: str
    reason: str


@router.post("/epic/{epic_id}/checkpoint/approve", response_model=SuccessResponse)
async def approve_checkpoint(epic_id: str, request: CheckpointApprovalRequest):
    """
    Approve a checkpoint to continue epic execution.

    When the orchestrator reaches a checkpoint task, it waits for user approval.
    This endpoint approves the checkpoint and allows execution to continue.
    """
    try:
        if epic_id not in _epic_orchestrators:
            return SuccessResponse(success=False, error="No running orchestrator for this epic")

        orchestrator = _epic_orchestrators[epic_id]
        success = orchestrator.approve_checkpoint(request.task_id, request.response)

        if success:
            logger.info("checkpoint_approved", epic_id=epic_id, task_id=request.task_id)
            return SuccessResponse(success=True)
        else:
            return SuccessResponse(success=False, error="Checkpoint not found or already processed")

    except Exception as e:
        logger.error("checkpoint_approval_failed", epic_id=epic_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.post("/epic/{epic_id}/checkpoint/reject", response_model=SuccessResponse)
async def reject_checkpoint(epic_id: str, request: CheckpointRejectRequest):
    """
    Reject a checkpoint, marking it as failed.

    This will cause the checkpoint task to fail and stop epic execution.
    """
    try:
        if epic_id not in _epic_orchestrators:
            return SuccessResponse(success=False, error="No running orchestrator for this epic")

        orchestrator = _epic_orchestrators[epic_id]
        success = orchestrator.task_executor.reject_checkpoint(request.task_id, request.reason)

        if success:
            logger.info("checkpoint_rejected", epic_id=epic_id, task_id=request.task_id, reason=request.reason)
            return SuccessResponse(success=True)
        else:
            return SuccessResponse(success=False, error="Checkpoint not found or already processed")

    except Exception as e:
        logger.error("checkpoint_rejection_failed", epic_id=epic_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.post("/epic/{epic_id}/pause", response_model=SuccessResponse)
async def pause_epic_execution(epic_id: str):
    """
    Pause epic execution at the next task boundary.

    The current task will complete, but no new tasks will start.
    """
    try:
        if epic_id not in _epic_orchestrators:
            return SuccessResponse(success=False, error="No running orchestrator for this epic")

        orchestrator = _epic_orchestrators[epic_id]
        orchestrator.pause()

        logger.info("epic_paused", epic_id=epic_id)
        return SuccessResponse(success=True)

    except Exception as e:
        logger.error("epic_pause_failed", epic_id=epic_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


@router.get("/epic/{epic_id}/execution-status")
async def get_epic_execution_status(epic_id: str, project_path: str = Query(...)):
    """
    Get the current execution status of an epic.

    Returns whether the orchestrator is running, paused, and current task info.
    """
    try:
        status = {
            "epic_id": epic_id,
            "is_running": False,
            "is_paused": False,
            "current_task_id": None,
        }

        if epic_id in _epic_orchestrators:
            orchestrator = _epic_orchestrators[epic_id]
            status["is_running"] = orchestrator.is_running()
            status["is_paused"] = orchestrator.is_paused()
            status["current_task_id"] = orchestrator._current_task_id

        # Also get task progress from stored file
        import sys
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_orchestrator import EpicOrchestrator as EO

        temp_orch = EO(project_path)
        file_status = temp_orch.get_epic_status(epic_id)

        if file_status:
            status.update(file_status)

        return status

    except Exception as e:
        logger.error("epic_status_failed", epic_id=epic_id, error=str(e))
        return {"epic_id": epic_id, "error": str(e)}


# =============================================================================
# Parallelism Configuration
# =============================================================================

class ParallelismConfig(BaseModel):
    """Request to set parallelism."""
    max_parallel_tasks: int = 1  # 1-5


@router.get("/epic/{epic_id}/parallel-config")
async def get_parallel_config(epic_id: str):
    """
    Get the current parallelism configuration for an epic.

    Returns the max parallel tasks setting and current running task count.
    """
    try:
        if epic_id not in _epic_orchestrators:
            return {
                "epic_id": epic_id,
                "max_parallel_tasks": 1,
                "currently_running": 0,
                "running_task_ids": [],
                "max_allowed": 5,
                "message": "No active orchestrator, using defaults"
            }

        orchestrator = _epic_orchestrators[epic_id]
        config = orchestrator.get_parallel_config()
        config["epic_id"] = epic_id
        return config

    except Exception as e:
        logger.error("get_parallel_config_failed", epic_id=epic_id, error=str(e))
        return {"epic_id": epic_id, "error": str(e)}


@router.post("/epic/{epic_id}/parallel-config", response_model=SuccessResponse)
async def set_parallel_config(epic_id: str, config: ParallelismConfig):
    """
    Set the parallelism configuration for an epic.

    Args:
        epic_id: The epic to configure
        config.max_parallel_tasks: Number of tasks to run in parallel (1-5)

    Note: Setting max_parallel_tasks > 1 enables parallel execution of
    independent tasks (tasks with no dependencies on each other).
    Recommended: Start with 2-3 for typical projects.
    """
    try:
        if epic_id not in _epic_orchestrators:
            return SuccessResponse(
                success=False,
                error=f"No active orchestrator for {epic_id}. Start the epic first."
            )

        orchestrator = _epic_orchestrators[epic_id]
        success = orchestrator.set_max_parallel_tasks(config.max_parallel_tasks)

        if success:
            logger.info(
                "parallel_config_updated",
                epic_id=epic_id,
                max_parallel=config.max_parallel_tasks
            )
            return SuccessResponse(success=True)
        else:
            return SuccessResponse(
                success=False,
                error=f"Invalid value. Must be 1-5."
            )

    except Exception as e:
        logger.error("set_parallel_config_failed", epic_id=epic_id, error=str(e))
        return SuccessResponse(success=False, error=str(e))


class StartEpicGenerationRequest(BaseModel):
    """Request to start full epic-based generation for a project."""
    project_path: str
    output_dir: str
    vnc_port: int = 6090
    app_port: int = 3100
    max_parallel_tasks: int = 1  # 1=sequential (default), 2-5=parallel


@router.post("/start-epic-generation", response_model=SuccessResponse)
async def start_epic_generation(request: StartEpicGenerationRequest):
    """
    Start full epic-based code generation for a project.

    This is the main entry point when "Generate Code" is clicked on an RE project.
    It parses all epics, creates an EpicOrchestrator, and runs all epics in sequence
    as a background task. Progress updates are pushed via WebSocket events.
    Data is persisted to PostgreSQL (projects/jobs/tasks tables).
    """
    try:
        import sys as _sys
        engine_root = Path(__file__).parent.parent.parent.parent
        _sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_orchestrator import EpicOrchestrator

        # Load SoM bridge config from society_defaults.json
        som_config = {}
        config_path = engine_root / "config" / "society_defaults.json"
        if config_path.exists():
            try:
                import json as _json
                raw = _json.loads(config_path.read_text(encoding="utf-8"))
                som_config = raw.get("som_bridge", {})
                # Override VNC/app ports with the allocated ones
                som_config["vnc_port"] = request.vnc_port
                som_config["app_port"] = request.app_port
            except Exception:
                pass

        # Resolve output dir
        output_dir = request.output_dir
        if not Path(output_dir).is_absolute():
            output_dir = str(Path(request.project_path) / output_dir)

        orchestrator = EpicOrchestrator(
            project_path=request.project_path,
            output_dir=output_dir,
            event_bus=_event_bus,
            max_parallel_tasks=request.max_parallel_tasks,
            enable_som=True,
            som_config=som_config,
        )

        # Generate project-specific MCP config for dynamic server configuration
        try:
            from src.mcp.project_config import generate_project_mcp_config, save_project_mcp_config
            project_id = Path(request.project_path).name
            mcp_config = generate_project_mcp_config(
                project_id=project_id,
                project_path=request.project_path,
                output_dir=output_dir,
                sandbox_container=f"sandbox-{project_id}",
                vnc_port=request.vnc_port,
                app_port=request.app_port,
            )
            save_project_mcp_config(mcp_config)
            logger.info("mcp_config_generated_for_project", project_id=project_id)
        except Exception as mcp_err:
            logger.warning("mcp_config_generation_failed", error=str(mcp_err))

        # Store orchestrator reference
        _epic_orchestrators[f"all:{request.project_path}"] = orchestrator

        # --- Persist Project + Job to PostgreSQL ---
        db_project_id = None
        db_job_id = None
        try:
            from src.models.base import get_session_factory
            from src.models.project import Project, ProjectStatus
            from src.models.job import Job, JobStatus
            import json as _json

            session_factory = get_session_factory()
            async with session_factory() as session:
                project_id_name = Path(request.project_path).name
                # Upsert project
                from sqlalchemy import select
                result = await session.execute(
                    select(Project).where(Project.name == project_id_name)
                )
                db_project = result.scalar_one_or_none()
                if not db_project:
                    db_project = Project(
                        name=project_id_name,
                        description=f"Generated from {request.project_path}",
                        status=ProjectStatus.ACTIVE,
                        config_json=_json.dumps({
                            "project_path": request.project_path,
                            "output_dir": output_dir,
                            "vnc_port": request.vnc_port,
                            "app_port": request.app_port,
                        }),
                    )
                    session.add(db_project)
                    await session.flush()
                else:
                    db_project.status = ProjectStatus.ACTIVE
                db_project_id = db_project.id

                # Fix #10: Reuse existing RUNNING job instead of creating duplicate
                existing_job = (await session.execute(
                    select(Job).where(Job.project_id == db_project.id, Job.status == JobStatus.RUNNING)
                )).scalar_one_or_none()
                if existing_job:
                    db_job = existing_job
                    logger.info("reusing_existing_job", job_id=existing_job.id)
                else:
                    db_job = Job(
                        project_id=db_project.id,
                        status=JobStatus.RUNNING,
                        requirements_json="{}",
                        source_file=request.project_path,
                    )
                    session.add(db_job)
                    await session.flush()
                db_job_id = db_job.id
                await session.commit()
            logger.info("db_project_job_created", project_id=db_project_id, job_id=db_job_id)
        except Exception as db_err:
            logger.warning("db_persist_failed_continuing", error=str(db_err))

        # Set generation state so status endpoint reflects progress
        project_id = Path(request.project_path).name
        _generation_state[project_id] = {
            "phase": "generation",
            "progress_pct": 0,
            "completed": 0,
            "failed": 0,
            "total": 0,
            "agents": [],
            "epics": [],
            "service_count": 0,
            "endpoint_count": 0,
            "project_path": request.project_path,
            "db_project_id": db_project_id,
            "db_job_id": db_job_id,
        }

        # Run all epics as async task in the SAME event loop
        # Must stay in uvicorn's loop so DB + EventBus work correctly
        asyncio.create_task(
            _run_all_epics_background(request.project_path, orchestrator, project_id)
        )

        logger.info(
            "epic_generation_started",
            project_path=request.project_path,
            output_dir=output_dir,
            vnc_port=request.vnc_port,
            db_project_id=db_project_id,
            db_job_id=db_job_id,
        )

        return SuccessResponse(success=True)

    except Exception as e:
        logger.error("epic_generation_start_failed", error=str(e))
        return SuccessResponse(success=False, error=str(e))


async def _run_all_epics_background(project_path: str, orchestrator, project_id: str = ""):
    """Background task to run all epics for a project. Persists progress to PostgreSQL."""
    if not project_id:
        project_id = Path(project_path).name

    # Get DB IDs from generation state
    gen_state = _generation_state.get(project_id, {})
    db_job_id = gen_state.get("db_job_id")
    db_project_id = gen_state.get("db_project_id")

    # Helper to update generation state from task files AND sync to DB
    async def _update_progress():
        try:
            import json as _json
            tasks_dir = Path(project_path) / "tasks"
            completed = failed = total = 0
            task_records = []
            for tf in tasks_dir.glob("epic-*-tasks.json"):
                with open(tf) as f:
                    data = _json.load(f)
                for t in data.get("tasks", []):
                    total += 1
                    s = t.get("status", "pending")
                    if s == "completed":
                        completed += 1
                    elif s == "failed":
                        failed += 1
                    task_records.append(t)
            if project_id in _generation_state:
                _generation_state[project_id]["completed"] = completed
                _generation_state[project_id]["failed"] = failed
                _generation_state[project_id]["total"] = total
                _generation_state[project_id]["progress_pct"] = int(completed * 100 / max(total, 1))

                # Track real running agents from task status
                import time as _time
                running_agents = []
                for t in task_records:
                    if t.get("status") == "running":
                        started = t.get("started_at", "")
                        elapsed = 0
                        if started:
                            try:
                                from datetime import datetime as _dt
                                st = _dt.fromisoformat(started.replace("Z", "+00:00"))
                                elapsed = int(_time.time() - st.timestamp())
                            except Exception:
                                pass
                        running_agents.append({
                            "name": (t.get("title") or t.get("command") or t.get("id", ""))[:30],
                            "status": "running",
                            "task": t.get("id", ""),
                            "elapsed_seconds": max(0, elapsed),
                        })
                _generation_state[project_id]["agents"] = running_agents[:20]

            # #6: Broadcast progress via WebSocket
            try:
                from src.api.routes.dashboard_websocket import dashboard_manager
                if dashboard_manager.active_connections:
                    await dashboard_manager.broadcast({
                        "type": "generation_progress",
                        "project_id": project_id,
                        "phase": "generation",
                        "progress_pct": int(completed * 100 / max(total, 1)),
                        "completed": completed,
                        "failed": failed,
                        "total": total,
                        "agents": len(running_agents),
                    })
            except Exception:
                pass

            # Sync tasks to PostgreSQL
            if db_job_id and task_records:
                try:
                    await _sync_tasks_to_db(db_job_id, task_records)
                except Exception as db_err:
                    logger.debug("db_task_sync_failed", error=str(db_err))

            # Post newly completed/failed tasks to Discord MQ
            try:
                await _post_task_changes_to_discord(task_records, project_id)
            except Exception:
                pass
        except Exception:
            pass

    # Track which tasks we already posted to Discord
    _posted_tasks: set = set()
    _discord_queue: list = []  # Batched messages
    _last_discord_post = 0.0

    async def _post_task_changes_to_discord(tasks: list, proj_id: str):
        """Batch task changes and post summary to Discord (max 1 msg / 10s)."""
        nonlocal _last_discord_post
        import time as _time

        now = _time.time()
        new_completed = []
        new_failed = []

        for t in tasks:
            tid = t.get("id", "")
            status = t.get("status", "")
            if not tid or tid in _posted_tasks:
                continue

            if status == "completed":
                _posted_tasks.add(tid)
                new_completed.append(tid)
            elif status == "failed":
                _posted_tasks.add(tid)
                error = (
                    t.get("error_message")
                    or t.get("error")
                    or t.get("result")
                    or "No error details"
                )
                new_failed.append((tid, t.get("title", tid), str(error)[:200]))

        if not new_completed and not new_failed:
            return

        # Rate limit: max 1 Discord post per 10 seconds
        if now - _last_discord_post < 10:
            return

        try:
            from src.tools.discord_agent import DiscordAgent
            discord = DiscordAgent()
            if not discord.bot_token:
                return

            from src.tools.discord_mq import CHANNELS
            fixes_ch = CHANNELS.get("fixes", "")
            done_ch = CHANNELS.get("done", "")

            # Post completed summary (batch)
            if new_completed and done_ch:
                msg = "**BATCH_VERIFIED** | %d tasks completed\n`%s`" % (
                    len(new_completed),
                    "`, `".join(new_completed[:10]),
                )
                if len(new_completed) > 10:
                    msg += "\n... and %d more" % (len(new_completed) - 10)
                try:
                    await discord.send(msg[:2000], channel_id=done_ch)
                except Exception:
                    pass

            # Post failed summary (batch, max 3 detailed)
            if new_failed and fixes_ch:
                lines = ["**BATCH_FIX_NEEDED** | %d tasks failed" % len(new_failed)]
                for tid, title, error in new_failed[:3]:
                    scope = "BACKEND" if "api" in tid.lower() or "service" in tid.lower() else "FRONTEND"
                    lines.append(
                        "\n**%s** | `%s`\n%s\n```\n%s\n```" % (scope, tid, title, error[:150])
                    )
                if len(new_failed) > 3:
                    lines.append("\n... and %d more failed tasks" % (len(new_failed) - 3))
                lines.append(
                    "\n||`%s`||" % json.dumps({"type": "FIX_NEEDED", "batch": True, "count": len(new_failed)})
                )
                try:
                    await discord.send("\n".join(lines)[:2000], channel_id=fixes_ch)
                except Exception:
                    pass

            _last_discord_post = _time.time()

        except Exception as e:
            logger.debug("discord_batch_post_failed: %s", e)

    # Start a background progress updater
    async def _progress_loop():
        while project_id in _generation_state and _generation_state[project_id].get("phase") == "generation":
            await _update_progress()
            await asyncio.sleep(5)

    progress_task = asyncio.create_task(_progress_loop())

    try:
        results = await orchestrator.run_all_epics()

        # Summarize results
        total_completed = sum(r.completed_tasks for r in results.values())
        total_failed = sum(r.failed_tasks for r in results.values())
        all_success = all(r.success for r in results.values())

        # Update final state
        if project_id in _generation_state:
            _generation_state[project_id]["phase"] = "complete" if all_success else "failed"
            _generation_state[project_id]["progress_pct"] = 100 if all_success else _generation_state[project_id].get("progress_pct", 0)
            _generation_state[project_id]["completed"] = total_completed
            _generation_state[project_id]["failed"] = total_failed

        # Final DB sync
        await _update_progress()

        # Update Job status in DB
        if db_job_id:
            try:
                from src.models.base import get_session_factory
                from src.models.job import Job, JobStatus
                from src.models.project import Project, ProjectStatus
                session_factory = get_session_factory()
                async with session_factory() as session:
                    job = await session.get(Job, db_job_id)
                    if job:
                        job.status = JobStatus.COMPLETED if all_success else JobStatus.FAILED
                        job.tasks_completed = total_completed
                        job.tasks_failed = total_failed
                        job.total_tasks = total_completed + total_failed
                    if db_project_id:
                        project = await session.get(Project, db_project_id)
                        if project:
                            project.status = ProjectStatus.COMPLETED if all_success else ProjectStatus.FAILED
                    await session.commit()
                logger.info("db_job_finalized", job_id=db_job_id, success=all_success)
            except Exception as db_err:
                logger.warning("db_job_finalize_failed", error=str(db_err))

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.GENERATION_COMPLETE if all_success else EventType.BUILD_FAILED,
                source="epic_orchestrator",
                data={
                    "project_path": project_path,
                    "epic_count": len(results),
                    "all_success": all_success,
                    "completed_tasks": total_completed,
                    "failed_tasks": total_failed,
                }
            ))

        logger.info(
            "all_epics_completed",
            project_path=project_path,
            epic_count=len(results),
            all_success=all_success,
            completed=total_completed,
            failed=total_failed,
        )

    except Exception as e:
        logger.error("all_epics_background_failed", project_path=project_path, error=str(e))

        if project_id in _generation_state:
            _generation_state[project_id]["phase"] = "failed"
            _generation_state[project_id]["error"] = str(e)

        # Mark Job as failed in DB
        if db_job_id:
            try:
                from src.models.base import get_session_factory
                from src.models.job import Job, JobStatus
                session_factory = get_session_factory()
                async with session_factory() as session:
                    job = await session.get(Job, db_job_id)
                    if job:
                        job.status = JobStatus.FAILED
                        job.error_log = str(e)
                    await session.commit()
            except Exception:
                pass

        if _event_bus:
            await _event_bus.publish(Event(
                type=EventType.BUILD_FAILED,
                source="epic_orchestrator",
                data={"project_path": project_path, "error": str(e)}
            ))
    finally:
        progress_task.cancel()


async def _sync_tasks_to_db(job_id: int, task_records: list):
    """Sync task records from JSON files to PostgreSQL tasks table."""
    from src.models.base import get_session_factory
    from src.models.task import Task, TaskStatus, TaskType
    from sqlalchemy import select
    import json as _json

    status_map = {
        "pending": TaskStatus.PENDING,
        "running": TaskStatus.RUNNING,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
        "blocked": TaskStatus.BLOCKED,
        "cancelled": TaskStatus.CANCELLED,
    }

    session_factory = get_session_factory()
    async with session_factory() as session:
        for t in task_records:
            # Task files use "id" field, model uses "task_id"
            tid = t.get("id", t.get("task_id", ""))
            if not tid:
                continue

            # Check if task exists
            result = await session.execute(
                select(Task).where(Task.job_id == job_id, Task.task_id == str(tid))
            )
            existing = result.scalar_one_or_none()

            task_status = status_map.get(t.get("status", "pending"), TaskStatus.PENDING)

            if existing:
                existing.status = task_status
                existing.status_message = t.get("error_message", t.get("error", t.get("status_message")))
                if t.get("result"):
                    existing.agent_response = _json.dumps(t["result"]) if isinstance(t["result"], dict) else str(t["result"])
            else:
                # prompt MUST not be null
                prompt = t.get("command") or t.get("description") or t.get("title") or str(tid)
                new_task = Task(
                    job_id=job_id,
                    task_id=str(tid),
                    requirement_ids=t.get("related_requirements", []),
                    title=t.get("title", t.get("description", str(tid))),
                    description=t.get("description", ""),
                    prompt=prompt,
                    depends_on=t.get("dependencies", t.get("depends_on", [])),
                    status=task_status,
                    status_message=t.get("error_message"),
                    retry_count=t.get("retry_count", 0),
                    max_retries=t.get("max_retries", 3),
                )
                session.add(new_task)

        await session.commit()


@router.get("/db/projects")
async def get_db_projects():
    """Get all projects from PostgreSQL."""
    try:
        from src.models.base import get_session_factory
        from src.models.project import Project
        from sqlalchemy import select
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(Project).order_by(Project.updated_at.desc()))
            projects = result.scalars().all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "status": p.status.value if p.status else "unknown",
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in projects
            ]
    except Exception as e:
        logger.error("db_projects_fetch_failed", error=str(e))
        return []


@router.get("/db/projects/{project_id}/tasks")
async def get_db_tasks(project_id: int):
    """Get all tasks for a project from PostgreSQL (via latest job)."""
    try:
        from src.models.base import get_session_factory
        from src.models.job import Job
        from src.models.task import Task
        from sqlalchemy import select
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Get latest job for project
            result = await session.execute(
                select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc()).limit(1)
            )
            job = result.scalar_one_or_none()
            if not job:
                return {"tasks": [], "job": None}

            # Get tasks for job
            result = await session.execute(
                select(Task).where(Task.job_id == job.id).order_by(Task.id)
            )
            tasks = result.scalars().all()
            # Use actual task count from DB (not stale job.total_tasks)
            actual_total = len(tasks)
            actual_completed = sum(1 for t in tasks if t.status and t.status.value == "completed")
            actual_failed = sum(1 for t in tasks if t.status and t.status.value == "failed")
            actual_pct = (actual_completed / actual_total * 100) if actual_total > 0 else 0

            return {
                "job": {
                    "id": job.id,
                    "status": job.status.value if job.status else "unknown",
                    "tasks_completed": actual_completed,
                    "tasks_failed": actual_failed,
                    "total_tasks": actual_total,
                    "progress_pct": round(actual_pct, 1),
                },
                "tasks": [
                    {
                        "id": t.id,
                        "task_id": t.task_id,
                        "title": t.title,
                        "description": t.description,
                        "status": t.status.value if t.status else "pending",
                        "status_message": t.status_message,
                        "task_type": t.task_type.value if t.task_type else "general",
                        "depends_on": t.depends_on or [],
                        "retry_count": t.retry_count,
                        "execution_time_ms": t.execution_time_ms,
                        "tokens_used": t.tokens_used,
                        "cost_usd": t.cost_usd,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                    }
                    for t in tasks
                ],
            }
    except Exception as e:
        logger.error("db_tasks_fetch_failed", error=str(e))
        return {"tasks": [], "job": None, "error": str(e)}


@router.post("/generate-task-lists")
async def generate_all_task_lists(request: GenerateTaskListsRequest, db: AsyncSession = Depends(get_db)):
    """
    Phase A: Generate task lists for all epics WITHOUT executing code generation.
    Tasks are saved to JSON files AND synced to the database.
    User can then review/sort/disable tasks in the UI before starting Phase B.
    """
    try:
        import sys, json as _json
        engine_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(engine_root / "mcp_plugins" / "servers" / "grpc_host"))

        from epic_parser import EpicParser
        from epic_task_generator import EpicTaskGenerator

        # Read consolidation_mode from engine_settings
        consolidation_mode = "feature"
        try:
            from src.engine_settings import get_setting
            consolidation_mode = get_setting("generation.consolidation_mode", "feature")
        except Exception:
            pass

        # Save epics summary
        parser = EpicParser(request.project_path)
        parser.save_epics_json()

        # Generate tasks with consolidation mode
        generator = EpicTaskGenerator(request.project_path, consolidation_mode=consolidation_mode)
        saved_files = generator.save_all_epic_tasks()

        # Count total tasks from saved files
        total_tasks = 0
        task_breakdown = {}
        for f in saved_files:
            try:
                data = _json.loads(Path(f).read_text(encoding="utf-8"))
                tasks = data.get("tasks", [])
                total_tasks += len(tasks)
                epic_id = data.get("epic_id", "unknown")
                task_breakdown[epic_id] = len(tasks)
            except Exception:
                pass

        # Sync to DB: create job + tasks
        try:
            from sqlalchemy import text as sql_text

            # Get or create project
            proj_result = await db.execute(sql_text("SELECT id FROM projects LIMIT 1"))
            proj_row = proj_result.first()
            project_db_id = proj_row[0] if proj_row else 1

            # Create new job
            await db.execute(sql_text(
                "INSERT INTO jobs (project_id, status, total_tasks, created_at, updated_at) "
                "VALUES (:pid, 'PENDING', :total, NOW(), NOW())"
            ), {"pid": project_db_id, "total": total_tasks})
            job_result = await db.execute(sql_text("SELECT MAX(id) FROM jobs"))
            job_id = job_result.scalar()

            # Insert all tasks from JSON files
            inserted = 0
            for f in saved_files:
                try:
                    data = _json.loads(Path(f).read_text(encoding="utf-8"))
                    for t in data.get("tasks", []):
                        await db.execute(sql_text(
                            "INSERT INTO tasks (job_id, task_id, title, description, prompt, status, "
                            "task_type, depends_on, requirement_ids, depth_level, created_at, updated_at) "
                            "VALUES (:jid, :tid, :title, :desc, :prompt, 'PENDING', "
                            "'general', :deps, :reqs, 0, NOW(), NOW())"
                        ), {
                            "jid": job_id,
                            "tid": t.get("id", ""),
                            "title": t.get("title", "")[:512],
                            "desc": t.get("description", "")[:2000],
                            "prompt": t.get("description", ""),
                            "deps": _json.dumps(t.get("dependencies", [])),
                            "reqs": _json.dumps(t.get("related_requirements", [])),
                        })
                        inserted += 1
                except Exception as e:
                    logger.warning("task_insert_failed", file=str(f), error=str(e)[:100])

            await db.commit()
            logger.info("tasks_synced_to_db", job_id=job_id, inserted=inserted, total=total_tasks)
        except Exception as e:
            logger.error("db_sync_failed", error=str(e)[:200])

        return {
            "success": True,
            "consolidation_mode": consolidation_mode,
            "total_tasks": total_tasks,
            "task_breakdown": task_breakdown,
            "files_created": len(saved_files),
            "message": "Tasks generated. Review in UI, then call /generate-code to start."
        }

    except Exception as e:
        logger.error("task_lists_generation_failed", project_path=request.project_path, error=str(e))
        return {"success": False, "error": str(e)}


class ExecuteGenerationRequest(BaseModel):
    project_name: str = ""
    skip_completed: bool = True  # Skip already-completed tasks


@router.post("/execute-generation")
async def execute_generation(request: ExecuteGenerationRequest):
    """
    Phase B: Execute code generation for existing tasks (from DB/JSON).
    Requires Phase A (/generate-task-lists) to have been run first.
    Passes --skip-task-gen flag so the orchestrator only executes, not generates.
    """
    try:
        from src.engine_settings import get_project
        proj = get_project(request.project_name)
        if not proj:
            return {"success": False, "error": "Project not found"}

        project_path = proj.get("requirements_path", "")
        output_dir = proj.get("output_dir", "")

        if not project_path or not output_dir:
            return {"success": False, "error": "Project paths not configured"}

        # Check for existing task files
        tasks_dir = Path(project_path) / "tasks"
        if not tasks_dir.exists() or not list(tasks_dir.glob("epic-*-tasks*.json")):
            return {"success": False, "error": "No task files found. Run /generate-task-lists first."}

        # Remove stale lock
        lock_file = Path(output_dir) / ".generation_running"
        if lock_file.exists():
            lock_file.unlink()

        # Start generation subprocess with --skip-task-gen
        import subprocess
        env = os.environ.copy()
        cmd = [
            "python", "run_generation.py",
            "--project-path", project_path,
            "--output-dir", output_dir,
            "--project-id", proj.get("id", ""),
            "--db-schema", proj.get("db_schema", "coding_engine"),
            "--parallelism", str(proj.get("max_parallel_tasks", 3)),
            "--skip-task-gen",  # Key flag: don't regenerate tasks
        ]

        log_file = Path(output_dir) / "generation.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        process = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).parent.parent.parent.parent),
            stdout=open(str(log_file), "a"),
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

        # Write lock file
        import json as _json, time
        lock_file.write_text(_json.dumps({
            "project_id": proj.get("id", ""),
            "started_at": time.time(),
            "pid": process.pid,
            "skip_task_gen": True,
        }))

        logger.info("code_generation_started", project=proj.get("id"), pid=process.pid, skip_task_gen=True)
        return {"success": True, "pid": process.pid, "message": "Code generation started (tasks from existing files)"}

    except Exception as e:
        return {"success": False, "error": str(e)[:300]}


# ─── Project MCP Config Endpoints ────────────────────────────────────


class MCPConfigUpdateRequest(BaseModel):
    """Request to update project MCP config."""
    project_path: str
    updates: dict  # Partial update dict


@router.get("/project/mcp-config")
async def get_project_mcp_config(project_path: str = Query(...)):
    """
    Get the MCP server config for a project.

    Returns the .mcp-config.json content showing which MCP servers
    are configured and their project-specific overrides.
    """
    try:
        from src.mcp.project_config import load_project_mcp_config, generate_project_mcp_config, save_project_mcp_config

        config = load_project_mcp_config(project_path)
        if not config:
            # Generate default config if none exists
            project_id = Path(project_path).name
            output_dir = str(Path(project_path) / "output")
            config = generate_project_mcp_config(
                project_id=project_id,
                project_path=project_path,
                output_dir=output_dir,
            )
            save_project_mcp_config(config)

        return config.to_dict()

    except Exception as e:
        logger.error("get_mcp_config_failed", project_path=project_path, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/project/mcp-config")
async def update_project_mcp_config(request: MCPConfigUpdateRequest):
    """
    Update MCP server config for a project.

    Supports partial updates:
    {
        "project_path": "/data/projects/my-app",
        "updates": {
            "servers": {
                "postgres": {"env_vars": {"DATABASE_URL": "postgresql://..."}}
            }
        }
    }
    """
    try:
        from src.mcp.project_config import update_project_mcp_config as _update, load_project_mcp_config

        config = _update(request.project_path, request.updates)
        if not config:
            raise HTTPException(status_code=404, detail="No MCP config found for project")

        return config.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_mcp_config_failed", project_path=request.project_path, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Task Verification + Kill/Restart Control Endpoints
# ============================================================

@router.post("/kill")
async def kill_verification():
    """Stop all running verification loops. Called by Minibook."""
    try:
        from src.tools.task_verifier import request_kill
        request_kill()
        return {"success": True, "message": "Kill signal sent"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/restart")
async def restart_verification():
    """Reset kill signal and prepare for next project. Called by Minibook."""
    try:
        from src.tools.task_verifier import reset_kill
        reset_kill()
        return {"success": True, "message": "Ready for next project"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/verification-status")
async def verification_status():
    """Get current task verification progress."""
    try:
        from src.tools.task_verifier import is_killed
        return {
            "kill_active": is_killed(),
            "status": "stopped" if is_killed() else "running",
        }
    except Exception as e:
        return {"kill_active": False, "status": "unknown", "error": str(e)}


class VerifyTaskRequest(BaseModel):
    task_id: str
    task_name: str = ""
    preview_url: str = "http://localhost:3100"
    component: str = ""
    requirements: str = ""


@router.post("/verify-task")
async def verify_single_task(request: VerifyTaskRequest):
    """Manually trigger verification for a single task."""
    try:
        from src.tools.task_verifier import TaskVerifier
        verifier = TaskVerifier(preview_url=request.preview_url)
        result = await verifier.verify_task(
            task_id=request.task_id,
            task_name=request.task_name or request.task_id,
            component=request.component,
            requirements=request.requirements,
        )
        return {
            "task_id": result.task_id,
            "status": result.status.value,
            "errors": result.errors,
            "attempts": result.attempts,
            "fix_applied": result.fix_applied,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Verify Generation ──────────────────────────────────────

class VerifyGenerationRequest(BaseModel):
    project_dir: str = ""


@router.post("/verify-generation")
async def verify_generation(request: VerifyGenerationRequest):
    """Verify generated code: count files, check structure, run build."""
    import asyncio as _aio

    _pdir = request.project_dir
    if not _pdir:
        try:
            from src.engine_settings import get_project
            proj = get_project()
            _pdir = proj.get("output_dir", "/app/output") if proj else "/app/output"
        except Exception:
            _pdir = "/app/output"
    project_dir = Path(_pdir)

    issues = []
    files_count = 0
    build_ok = False

    # 1. Count generated files
    try:
        src_files = list(project_dir.rglob("*.ts")) + list(project_dir.rglob("*.tsx"))
        src_files = [f for f in src_files if "node_modules" not in str(f)]
        files_count = len(src_files)
        if files_count < 10:
            issues.append("Only %d source files found (expected more)" % files_count)
    except Exception as e:
        issues.append("File scan error: %s" % str(e)[:100])

    # 2. Check critical files exist
    critical_files = [
        "package.json", "tsconfig.json",
        "prisma/schema.prisma",
        "src/main.ts",
    ]
    for cf in critical_files:
        if not (project_dir / cf).exists():
            issues.append("Missing: %s" % cf)

    # 3. Check prisma models
    schema_file = project_dir / "prisma" / "schema.prisma"
    if schema_file.exists():
        schema_content = schema_file.read_text(encoding="utf-8", errors="replace")
        import re as _re
        model_count = len(_re.findall(r"^model ", schema_content, _re.MULTILINE))
        if model_count < 5:
            issues.append("Only %d Prisma models (expected 30+)" % model_count)
    else:
        issues.append("No prisma/schema.prisma")

    # 4. Run build
    try:
        env = os.environ.copy()
        # Resolve DATABASE_URL from project settings
        try:
            from src.engine_settings import get_project
            _proj = get_project()
            _db_schema = _proj.get("db_schema", "coding_engine") if _proj else "coding_engine"
        except Exception:
            _db_schema = "coding_engine"
        env["DATABASE_URL"] = "postgresql://postgres:postgres@postgres:5432/%s?schema=public" % _db_schema
        proc = await _aio.create_subprocess_exec(
            "npm", "run", "build",
            cwd=str(project_dir), env=env,
            stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.STDOUT,
        )
        stdout, _ = await _aio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        build_ok = proc.returncode == 0
        if not build_ok:
            # Extract last error lines
            error_lines = [l for l in output.split("\n") if "error" in l.lower()][-3:]
            issues.append("Build failed: %s" % "; ".join(error_lines)[:200])
    except _aio.TimeoutError:
        issues.append("Build timed out after 120s")
    except Exception as e:
        issues.append("Build error: %s" % str(e)[:100])

    # 5. Check DB task stats
    completed = 0
    failed = 0
    total = 0
    try:
        import asyncpg
        db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
        if "asyncpg" in db_url:
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(db_url.split("?")[0])
        rows = await conn.fetch(
            "SELECT status, COUNT(*) as cnt FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) GROUP BY status"
        )
        for row in rows:
            if row["status"].upper() == "COMPLETED":
                completed = row["cnt"]
            elif row["status"].upper() == "FAILED":
                failed = row["cnt"]
            total += row["cnt"]
        await conn.close()
    except Exception:
        pass

    return {
        "success": len(issues) == 0 and build_ok,
        "files_count": files_count,
        "build_ok": build_ok,
        "issues": issues,
        "tasks": {"completed": completed, "failed": failed, "total": total},
    }


# Alias: /status -> /project/status (frontend tries this first)
@router.get("/status")
async def get_status_alias(projectId: str = Query("", description="Project ID")):
    """Alias for /project/status -- frontend compatibility."""
    if not projectId:
        try:
            from src.engine_settings import get_project
            proj = get_project()
            projectId = proj["id"] if proj else ""
        except Exception:
            projectId = ""
    return await get_project_status(projectId)


# Container logs endpoint for LogViewer
# Uses create_subprocess_exec with explicit args (no shell injection)
@router.get("/container-logs")
async def get_container_logs(
    project: str = Query("coding-engine-api", description="Container name"),
    tail: int = Query(200, description="Number of lines"),
):
    """Get Docker container logs for the LogViewer tab."""
    # Whitelist allowed container names to prevent injection
    allowed_prefixes = ("coding-engine", "trae-")
    if not any(project.startswith(p) for p in allowed_prefixes):
        return {"logs": [], "container": project, "error": "Container not in whitelist"}
    try:
        # Find actual container name (Swarm adds suffixes)
        find_proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "--format", "{{.Names}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        find_out, _ = await asyncio.wait_for(find_proc.communicate(), timeout=5)
        containers = find_out.decode().strip().split("\n")
        actual = project
        for c in containers:
            if c.startswith(project):
                actual = c
                break
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", actual, "--tail", str(min(tail, 500)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        lines = stdout.decode("utf-8", errors="replace").strip().split("\n")
        return {"logs": lines[-tail:], "container": project, "count": len(lines)}
    except Exception as e:
        return {"logs": [], "container": project, "error": str(e)}


# ============================================================
# Discord MQ Agent Pipeline
# ============================================================
_agent_pipeline = None

# Active code generation backend (shared with discord_mq)
_active_backend = {"name": "openrouter", "model": ""}


class BackendConfigRequest(BaseModel):
    backend: str = "openrouter"  # "openrouter" | "kilo" | "claude"
    model: str = ""  # Override specific model


class BackendConfigResponse(BaseModel):
    success: bool
    active_backend: str = ""
    active_model: str = ""
    available_backends: list = []
    error: str = ""


@router.post("/pipeline/start")
async def start_agent_pipeline():
    """Start the Discord MQ agent pipeline (all 5 agents)."""
    global _agent_pipeline
    try:
        from src.tools.discord_mq import create_default_pipeline
        if _agent_pipeline:
            await _agent_pipeline.stop_all()
        _agent_pipeline = create_default_pipeline()
        asyncio.create_task(_agent_pipeline.start_all())

        # Also start Discord->CLI trigger for error routing
        try:
            from src.services.discord_cli_trigger import get_discord_cli_trigger
            trigger = get_discord_cli_trigger()
            await trigger.start()
            logger.info("discord_cli_trigger_started")
        except Exception as e:
            logger.warning("discord_cli_trigger_start_failed", error=str(e))

        return {
            "success": True,
            "agents": list(_agent_pipeline.agents.keys()),
            "message": "Pipeline started with %d agents" % len(_agent_pipeline.agents),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/pipeline/stop")
async def stop_agent_pipeline():
    """Stop the Discord MQ agent pipeline."""
    global _agent_pipeline
    if _agent_pipeline:
        await _agent_pipeline.stop_all()
        _agent_pipeline = None
        return {"success": True, "message": "Pipeline stopped"}
    return {"success": True, "message": "No pipeline running"}


class DebugRequest(BaseModel):
    file_path: str = ""
    task_id: str = ""
    error: str = ""
    sandbox_url: str = "http://coding-engine-sandbox:3100"


@router.post("/pipeline/debug")
async def debug_with_automation_ui(request: DebugRequest):
    """Trigger Automation UI to debug a specific file/component in the sandbox."""
    import httpx

    try:
        intent = "Debug the component at %s in the sandbox app at %s." % (
            request.file_path or request.task_id, request.sandbox_url
        )
        if request.error:
            intent += " Error context: %s" % request.error[:300]

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                os.environ.get("AUTOMATION_UI_URL", "http://coding-engine-automation-ui:8007") + "/api/llm/intent",
                json={"intent": intent, "conversation_id": "debug-%s" % (request.task_id or "manual")},
            )
            if resp.status_code == 200:
                return {"success": True, "result": resp.json()}
            return {"success": False, "error": "Automation UI returned %d" % resp.status_code}
    except httpx.ConnectError:
        return {"success": False, "error": "Automation UI not available at localhost:8007"}
    except Exception as e:
        return {"success": False, "error": str(e)}


class VerifyEpicRequest(BaseModel):
    epic_id: str
    expected_files: list = []
    requirements: list = []


@router.post("/pipeline/verify-epic")
async def verify_epic(request: VerifyEpicRequest):
    """Manually trigger post-epic MCMP verification."""
    try:
        from src.services.mcmp_prerun import get_prerun
        prerun = get_prerun()
        await prerun.index_project()
        result = await prerun.verify_epic_completeness(
            epic_id=request.epic_id,
            expected_files=request.expected_files,
            requirements=request.requirements,
        )
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/pipeline/status")
async def pipeline_status():
    """Get pipeline status."""
    if not _agent_pipeline:
        return {"running": False, "agents": []}
    return {
        "running": True,
        "agents": [
            {"name": a.name, "listen": a.listen_channel, "output": a.output_channel}
            for a in _agent_pipeline.agents.values()
        ],
    }


# ============================================================
# Backend Selection API
# ============================================================


@router.get("/pipeline/backend")
async def get_backend_config():
    """Get current code generation backend configuration with auth status."""
    import shutil
    from src.llm_config import get_model

    # Check auth readiness for each backend
    auth_status = {}

    # OpenRouter: needs OPENROUTER_API_KEY
    or_key = get_secret("openrouter_api_key")
    auth_status["openrouter"] = {"ready": bool(or_key), "reason": "OPENROUTER_API_KEY set" if or_key else "OPENROUTER_API_KEY not set"}

    # Kilo: needs kilo binary + OPENROUTER_API_KEY (uses it from env)
    kilo_installed = bool(shutil.which("kilo"))
    kilo_ready = kilo_installed and bool(or_key)
    kilo_reason = []
    if not kilo_installed:
        kilo_reason.append("kilo CLI not installed")
    if not or_key:
        kilo_reason.append("OPENROUTER_API_KEY not set")
    auth_status["kilo"] = {"ready": kilo_ready, "reason": ", ".join(kilo_reason) if kilo_reason else "kilo CLI + OpenRouter key ready"}

    # Claude: needs claude binary + ANTHROPIC_API_KEY
    claude_installed = bool(shutil.which("claude"))
    ant_key = get_secret("anthropic_api_key")
    claude_ready = claude_installed and bool(ant_key)
    claude_reason = []
    if not claude_installed:
        claude_reason.append("claude CLI not installed")
    if not ant_key:
        claude_reason.append("ANTHROPIC_API_KEY not set")
    auth_status["claude"] = {"ready": claude_ready, "reason": ", ".join(claude_reason) if claude_reason else "claude CLI + Anthropic key ready"}

    return {
        "success": True,
        "active_backend": _active_backend["name"],
        "active_model": _active_backend.get("model") or get_model("primary"),
        "available_backends": ["openrouter", "kilo", "claude"],
        "auth_status": auth_status,
    }


@router.post("/pipeline/backend", response_model=BackendConfigResponse)
async def set_backend_config(request: BackendConfigRequest):
    """Switch code generation backend (openrouter/kilo/claude)."""
    valid = ["openrouter", "kilo", "claude"]
    if request.backend not in valid:
        return BackendConfigResponse(success=False, error="Backend must be one of: %s" % ", ".join(valid))

    _active_backend["name"] = request.backend
    _active_backend["model"] = request.model

    # Verify backend is available
    if request.backend == "kilo":
        try:
            import shutil
            if not shutil.which("kilo"):
                return BackendConfigResponse(
                    success=True, active_backend="kilo",
                    active_model=request.model or "kilo/openrouter/free",
                    available_backends=valid,
                    error="Warning: kilo CLI not found in PATH, install with: npm install -g kilocode",
                )
        except Exception:
            pass

    if request.backend == "claude":
        api_key = get_secret("anthropic_api_key")
        if not api_key:
            return BackendConfigResponse(
                success=True, active_backend="claude",
                active_model=request.model or "claude-sonnet-4-6",
                available_backends=valid,
                error="Warning: ANTHROPIC_API_KEY not set",
            )

    from src.llm_config import get_model
    model = request.model or get_model("primary") if request.backend == "openrouter" else request.model

    logger.info("backend_switched", backend=request.backend, model=model)
    return BackendConfigResponse(
        success=True,
        active_backend=request.backend,
        active_model=model,
        available_backends=valid,
    )


# ============================================================
# Discord → CLI Trigger
# ============================================================


@router.post("/pipeline/discord-trigger/start")
async def start_discord_trigger():
    """Start the Discord->CLI trigger that watches for errors and routes to tools."""
    try:
        from src.services.discord_cli_trigger import get_discord_cli_trigger
        trigger = get_discord_cli_trigger()
        await trigger.start()
        return {"success": True, "status": "running"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/pipeline/discord-trigger/stop")
async def stop_discord_trigger():
    """Stop the Discord->CLI trigger."""
    try:
        from src.services.discord_cli_trigger import get_discord_cli_trigger
        trigger = get_discord_cli_trigger()
        await trigger.stop()
        return {"success": True, "status": "stopped"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Engine Settings API — Central config for all components
# ============================================================


@router.get("/engine-settings")
async def get_engine_settings(section: str = ""):
    """Get engine settings (all or specific section)."""
    from src.engine_settings import get_settings, get_setting
    if section:
        data = get_setting(section)
        if data is None:
            raise HTTPException(status_code=404, detail="Section '%s' not found" % section)
        return {section: data}
    return get_settings()


@router.get("/engine-settings/models")
async def get_engine_models():
    """Get model configuration for all roles."""
    from src.engine_settings import get_setting
    return get_setting("models", {})


@router.get("/engine-settings/discord")
async def get_engine_discord():
    """Get Discord configuration."""
    from src.engine_settings import get_setting
    return get_setting("discord", {})


@router.get("/engine-settings/projects")
async def get_engine_projects():
    """Get registered projects."""
    from src.engine_settings import get_setting
    return get_setting("projects", {})


@router.get("/engine-settings/generation")
async def get_engine_generation():
    """Get generation pipeline settings."""
    from src.engine_settings import get_setting
    return get_setting("generation", {})


@router.get("/engine-settings/fix-strategies")
async def get_engine_fix_strategies():
    """Get fix strategies per task type."""
    from src.engine_settings import get_setting
    return get_setting("fix_strategies", {})


class SettingUpdate(BaseModel):
    path: str
    value: Any = None


@router.patch("/engine-settings")
async def update_engine_setting(update: SettingUpdate):
    """Update a single setting by dot-notation path."""
    from src.engine_settings import update_setting, get_setting

    # Validate path exists (or allow new paths under known sections)
    known_sections = ["models", "providers", "discord", "generation", "fix_strategies", "verification", "projects", "infrastructure"]
    root = update.path.split(".")[0]
    if root not in known_sections:
        raise HTTPException(status_code=400, detail="Unknown section: '%s'. Valid: %s" % (root, ", ".join(known_sections)))

    ok = update_setting(update.path, update.value)
    if ok:
        return {"success": True, "path": update.path, "value": update.value}
    raise HTTPException(status_code=500, detail="Failed to write settings")


@router.put("/engine-settings")
async def replace_engine_settings(settings: dict):
    """Replace entire settings (full YAML rewrite)."""
    from src.engine_settings import _resolve_path, _lock
    import yaml as _yaml

    path = _resolve_path()
    try:
        with _lock:
            with open(path, "w", encoding="utf-8") as f:
                _yaml.dump(settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
