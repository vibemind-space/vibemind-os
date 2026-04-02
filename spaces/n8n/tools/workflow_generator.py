"""
n8n Workflow Generator

Two-phase approach:
1. Planning Phase (LLM): NL description -> structured workflow plan
2. Assembly Phase (Templates + LLM): Plan -> valid n8n workflow JSON

Uses OpenRouter (OpenAI-compatible) for LLM calls.
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_config import get_model as _get_llm_model, get_client

logger = logging.getLogger(__name__)

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# LLM client (lazy init) — provider-agnostic via llm_config
_llm_client: Any = None
_llm_model: Optional[str] = None


def _get_llm_client():
    """Get or create LLM client via llm_config."""
    global _llm_client, _llm_model
    if _llm_client is not None:
        return _llm_client

    try:
        _llm_client = get_client("n8n_generator")
        _llm_model = _get_llm_model("n8n_generator")
        logger.info(f"n8n generator using model: {_llm_model}")
        return _llm_client
    except Exception as e:
        logger.error(f"Failed to create n8n generator client: {e}")
        return None


def _fallback_to_openrouter():
    """Reset client and retry (provider fallback handled by llm_config)."""
    global _llm_client, _llm_model
    _llm_client = None
    _llm_model = None
    client = _get_llm_client()
    if client:
        logger.info("Recreated n8n generator client after error")
    return client


def _get_model() -> str:
    """Get the resolved model name."""
    if _llm_model:
        return _llm_model
    return _get_llm_model("n8n_generator")


def _load_template(template_name: str) -> Dict[str, Any]:
    """Load a node template JSON file."""
    path = TEMPLATES_DIR / f"{template_name}.json"
    if not path.exists():
        logger.warning(f"Template not found: {template_name}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Remove _meta (internal documentation)
    data.pop("_meta", None)
    return data


def _get_available_templates() -> Dict[str, Dict]:
    """Load all available templates with their metadata."""
    templates = {}
    if not TEMPLATES_DIR.exists():
        return templates
    for f in TEMPLATES_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            templates[f.stem] = {
                "description": data.get("_meta", {}).get("description", ""),
                "type": data.get("type", ""),
                "name": data.get("name", f.stem),
            }
        except (json.JSONDecodeError, KeyError):
            continue
    return templates


# ── Phase 1: Planning ───────────────────────────────────────────────────

PLANNING_PROMPT = """Du bist ein n8n Workflow-Architekt. Analysiere die folgende Workflow-Beschreibung und erstelle einen strukturierten Plan.

Verfuegbare Node-Templates:
{available_templates}

Antworte NUR mit validem JSON in diesem Format:
{{
  "workflow_name": "Name des Workflows",
  "description": "Kurzbeschreibung",
  "nodes": [
    {{
      "template": "template_name",
      "name": "Display Name im Workflow",
      "role": "trigger|agent|tool|memory|llm|processor|output",
      "customizations": {{
        "key": "value"
      }}
    }}
  ],
  "connections": [
    {{
      "from": "Node Name",
      "to": "Node Name",
      "type": "main|ai_tool|ai_languageModel|ai_memory"
    }}
  ],
  "credentials_needed": ["OpenAI API Key", "PostgreSQL"],
  "notes": "Wichtige Hinweise"
}}

Connection-Typen:
- "main": Normaler Datenfluss (Trigger -> Agent -> Output)
- "ai_tool": Tool-Verbindung zum AI Agent (DB, HTTP, Think, Code -> Agent)
- "ai_languageModel": LLM-Verbindung zum AI Agent (OpenAI Chat Model -> Agent)
- "ai_memory": Memory-Verbindung zum AI Agent (Buffer Memory -> Agent)

