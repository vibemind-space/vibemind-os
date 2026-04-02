"""eyeTerm REST API router — status and control endpoints.

Proxies to the eyeTerm process running in VibeMind's Python backend.
The eyeTerm MJPEG stream runs on port 8099; this router provides
status and control at /api/eyeterm/*.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/eyeterm", tags=["eyeterm"])

# Shared state — set by VibeMind's electron_backend when eyeTerm starts
_eyeterm_state = {
    "running": False,
    "state": "idle",
    "cursor_enabled": False,
    "stream_port": 8099,
}


def update_eyeterm_state(state: dict):
    """Called from eyeTerm's heartbeat to update shared state."""
    _eyeterm_state.update(state)


@router.get("/status")
async def eyeterm_status():
    """Get current eyeTerm state for the PiP overlay."""
    return _eyeterm_state


@router.post("/toggle-cursor")
async def toggle_cursor():
    """Toggle cursor control on/off."""
    # This will be wired to the actual eyeTerm instance
    _eyeterm_state["cursor_enabled"] = not _eyeterm_state["cursor_enabled"]
    return {"cursor_enabled": _eyeterm_state["cursor_enabled"]}
