"""
Radial Dashboard Router -- REST + SSE endpoints for radial attention monitoring.

Provides:
  - GET /api/bridges        -- All 10 bridge states as JSON
  - GET /api/radial/rings   -- Ring activations (5 rings)
  - GET /api/modulation     -- 4 composite factors + 29 hook values
  - GET /api/experience-buffer/stats -- Buffer size, capacity, rewards
  - GET /api/minibook/activity       -- Minibook social feed (graceful offline)
  - GET /api/radial/stream           -- SSE stream (2 Hz bridge+ring+modulation)

All state lives on ``request.app.state.agent_loop`` which holds:
  .radial_network, ._last_radial_output, .experience_buffer, .seed_encoder
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _convert(obj: Any) -> Any:
    """Recursively convert numpy / dataclass / non-JSON types to plain Python."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
    except ImportError:
        pass

    try:
        import torch
        if isinstance(obj, torch.Tensor):
            return obj.detach().cpu().tolist()
    except ImportError:
        pass

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _convert(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert(i) for i in obj]
    return obj


def _get_agent_loop(request: Request):
    """Return agent_loop from app.state or None."""
    return getattr(request.app.state, "agent_loop", None)


def _get_radial(request: Request):
    """Return radial_network from agent_loop or None."""
    loop = _get_agent_loop(request)
    if loop is None:
        return None
    return getattr(loop, "radial_network", None)


def _bridge_state_dict(bridge_name: str, state_obj) -> dict:
    """Serialize a bridge state dataclass to a JSON-safe dict."""
    if state_obj is None:
        return {"bridge": bridge_name, "status": "inactive"}
    d = _convert(state_obj)
    d["bridge"] = bridge_name
    d["status"] = "active"
    return d


# ---------------------------------------------------------------------------
# Bridge name → attribute name mapping
# ---------------------------------------------------------------------------
_BRIDGE_MAP = {
    "neuromodulation": "neuromod",
    "cortex": "cortex",
    "limbic": "limbic",
    "sleep_wake": "sleep_wake",
    "motor": "motor",
    "defense": "defense",
    "memory": "memory",
    "integration": "integration",
    "visceral": "visceral",
    "social_perception": "social",
}


def _collect_bridge_states(request: Request) -> dict:
    """Collect all 10 bridge states from the last radial output's modulation."""
    loop = _get_agent_loop(request)
    radial = _get_radial(request)
    bridges = {}

    if radial is not None:
        # RadialAttentionNetwork stores modulation context with bridge states
        mod_ctx = getattr(radial, "_modulation_context", None)
        if mod_ctx is not None:
            for display_name, attr_name in _BRIDGE_MAP.items():
                state_obj = getattr(mod_ctx, attr_name, None)
                bridges[display_name] = _bridge_state_dict(display_name, state_obj)
            return bridges

    # Fallback: try reading from _last_radial_output
    if loop is not None:
        last = getattr(loop, "_last_radial_output", None)
        if last is not None and isinstance(last, dict):
            # Check for modulation_context in output
            mod_ctx = last.get("modulation_context")
            if mod_ctx is not None:
                for display_name, attr_name in _BRIDGE_MAP.items():
                    state_obj = getattr(mod_ctx, attr_name, None)
                    bridges[display_name] = _bridge_state_dict(display_name, state_obj)
                return bridges

    # No bridge data available
    for display_name in _BRIDGE_MAP:
        bridges[display_name] = _bridge_state_dict(display_name, None)
    return bridges


# ===================================================================
# REST Endpoints
# ===================================================================

@router.get("/api/bridges")
async def get_bridges(request: Request):
    """Return all 10 bridge states as JSON.

    Each bridge returns its field values or {status: "inactive"} if
    the bridge hasn't been activated yet.
    """
    bridges = _collect_bridge_states(request)
    return JSONResponse({
        "bridges": bridges,
        "timestamp": time.time(),
        "count": sum(1 for b in bridges.values() if b.get("status") == "active"),
    })


