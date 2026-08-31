"""
Training Router — pure data-sink endpoints for Klotski and Evolutionary training.

No brain module imports.  All state lives in ``request.app.state.training_state``
which is initialised by :func:`web.brain_server._init_brain_state`.

Thread safety is ensured with a module-level :class:`threading.Lock`.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(request: Request) -> dict:
    """Shortcut to the shared training_state dict."""
    return request.app.state.training_state


def _templates(request: Request):
    """Shortcut to the Jinja2Templates instance stored on app state."""
    return request.app.state.templates


# ===================================================================
# Klotski endpoints
# ===================================================================

@router.get("/api/train/klotski/status")
async def klotski_status(request: Request) -> JSONResponse:
    with _lock:
        state = dict(_ts(request)["klotski"])
    return JSONResponse(state)


@router.post("/api/train/klotski/update")
async def klotski_update(request: Request) -> JSONResponse:
    body: Dict[str, Any] = await request.json()
    with _lock:
        _ts(request)["klotski"].update(body)
        state = dict(_ts(request)["klotski"])
    return JSONResponse({"ok": True, "klotski": state})


@router.post("/api/train/klotski/agent")
async def klotski_agent(request: Request) -> JSONResponse:
    body: Dict[str, Any] = await request.json()
    agent_id = body.get("agent_id", "default")
    with _lock:
        _ts(request)["klotski"]["agents"][agent_id] = body
    return JSONResponse({"ok": True, "agent_id": agent_id})


@router.post("/api/train/klotski/reset")
async def klotski_reset(request: Request) -> JSONResponse:
    with _lock:
        _ts(request)["klotski"] = {
            "status": "idle",
            "epoch": 0,
            "loss": 0.0,
            "agents": {},
        }
    return JSONResponse({"ok": True, "status": "reset"})


# ===================================================================
# Evolutionary training endpoints
# ===================================================================

@router.get("/api/train/evolutionary/status")
async def evolutionary_status(request: Request) -> JSONResponse:
    with _lock:
        raw = _ts(request)["evolutionary"]
        # deque is not JSON-serialisable → convert to list
        state = {k: (list(v) if isinstance(v, deque) else v) for k, v in raw.items()}
    return JSONResponse(state)


@router.post("/api/train/evolutionary/positions")
async def evolutionary_positions(request: Request) -> JSONResponse:
    body = await request.json()
    positions = body.get("positions", [])
    with _lock:
        _ts(request)["evolutionary"]["positions"] = positions
    return JSONResponse({"ok": True, "count": len(positions)})


@router.post("/api/train/evolutionary/metrics")
async def evolutionary_metrics(request: Request) -> JSONResponse:
    body = await request.json()
    with _lock:
        _ts(request)["evolutionary"]["metrics"].update(body)
        metrics = dict(_ts(request)["evolutionary"]["metrics"])
    return JSONResponse({"ok": True, "metrics": metrics})


@router.post("/api/train/evolutionary/message")
async def evolutionary_message(request: Request) -> JSONResponse:
    body = await request.json()
    msg = body.get("message", "")
    with _lock:
        _ts(request)["evolutionary"]["messages"].append(msg)
        count = len(_ts(request)["evolutionary"]["messages"])
    return JSONResponse({"ok": True, "queue_size": count})


@router.post("/api/train/evolutionary/reset")
async def evolutionary_reset(request: Request) -> JSONResponse:
    with _lock:
        _ts(request)["evolutionary"] = {
            "status": "idle",
            "generation": 0,
            "best_fitness": 0.0,
            "positions": [],
            "metrics": {},
            "messages": deque(maxlen=100),
        }
    return JSONResponse({"ok": True, "status": "reset"})


# ===================================================================
# Training UI pages
# ===================================================================

@router.get("/ui/training/klotski", response_class=HTMLResponse)
async def klotski_ui(request: Request) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request, "klotski_dashboard.html"
    )


@router.get("/ui/training/evolutionary", response_class=HTMLResponse)
async def evolutionary_ui(request: Request) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request, "evolutionary_training_dashboard.html"
    )
