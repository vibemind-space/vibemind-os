"""Brain routing endpoints — fast intent routing via RadialNetwork + SpaceRoutingHead."""
from __future__ import annotations

import logging
import time

import torch
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger('brain.routing')

router = APIRouter()


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

    try:
        seed_np = agent_loop.seed_encoder.encode_from_description(user_text[:200])
        seed_tensor = torch.tensor(seed_np, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            result = agent_loop.radial_network.forward(seed_tensor)

        ring3 = result['ring_activations'][2]
        applied = routing_head.train_supervised(ring3, correct_space)

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
