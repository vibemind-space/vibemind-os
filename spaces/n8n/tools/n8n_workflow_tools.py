"""
n8n Workflow Tools

Voice/Chat-callable tool functions for the N8nBackendAgent.
Each function maps to an event type (n8n.generate, n8n.list, etc.).
"""

import json
import logging
import os
from typing import Any, Dict, Optional

from spaces.n8n.tools.n8n_api_client import get_n8n_client
from spaces.n8n.tools.workflow_generator import generate_workflow_json, generate_workflow_json_society

logger = logging.getLogger(__name__)

# Electron broadcast (optional import)
try:
    from tools.workspace_tools import _broadcast_to_electron
except ImportError:
    def _broadcast_to_electron(msg):
        pass


def generate_workflow(description: str, **kwargs) -> Dict[str, Any]:
    """
    Generate an n8n workflow from a natural language description and push it to n8n.

    Supports two modes:
    1. With checklist context (from VibeCoder) — enriched description + structured data
    2. Without checklist — triggers clarification questions via response_hint

    Args:
        description: Natural language workflow description
        **kwargs: Optional checklist data:
            - checklist: Dict with trigger_type, data_sources, ai_model, output
            - session_id: VibeCoder session ID (skip clarification if present)

    Returns:
        Dict with success, workflow_id, workflow_url, message
    """
    if not description or not description.strip():
        return {
            "success": False,
            "message": "No workflow description provided.",
        }

    logger.info(f"Generating workflow from description: {description[:100]}...")

    # ── Check for VibeCoder checklist context ──
    checklist = kwargs.get("checklist")
    session_id = kwargs.get("session_id")

    # If no checklist and description is short, start VibeCoder session + broadcast
    if not checklist and not session_id and len(description.split()) < 12:
        try:
            from spaces.n8n.tools.workflow_chat import get_workflow_chat_manager, CHECKLIST_ITEMS
            mgr = get_workflow_chat_manager()
            session = mgr.create_session(description)
            vibecoder_session_id = session.get("session_id", "")

            # Broadcast to Electron so UI can show checklist
            _broadcast_to_electron({
                "type": "n8n_vibecoder_checklist_needed",
                "session_id": vibecoder_session_id,
                "description": description,
                "checklist_items": CHECKLIST_ITEMS,
            })

            return {
                "success": True,
                "message": (
                    "Ich brauche noch ein paar Details bevor ich den Workflow baue. "
                    "Welcher Trigger (Chat, Webhook, Schedule)? "
                    "Welche Datenquellen (PostgreSQL, API, CSV)? "
                    "Welches AI Model (GPT-4o, GPT-5.4, Claude)? "
                    "Was soll der Output sein?"
                ),
                "response_hint": (
                    "Ich brauche noch ein paar Details: "
                    "Welcher Trigger? Welche Datenquellen? Welches AI Model? Was ist der Output?"
                ),
                "needs_checklist": True,
                "vibecoder_session_id": vibecoder_session_id,
                "description": description,
            }
        except Exception as e:
            logger.warning(f"VibeCoder session creation failed: {e}, proceeding without checklist")
            # Fall through to generation without checklist

    # Build enriched description from checklist
    enriched_description = description
    if checklist:
        parts = [description]
        if checklist.get("trigger_type"):
            parts.append(f"Trigger: {checklist['trigger_type']}")
        if checklist.get("data_sources"):
            parts.append(f"Datenquellen: {checklist['data_sources']}")
        if checklist.get("ai_model"):
            parts.append(f"AI Model: {checklist['ai_model']}")
        if checklist.get("output"):
            parts.append(f"Output: {checklist['output']}")
        enriched_description = ". ".join(parts)
        logger.info(f"Enriched description from checklist: {enriched_description[:150]}...")

    # Minibook collaboration path (when enabled)
    use_minibook = os.getenv("USE_MINIBOOK_HUB", "false").lower() == "true"
    if use_minibook:
        try:
            from spaces.minibook.minibook_hub import MinibookHub
            logger.info("Delegating workflow generation to MinibookHub for multi-space collaboration")
        except ImportError:
            pass

    # ── Society of Mind path (multi-agent, iterative) ──
    use_society = os.getenv("N8N_USE_SOCIETY", "false").lower() == "true"
    if use_society:
        logger.info("Using Society of Mind for workflow generation")
        result = generate_workflow_json_society(enriched_description)

        # Society deploys directly to n8n — check if it returned a workflow_id
        if result.get("success") and result.get("workflow_id"):
            n8n_url = get_n8n_client().base_url
            workflow_id = result["workflow_id"]
            workflow_name = result.get("workflow_name", "Generated Workflow")

            _broadcast_to_electron({
                "type": "n8n_workflow_created",
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "n8n_url": f"{n8n_url}/workflow/{workflow_id}",
            })

            return {
                "success": True,
                "message": f"Workflow '{workflow_name}' created via Society of Mind"
                    + (" and approved." if result.get("approved") else " (Review pending)."),
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "workflow_url": f"{n8n_url}/workflow/{workflow_id}",
                "approved": result.get("approved", False),
            }
        # If society returned a non-deployed result, fall through to 2-phase
        elif result.get("success") and result.get("workflow"):
            # Society produced JSON but didn't deploy — use normal push path
            workflow_json = result["workflow"]
        else:
            # Society failed — fall through to 2-phase generator
            logger.info("Society failed, falling back to 2-phase generator")
            use_society = False  # Force 2-phase path below

    # ── 2-Phase path (LLM plan + template assembly + API push) ──
    if not use_society or 'workflow_json' not in dir():
        result = generate_workflow_json(enriched_description)
        if not result["success"]:
            return {
                "success": False,
                "message": f"Workflow generation failed: {result['error']}",
            }
        workflow_json = result["workflow"]

    # Phase 3: Push to n8n
    client = get_n8n_client()
    health = client.health_check()
    if not health.get("online"):
        return {
            "success": False,
            "message": "n8n is not reachable. Start with: docker compose -f docker-compose.n8n.yml up -d",
            "workflow_json": workflow_json,  # Return JSON anyway for manual import
        }

    created = client.create_workflow(workflow_json)
    if "error" in created:
        return {
            "success": False,
            "message": f"Workflow could not be pushed: {created['error']}",
            "workflow_json": workflow_json,
        }

    workflow_id = created.get("id", "")
    workflow_name = created.get("name", workflow_json.get("name", ""))
    n8n_url = client.base_url

    # Broadcast to Electron UI
    _broadcast_to_electron({
        "type": "n8n_workflow_created",
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "n8n_url": f"{n8n_url}/workflow/{workflow_id}",
    })

    # Publish workflow to Rowboat MongoDB (for Brain seeding)
    try:
        from publishing import get_ideas_publisher
        pub = get_ideas_publisher()
        if hasattr(pub, 'publish_n8n_workflow'):
            pub.publish_n8n_workflow(workflow_name, {
                "name": workflow_name,
                "nodes": workflow_json.get("nodes", []),
                "connections": workflow_json.get("connections", []),
                "credentials_needed": result.get("plan", {}).get("credentials_needed", []),
                "description": description,
            })
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Workflow '{workflow_name}' created and saved in n8n.",
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "workflow_url": f"{n8n_url}/workflow/{workflow_id}",
        "nodes_count": len(workflow_json.get("nodes", [])),
        "credentials_needed": result.get("plan", {}).get("credentials_needed", []),
    }


