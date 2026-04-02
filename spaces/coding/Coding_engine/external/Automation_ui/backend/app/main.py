"""TRAE Backend FastAPI Application Factory

Creates and configures the FastAPI application with all necessary
routers, middleware, and service integrations.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import close_db, init_db
from .logger_config import get_logger
from .routers import (
    api_v1_router, client_manager_router, desktop_router, health_router,
    mcp_bridge_router, node_configs_router, ocr_router, shell_router,
    websocket_router, workflows_router)
from .routers.automation import router as automation_router
from .routers.clawdbot import router as clawdbot_router
from .routers.clawhub import router as clawhub_router
from .routers.configs import router as configs_router
from .routers.llm_intent import router as llm_intent_router
from .services.client_manager_service import get_client_manager
from .services.manager import ServiceManager
from .services.redis_pubsub import redis_pubsub

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting TRAE Backend services...")
    settings = get_settings()

    try:
        # Initialize database
        logger.info("Initializing database connection...")
        init_db(
            database_url=settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            echo=settings.database_echo
        )
        logger.info("Database initialized successfully")

        # Initialize Redis PubSub (optional - graceful degradation if unavailable)
        logger.info("Initializing Redis PubSub...")
        try:
            await redis_pubsub.connect(settings.redis_url)
            logger.info("Redis PubSub initialized successfully")
        except Exception as redis_err:
            logger.warning(f"Redis PubSub unavailable (non-critical): {redis_err}")
            logger.warning("Continuing without Redis - task queue and pub/sub features disabled")

        # Setup Task Queue Bridge (Redis → WebSocket for voice commands)
        try:
            from .routers.websocket import setup_task_queue_bridge
            bridge_ok = await setup_task_queue_bridge()
            if bridge_ok:
                logger.info("Task Queue Bridge initialized successfully")
            else:
                logger.warning("Task Queue Bridge setup skipped (Redis may not be available)")
        except Exception as e:
            logger.warning(f"Task Queue Bridge setup failed: {e}")

        # Initialize service manager
        service_manager = ServiceManager()
        await service_manager.initialize()

        # Store in app state for router access
        app.state.service_manager = service_manager

        # Wire ActionRouter with WebSocket manager
        from .services.action_router import action_router
        from .routers.websocket import manager as ws_manager
        action_router.set_ws_manager(ws_manager)
        action_router.configure(settings)
        if settings.execution_mode == "remote":
            logger.info("ActionRouter: REMOTE mode - desktop actions delegated to client")

        # Start Discord Analyzer Listener (polls #fixes, posts fix suggestions to #dev-tasks)
        try:
            from .services.discord_listener import start_analyzer_listener
            await start_analyzer_listener()
            logger.info("Discord Analyzer Listener started")
        except Exception as e:
            logger.warning(f"Discord Analyzer Listener failed to start (non-critical): {e}")

        logger.info("All services initialized successfully")

        yield

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down TRAE Backend services...")

        # Cleanup Client Manager (stop Python desktop client)
        try:
            client_manager = get_client_manager()
            await client_manager.cleanup()
            logger.info("Client Manager cleanup completed")
        except Exception as e:
            logger.error(f"Client Manager cleanup failed: {e}")

        # Cleanup Service Manager
        if hasattr(app.state, "service_manager"):
            await app.state.service_manager.cleanup()

        # Cleanup Redis PubSub
        try:
            await redis_pubsub.close()
            logger.info("Redis PubSub closed")
        except Exception as e:
            logger.error(f"Redis PubSub cleanup failed: {e}")

        # Cleanup Database
        try:
            await close_db()
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")

        logger.info("Cleanup completed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title="TRAE Backend API",
        description="Visual Node-Based Automation Backend with Live Desktop Integration",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS configuration for frontend integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:5174",  # Alternative Vite dev server
            "http://localhost:5175",  # Alternative Vite dev server
            "http://localhost:3000",  # Alternative dev port
            "http://localhost:3003",  # Frontend dev port
            "http://localhost:8007",  # Backend API port
            "http://localhost:8765",  # Voice Control (Vapi) server
            "http://localhost:18789",  # Clawdbot Gateway
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers with prefixes
    app.include_router(health_router, prefix="/api/health", tags=["Health"])
    app.include_router(desktop_router, prefix="/api/desktop", tags=["Desktop"])
    app.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])
    app.include_router(
        node_configs_router, prefix="/api/node-configs", tags=["Node Configurations"]
    )
    app.include_router(shell_router, prefix="/api/shell", tags=["Shell"])

    # Enable automation router for click functionality
    app.include_router(automation_router, prefix="/api/automation", tags=["Automation"])

    # Enable workflow and API v1 routers
    app.include_router(workflows_router, prefix="/api/workflows", tags=["Workflows"])

    # Enable OCR router first to avoid routing conflicts
    app.include_router(ocr_router, prefix="/api/v1/ocr", tags=["OCR"])

    # Include API v1 router last (it also has OCR endpoints but they should be overridden)
    app.include_router(api_v1_router, prefix="/api/v1", tags=["API v1"])

    # Client Manager Router - für Start/Stop/Status des Desktop Capture Clients
    app.include_router(
        client_manager_router, prefix="/api/client", tags=["Client Manager"]
    )

    # MCP Bridge Router - VibeMind Integration mit Moire MCP Tools
    app.include_router(mcp_bridge_router, prefix="/api/mcp", tags=["MCP Bridge"])

    # Configs Router - Live Desktop Configurations (replaces Supabase)
    app.include_router(configs_router, prefix="/api/configs", tags=["Configs"])

    # Clawdbot Router - Messaging integration (WhatsApp, Telegram, Discord, etc.)
    app.include_router(clawdbot_router, prefix="/api/clawdbot", tags=["Clawdbot"])

    # ClawHub Router - Skill Marketplace (ClawHub.ai integration)
    app.include_router(clawhub_router, prefix="/api/clawhub", tags=["ClawHub"])

    # LLM Intent Router - Agentic Desktop Automation via Claude Opus 4.6
    app.include_router(llm_intent_router, prefix="/api/llm", tags=["LLM Intent"])

    # E2E Test Runner - Autonomous testing via Playwright MCP
    try:
        from app.routers.e2e_tests import router as e2e_router
        app.include_router(e2e_router, tags=["E2E Tests"])
    except ImportError as e:
        logger.warning(f"E2E test router not available: {e}")

    logger.info("FastAPI application created with all routers")

    return app


# Create app instance for uvicorn
app = create_app()
