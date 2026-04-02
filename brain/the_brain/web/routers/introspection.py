"""
Introspection Router -- FastAPI endpoints for brain self-monitoring (Default Mode Network).

Extracted from the old brain_dashboard_server.py (~30+ routes).  Covers:
  - Brain state / gates / activation / strategies
  - Emotional / homeostatic / memory state (graceful fallback)
  - Cognitive loop / agent loop state (graceful fallback)
  - Health sub-endpoints (components, dependencies, readiness, liveness)
  - Frequency controller
  - Monitoring / observability (metrics, audit trail, loop traces, error rates, heatmap)
  - Goals / evolution / CTM / cognitive status
  - Causal / meta / federated subsystems
  - LLM stats
  - Heartbeat / consciousness / neuromodulation proxies
  - Conversation monitoring / simulation
  - Advanced learning health
  - Sensory extract / predict path

All state lives on ``request.app.state.<module>`` attributes.
Every route gracefully handles ``module is None`` (testing mode) —
no HTTP proxying to localhost:5003.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

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



# ===================================================================
# Group 1 — Brain State  (meta_router, brain_monitor, strategy_lib)
# ===================================================================

@router.get("/api/brain/state")
async def brain_state(request: Request):
    """Current brain routing state."""
    mr = request.app.state.meta_router
    if mr is None:
        return JSONResponse({
            "state": None,
            "message": "meta_router not initialized",
            "timestamp": time.time(),
        })
    try:
        state = mr.get_state()
        return JSONResponse({
            "state": convert_numpy(state),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "state": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/brain/gates")
async def brain_gates(request: Request):
    """Current gate values from BrainActivityMonitor."""
    bm = request.app.state.brain_monitor
    if bm is None:
        return JSONResponse({
            "gates": None,
            "message": "brain_monitor not initialized",
            "timestamp": time.time(),
        })
    try:
        gates = bm.get_gates()
        return JSONResponse({
            "gates": convert_numpy(gates),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "gates": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/brain/activation")
async def brain_activation(request: Request):
    """Activation map from BrainActivityMonitor."""
    bm = request.app.state.brain_monitor
    if bm is None:
        return JSONResponse({
            "activation": None,
            "message": "brain_monitor not initialized",
            "timestamp": time.time(),
        })
    try:
        activation = bm.get_activation()
        return JSONResponse({
            "activation": convert_numpy(activation),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "activation": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/brain/strategies")
async def brain_strategies(request: Request):
    """Available strategies from StrategyLibrary."""
    sl = request.app.state.strategy_lib
    if sl is None:
        return JSONResponse({
            "strategies": None,
            "message": "strategy_lib not initialized",
            "timestamp": time.time(),
        })
    try:
        strategies = sl.list_strategies()
        return JSONResponse({
            "strategies": convert_numpy(strategies),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "strategies": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/brain/interventions")
async def brain_interventions(request: Request):
    """Recent interventions from LiveBrainMonitor."""
    lm = request.app.state.live_monitor
    if lm is None:
        return JSONResponse({
            "interventions": [],
            "message": "live_monitor not initialized",
            "timestamp": time.time(),
        })
    try:
        interventions = lm.get_interventions()
        return JSONResponse({
            "interventions": convert_numpy(interventions),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "interventions": [],
            "error": str(exc),
            "timestamp": time.time(),
        })


# ===================================================================
# Group 2 — Proxy-replacement routes (graceful fallbacks)
# ===================================================================

@router.get("/api/brain/cognitive_loop")
async def cognitive_loop(request: Request):
    """Cognitive loop state — graceful fallback when unified brain is not wired."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "cognitive loop not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/agent_loop_state")
async def agent_loop_state(request: Request):
    """Agent loop state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "agent loop not connected to unified brain",
        "timestamp": time.time(),
    })


@router.post("/api/brain/agent_loop/submit")
async def agent_loop_submit(request: Request):
    """Submit task to agent loop — 503 until unified brain is wired."""
    return JSONResponse(
        {"error": "agent loop not initialized", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/brain/emotional_state")
async def emotional_state(request: Request):
    """Emotional state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "emotional state not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/homeostatic_state")
async def homeostatic_state(request: Request):
    """Homeostatic state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "homeostatic state not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/memory_state")
async def memory_state(request: Request):
    """Memory state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "memory state not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/heartbeat_status")
