"""Async HTTP client for OpenFang Agent OS API."""

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from bridge.config import settings

logger = logging.getLogger(__name__)

# Cache: template name → agent ID
_agent_cache: dict[str, str] = {}


@dataclass
class AgentResult:
    task_id: str = ""
    status: str = "failed"
    text: str = ""
    error: Optional[str] = None


async def ensure_agent(template: str) -> Optional[str]:
    """Ensure a brain-* agent is running in OpenFang. Returns agent ID.

    1. Check cache
    2. GET /api/agents → find by name
    3. POST /api/agents → spawn from template if not found
    """
    # Check cache
    if template in _agent_cache:
        return _agent_cache[template]

    base = settings.openfang_url

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # List running agents
            resp = await client.get(f"{base}/api/agents")
            resp.raise_for_status()
            agents = resp.json()

            # Find existing agent with matching name
            for agent in agents:
                if agent.get("name") == template:
                    agent_id = agent["id"]
                    _agent_cache[template] = agent_id
                    logger.info(f"Found existing agent {template} → {agent_id}")
                    return agent_id

            # Spawn new agent from template
            resp = await client.post(
                f"{base}/api/agents",
                json={"template": template},
            )
            resp.raise_for_status()
            data = resp.json()
            agent_id = data.get("id", data.get("agent_id", ""))
            if agent_id:
                _agent_cache[template] = agent_id
                logger.info(f"Spawned agent {template} → {agent_id}")
                return agent_id

            logger.error(f"Spawn returned no agent ID: {data}")
            return None

    except Exception as e:
        logger.error(f"Failed to ensure agent {template}: {e}")
        return None


async def send_message(
    agent_id: str, message: str, timeout: int = 300
) -> AgentResult:
    """Send a task message to an OpenFang agent.

    POST /api/agents/{id}/message → agent response
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.openfang_url}/api/agents/{agent_id}/message",
                json={"message": message},
            )
            resp.raise_for_status()
            data = resp.json()

            return AgentResult(
                task_id=data.get("id", agent_id),
                status="completed",
                text=data.get("response", data.get("text", str(data))),
            )
    except httpx.TimeoutException:
        return AgentResult(
            status="failed",
            error=f"Agent {agent_id} timed out after {timeout}s",
        )
    except Exception as e:
        return AgentResult(status="failed", error=str(e))


async def health_check() -> bool:
    """Check if OpenFang is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.openfang_url}/api/health")
            return resp.status_code == 200
    except Exception:
        return False


def invalidate_cache(template: str = ""):
    """Clear agent ID cache. If template given, clear only that entry."""
    if template:
        _agent_cache.pop(template, None)
    else:
        _agent_cache.clear()
