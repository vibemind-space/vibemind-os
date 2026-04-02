"""AgentFarm tool functions for Autogen 0.4 team orchestration.

All tools return {"success": bool, "message": str, ...} and broadcast
UI updates via _broadcast_to_electron().
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from tools.workspace_tools import _broadcast_to_electron
except ImportError:
    def _broadcast_to_electron(msg):
        pass

# In-memory team registry: team_id -> team_config
_team_registry: Dict[str, Dict[str, Any]] = {}

# Path to submodule
_SUBMODULE_PATH = Path(__file__).resolve().parents[4] / "external" / "Autogen_AgentFarm"


def create_team(
    template_id: Optional[str] = None,
    team_name: Optional[str] = None,
    team_config: Optional[Dict] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Create a new agent team from template or config."""
    if template_id and not team_config:
        tpl = _load_template(template_id)
        if not tpl:
            return {"success": False, "message": f"Template '{template_id}' not found."}
        team_config = tpl

    if not team_config or "agents" not in team_config:
        return {"success": False, "message": "No team config or template_id provided."}

    team_id = str(uuid4())
    name = team_name or team_config.get("name", f"Team-{team_id[:8]}")
    team_config["name"] = name

    _team_registry[team_id] = team_config
    agent_names = [a["name"] for a in team_config.get("agents", [])]

    _broadcast_to_electron({
        "type": "agentfarm_team_created",
        "team_id": team_id,
        "team_name": name,
        "agent_count": len(agent_names),
    })

    return {
        "success": True,
        "message": f"Team '{name}' created with {len(agent_names)} agents.",
        "team_id": team_id,
        "team_name": name,
        "agent_count": len(agent_names),
        "agent_names": agent_names,
        "response_hint": f"Team {name} mit {len(agent_names)} Agents erstellt.",
    }


async def run_team(team_id: str = "", task: str = "", **kwargs) -> Dict[str, Any]:
    """Start an async team run. Returns immediately with run_id."""
    if not team_id or team_id not in _team_registry:
        return {"success": False, "message": f"Team '{team_id}' not found."}
    if not task:
        return {"success": False, "message": "No task provided."}

    from spaces.autogen.runner.team_runner import TeamRunner
    runner = TeamRunner.get_instance()
    run_id = await runner.start_run(team_id, _team_registry[team_id], task)

    return {
        "success": True,
        "message": f"Team run started.",
        "run_id": run_id,
        "team_id": team_id,
        "status": "started",
        "response_hint": f"Team-Run gestartet. Run-ID: {run_id[:8]}",
    }


def get_farm_status(**kwargs) -> Dict[str, Any]:
    """Get overview of all teams and runs."""
    from spaces.autogen.runner.team_runner import TeamRunner
    runner = TeamRunner.get_instance()
    runs = runner.get_status()

    running = [r for r in runs.values() if r["status"] == "running"]

    return {
        "success": True,
        "message": f"{len(_team_registry)} teams, {len(running)} active runs.",
        "total_teams": len(_team_registry),
        "active_runs": len(running),
        "runs": runs,
        "response_hint": f"{len(_team_registry)} Teams registriert, {len(running)} laufende Runs.",
    }


def list_teams(**kwargs) -> Dict[str, Any]:
    """List all registered teams."""
    teams = []
    for tid, cfg in _team_registry.items():
        teams.append({
            "team_id": tid,
            "name": cfg.get("name", "unnamed"),
            "agent_count": len(cfg.get("agents", [])),
            "team_type": cfg.get("team_type", "selector"),
            "agent_names": [a["name"] for a in cfg.get("agents", [])],
        })

    return {
        "success": True,
        "message": f"{len(teams)} teams registered.",
        "team_count": len(teams),
        "teams": teams,
        "response_hint": f"{len(teams)} Teams registriert.",
    }


def stop_run(run_id: str = "", **kwargs) -> Dict[str, Any]:
    """Stop a running team."""
    if not run_id:
        return {"success": False, "message": "No run_id provided."}

    from spaces.autogen.runner.team_runner import TeamRunner
    runner = TeamRunner.get_instance()
    cancelled = runner.cancel_run(run_id)

    if cancelled:
        return {
            "success": True,
            "message": f"Run {run_id[:8]} cancelled.",
            "response_hint": "Run gestoppt.",
        }
    return {
        "success": False,
        "message": f"Run '{run_id[:8]}' not found or not running.",
    }