@router.get("/api/radial/rings")
async def get_ring_activations(request: Request):
    """Return ring activations from the last radial forward pass.

    Returns 5 entries (one per ring) with activation norms and dims.
    """
    loop = _get_agent_loop(request)
    if loop is None:
        return JSONResponse(
            {"error": "agent_loop not available", "rings": []},
            status_code=503,
        )

    last = getattr(loop, "_last_radial_output", None)
    if last is None:
        return JSONResponse({
            "rings": [],
            "message": "No radial forward has run yet",
            "timestamp": time.time(),
        })

    ring_data = []
    ring_activations = last.get("ring_activations", [])

    # ring_activations is a list of tensors [ring0, ring1, ...]
    ring_names = ["sensory", "pattern", "semantic", "abstract", "meta"]
    ring_dims = [64, 128, 256, 256, 128]

    for i, (name, dim) in enumerate(zip(ring_names, ring_dims)):
        act = ring_activations[i] if i < len(ring_activations) else None
        if act is not None:
            try:
                import torch
                if isinstance(act, torch.Tensor):
                    act_np = act.detach().cpu().numpy()
                else:
                    import numpy as np
                    act_np = np.asarray(act)
                norm = float(act_np.flatten().__abs__().sum() / max(act_np.size, 1))
                ring_data.append({
                    "ring": i,
                    "name": name,
                    "dim": dim,
                    "norm": round(norm, 6),
                    "min": round(float(act_np.min()), 6),
                    "max": round(float(act_np.max()), 6),
                    "mean": round(float(act_np.mean()), 6),
                })
            except Exception:
                ring_data.append({"ring": i, "name": name, "dim": dim, "status": "error"})
        else:
            ring_data.append({"ring": i, "name": name, "dim": dim, "status": "no_data"})

    return JSONResponse({
        "rings": ring_data,
        "timestamp": time.time(),
    })


@router.get("/api/modulation")
async def get_modulation(request: Request):
    """Return ModulationContext's 4 composite factors and individual hook values."""
    radial = _get_radial(request)
    if radial is None:
        return JSONResponse(
            {"error": "radial_network not available"},
            status_code=503,
        )

    mod_ctx = getattr(radial, "_modulation_context", None)
    if mod_ctx is None:
        # Try from last output
        loop = _get_agent_loop(request)
        last = getattr(loop, "_last_radial_output", None) if loop else None
        if last and isinstance(last, dict):
            mod_ctx = last.get("modulation_context")

    if mod_ctx is None:
        return JSONResponse({
            "factors": {"attention_gain": 1.0, "precision_boost": 1.0,
                        "ffn_throughput": 1.0, "threshold_mod": 1.0},
            "message": "No modulation context yet",
            "timestamp": time.time(),
        })

    # Composite factors
    factors = {
        "attention_gain": round(getattr(mod_ctx, "attention_gain", 1.0), 4),
        "precision_boost": round(getattr(mod_ctx, "precision_boost", 1.0), 4),
        "ffn_throughput": round(getattr(mod_ctx, "ffn_throughput", 1.0), 4),
        "threshold_mod": round(getattr(mod_ctx, "threshold_mod", 1.0), 4),
    }

    # Reconstruct individual hook contributions by re-reading bridge states
    hooks = {}
    if getattr(mod_ctx, "neuromod", None) is not None:
        nm = mod_ctx.neuromod
        hooks["H1_ne_gain"] = round(0.5 + nm.ne_gain, 4)
        hooks["H2_da_precision"] = round((0.5 + nm.dopamine) * (1.0 - 0.3 * nm.anti_reward), 4)
        hooks["H3_ach_ffn"] = round(0.5 + nm.acetylcholine, 4)
        hooks["H4_5ht_stability"] = round(0.8 + 0.4 * nm.serotonin, 4)
        hooks["H6_explore_threshold"] = round(1.5 - nm.explore_ratio, 4)

    if getattr(mod_ctx, "cortex", None) is not None:
        cx = mod_ctx.cortex
        hooks["H8_acc_conflict"] = round(1.0 - 0.3 * cx.conflict, 4)
        hooks["H9_ofc_value"] = round(0.7 + 0.6 * cx.subjective_value, 4)

    if getattr(mod_ctx, "limbic", None) is not None:
        lm = mod_ctx.limbic
        hooks["H10_arousal"] = round(0.7 + 0.6 * lm.arousal, 4)
        hooks["H11_salience"] = round(0.8 + 0.4 * lm.salience, 4)
        hooks["H12_nogo"] = round(1.0 - 0.2 * lm.nogo_drive, 4)
        hooks["H13_urgency"] = round(0.8 + 0.4 * lm.urgency, 4)

    if getattr(mod_ctx, "sleep_wake", None) is not None:
        sw = mod_ctx.sleep_wake
        hooks["H14_sleep_arousal"] = round(0.5 + sw.arousal, 4)
        hooks["H15_histamine"] = round(0.5 + 0.5 * sw.histamine, 4)
        hooks["H16_melatonin"] = round(1.0 + 0.3 * sw.melatonin, 4)

    if getattr(mod_ctx, "motor", None) is not None:
        mt = mod_ctx.motor
        hooks["H17_motor_confidence"] = round(0.8 + 0.4 * mt.model_confidence, 4)
        hooks["H18_action_tendency"] = round(0.8 + 0.4 * mt.action_tendency, 4)

    if getattr(mod_ctx, "defense", None) is not None:
        df = mod_ctx.defense
        hooks["H19_defense_intensity"] = round(0.7 + 0.8 * df.defense_intensity, 4)
        hooks["H20_anxiety"] = round(1.0 - 0.4 * df.anxiety_level, 4)

    if getattr(mod_ctx, "memory", None) is not None:
        mm = mod_ctx.memory
        hooks["H21_theta"] = round(0.8 + 0.4 * mm.theta_power, 4)
        hooks["H22_consolidation"] = round(0.8 + 0.4 * mm.consolidation_strength, 4)

    if getattr(mod_ctx, "integration", None) is not None:
        ig = mod_ctx.integration
        hooks["H23_binding"] = round(0.7 + 0.6 * ig.binding_strength, 4)
        hooks["H24_dmn"] = round(1.0 - 0.3 * ig.dmn_activation, 4)
        hooks["H25_orienting"] = round(0.8 + 0.4 * ig.orienting_saliency, 4)

    if getattr(mod_ctx, "visceral", None) is not None:
        vs = mod_ctx.visceral
        hooks["H26_afferent"] = round(1.0 - 0.2 * vs.afferent_strength, 4)
        hooks["H27_liking"] = round(0.9 + 0.2 * vs.liking, 4)

    if getattr(mod_ctx, "social", None) is not None:
        sc = mod_ctx.social
        hooks["H28_social_salience"] = round(0.9 + 0.2 * sc.social_salience, 4)
        hooks["H29_familiarity"] = round(0.9 + 0.2 * sc.familiarity, 4)

    return JSONResponse({
        "factors": factors,
        "hooks": hooks,
        "hook_count": len(hooks),
        "timestamp": time.time(),
    })


