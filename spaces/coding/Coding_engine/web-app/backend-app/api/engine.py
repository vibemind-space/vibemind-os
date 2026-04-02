"""Engine API endpoints for project listing, generation control, and WebSocket events."""
import logging
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional

from app.schemas.engine import (
    EngineProjectSummary,
    EngineProjectDetail,
    GenerationStatus,
    StartGenerationRequest,
)
from app.services.engine_service import EngineService

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket connections for engine events
_ws_connections: list[WebSocket] = []


@router.get("/projects", response_model=list[EngineProjectSummary])
def list_engine_projects():
    """List all engine projects from Data/all_services/."""
    return EngineService.list_projects()


@router.get("/projects/{project_name}", response_model=EngineProjectDetail)
def get_engine_project(project_name: str):
    """Get detailed engine project info."""
    project = EngineService.get_project(project_name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Engine project not found: {project_name}")
    return project


@router.get("/projects/{project_name}/status", response_model=GenerationStatus)
def get_generation_status(project_name: str):
    """Get current generation status."""
    return EngineService.get_generation_status(project_name)


@router.post("/projects/{project_name}/start", response_model=GenerationStatus)
def start_generation(project_name: str, request: StartGenerationRequest = StartGenerationRequest()):
    """Start generation pipeline for a project."""
    try:
        return EngineService.start_generation(
            project_name,
            skeleton_only=request.skeleton_only,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Generation start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_name}/stop", response_model=GenerationStatus)
def stop_generation(project_name: str):
    """Stop generation for a project."""
    return EngineService.stop_generation(project_name)


@router.websocket("/ws")
async def engine_websocket(websocket: WebSocket):
    """WebSocket for real-time engine events."""
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            # Keep connection alive, receive client messages if needed
            data = await websocket.receive_text()
            # Could handle client commands here
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)


async def broadcast_engine_event(event_type: str, data: dict):
    """Broadcast an engine event to all connected WebSocket clients."""
    message = {"type": event_type, "data": data}
    disconnected = []
    for ws in _ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_connections.remove(ws)