def list_workflows(**kwargs) -> Dict[str, Any]:
    """List all workflows in the n8n instance."""
    logger.debug("list_workflows called")
    client = get_n8n_client()
    workflows = client.list_workflows()

    if not workflows:
        health = client.health_check()
        if not health.get("online"):
            return {
                "success": False,
                "message": "n8n is not reachable.",
            }
        return {
            "success": True,
            "message": "No workflows available.",
            "workflows": [],
        }

    summary = []
    for wf in workflows:
        summary.append({
            "id": wf.get("id"),
            "name": wf.get("name"),
            "active": wf.get("active", False),
            "created_at": wf.get("createdAt", ""),
            "updated_at": wf.get("updatedAt", ""),
        })

    return {
        "success": True,
        "message": f"{len(summary)} workflow(s) found.",
        "workflows": summary,
    }


def get_n8n_status(**kwargs) -> Dict[str, Any]:
    """Check if the n8n instance is online and reachable."""
    client = get_n8n_client()
    health = client.health_check()

    if health.get("online"):
        workflows = client.list_workflows()
        return {
            "success": True,
            "message": f"n8n is online at {health['url']}. {len(workflows)} workflow(s).",
            "online": True,
            "url": health["url"],
            "workflow_count": len(workflows),
        }
    else:
        return {
            "success": True,
            "message": f"n8n is not reachable ({health.get('error', 'unknown')}). "
                       f"Start with: docker compose -f docker-compose.n8n.yml up -d",
            "online": False,
            "url": health["url"],
        }