def get_run_results(run_id: str = "", **kwargs) -> Dict[str, Any]:
    """Get results of a completed or running team run."""
    if not run_id:
        return {"success": False, "message": "No run_id provided."}

    from spaces.autogen.runner.team_runner import TeamRunner
    runner = TeamRunner.get_instance()
    state = runner.get_run(run_id)

    if not state:
        return {"success": False, "message": f"Run '{run_id[:8]}' not found."}

    duration = None
    if state.completed_at and state.started_at:
        duration = (state.completed_at - state.started_at).total_seconds()

    return {
        "success": True,
        "message": f"Run {run_id[:8]}: {state.status}, {state.step_count} steps.",
        "run_id": run_id,
        "status": state.status,
        "step_count": state.step_count,
        "duration_seconds": duration,
        "messages": state.messages,
        "error": state.error,
        "response_hint": f"Run {state.status}: {state.step_count} Schritte.",
    }


def list_templates(**kwargs) -> Dict[str, Any]:
    """List available team templates from the AgentFarm submodule."""
    if not _SUBMODULE_PATH.is_dir():
        return {
            "success": False,
            "message": "AgentFarm submodule not found. Run: git submodule update --init external/Autogen_AgentFarm",
        }

    templates = []
    for p in _SUBMODULE_PATH.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "agents" in data:
                templates.append({
                    "id": p.stem,
                    "name": data.get("name", p.stem),
                    "description": data.get("description", ""),
                    "agent_count": len(data.get("agents", [])),
                    "path": str(p.relative_to(_SUBMODULE_PATH)),
                })
        except (json.JSONDecodeError, OSError):
            continue

    return {
        "success": True,
        "message": f"{len(templates)} templates found.",
        "templates": templates,
        "response_hint": f"{len(templates)} Team-Templates verfuegbar.",
    }


def start_collaboration(task: str = "", goal: str = "", **kwargs) -> Dict[str, Any]:
    """Start multi-space collaboration via Minibook."""
    enabled = os.getenv("MINIBOOK_ENABLED", "false").lower() == "true"
    if not enabled:
        return {
            "success": False,
            "message": "Minibook is disabled. Set MINIBOOK_ENABLED=true in .env.",
        }

    try:
        from spaces.minibook.tools.collaboration_tools import start_collaboration as _collab
        return _collab(task=task, goal=goal)
    except ImportError as e:
        return {"success": False, "message": f"Minibook not available: {e}"}


def _load_template(template_id: str) -> Optional[Dict]:
    """Load a template from the submodule by ID."""
    if not _SUBMODULE_PATH.is_dir():
        return None
    for p in _SUBMODULE_PATH.rglob("*.json"):
        if p.stem == template_id:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if "agents" in data:
                    return data
            except (json.JSONDecodeError, OSError):
                pass
    return None


# ---------------------------------------------------------------------------
# Pipeline State (module-level singleton for status tracking)
# ---------------------------------------------------------------------------

_active_pipeline: Optional[Dict[str, Any]] = None
_active_forge: Optional[Dict[str, Any]] = None
_hybrid_pipeline = None  # HybridPipeline instance (for status tracking)