@router.get("/api/experience-buffer/stats")
async def get_experience_buffer_stats(request: Request):
    """Return experience buffer size, capacity, and recent reward distribution."""
    loop = _get_agent_loop(request)
    if loop is None:
        return JSONResponse(
            {"error": "agent_loop not available"},
            status_code=503,
        )

    buf = getattr(loop, "experience_buffer", None)
    if buf is None:
        return JSONResponse({
            "size": 0,
            "capacity": 0,
            "message": "No experience buffer configured",
            "timestamp": time.time(),
        })

    try:
        stats = buf.get_stats() if hasattr(buf, "get_stats") else {}
    except Exception:
        stats = {}

    # Compute reward distribution from recent entries
    reward_dist = {"positive": 0, "negative": 0, "neutral": 0}
    try:
        entries = list(buf._buffer) if hasattr(buf, "_buffer") else []
        for entry in entries[-100:]:  # last 100 entries
            reward = entry.get("kuro_reward", 0.0)
            if reward > 0.1:
                reward_dist["positive"] += 1
            elif reward < -0.1:
                reward_dist["negative"] += 1
            else:
                reward_dist["neutral"] += 1
    except Exception:
        pass

    return JSONResponse({
        "size": len(getattr(buf, "_buffer", [])),
        "capacity": getattr(buf, "max_size", getattr(buf, "_max_size", 5000)),
        "stats": _convert(stats),
        "recent_rewards": reward_dist,
        "timestamp": time.time(),
    })


@router.get("/api/minibook/activity")
async def get_minibook_activity(request: Request):
    """Proxy Minibook notifications + recent posts for The Brain's agent.

    Returns empty gracefully if Minibook is not running.
    """
    import httpx

    minibook_url = "http://localhost:3456"
    result = {
        "online": False,
        "notifications": [],
        "recent_posts": [],
        "timestamp": time.time(),
    }

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            # Check if Minibook is alive
            health = await client.get(f"{minibook_url}/health")
            if health.status_code != 200:
                return JSONResponse(result)

            result["online"] = True

            # Get notifications for brain agent
            try:
                notif_resp = await client.get(
                    f"{minibook_url}/api/v1/notifications",
                    params={"limit": 10},
                )
                if notif_resp.status_code == 200:
                    result["notifications"] = notif_resp.json()
            except Exception:
                pass

            # Get recent posts
            try:
                posts_resp = await client.get(
                    f"{minibook_url}/api/v1/posts",
                    params={"limit": 5},
                )
                if posts_resp.status_code == 200:
                    result["recent_posts"] = posts_resp.json()
            except Exception:
                pass

    except Exception:
        pass  # Minibook offline — return empty gracefully

    return JSONResponse(result)