def activate_workflow(workflow_id: str = None, name: str = None, **kwargs) -> Dict[str, Any]:
    """Activate a workflow by ID or name."""
    client = get_n8n_client()

    wf_id = workflow_id or _find_workflow_id_by_name(client, name)
    if not wf_id:
        return {"success": False, "message": f"Workflow not found: {name or workflow_id}"}

    result = client.activate_workflow(wf_id)
    if "error" in result:
        return {"success": False, "message": f"Activation failed: {result['error']}"}

    return {"success": True, "message": f"Workflow '{result.get('name', wf_id)}' activated."}


def deactivate_workflow(workflow_id: str = None, name: str = None, **kwargs) -> Dict[str, Any]:
    """Deactivate a workflow by ID or name."""
    client = get_n8n_client()

    wf_id = workflow_id or _find_workflow_id_by_name(client, name)
    if not wf_id:
        return {"success": False, "message": f"Workflow not found: {name or workflow_id}"}

    result = client.deactivate_workflow(wf_id)
    if "error" in result:
        return {"success": False, "message": f"Deactivation failed: {result['error']}"}

    return {"success": True, "message": f"Workflow '{result.get('name', wf_id)}' deactivated."}


def delete_workflow(workflow_id: str = None, name: str = None, **kwargs) -> Dict[str, Any]:
    """Delete a workflow by ID or name."""
    client = get_n8n_client()

    wf_id = workflow_id or _find_workflow_id_by_name(client, name)
    if not wf_id:
        return {"success": False, "message": f"Workflow not found: {name or workflow_id}"}

    result = client.delete_workflow(wf_id)
    if "error" in result:
        return {"success": False, "message": f"Deletion failed: {result['error']}"}

    return {"success": True, "message": f"Workflow deleted."}


def execute_workflow(workflow_id: str = None, name: str = None, data: Dict = None, **kwargs) -> Dict[str, Any]:
    """Execute a workflow manually."""
    client = get_n8n_client()

    wf_id = workflow_id or _find_workflow_id_by_name(client, name)
    if not wf_id:
        return {"success": False, "message": f"Workflow not found: {name or workflow_id}"}

    result = client.execute_workflow(wf_id, data)
    if "error" in result:
        return {"success": False, "message": f"Execution failed: {result['error']}"}

    return {
        "success": True,
        "message": f"Workflow started.",
        "execution_id": result.get("id"),
    }


def describe_workflow(workflow_id: str = None, name: str = None, **kwargs) -> Dict[str, Any]:
    """Get detailed information about a workflow."""
    client = get_n8n_client()

    logger.debug("describe_workflow called: workflow_id=%s, name=%s", workflow_id, name)
    wf_id = workflow_id or _find_workflow_id_by_name(client, name)
    if not wf_id:
        return {"success": False, "message": f"Workflow not found: {name or workflow_id}"}

    wf = client.get_workflow(wf_id)
    if "error" in wf:
        return {"success": False, "message": f"Error: {wf['error']}"}

    nodes = wf.get("nodes", [])
    node_summary = [f"- {n.get('name')} ({n.get('type')})" for n in nodes]

    return {
        "success": True,
        "message": (
            f"Workflow: {wf.get('name')}\n"
            f"ID: {wf.get('id')}\n"
            f"Active: {wf.get('active', False)}\n"
            f"Nodes ({len(nodes)}):\n" + "\n".join(node_summary)
        ),
        "workflow": wf,
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def _find_workflow_id_by_name(client, name: Optional[str]) -> Optional[str]:
    """Find a workflow ID by its name (fuzzy match)."""
    if not name:
        return None
    workflows = client.list_workflows()
    name_lower = name.lower().strip()
    for wf in workflows:
        if wf.get("name", "").lower().strip() == name_lower:
            return wf["id"]
    # Partial match
    for wf in workflows:
        if name_lower in wf.get("name", "").lower():
            return wf["id"]
    return None


__all__ = [
    "generate_workflow",
    "list_workflows",
    "get_n8n_status",
    "activate_workflow",
    "deactivate_workflow",
    "delete_workflow",
    "execute_workflow",
    "describe_workflow",
]
