"""
Dashboard integration module for FastAPI application.
Initializes dashboard routes, WebSocket handlers, and event tracking.
"""

from typing import Callable
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes import dashboard, dashboard_websocket
from src.api.routes.dashboard_websocket import dashboard_manager
from src.api.routes.dashboard import set_review_gate_dependencies
from src.services.dashboard_event_tracker import create_dashboard_event_tracker
from src.mind.event_bus import EventBus
from src.mind.shared_state import SharedState
import structlog

logger = structlog.get_logger(__name__)


def init_dashboard(
    app: FastAPI,
    event_bus: EventBus,
    db_session_factory: Callable[[], AsyncSession]
) -> None:
    """
    Initialize dashboard system with FastAPI application.

    Sets up:
    - REST API routes for dashboard data
    - WebSocket endpoints for real-time updates
    - EventBus integration for event tracking
    - Database event storage

    Args:
        app: FastAPI application instance
        event_bus: EventBus instance for event subscriptions
        db_session_factory: Factory function to create database sessions

    Example:
        ```python
        from fastapi import FastAPI
        from src.mind.event_bus import EventBus
        from src.models.base import get_db

        app = FastAPI()
        event_bus = EventBus()

        # Initialize dashboard
        init_dashboard(app, event_bus, get_db)
        ```
    """
    # Include REST API routes
    app.include_router(dashboard.router)
    logger.info("dashboard_rest_routes_registered", prefix="/api/v1/dashboard")

    # Include project data routes (epics, requirements, API endpoints, diagrams, tests)
    try:
        from src.api.routes import project_data
        app.include_router(project_data.router)
        logger.info("project_data_routes_registered")
    except Exception as e:
        logger.warning("project_data_routes_failed", error=str(e))

    # Initialize SharedState and set dependencies for review gate and sandbox error reporting
    shared_state = SharedState()
    set_review_gate_dependencies(shared_state, event_bus)
    logger.info("review_gate_dependencies_set")

    # Include WebSocket routes
    app.include_router(dashboard_websocket.router)
    logger.info("dashboard_websocket_routes_registered", prefix="/api/v1/dashboard/ws")

    # Create and start event tracker (needs DB, skip if unavailable)
    tracker = None
    if db_session_factory is not None:
        try:
            tracker = create_dashboard_event_tracker(
                event_bus=event_bus,
                db_session_factory=db_session_factory,
                dashboard_manager=dashboard_manager
            )
        except Exception as e:
            logger.warning("event_tracker_init_skipped", error=str(e))

    logger.info(
        "dashboard_integration_complete",
        rest_routes=True,
        websocket_routes=True,
        event_tracking=tracker is not None,
    )

    # Store tracker reference on app for lifecycle management
    app.state.dashboard_event_tracker = tracker


def get_dashboard_stats() -> dict:
    """
    Get dashboard system statistics.

    Returns:
        Dictionary with WebSocket and event tracking stats
    """
    return {
        "websocket": dashboard_manager.get_stats(),
        "event_tracker_running": True  # Can be enhanced with tracker stats
    }


__all__ = ["init_dashboard", "get_dashboard_stats", "dashboard_manager"]