async def heartbeat_status(request: Request):
    """Heartbeat status — graceful fallback."""
    return JSONResponse({
        "active": False,
        "message": "heartbeat not connected to unified brain",
        "timestamp": time.time(),
    })


@router.post("/api/brain/sensory_extract")
async def sensory_extract(request: Request):
    """Sensory extract — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "message": "sensory extract not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/goal_graph_state")
async def goal_graph_state(request: Request):
    """Goal graph state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "goal graph not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/neuromodulation_state")
async def neuromodulation_state(request: Request):
    """Neuromodulation state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "neuromodulation not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/consciousness_state")
async def consciousness_state(request: Request):
    """Consciousness state — graceful fallback."""
    return JSONResponse({
        "enabled": False,
        "state": None,
        "message": "consciousness module not connected to unified brain",
        "timestamp": time.time(),
    })


# ===================================================================
# Group 3 — Monitoring & Observability
# ===================================================================

@router.get("/api/brain/metrics")
async def brain_metrics(request: Request):
    """Prometheus-style metrics — returns plain text."""
    return PlainTextResponse(
        "# Metrics unavailable — unified brain not connected\n",
        media_type="text/plain",
    )


@router.get("/api/brain/metrics_json")
async def brain_metrics_json(request: Request):
    """JSON metrics — graceful fallback."""
    return JSONResponse({
        "error": "metrics unavailable",
        "timestamp": time.time(),
    })


@router.get("/api/brain/audit_trail")
async def audit_trail(request: Request):
    """Recent audit trail entries."""
    return JSONResponse({
        "recent": [],
        "stats": {},
        "timestamp": time.time(),
    })


@router.get("/api/brain/loop_traces")
async def loop_traces(request: Request):
    """Cognitive loop traces."""
    return JSONResponse({
        "recent_traces": [],
        "phase_stats": {},
        "total_traces": 0,
        "timestamp": time.time(),
    })


@router.get("/api/brain/error_rates")
async def error_rates(request: Request):
    """Error rates by component."""
    return JSONResponse({
        "error_rates": {},
        "recent_errors": [],
        "timestamp": time.time(),
    })


@router.get("/api/brain/heatmap")
async def heatmap(request: Request):
    """Modality activation heatmap data."""
    return JSONResponse({
        "heatmap": {
            "modalities": [],
            "matrix": [],
        },
        "modality_averages": {},
        "timestamp": time.time(),
    })


# ===================================================================
# Group 4 — Frequency Controller
# ===================================================================

@router.get("/api/brain/frequency")
async def brain_frequency(request: Request):
    """Current brain frequency state."""
    fc = request.app.state.frequency_controller
    if fc is None:
        return JSONResponse({
            "frequency": None,
            "message": "frequency_controller not initialized",
            "timestamp": time.time(),
        })
    try:
        state = fc.get_state()
        return JSONResponse({
            "frequency": convert_numpy(state),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "frequency": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.post("/api/brain/frequency/set")
async def brain_frequency_set(request: Request):
    """Set brain frequency parameters."""
    fc = request.app.state.frequency_controller
    if fc is None:
        return JSONResponse({
            "ok": False,
            "message": "frequency_controller not initialized",
            "timestamp": time.time(),
        })
    try:
        body = await request.json()
        # Whitelist accepted keys to avoid parameter injection
        allowed = {"mode", "band", "target_hz", "ramp_time", "activation", "suppress_others"}
        filtered = {k: v for k, v in body.items() if k in allowed}
        result = fc.set_frequency(**filtered)
        return JSONResponse({
            "ok": True,
            "result": convert_numpy(result),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/brain/frequency/bands")
async def brain_frequency_bands(request: Request):
    """Available frequency bands."""
    fc = request.app.state.frequency_controller
    if fc is None:
        return JSONResponse({
            "bands": None,
            "message": "frequency_controller not initialized",
            "timestamp": time.time(),
        })
    try:
        bands = fc.get_bands()
        return JSONResponse({
            "bands": convert_numpy(bands),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "bands": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/brain/frequency/markers")
async def brain_frequency_markers(request: Request):
    """Frequency event markers."""
    fc = request.app.state.frequency_controller
    if fc is None:
        return JSONResponse({
            "markers": None,
            "message": "frequency_controller not initialized",
            "timestamp": time.time(),
        })
    try:
        markers = fc.get_markers()
        return JSONResponse({
            "markers": convert_numpy(markers),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "markers": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


# ===================================================================
# Group 5 — Health (system-level)
# ===================================================================

@router.get("/api/health/components")
async def health_components(request: Request):
    """Health of individual brain components."""
    state = request.app.state
    components = {
        "meta_router": state.meta_router is not None,
        "brain_monitor": state.brain_monitor is not None,
        "strategy_lib": state.strategy_lib is not None,
        "live_monitor": state.live_monitor is not None,
        "path_planner": state.path_planner is not None,
        "llm_router": state.llm_router is not None,
        "frequency_controller": state.frequency_controller is not None,
        "oscillator": state.oscillator is not None,
        "checkpoint_manager": state.checkpoint_manager is not None,
        "swarm_orchestrator": state.swarm_orchestrator is not None,
    }
    total = len(components)
    healthy = sum(1 for v in components.values() if v)
    return JSONResponse({
        "components": components,
        "healthy": healthy,
        "total": total,
        "status": "healthy" if healthy == total else ("degraded" if healthy > 0 else "not_initialized"),
        "timestamp": time.time(),
    })


@router.get("/api/health/dependencies")
async def health_dependencies(request: Request):
    """External dependency health."""
    return JSONResponse({
        "dependencies": {
            "unified_brain": False,
            "memory_api": False,
            "llm_service": False,
        },
        "message": "dependency checks not yet wired",
        "timestamp": time.time(),
    })


@router.get("/api/health/readiness")
async def health_readiness(request: Request):
    """Kubernetes-style readiness probe."""
    return JSONResponse({
        "ready": True,
        "timestamp": time.time(),
    })


@router.get("/api/health/liveness")
async def health_liveness(request: Request):
    """Kubernetes-style liveness probe."""
    return JSONResponse({
        "alive": True,
        "timestamp": time.time(),
    })


# ===================================================================
# Group 6 — LLM Stats
# ===================================================================

@router.get("/api/llm/stats")
async def llm_stats(request: Request):
    """LLM routing statistics."""
    lr = request.app.state.llm_router
    if lr is None:
        return JSONResponse(
            {"error": "llm_router not initialized", "timestamp": time.time()},
            status_code=503,
        )
    try:
        stats = lr.get_stats()
        return JSONResponse({
            "stats": convert_numpy(stats),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "stats": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


# ===================================================================
# Group 7 — Goals / Evolution / CTM / Cognitive Status
# ===================================================================

@router.get("/api/brain/goals")
async def brain_goals(request: Request):
    """Current goals — graceful fallback."""
    return JSONResponse({
        "goals": [],
        "enabled": False,
        "message": "goal system not connected to unified brain",
        "timestamp": time.time(),
    })


@router.post("/api/brain/goals/add")
async def brain_goals_add(request: Request):
    """Add a goal — 503 until wired."""
    return JSONResponse(
        {"error": "goal system not initialized", "timestamp": time.time()},
        status_code=503,
    )


@router.post("/api/brain/goals/{goal_id}/complete")
async def brain_goals_complete(goal_id: str, request: Request):
    """Mark goal complete — 503 until wired."""
    return JSONResponse(
        {"error": "goal system not initialized", "goal_id": goal_id, "timestamp": time.time()},
        status_code=503,
    )


@router.post("/api/brain/goals/{goal_id}/fail")
async def brain_goals_fail(goal_id: str, request: Request):
    """Mark goal failed — 503 until wired."""
    return JSONResponse(
        {"error": "goal system not initialized", "goal_id": goal_id, "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/brain/evolution")
async def brain_evolution(request: Request):
    """Evolution state — graceful fallback."""
    return JSONResponse({
        "evolution": None,
        "enabled": False,
        "message": "evolution system not connected to unified brain",
        "timestamp": time.time(),
    })


@router.post("/api/brain/evolution/evolve")
async def brain_evolution_evolve(request: Request):
    """Trigger evolution step — 503 until wired."""
    return JSONResponse(
        {"error": "evolution system not initialized", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/brain/ctm_health")
async def ctm_health(request: Request):
    """CTM health — graceful fallback."""
    return JSONResponse({
        "ctm_health": None,
        "enabled": False,
        "message": "CTM not connected to unified brain",
        "timestamp": time.time(),
    })


@router.get("/api/brain/cognitive_status")
async def cognitive_status(request: Request):
    """Cognitive status summary — graceful fallback."""
    return JSONResponse({
        "cognitive_status": None,
        "enabled": False,
        "message": "cognitive status not connected to unified brain",
        "timestamp": time.time(),
    })


# ===================================================================
# Group 8 — Causal / Meta / Federated / Advanced Learning
# ===================================================================

@router.get("/api/causal/status")
async def causal_status(request: Request):
    """Causal reasoning status — not yet wired."""
    return JSONResponse(
        {"error": "causal reasoning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/causal/graph")
async def causal_graph(request: Request):
    """Causal graph — not yet wired."""
    return JSONResponse(
        {"error": "causal reasoning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.post("/api/causal/analyze")
async def causal_analyze(request: Request):
    """Causal analysis — not yet wired."""
    return JSONResponse(
        {"error": "causal reasoning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/meta/status")
async def meta_status(request: Request):
    """Meta-learning status — not yet wired."""
    return JSONResponse(
        {"error": "meta-learning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.post("/api/meta/adapt")
async def meta_adapt(request: Request):
    """Meta-learning adapt — not yet wired."""
    return JSONResponse(
        {"error": "meta-learning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/federated/status")
async def federated_status(request: Request):
    """Federated learning status — not yet wired."""
    return JSONResponse(
        {"error": "federated learning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/federated/nodes")
async def federated_nodes(request: Request):
    """Federated learning nodes — not yet wired."""
    return JSONResponse(
        {"error": "federated learning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/federated/rounds")
async def federated_rounds(request: Request):
    """Federated learning rounds — not yet wired."""
    return JSONResponse(
        {"error": "federated learning not available", "timestamp": time.time()},
        status_code=503,
    )


@router.get("/api/advanced_learning/health")
async def advanced_learning_health(request: Request):
    """Advanced learning health — not yet wired."""
    return JSONResponse(
        {"error": "advanced learning not available", "timestamp": time.time()},
        status_code=503,
    )


# ===================================================================
# Group 9 — Conversation Monitoring & Simulation
# ===================================================================

@router.get("/api/conversation/active")
async def conversation_active(request: Request):
    """Active conversations from LiveBrainMonitor."""
    lm = request.app.state.live_monitor
    if lm is None:
        return JSONResponse({
            "conversations": [],
            "message": "live_monitor not initialized",
            "timestamp": time.time(),
        })
    try:
        convos = lm.get_active_conversations()
        return JSONResponse({
            "conversations": convert_numpy(convos),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "conversations": [],
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.get("/api/conversation/history")
async def conversation_history(request: Request):
    """Conversation history."""
    lm = request.app.state.live_monitor
    if lm is None:
        return JSONResponse({
            "history": [],
            "message": "live_monitor not initialized",
            "timestamp": time.time(),
        })
    try:
        history = lm.get_conversation_history()
        return JSONResponse({
            "history": convert_numpy(history),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "history": [],
            "error": str(exc),
            "timestamp": time.time(),
        })


@router.post("/api/simulate/conversation")
async def simulate_conversation(request: Request):
    """Simulate a conversation for testing — 503 until wired."""
    return JSONResponse(
        {"error": "simulation not available", "timestamp": time.time()},
        status_code=503,
    )


# ===================================================================
# Group 10 — Predict Path
# ===================================================================

@router.post("/api/predict/path")
async def predict_path(request: Request):
    """Predict conversation path using ConversationPathPlanner."""
    pp = request.app.state.path_planner
    if pp is None:
        return JSONResponse({
            "path": None,
            "message": "path_planner not initialized",
            "timestamp": time.time(),
        })
    try:
        body = await request.json()
        task = body.get("task", "")
        if not task:
            return JSONResponse({"error": "task is required"}, status_code=400)
        result = pp.predict_path(task)
        return JSONResponse({
            "path": convert_numpy(result),
            "timestamp": time.time(),
        })
    except Exception as exc:
        return JSONResponse({
            "path": None,
            "error": str(exc),
            "timestamp": time.time(),
        })


# ===================================================================
# UI page
# ===================================================================

@router.get("/ui/brain", response_class=HTMLResponse)
async def brain_ui(request: Request) -> HTMLResponse:
    """Render brain dashboard."""
    return request.app.state.templates.TemplateResponse(
        request, "brain_dashboard.html"
    )