Workflow-Beschreibung:
{description}"""


def plan_workflow(description: str) -> Dict[str, Any]:
    """
    Phase 1: Use LLM to create a structured workflow plan from NL description.

    Args:
        description: Natural language workflow description

    Returns:
        Structured plan dict with nodes, connections, credentials
    """
    client = _get_llm_client()
    if not client:
        logger.error("No LLM client available (OPENROUTER_API_KEY not set)")
        return {"error": "LLM client not available. Set OPENROUTER_API_KEY."}

    templates = _get_available_templates()
    templates_str = "\n".join(
        f"- {name}: {info['description']} (type: {info['type']})"
        for name, info in templates.items()
    )

    model = _get_model()

    messages = [
        {
            "role": "system",
            "content": "Du bist ein n8n Workflow-Experte. Antworte immer mit validem JSON."
        },
        {
            "role": "user",
            "content": PLANNING_PROMPT.format(
                available_templates=templates_str,
                description=description,
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        # On quota/auth errors, try OpenRouter fallback
        if "429" in str(e) or "insufficient_quota" in str(e) or "401" in str(e):
            client = _fallback_to_openrouter()
            if client:
                model = _get_model()
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
            else:
                logger.error(f"Planning failed: {e}")
                return {"error": f"Planning failed: {str(e)}"}
        else:
            logger.error(f"Planning failed: {e}")
            return {"error": f"Planning failed: {str(e)}"}

    try:
        plan_text = response.choices[0].message.content
        plan = json.loads(plan_text)
        logger.info(f"Workflow plan created: {plan.get('workflow_name', 'unnamed')}")
        return plan
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {"error": f"Planning failed: {str(e)}"}


# ── Phase 2: Assembly ───────────────────────────────────────────────────

def assemble_workflow(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Assemble valid n8n workflow JSON from a structured plan.

    Takes node templates, applies customizations, generates connections,
    and produces a complete workflow ready for the n8n API.

    Args:
        plan: Structured plan from plan_workflow()

    Returns:
        Complete n8n workflow JSON
    """
    if "error" in plan:
        return plan

    workflow_name = plan.get("workflow_name", "Generated Workflow")
    nodes = []
    node_id_map = {}  # name -> id
    x_positions = {
        "trigger": 200,
        "llm": 500,
        "memory": 500,
        "agent": 800,
        "tool": 1100,
        "processor": 1100,
        "output": 1400,
    }
    y_offset = 0

    # Build nodes from plan
    for i, node_plan in enumerate(plan.get("nodes", [])):
        template_name = node_plan.get("template", "")
        template = _load_template(template_name)

        if not template:
            # Create a generic node if template not found
            template = {
                "type": "n8n-nodes-base.noOp",
                "typeVersion": 1,
                "name": node_plan.get("name", f"Node {i}"),
                "parameters": {},
            }

        # Generate unique ID
        node_id = str(uuid.uuid4())
        node_name = node_plan.get("name", template.get("name", f"Node {i}"))
        node_id_map[node_name] = node_id

        # Apply position based on role
        role = node_plan.get("role", "processor")
        x = x_positions.get(role, 800)
        y = 300 + (y_offset * 150)

        # Count nodes at same x position for y-offset
        same_x_count = sum(1 for n in nodes if n.get("position", [0])[0] == x)
        y = 300 + (same_x_count * 180)

        # Apply customizations — only override existing template params
        # to prevent LLM-hallucinated parameters from breaking n8n
        customizations = node_plan.get("customizations", {})
        parameters = {**template.get("parameters", {})}
        for key, value in customizations.items():
            if key in parameters:
                parameters[key] = value
            elif isinstance(parameters.get("options"), dict):
                parameters["options"][key] = value
            # Skip unknown params — LLM may hallucinate non-existent fields

        node = {
            "id": node_id,
            "name": node_name,
            "type": template["type"],
            "typeVersion": template.get("typeVersion", 1),
            "position": [x, y],
            "parameters": parameters,
        }

        # Copy webhookId if present
        if "webhookId" in template:
            node["webhookId"] = str(uuid.uuid4())

        nodes.append(node)

    # Build connections
    connections = {}
    for conn in plan.get("connections", []):
        from_name = conn.get("from", "")
        to_name = conn.get("to", "")
        conn_type = conn.get("type", "main")

        if from_name not in node_id_map or to_name not in node_id_map:
            logger.warning(f"Connection skipped: {from_name} -> {to_name} (node not found)")
            continue

        if from_name not in connections:
            connections[from_name] = {}

        if conn_type not in connections[from_name]:
            connections[from_name][conn_type] = [[]]

        connections[from_name][conn_type][0].append({
            "node": to_name,
            "type": conn_type,
            "index": 0,
        })

    # Strip node IDs — n8n assigns its own on creation
    for node in nodes:
        node.pop("id", None)

    # Assemble final workflow (don't include "active" — it's read-only on create)
    workflow = {
        "name": workflow_name,
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
        },
    }

    logger.info(
        f"Workflow assembled: {workflow_name} "
        f"({len(nodes)} nodes, {len(plan.get('connections', []))} connections)"
    )
    return workflow


