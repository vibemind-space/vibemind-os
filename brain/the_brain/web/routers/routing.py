"""Brain routing endpoints — fast intent routing via RadialNetwork + SpaceRoutingHead."""
from __future__ import annotations

import logging
import time

import torch
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger('brain.routing')

router = APIRouter()


def _inference_replica() -> bool:
    """Phase D: an inference replica must not apply reward/train locally
    (the routing-head methods already no-op, but returning an explicit
    response lets the caller — Bridge/forwarder — know to send it to the
    learner instead). Fail-safe → False (mono behaves as before)."""
    try:
        from core import config as _cfg
        return not _cfg.is_learner()
    except Exception:
        return False


async def _forward_to_learner(path: str, body: dict) -> JSONResponse:
    """Phase D2: an inference replica forwards a reward/train POST to the
    learner so the (single) learner owns all centroid mutation.

    - learner URL unset  → 202 not-applied (D1 behaviour; signal not lost
      to a wrong target, caller can decide what to do).
    - learner unreachable → 502 (explicit; caller may retry).
    Short timeout: reward is fire-and-forget-ish, must not block routing.
    """
    try:
        from core import config as _cfg
        lurl = _cfg.learner_url()
    except Exception:
        lurl = None
    if not lurl:
        return JSONResponse(
            {"ok": False, "role": "inference", "applied": False,
             "note": "inference replica is read-only; BRAIN_LEARNER_URL unset"},
            status_code=202)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(f"{lurl}{path}", json=body)
        return JSONResponse(
            {"ok": r.status_code == 200, "role": "inference",
             "forwarded_to": lurl, "learner_status": r.status_code},
            status_code=200 if r.status_code == 200 else 502)
    except Exception as e:
        logger.warning(f"reward forward to learner failed: {e}")
        return JSONResponse(
            {"ok": False, "role": "inference", "forwarded_to": lurl,
             "error": "learner unreachable"},
            status_code=502)


@router.post("/api/cortex/route")
async def brain_route(request: Request) -> JSONResponse:
    """Fast routing via RadialNetwork + SpaceRoutingHead.

    Takes user_text, runs it through the radial network, extracts Ring 3
    activation, and computes cosine similarity against space centroids.

    Target latency: <100ms.
    """
    try:
        body = await request.json()
    except Exception:
        # Handle encoding issues (Windows curl sends Latin-1)
        raw = await request.body()
        import json as _json
        body = _json.loads(raw.decode('utf-8', errors='replace'))
    user_text = body.get("user_text", "")
    event_type = body.get("event_type", "")
    context = body.get("context", {})

    # Enrich user_text with workspace context for context-aware embeddings
    if context:
        prefix_parts = []
        if context.get("current_space"):
            prefix_parts.append(f"space:{context['current_space']}")
        if context.get("current_bubble"):
            prefix_parts.append(f"bubble:{context['current_bubble']}")
        if context.get("idea_count"):
            prefix_parts.append(f"ideas:{context['idea_count']}")
        if context.get("active_task_count"):
            prefix_parts.append(f"tasks:{context['active_task_count']}")
        if prefix_parts:
            user_text = f"[{' '.join(prefix_parts)}] {user_text}"

    agent_loop = getattr(request.app.state, 'agent_loop', None)
    routing_head = getattr(request.app.state, 'space_routing_head', None)

    if agent_loop is None or routing_head is None:
        return JSONResponse({"error": "routing not available"}, status_code=503)

    if not user_text:
        return JSONResponse({"error": "user_text required"}, status_code=400)

    t0 = time.time()

    try:
        # Embed user text via SeedEncoder
        seed_np = agent_loop.seed_encoder.encode_from_description(user_text[:200])
        seed_tensor = torch.tensor(seed_np, dtype=torch.float32).unsqueeze(0)

        # Forward pass through RadialNetwork
        with torch.no_grad():
            result = agent_loop.radial_network.forward(seed_tensor)

        # Extract Ring 3 (Semantic, 256-dim)
        ring3 = result['ring_activations'][2]

        # Route via SpaceRoutingHead
        decision = routing_head.route(ring3)
        decision['event_type'] = event_type
        decision['latency_ms'] = round((time.time() - t0) * 1000, 1)

        return JSONResponse(decision)

    except Exception as e:
        logger.error(f"Routing failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/cortex/route/reward")
async def brain_route_reward(request: Request) -> JSONResponse:
    """Reward signal for a previous routing decision.

    Called when an agent completes execution — success strengthens the
    centroid, failure weakens it.
    """
    body = await request.json()
    routing_head = getattr(request.app.state, 'space_routing_head', None)

    if routing_head is None:
        return JSONResponse({"error": "routing not available"}, status_code=503)

    routing_id = body.get("routing_id", "")
    success = body.get("success", False)

    if not routing_id:
        return JSONResponse({"error": "routing_id required"}, status_code=400)

    # Phase D2: inference replica does not learn — forward to the learner
    # (or 202 if no learner configured). The learner owns all mutation.
    if _inference_replica():
        return await _forward_to_learner(
            "/api/cortex/route/reward",
            {"routing_id": routing_id, "success": success})

    applied = routing_head.reward(routing_id, success)
    return JSONResponse({"ok": applied, "routing_id": routing_id})


@router.post("/api/cortex/route/train")
async def brain_route_train(request: Request) -> JSONResponse:
    """Supervised training from shadow observer ground truth.

    Accepts the correct routing decision and trains the SpaceRoutingHead
    to move its centroid toward the correct space embedding.
    """
    try:
        body = await request.json()
    except Exception:
        raw = await request.body()
        import json as _json
        body = _json.loads(raw.decode('utf-8', errors='replace'))

    user_text = body.get("user_text", "")
    correct_space = body.get("correct_space", "")

    agent_loop = getattr(request.app.state, 'agent_loop', None)
    routing_head = getattr(request.app.state, 'space_routing_head', None)

    if not agent_loop or not routing_head:
        return JSONResponse({"error": "routing not available"}, status_code=503)
    if not user_text or not correct_space:
        return JSONResponse({"error": "user_text and correct_space required"}, status_code=400)

    # Phase D2: inference replica forwards train to the learner.
    if _inference_replica():
        return await _forward_to_learner(
            "/api/cortex/route/train",
            {"user_text": user_text, "correct_space": correct_space})

    try:
        seed_np = agent_loop.seed_encoder.encode_from_description(user_text[:200])
        seed_tensor = torch.tensor(seed_np, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            result = agent_loop.radial_network.forward(seed_tensor)

        ring3 = result['ring_activations'][2]
        applied = routing_head.train_supervised(ring3, correct_space)

        # Autosave periodically so accumulated training survives a crash
        if applied and hasattr(routing_head, 'should_autosave') and routing_head.should_autosave():
            try:
                ckpt_path = getattr(request.app.state, 'space_routing_head_ckpt', None)
                if ckpt_path:
                    routing_head.save(ckpt_path)
            except Exception as save_err:
                logger.warning(f"Space autosave failed: {save_err}")

        return JSONResponse({"ok": applied, "trained_space": correct_space})

    except Exception as e:
        logger.error(f"Training failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/cortex/route/stats")
async def brain_route_stats(request: Request) -> JSONResponse:
    """Stats for the SpaceRoutingHead — routes, rewards, centroid norms."""
    routing_head = getattr(request.app.state, 'space_routing_head', None)
    if routing_head is None:
        return JSONResponse({"error": "routing not available"}, status_code=503)
    return JSONResponse(routing_head.get_stats())
