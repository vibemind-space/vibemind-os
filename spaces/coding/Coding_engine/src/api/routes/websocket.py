"""
WebSocket Routes - Endpoints for real-time event streaming.

Provides WebSocket endpoints for:
- Event streaming from Society of Mind
- Session-specific subscriptions
- Connection statistics
"""

import uuid
from typing import Optional
from fastapi import APIRouter, WebSocket, Query
import structlog

from ..websocket import websocket_endpoint, get_connection_manager

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/{session_id}")
async def session_websocket(
    websocket: WebSocket,
    session_id: str,
    client_id: Optional[str] = Query(default=None),
):
    """
    WebSocket endpoint for a specific session.

    Args:
        websocket: WebSocket connection
        session_id: Session ID to subscribe to
        client_id: Optional client identifier (auto-generated if not provided)
    """
    if not client_id:
        client_id = f"client_{uuid.uuid4().hex[:8]}"

    await websocket_endpoint(websocket, client_id, session_id)


@router.websocket("/ws")
async def global_websocket(
    websocket: WebSocket,
    client_id: Optional[str] = Query(default=None),
):
    """
    Global WebSocket endpoint (receives all events).

    Args:
        websocket: WebSocket connection
        client_id: Optional client identifier (auto-generated if not provided)
    """
    if not client_id:
        client_id = f"client_{uuid.uuid4().hex[:8]}"

    await websocket_endpoint(websocket, client_id, session_id=None)


@router.websocket("/engine/generation/ws")
async def generation_websocket(
    websocket: WebSocket,
    client_id: Optional[str] = Query(default=None),
):
    """
    WebSocket endpoint for generation event streaming.
    Used by the frontend Engine Editor for real-time updates.
    """
    if not client_id:
        client_id = f"gen_{uuid.uuid4().hex[:8]}"

    await websocket_endpoint(websocket, client_id, session_id=None)


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    manager = get_connection_manager()
    return manager.get_stats()