# ===================================================================
# SSE Stream
# ===================================================================

async def _sse_generator(request: Request):
    """Generate Server-Sent Events at ~2 Hz with bridge states, ring norms, and modulation factors."""
    while True:
        # Check if client disconnected
        if await request.is_disconnected():
            break

        data = {
            "timestamp": time.time(),
        }

        # --- Bridge states ---
        bridges = _collect_bridge_states(request)
        # Compact: only send active bridges' numeric fields
        bridge_summary = {}
        for name, state in bridges.items():
            if state.get("status") == "active":
                # Filter to numeric fields only
                bridge_summary[name] = {
                    k: v for k, v in state.items()
                    if isinstance(v, (int, float)) and k not in ("status",)
                }
        data["bridges"] = bridge_summary

        # --- Ring activation norms ---
        loop = _get_agent_loop(request)
        ring_norms = [0.0] * 5
        if loop is not None:
            last = getattr(loop, "_last_radial_output", None)
            if last is not None and isinstance(last, dict):
                ring_activations = last.get("ring_activations", [])
                for i in range(5):
                    act = ring_activations[i] if i < len(ring_activations) else None
                    if act is not None:
                        try:
                            import torch
                            if isinstance(act, torch.Tensor):
                                ring_norms[i] = round(float(act.norm()), 4)
                            else:
                                import numpy as np
                                ring_norms[i] = round(float(np.linalg.norm(act)), 4)
                        except Exception:
                            pass
        data["ring_norms"] = ring_norms

        # --- Modulation factors ---
        radial = _get_radial(request)
        mod_ctx = getattr(radial, "_modulation_context", None) if radial else None
        if mod_ctx is None and loop is not None:
            last = getattr(loop, "_last_radial_output", None)
            if last and isinstance(last, dict):
                mod_ctx = last.get("modulation_context")

        if mod_ctx is not None:
            data["modulation"] = {
                "attention_gain": round(getattr(mod_ctx, "attention_gain", 1.0), 4),
                "precision_boost": round(getattr(mod_ctx, "precision_boost", 1.0), 4),
                "ffn_throughput": round(getattr(mod_ctx, "ffn_throughput", 1.0), 4),
                "threshold_mod": round(getattr(mod_ctx, "threshold_mod", 1.0), 4),
            }
        else:
            data["modulation"] = {
                "attention_gain": 1.0, "precision_boost": 1.0,
                "ffn_throughput": 1.0, "threshold_mod": 1.0,
            }

        # Outcome + Plasticity stats for dashboard
        tracker = getattr(request.app.state, 'outcome_tracker', None)
        if tracker is not None:
            data["outcome"] = tracker.get_stats()
        jury = getattr(request.app.state, 'thought_jury', None)
        if jury is not None:
            total = getattr(jury, '_total_positive', 0) + getattr(jury, '_total_negative', 0)
            data["jury_pct"] = round(jury._total_positive / total * 100, 1) if total > 0 else 0
        bridge = getattr(request.app.state, 'thought_radial_bridge', None)
        if bridge is not None:
            data["bridge_rewards"] = getattr(bridge, '_total_rewards', 0)

        # --- Agent loop state ---
        if loop is not None:
            fsm = getattr(loop, "fsm", None)
            if fsm is not None:
                data["agent_state"] = str(getattr(fsm, "state", "unknown"))

        # Emit SSE event
        try:
            yield f"data: {json.dumps(data, default=str)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'error': 'serialization', 'timestamp': time.time()})}\n\n"

        await asyncio.sleep(0.5)  # 2 Hz


@router.get("/api/radial/stream")
async def radial_stream(request: Request):
    """SSE stream of radial attention state at 2 Hz.

    Emits bridge states, ring activation norms, and modulation factors
    as Server-Sent Events. Connect with EventSource in JavaScript.
    """
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