# ── Combined: Generate Full Workflow ────────────────────────────────────

def generate_workflow_json(description: str) -> Dict[str, Any]:
    """
    Generate complete n8n workflow JSON from natural language description.

    Combines planning (LLM) and assembly (templates) into one call.

    Args:
        description: Natural language workflow description

    Returns:
        Dict with:
            - success: bool
            - workflow: n8n workflow JSON (if success)
            - plan: The intermediate plan (for debugging)
            - error: Error message (if failed)
    """
    # Phase 1: Plan
    plan = plan_workflow(description)
    if "error" in plan:
        return {"success": False, "error": plan["error"], "plan": None, "workflow": None}

    # Phase 2: Assemble
    workflow = assemble_workflow(plan)
    if "error" in workflow:
        return {"success": False, "error": workflow["error"], "plan": plan, "workflow": None}

    return {
        "success": True,
        "workflow": workflow,
        "plan": plan,
        "error": None,
    }


# ── Society of Mind: Multi-Agent Generation ───────────────────────────

# Feature flag: set N8N_USE_SOCIETY=true in .env to enable
_USE_SOCIETY = os.getenv("N8N_USE_SOCIETY", "false").lower() == "true"

# Lazy import to avoid loading autogen if not needed
_society_available = None


def _check_society_available() -> bool:
    """Check if the Society of Mind system is available."""
    global _society_available
    if _society_available is not None:
        return _society_available
    try:
        from ..society import run_workflow_society  # noqa: F401
        _society_available = True
        logger.info("n8n Society of Mind available")
    except ImportError as e:
        _society_available = False
        logger.info(f"n8n Society of Mind not available: {e}")
    return _society_available


def generate_workflow_json_society(description: str) -> Dict[str, Any]:
    """
    Generate n8n workflow using the Society of Mind multi-agent system.

    Falls back to the 2-phase generator if:
    - Society is not available (autogen not installed)
    - n8n is offline
    - Society execution fails

    Args:
        description: Natural language workflow description

    Returns:
        Dict with success, workflow_id, workflow_name, etc.
    """
    if not _check_society_available():
        logger.info("Society not available, using 2-phase generator")
        return generate_workflow_json(description)

    # Check n8n health first
    try:
        from .n8n_api_client import get_n8n_client
        client = get_n8n_client()
        health = client.health_check()
        if not health.get("online"):
            logger.warning("n8n offline, falling back to 2-phase generator")
            return generate_workflow_json(description)
    except Exception:
        logger.warning("n8n health check failed, falling back to 2-phase generator")
        return generate_workflow_json(description)

    # Run the Society
    from ..society import run_workflow_society

    try:
        result = run_workflow_society(description)
        if result.get("success"):
            return {
                "success": True,
                "workflow_id": result.get("workflow_id"),
                "workflow_name": result.get("workflow_name"),
                "approved": result.get("approved", False),
                "summary": result.get("summary", ""),
                "plan": None,  # Society doesn't produce a separate plan
                "workflow": None,  # Workflow is already deployed to n8n
                "error": None,
            }
        else:
            logger.warning(f"Society failed: {result.get('error')}, falling back to 2-phase")
            return generate_workflow_json(description)

    except Exception as e:
        logger.error(f"Society execution error: {e}", exc_info=True)
        logger.info("Falling back to 2-phase generator")
        return generate_workflow_json(description)


__all__ = [
    "plan_workflow",
    "assemble_workflow",
    "generate_workflow_json",
    "generate_workflow_json_society",
]