async def _ensure_minibook_setup() -> Dict[str, Any]:
    """Register agents + create project at Minibook. Returns {agents, project_id}.

    Uses VibeMind's MINIBOOK_URL (default: localhost:3480) directly,
    bypassing the submodule's hardcoded URL.
    """
    import aiohttp

    minibook_url = os.getenv("MINIBOOK_URL", "http://localhost:3480")
    from spaces.autogen.wrapper import AGENT_ROLES

    creds_path = Path(__file__).resolve().parents[1] / "config" / "swarm_agents.json"
    creds = json.loads(creds_path.read_text()) if creds_path.exists() else {}

    async with aiohttp.ClientSession() as session:
        agents = {}

        for name in AGENT_ROLES.keys():
            # Check cached credentials
            if name in creds:
                agents[name] = creds[name]
                continue

            # Register new agent
            async with session.post(
                f"{minibook_url}/api/v1/agents",
                json={"name": name},
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    if "already taken" in body:
                        raise Exception(f"Agent {name} exists but no saved key. Delete swarm_agents.json.")
                    raise Exception(f"Register {name} failed: {resp.status} {body}")
                result = await resp.json()
                agents[name] = result
                creds[name] = result

        # Save credentials
        creds_path.write_text(json.dumps(creds, indent=2))

        # Create project
        lead_key = list(agents.keys())[0]
        lead_api_key = agents[lead_key].get("api_key", "")

        async with session.post(
            f"{minibook_url}/api/v1/projects",
            json={"name": f"pipeline-{uuid4().hex[:6]}", "description": "VibeMind HybridPipeline"},
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {lead_api_key}"},
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise Exception(f"Create project failed: {resp.status} {body}")
            project = await resp.json()
            project_id = project.get("id", project.get("project_id", ""))

    return {"agents": agents, "project_id": project_id}


def run_pipeline(task_description: str = "", channel: str = "", session_id: str = "", **kwargs) -> Dict[str, Any]:
    """Start the 13-step HybridPipeline (OpenClaw + Swarm + Claude CLI).

    If the task description is too short, starts a multi-turn enrichment dialog
    (Rachel asks clarifying questions about data sources, output format, tools).
    Once enriched, starts the pipeline in background.

    Routes each step to the best orchestrator:
    - Swarm: LLM reasoning (Spec, Review, Report)
    - OpenClaw: Docker sandbox + user communication (no timeout!)
    - Claude CLI: Code generation via ACP (no truncation)
    """
    global _active_pipeline, _hybrid_pipeline
    if not task_description:
        return {"success": False, "message": "task_description required — beschreibe was generiert werden soll."}

    # --- Pre-Pipeline Enrichment (multi-turn voice dialog) ---
    from spaces.autogen.orchestrator.pipeline_enrichment import get_pipeline_enrichment
    enrichment = get_pipeline_enrichment()
    sid = session_id or "default"

    result = enrichment.start_session(sid, task_description)

    if result["action"] == "ask":
        # Need more info — Rachel asks a question, pipeline waits
        return {
            "success": True,
            "message": result["question"],
            "response_hint": result["question"],
            "enrichment_active": True,
            "question_id": result.get("question_id"),
        }

    if result["action"] == "confirm":
        # Got enough info — ask for confirmation
        return {
            "success": True,
            "message": result["confirmation"],
            "response_hint": result["confirmation"],
            "enrichment_active": True,
            "awaiting_confirmation": True,
        }

    # action == "ready" — task is detailed enough, start pipeline
    task_description = result.get("enriched_task", task_description)

    try:
        import asyncio
        import threading

        from spaces.autogen.orchestrator.hybrid_pipeline import HybridPipeline

        _hybrid_pipeline = HybridPipeline()
        _active_pipeline = {"status": "starting", "task": task_description}
        _broadcast_to_electron({"type": "agentfarm_pipeline_started", "task": task_description[:100]})

        # Run in background thread (HybridPipeline is async, may wait for user)
        def _run_hybrid():
            global _active_pipeline
            try:
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    _hybrid_pipeline.run(task_description, channel=channel or None)
                )
                loop.close()
                _active_pipeline = {
                    "status": "completed",
                    "task": task_description,
                    "result": str(result)[:500],
                }
            except Exception as e:
                _active_pipeline = {"status": "error", "error": str(e)}
                logger.error(f"HybridPipeline failed: {e}")

        thread = threading.Thread(target=_run_hybrid, daemon=True, name="hybrid-pipeline")
        thread.start()

        return {
            "success": True,
            "message": f"HybridPipeline gestartet fuer: {task_description[:100]}. Updates kommen via Channel.",
            "response_hint": f"Pipeline gestartet. Du bekommst Updates via {channel or 'Electron UI'}.",
        }
    except Exception as e:
        _active_pipeline = {"status": "error", "error": str(e)}
        logger.error(f"Pipeline start failed: {e}")
        return {"success": False, "message": f"Pipeline failed: {e}"}


def get_pipeline_status(**kwargs) -> Dict[str, Any]:
    """Get current HybridPipeline status with per-step details."""
    if _hybrid_pipeline:
        status = _hybrid_pipeline.get_status()
        return {"success": True, **status, "message": f"Pipeline: {status.get('status', 'unknown')}"}
    if _active_pipeline:
        return {"success": True, **_active_pipeline, "message": f"Pipeline: {_active_pipeline.get('status', 'unknown')}"}
    return {"success": True, "status": "idle", "message": "Keine Pipeline aktiv."}


def start_forge(project_id: str = "", **kwargs) -> Dict[str, Any]:
    """Start ForgeOrchestrator for continuous improvement.

    Runs as background daemon via OpenClaw sandbox (or local fallback).
    Requires Minibook server running.
    """
    global _active_forge
    try:
        import asyncio
        import threading

        loop = asyncio.new_event_loop()
        setup = loop.run_until_complete(_ensure_minibook_setup())
        agents = setup["agents"]
        pid = project_id or setup["project_id"]

        from spaces.autogen.wrapper import ForgeOrchestrator

        forge = ForgeOrchestrator(agents=agents, project_id=pid)

        _active_forge = {"status": "running", "project_id": pid}
        _broadcast_to_electron({"type": "agentfarm_forge_started", "project_id": pid})

        def _run_forge():
            global _active_forge
            try:
                bg_loop = asyncio.new_event_loop()
                bg_loop.run_until_complete(forge.start())
            except Exception as e:
                _active_forge = {"status": "error", "error": str(e)}
                logger.error(f"Forge background error: {e}")

        thread = threading.Thread(target=_run_forge, daemon=True, name="forge-server")
        thread.start()
        loop.close()

        return {
            "success": True,
            "message": f"Forge gestartet auf Port 8890. Dashboard: http://localhost:8890/forge/status",
            "project_id": pid,
            "response_hint": "Forge-Orchestrator laeuft im Hintergrund.",
        }
    except Exception as e:
        _active_forge = {"status": "error", "error": str(e)}
        logger.error(f"Forge failed: {e}")
        return {"success": False, "message": f"Forge failed: {e}"}


def get_forge_status(**kwargs) -> Dict[str, Any]:
    """Get ForgeOrchestrator status."""
    if _active_forge:
        return {"success": True, **_active_forge, "message": f"Forge: {_active_forge.get('status', 'unknown')}"}
    return {"success": True, "status": "idle", "message": "Kein Forge aktiv."}


def pipeline_answer(answer: str = "", session_id: str = "", **kwargs) -> Dict[str, Any]:
    """Answer a pipeline enrichment question (Rachel follow-up).

    Called when user responds to Rachel's clarifying questions
    during pre-pipeline enrichment.
    """
    from spaces.autogen.orchestrator.pipeline_enrichment import get_pipeline_enrichment
    enrichment = get_pipeline_enrichment()
    sid = session_id or "default"

    # Check for confirmation responses
    if answer.lower() in ("ja", "yes", "ok", "los", "start", "loslegen", "go"):
        result = enrichment.confirm(sid, confirmed=True)
        if result["action"] == "ready":
            # Start pipeline with enriched task
            return run_pipeline(
                task_description=result["enriched_task"],
                session_id=sid,
            )
        return {"success": False, "message": "Keine aktive Enrichment-Session."}

    if answer.lower() in ("nein", "no", "stop", "abbruch", "cancel"):
        enrichment.cancel(sid)
        return {"success": True, "message": "Pipeline abgebrochen.", "response_hint": "Pipeline abgebrochen."}

    # Process answer to current question
    result = enrichment.answer(sid, answer)

    if result["action"] == "ask":
        return {
            "success": True,
            "message": result["question"],
            "response_hint": result["question"],
            "enrichment_active": True,
        }

    if result["action"] == "confirm":
        return {
            "success": True,
            "message": result["confirmation"],
            "response_hint": result["confirmation"],
            "enrichment_active": True,
            "awaiting_confirmation": True,
        }

    if result["action"] == "ready":
        return run_pipeline(task_description=result["enriched_task"], session_id=sid)

    return {"success": False, "message": result.get("message", "Unknown state")}
