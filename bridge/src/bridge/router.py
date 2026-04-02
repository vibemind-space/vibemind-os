"""Bridge API router — routes Brain decisions to OpenFang agents."""

import asyncio
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from bridge import brain_client, openfang_client, space_agent_mapper, task_store
from bridge.models import BridgeRequest, BridgeResponse, RoutingInfo, TaskStatus
from bridge.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bridge", tags=["bridge"])


@router.post("/route", response_model=BridgeResponse)
async def route_task(request: BridgeRequest):
    """Main endpoint: route a task through Brain → OpenFang.

    1. Brain /api/cortex/route → get space + confidence
    2. Map space → OpenFang agent template
    3. Ensure agent is running in OpenFang
    4. Send task to agent
    5. Reward Brain with success/failure
    """
    t0 = time.time()

    # 1. Route via Brain
    routing = await brain_client.route(
        request.task, request.event_type or ""
    )

    # 2. Map space to agent template
    agent_template = space_agent_mapper.map_space(
        routing.primary_space, routing.confidence
    )

    # 3. Ensure agent is running
    agent_id = await openfang_client.ensure_agent(agent_template)
    if not agent_id:
        # Fallback: try brain-fallback
        if agent_template != "brain-fallback":
            agent_template = "brain-fallback"
            agent_id = await openfang_client.ensure_agent("brain-fallback")
        if not agent_id:
            raise HTTPException(503, "OpenFang: could not spawn agent")

    # 4. Build enriched message with routing context
    message = (
        f"[Brain Context: space={routing.primary_space}, "
        f"confidence={routing.confidence:.2f}, "
        f"routing_id={routing.routing_id}]\n"
    )
    if routing.secondary_spaces:
        message += f"[Secondary spaces: {', '.join(routing.secondary_spaces)}]\n"
    message += f"\n{request.task}"

    timeout = request.timeout_secs or settings.default_timeout_secs

    if request.fire_and_forget:
        # 5a. Async mode: return immediately, execute in background
        task_id = str(uuid4())
        task_store.create(task_id, routing, agent_template)
        asyncio.create_task(
            _execute_and_reward(task_id, agent_id, message, routing, timeout)
        )
        return BridgeResponse(
            task_id=task_id,
            status="pending",
            routing=routing,
            agent=agent_template,
            latency_ms=(time.time() - t0) * 1000,
        )

    # 5b. Sync mode: wait for result
    result = await openfang_client.send_message(agent_id, message, timeout)
    success = result.status != "failed"

    # 6. Reward Brain (non-blocking)
    asyncio.create_task(brain_client.reward(routing.routing_id, success))

    return BridgeResponse(
        task_id=result.task_id or str(uuid4()),
        status=result.status,
        result=result.text or result.error,
        routing=routing,
        agent=agent_template,
        latency_ms=(time.time() - t0) * 1000,
    )


async def _execute_and_reward(
    task_id: str,
    agent_id: str,
    message: str,
    routing: RoutingInfo,
    timeout: int,
):
    """Background coroutine for fire-and-forget mode."""
    try:
        task_store.update(task_id, "working")
        result = await openfang_client.send_message(agent_id, message, timeout)
        success = result.status != "failed"
        task_store.update(
            task_id,
            "completed" if success else "failed",
            result=result.text,
            error=None if success else result.error,
        )
    except Exception as e:
        success = False
        task_store.update(task_id, "failed", error=str(e))
    finally:
        await brain_client.reward(routing.routing_id, success)


@router.get("/tasks/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Poll status of an async (fire-and-forget) task."""
    status = task_store.get(task_id)
    if not status:
        raise HTTPException(404, f"Task {task_id} not found")
    return status


@router.get("/health")
async def health():
    """Health check — pings Brain and OpenFang."""
    brain_ok = False
    openfang_ok = False
    try:
        routing = await brain_client.route("health check")
        brain_ok = routing.routing_id != "rt_fallback"
    except Exception:
        pass
    openfang_ok = await openfang_client.health_check()
    return {
        "bridge": "ok",
        "brain": "ok" if brain_ok else "unreachable",
        "openfang": "ok" if openfang_ok else "unreachable",
    }


@router.get("/mapping")
async def get_mapping():
    """Return current space→agent mapping."""
    return space_agent_mapper.get_mappings()


@router.put("/mapping/reload")
async def reload_mapping():
    """Hot-reload the space→agent mapping YAML."""
    space_agent_mapper.reload()
    return {"status": "reloaded", **space_agent_mapper.get_mappings()}
