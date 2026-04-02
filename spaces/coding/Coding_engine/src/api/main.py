"""
FastAPI Application - Main entry point for the Coding Engine API.

Provides REST endpoints for:
- Project management
- Job submission and monitoring
- Artifact retrieval
"""
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env file for persisted API keys (survives container restarts)
_env_path = project_root / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                _key, _val = _key.strip(), _val.strip()
                if _key and _val and _key not in os.environ:
                    os.environ[_key] = _val

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.models.base import init_db, get_session_factory
from src.api.routes import projects, jobs, artifacts, health
from src.api.routes import websocket as ws_routes
from src.api.routes import portal
from src.api.routes import colony
from src.api.routes import vision
from src.api.routes import llm_config as llm_config_routes
from src.api.routes import enrichment as enrichment_routes
from src.api.routes import vibe as vibe_routes
from src.api.dashboard_integration import init_dashboard
from src.mind.event_bus import EventBus

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()
settings = get_settings()

# Initialize EventBus for dashboard integration
# This can be overridden by set_shared_event_bus() before uvicorn starts
event_bus = EventBus()


def set_shared_event_bus(shared_bus: EventBus) -> None:
    """Override the module-level EventBus with an externally-created one.

    Called by run_engine.py to share a single EventBus between the
    EpicOrchestrator (publishing events) and the FastAPI WebSocket bridge
    (forwarding events to the Electron dashboard).

    Must be called BEFORE uvicorn.run() triggers the lifespan handler.
    """
    global event_bus
    event_bus = shared_bus
    logger.info("shared_event_bus_injected", source="run_engine.py")


# Shared SharedState for vibe-coding (Phase 31)
# Allows vibe.py to mark user-managed files in the same instance the pipeline uses.
# Set via set_shared_state() from run_engine.py — None until then.
shared_state = None


def set_shared_state(state) -> None:
    """Inject the pipeline's SharedState so vibe.py can mark user-managed files.

    Called by run_engine.py after creating the EpicOrchestrator.
    If not called, vibe.py will still publish EventBus events (the primary
    protection) but won't be able to mark files in SharedState.
    """
    global shared_state
    shared_state = state
    logger.info("shared_state_injected", source="run_engine.py")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("starting_application", env=settings.app_env)

    # Initialize database (skip if DB is unavailable - dashboard still works)
    try:
        await init_db()
        logger.info("database_initialized")

        # Initialize dashboard integration
        session_factory = get_session_factory()
        init_dashboard(
            app=app,
            event_bus=event_bus,
            db_session_factory=lambda: session_factory()
        )
        logger.info("dashboard_integration_initialized")
    except Exception as db_err:
        logger.warning("database_init_skipped", error=str(db_err),
                       hint="Dashboard API endpoints still work without DB")
        # Still init dashboard without DB session factory
        init_dashboard(app=app, event_bus=event_bus, db_session_factory=None)

    yield

    # Shutdown
    logger.info("shutting_down_application")


# Create FastAPI app
app = FastAPI(
    title="Coding Engine API",
    description="AI-Powered Code Generation Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_debug else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Jobs"])
app.include_router(artifacts.router, prefix="/api/v1/artifacts", tags=["Artifacts"])
app.include_router(ws_routes.router, prefix="/api/v1", tags=["WebSocket"])

# Portal routes (Cell Colony Community Portal)
app.include_router(portal.router, prefix="/api/v1", tags=["Portal"])

# Colony management routes
app.include_router(colony.router, prefix="/api/v1", tags=["Colony"])

# Vision API routes (Claude Vision for Review Gate)
app.include_router(vision.router, prefix="/api/v1", tags=["Vision"])

# LLM Config routes (Global model configuration editor)
app.include_router(llm_config_routes.router, tags=["LLM Config"])

# Enrichment Pipeline routes (Visualization dashboard)
app.include_router(enrichment_routes.router, tags=["Enrichment"])

# Vibe-Coding routes (Phase 31 - live user intervention during pipeline)
app.include_router(vibe_routes.router, prefix="/api/v1", tags=["Vibe-Coding"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_debug,
    )
