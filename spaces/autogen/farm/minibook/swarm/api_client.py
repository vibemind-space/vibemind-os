"""Minibook API client — HTTP helpers with retry, credential storage, agent registration."""

import asyncio
import json
import aiohttp

from .constants import MINIBOOK_URL, CREDS_FILE

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


async def _request_with_retry(method: str, session: aiohttp.ClientSession,
                               path: str, headers: dict, **kwargs):
    """Execute HTTP request with retry on connection errors."""
    url = f"{MINIBOOK_URL}{path}"
    for attempt in range(MAX_RETRIES):
        try:
            async with getattr(session, method)(url, headers=headers, **kwargs) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise Exception(f"API {resp.status} {method.upper()} {path}: {body}")
                return await resp.json()
        except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError,
                aiohttp.ClientConnectorError, ConnectionResetError) as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise


async def api_post(session: aiohttp.ClientSession, path: str, data: dict, api_key: str = None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return await _request_with_retry("post", session, path, headers, json=data)


async def api_put(session: aiohttp.ClientSession, path: str, data: dict, api_key: str = None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return await _request_with_retry("put", session, path, headers, json=data)


async def api_get(session: aiohttp.ClientSession, path: str, api_key: str = None, params: dict = None):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return await _request_with_retry("get", session, path, headers, params=params)


# --- Credential Storage ---

def load_credentials() -> dict:
    if CREDS_FILE.exists():
        return json.loads(CREDS_FILE.read_text())
    return {}


def save_credentials(creds: dict):
    CREDS_FILE.write_text(json.dumps(creds, indent=2))


async def register_agent(session: aiohttp.ClientSession, name: str, creds: dict) -> dict:
    if name in creds:
        print(f"  [=] Loaded {name}")
        return creds[name]
    try:
        result = await api_post(session, "/api/v1/agents", {"name": name})
        print(f"  [+] Registered {name}")
        creds[name] = result
        save_credentials(creds)
        return result
    except Exception as e:
        if "already taken" in str(e):
            raise Exception(f"Agent {name} exists but no saved key. Delete swarm_agents.json and minibook.db.")
        raise


# --- Agent Registry ---

# Team-key → community group mapping
COMMUNITY_GROUPS = {
    "core":          "sales_core",
    "outreach":      "outreach",
    "bdr":           "outreach",
    "intel":         "intelligence",
    "research":      "intelligence",
    "qualification": "qualification",
    "revops":        "operations",
    "callintel":     "operations",
    "workspace":     "content",
    "content":       "content",
    "wiring":        "sales_core",
}

COMMUNITY_PROJECTS = {
    "sales_core":     "Community: Sales Core Team",
    "outreach":       "Community: Channel Outreach",
    "intelligence":   "Community: Competitive Intel & Research",
    "qualification":  "Community: Lead Qualification",
    "operations":     "Community: RevOps & Call Intelligence",
    "content":        "Community: Content & Workspace",
}


async def ensure_community_project(
    session: aiohttp.ClientSession,
    team_key: str,
    registry_agent_api_key: str,
) -> str | None:
    """Get or create the community project for a team_key. Returns project_id."""
    group = COMMUNITY_GROUPS.get(team_key)
    if not group:
        return None
    project_name = COMMUNITY_PROJECTS[group]

    # Try GET all projects and find by name
    try:
        projects = await api_get(session, "/api/v1/projects", api_key=registry_agent_api_key)
        for p in projects:
            if p["name"] == project_name:
                return p["id"]
    except Exception as e:
        # Only proceed to creation on network/timeout errors, not auth failures
        if any(code in str(e) for code in ("401", "403", "500")):
            print(f"  [Community] GET projects failed ({e}) — skipping creation")
            return None

    # Create new community project
    try:
        proj = await api_post(session, "/api/v1/projects", {
            "name": project_name,
            "description": f"Validated agents for {group.replace('_', ' ').title()} capabilities.",
        }, api_key=registry_agent_api_key)
        print(f"  [Community] Created project: {project_name}")
        return proj["id"]
    except Exception as e:
        print(f"  [Community] Could not create project {project_name}: {e}")
        return None


async def register_agent_in_registry(
    session: aiohttp.ClientSession,
    team_key: str,
    run_id: str,
    eval_score: int,
    eval_reason: str,
    status: str,                     # "candidate" or "validated"
    output_dir: str | None,
    mcp_servers: list[str],
    capabilities: list[str],
    tools_py_path: str | None,
    agent_name: str | None,
    registry_agent_api_key: str | None,
    todo_status: str = "pending",
) -> dict | None:
    """Register (or update) a team in the agent registry.

    Called twice per successful team:
    1. After mock eval PASS → status='candidate'
    2. After real eval PASS (post-TODO impl) → status='validated'
    """
    try:
        payload = {
            "team_key": team_key,
            "run_id": run_id,
            "eval_score": eval_score,
            "eval_reason": eval_reason,
            "status": status,
            "todo_status": todo_status,
            "output_dir": output_dir,
            "tools_py_path": tools_py_path,
            "mcp_servers": mcp_servers,
            "capabilities": capabilities,
            "agent_name": agent_name,
        }
        entry = await api_post(session, "/api/v1/registry", payload)
        print(f"  [Registry] {team_key} registered as {status} (score={eval_score})")

        # If validated + community enabled → join community project
        if status == "validated" and registry_agent_api_key and agent_name:
            project_id = await ensure_community_project(session, team_key, registry_agent_api_key)
            if project_id and entry.get("id"):
                # Join community project with role "validated-agent"
                try:
                    await api_post(
                        session,
                        f"/api/v1/projects/{project_id}/join",
                        {"role": "validated-agent"},
                        api_key=registry_agent_api_key,
                    )
                    print(f"  [Registry] RegistryAgent joined community project {project_id} for {agent_name}")
                except Exception as e:
                    if "Already" not in str(e):
                        print(f"  [Registry] Community join failed: {e}")
                # Write community_project_id back to registry entry (I1 fix)
                try:
                    await api_put(
                        session,
                        f"/api/v1/registry/{entry['id']}/status",
                        {"status": status, "community_project_id": project_id},
                        api_key=registry_agent_api_key,
                    )
                except Exception as e:
                    print(f"  [Registry] Could not update community_project_id: {e}")
                # Post summary to community project
                try:
                    caps = ", ".join(capabilities) if capabilities else "general"
                    servers = ", ".join(mcp_servers) if mcp_servers else "none"
                    await api_post(
                        session,
                        f"/api/v1/projects/{project_id}/posts",
                        {
                            "title": f"Validated: {agent_name} ({team_key})",
                            "content": (
                                f"## New Validated Agent Team\n\n"
                                f"**Team:** {team_key}\n"
                                f"**Agent:** {agent_name}\n"
                                f"**Eval Score:** {eval_score}/10\n"
                                f"**MCP Servers:** {servers}\n"
                                f"**Capabilities:** {caps}\n"
                                f"**TODO Status:** {todo_status}\n\n"
                                f"**Eval Summary:** {eval_reason[:300]}\n\n"
                                f"Output: `{output_dir}`"
                            ),
                        },
                        api_key=registry_agent_api_key,
                    )
                    print(f"  [Registry] Posted summary to community project for {agent_name}")
                except Exception as e:
                    print(f"  [Registry] Summary post failed: {e}")
        return entry
    except Exception as e:
        print(f"  [Registry] Registration failed for {team_key}: {e}")
        return None

