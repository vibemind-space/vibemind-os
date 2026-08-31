"""
Swarm Router -- FastAPI endpoints for the BrainSwarmOrchestrator.

All state lives on ``request.app.state.swarm_orchestrator`` and
``request.app.state.swarm_logs``.

Every route gracefully handles ``swarm_orchestrator is None`` (testing mode).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _templates(request: Request):
    """Shortcut to the Jinja2Templates instance stored on app state."""
    return request.app.state.templates


# ===================================================================
# API endpoints
# ===================================================================

@router.post("/api/swarm/execute")
async def swarm_execute(request: Request) -> JSONResponse:
    """Execute task with brain + swarm."""
    orch = request.app.state.swarm_orchestrator
    if not orch:
        return JSONResponse(
            {"error": "swarm orchestrator not initialized"}, status_code=503
        )

    body = await request.json()
    task = body.get("task", "")
    if not task:
        return JSONResponse({"error": "No task provided"}, status_code=400)

    logs: list = request.app.state.swarm_logs

    # Log user input
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "type": "user",
        "sender": "User",
        "content": task,
    })

    try:
        # FastAPI is already async -- no need for new_event_loop hack
        result = await orch.process_task(task)

        brain_analysis = result.get("brain_analysis", {})
        prediction = brain_analysis.get("prediction", {})
        suggested_agent = result.get("suggested_agent", "unknown")

        # Log brain analysis
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "brain",
            "sender": "Autonomous Brain",
            "content": (
                f"Task Type: {prediction.get('task_type', 'unknown')}\n"
                f"Confidence: {prediction.get('confidence', 0.0):.2f}\n"
                f"Suggested Agent: {suggested_agent}"
            ),
        })

        # Log routing
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "handoff",
            "sender": "Coordinator",
            "content": f"Routing to {suggested_agent} (brain recommendation)",
        })

        return JSONResponse({
            "success": True,
            "result": {
                "task": task,
                "suggested_agent": suggested_agent,
                "prediction": prediction,
            },
        })

    except Exception as e:
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "error",
            "sender": "System",
            "content": str(e),
        })
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/swarm/logs")
async def swarm_logs(request: Request) -> JSONResponse:
    """Return execution logs."""
    logs: list = request.app.state.swarm_logs
    return JSONResponse({
        "execution_log": logs,
        "count": len(logs),
        "timestamp": datetime.now().isoformat(),
    })


@router.get("/api/swarm/stats")
async def swarm_stats(request: Request) -> JSONResponse:
    """Get swarm statistics."""
    orch = request.app.state.swarm_orchestrator
    if not orch:
        return JSONResponse({"stats": None, "message": "swarm orchestrator not initialized"})
    try:
        stats = orch.get_brain_stats()
        return JSONResponse({
            "stats": stats,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"stats": None, "error": str(e)})


@router.get("/api/swarm/health")
async def swarm_health(request: Request) -> JSONResponse:
    """Swarm health check."""
    orch = request.app.state.swarm_orchestrator

    health: dict[str, Any] = {
        "status": "operational" if orch else "not_initialized",
        "orchestrator_initialized": orch is not None,
        "log_count": len(request.app.state.swarm_logs),
        "timestamp": datetime.now().isoformat(),
    }

    if orch:
        try:
            swarm_status = orch.get_swarm_status()
            health["agents"] = swarm_status.get("agents_initialized", 0)
        except (AttributeError, TypeError):
            pass

    return JSONResponse(health)


# ===================================================================
# UI page
# ===================================================================

@router.get("/ui/swarm", response_class=HTMLResponse)
async def swarm_ui(request: Request) -> HTMLResponse:
    """Render autonomous swarm dashboard."""
    return _templates(request).TemplateResponse(
        request, "autonomous_swarm.html"
    )
