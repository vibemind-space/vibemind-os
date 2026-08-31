"""
Oscillator Router -- FastAPI endpoints for the Layer4TemporalRouter.

All state lives on ``request.app.state.oscillator`` (Layer4TemporalRouter)
and ``request.app.state.oscillator_history`` (list of history entries).

Every route gracefully handles ``oscillator is None`` (testing mode).
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

def convert_numpy(obj: Any) -> Any:
    """Convert NumPy types to native Python types for JSON serialisation."""
    try:
        import numpy as np
    except ImportError:
        return obj

    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy(i) for i in obj]
    return obj


def _templates(request: Request):
    """Shortcut to the Jinja2Templates instance stored on app state."""
    return request.app.state.templates


def _record_oscillator_state(osc: Any, history: list) -> None:
    """Record current oscillator state to history (max 100 entries)."""
    if osc is None:
        return
    try:
        osc_state = osc.get_oscillator_state()
        sync = osc.get_synchrony_vector()
        dominant = osc.get_dominant_channel()
        stats = osc.get_statistics()
        token_stats = stats.get("token_adapter", {})

        entry = {
            "timestamp": datetime.now().isoformat(),
            "A": float(osc_state.A.amplitude),
            "B": float(osc_state.B.amplitude),
            "C": float(osc_state.C.amplitude),
            "phase_A": float(osc_state.A.phase),
            "phase_B": float(osc_state.B.phase),
            "phase_C": float(osc_state.C.phase),
            "coherence": float(sync.mean_coherence),
            "dominant": dominant.value,
            "tokens_processed": token_stats.get("tokens_processed", 0),
        }

        history.append(entry)

        # Cap at 100 entries
        if len(history) > 100:
            del history[: len(history) - 100]

    except Exception:
        pass


# ===================================================================
# API endpoints
# ===================================================================

@router.get("/api/oscillator/state")
async def oscillator_state(request: Request) -> JSONResponse:
    """Get current oscillator state."""
    osc = request.app.state.oscillator
    if not osc:
        return JSONResponse({"state": None, "message": "oscillator not initialized"})
    try:
        osc_data = osc.get_oscillator_state()
        sync = osc.get_synchrony_vector()
        dominant = osc.get_dominant_channel()

        state = {
            "channels": {
                "A": {
                    "amplitude": float(osc_data.A.amplitude),
                    "phase": float(osc_data.A.phase),
                    "label": "Advance",
                },
                "B": {
                    "amplitude": float(osc_data.B.amplitude),
                    "phase": float(osc_data.B.phase),
                    "label": "Explore",
                },
                "C": {
                    "amplitude": float(osc_data.C.amplitude),
                    "phase": float(osc_data.C.phase),
                    "label": "Correct",
                },
            },
            "dominant": dominant.value,
            "synchrony": {
                "mean_coherence": float(sync.mean_coherence),
                "vector": convert_numpy(sync.to_vector()),
            },
            "timestamp": datetime.now().isoformat(),
        }
        return JSONResponse({"state": convert_numpy(state)})
    except Exception as e:
        return JSONResponse({"state": None, "error": str(e)})


@router.get("/api/oscillator/history")
async def oscillator_history(request: Request) -> JSONResponse:
    """Get oscillator history for charts."""
    history = request.app.state.oscillator_history
    return JSONResponse({
        "history": history[-50:],
        "count": len(history),
        "timestamp": datetime.now().isoformat(),
    })


@router.post("/api/oscillator/tokens")
async def oscillator_tokens(request: Request) -> JSONResponse:
    """Process text through EventBridge."""
    osc = request.app.state.oscillator
    if not osc:
        return JSONResponse(
            {"error": "oscillator not initialized"}, status_code=503
        )

    body = await request.json()
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "Text required"}, status_code=400)

    try:
        result = osc.event_bridge.process_text(text)

        # Record state
        _record_oscillator_state(osc, request.app.state.oscillator_history)

        # Updated state
        osc_data = osc.get_oscillator_state()
        dominant = osc.get_dominant_channel()

        return JSONResponse({
            "tokens_extracted": result,
            "token_count": len(result),
            "state_after": {
                "A": float(osc_data.A.amplitude),
                "B": float(osc_data.B.amplitude),
                "C": float(osc_data.C.amplitude),
                "dominant": dominant.value,
            },
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/oscillator/stats")
async def oscillator_stats(request: Request) -> JSONResponse:
    """Get processing statistics."""
    osc = request.app.state.oscillator
    if not osc:
        return JSONResponse({"stats": None, "message": "oscillator not initialized"})
    try:
        stats = osc.get_statistics()
        return JSONResponse({
            "stats": convert_numpy(stats),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"stats": None, "error": str(e)})


@router.post("/api/oscillator/route")
async def oscillator_route(request: Request) -> JSONResponse:
    """Route events through full pipeline."""
    osc = request.app.state.oscillator
    if not osc:
        return JSONResponse(
            {"error": "oscillator not initialized"}, status_code=503
        )

    body = await request.json()
    events = body.get("events", [])
    task = body.get("task", "Web Dashboard Test")

    if not events:
        return JSONResponse({"error": "Events required"}, status_code=400)

    try:
        result = osc.route(events, task_description=task)

        # Record state
        _record_oscillator_state(osc, request.app.state.oscillator_history)

        return JSONResponse({
            "should_execute": result.should_execute,
            "tool_name": result.tool_name,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
            "timing_confidence": float(result.decision.timing_confidence),
            "processing_time_ms": float(result.processing_time_ms),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/oscillator/checkpoint")
async def oscillator_checkpoint_save(request: Request) -> JSONResponse:
    """Save current oscillator checkpoint."""
    osc = request.app.state.oscillator
    cm = request.app.state.checkpoint_manager
    if not osc or not cm:
        return JSONResponse(
            {"error": "oscillator or checkpoint manager not initialized"},
            status_code=503,
        )

    body = await request.json()
    name = body.get("name", None)

    try:
        path = cm.save_checkpoint(osc, name)
        return JSONResponse({
            "status": "saved",
            "path": path,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/oscillator/checkpoints")
async def oscillator_checkpoints_list(request: Request) -> JSONResponse:
    """List available oscillator checkpoints."""
    cm = request.app.state.checkpoint_manager
    if not cm:
        return JSONResponse(
            {"checkpoints": [], "message": "checkpoint manager not initialized"}
        )
    try:
        checkpoints = cm.list_checkpoints()
        return JSONResponse({
            "checkpoints": checkpoints,
            "count": len(checkpoints),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"checkpoints": [], "error": str(e)})


@router.post("/api/oscillator/restore")
async def oscillator_restore(request: Request) -> JSONResponse:
    """Restore oscillator from checkpoint."""
    osc = request.app.state.oscillator
    cm = request.app.state.checkpoint_manager
    if not osc or not cm:
        return JSONResponse(
            {"error": "oscillator or checkpoint manager not initialized"},
            status_code=503,
        )

    body = await request.json()
    name = body.get("name", "")
    if not name:
        return JSONResponse({"error": "Checkpoint name required"}, status_code=400)

    try:
        checkpoint = cm.load_checkpoint(name)
        if checkpoint is None:
            return JSONResponse(
                {"error": f"Checkpoint not found: {name}"}, status_code=404
            )

        success = cm.restore_router(osc, checkpoint)
        if success:
            request.app.state.oscillator_history.clear()
            _record_oscillator_state(osc, request.app.state.oscillator_history)
            return JSONResponse({
                "status": "restored",
                "checkpoint_name": name,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            return JSONResponse(
                {"error": "Failed to restore checkpoint"}, status_code=500
            )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/oscillator/reset")
async def oscillator_reset(request: Request) -> JSONResponse:
    """Reset oscillator state."""
    osc = request.app.state.oscillator
    if not osc:
        return JSONResponse(
            {"error": "oscillator not initialized"}, status_code=503
        )
    try:
        osc.reset()
        request.app.state.oscillator_history.clear()
        return JSONResponse({
            "status": "reset",
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/oscillator/health")
async def oscillator_health(request: Request) -> JSONResponse:
    """Get oscillator health status."""
    osc = request.app.state.oscillator
    cm = request.app.state.checkpoint_manager

    health = {
        "status": "healthy" if osc else "not_initialized",
        "router_initialized": osc is not None,
        "checkpoint_manager": cm is not None,
        "history_size": len(request.app.state.oscillator_history),
        "timestamp": datetime.now().isoformat(),
    }

    if osc:
        try:
            health["using_mamba"] = osc.temporal_ctm.use_mamba
            health["using_ollama"] = osc.token_adapter._using_ollama
        except (AttributeError, TypeError):
            pass

    return JSONResponse(health)


# ===================================================================
# UI page
# ===================================================================

@router.get("/ui/oscillator", response_class=HTMLResponse)
async def oscillator_ui(request: Request) -> HTMLResponse:
    """Render oscillator dashboard."""
    return _templates(request).TemplateResponse(
        request, "oscillator_dashboard.html"
    )
