"""
Tool functions for the Society of Mind agents.

These are wrapped as AutoGen FunctionTool instances and bound to specific agents.
Each tool interacts with the n8n API or the local template system.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# ── Template Tools (for DocsExpert + Builder) ──────────────────────────


def load_template(template_name: str) -> str:
    """
    Load an n8n node template JSON by name.

    Returns the full template JSON as a string, including _meta documentation.
    Use this to check exact parameter schemas and node type names.

    Args:
        template_name: Template name without .json extension
                       (e.g., "ai_agent_base", "chat_trigger", "llm_openai")
    """
    path = TEMPLATES_DIR / f"{template_name}.json"
    if not path.exists():
        available = [f.stem for f in TEMPLATES_DIR.glob("*.json")]
        return json.dumps({
            "error": f"Template '{template_name}' not found",
            "available_templates": available,
        })
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return json.dumps(data, indent=2)


def assemble_section(template_name: str, customizations_json: str) -> str:
    """
    Safely merge customizations into a node template.

    Only applies customization keys that exist in the template parameters.
    Prevents LLM-hallucinated parameters from breaking n8n.

    Args:
        template_name: Template name (e.g., "ai_agent_base")
        customizations_json: JSON string with customization key-value pairs
    """
    logger.debug("assemble_section called: template=%s", template_name)
    path = TEMPLATES_DIR / f"{template_name}.json"
    if not path.exists():
        return json.dumps({"error": f"Template '{template_name}' not found"})

    with open(path, "r", encoding="utf-8") as f:
        template = json.load(f)

    # Remove internal metadata
    template.pop("_meta", None)

    try:
        customizations = json.loads(customizations_json) if customizations_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid customizations JSON"})

    # Safe merge: only override existing params or add to options
    parameters = {**template.get("parameters", {})}
    for key, value in customizations.items():
        if key in parameters:
            parameters[key] = value
        elif isinstance(parameters.get("options"), dict):
            parameters["options"][key] = value
        # Skip unknown params

    template["parameters"] = parameters

    # Generate webhookId if template has one
    if "webhookId" in template:
        template["webhookId"] = str(uuid.uuid4())

    return json.dumps(template, indent=2)


# ── Deployment Tools (for Tester) ──────────────────────────────────────


def deploy_workflow(workflow_json_str: str) -> str:
    """
    Deploy a workflow JSON to n8n.

    Args:
        workflow_json_str: Complete n8n workflow JSON as string

    Returns:
        JSON with workflow_id and success status
    """
    logger.debug("deploy_workflow called")
    from ..tools.n8n_api_client import get_n8n_client

    try:
        workflow_json = json.loads(workflow_json_str)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid workflow JSON: {e}"})

    client = get_n8n_client()
    result = client.create_workflow(workflow_json)

    if "error" in result:
        return json.dumps({"error": result["error"]})

    workflow_id = result.get("id", "")
    return json.dumps({
        "success": True,
        "workflow_id": str(workflow_id),
        "workflow_name": result.get("name", ""),
        "message": f"Workflow deployed with ID {workflow_id}",
    })


def activate_workflow(workflow_id: str) -> str:
    """
    Activate a deployed workflow so its webhooks become live.

    Args:
        workflow_id: The n8n workflow ID
    """
    from ..tools.n8n_api_client import get_n8n_client

    client = get_n8n_client()
    result = client.activate_workflow(workflow_id)

    if "error" in result:
        return json.dumps({"error": result["error"]})

    return json.dumps({
        "success": True,
        "message": f"Workflow {workflow_id} activated",
    })


def deactivate_workflow(workflow_id: str) -> str:
    """
    Deactivate a workflow.

    Args:
        workflow_id: The n8n workflow ID
    """
    from ..tools.n8n_api_client import get_n8n_client

    client = get_n8n_client()
    result = client.deactivate_workflow(workflow_id)

    if "error" in result:
        return json.dumps({"error": result["error"]})

    return json.dumps({"success": True, "message": f"Workflow {workflow_id} deactivated"})


def delete_workflow(workflow_id: str) -> str:
    """
    Delete a workflow from n8n (cleanup after failed tests).

    Args:
        workflow_id: The n8n workflow ID to delete
    """
    from ..tools.n8n_api_client import get_n8n_client

    client = get_n8n_client()
    result = client.delete_workflow(workflow_id)

    if "error" in result:
        return json.dumps({"error": result["error"]})

    return json.dumps({"success": True, "message": f"Workflow {workflow_id} deleted"})


def get_chat_trigger_url(workflow_id: str) -> str:
    """
    Get the Chat Trigger webhook URL for a deployed workflow.

    The workflow must be active for the webhook to work.

    Args:
        workflow_id: The n8n workflow ID
    """
    logger.debug("get_chat_trigger_url called: workflow_id=%s", workflow_id)
    from ..tools.n8n_api_client import get_n8n_client
    from .chat_trigger_client import get_chat_trigger_url as _get_url

    client = get_n8n_client()
    result = _get_url(workflow_id, client)
    return json.dumps(result)


def send_chat_message(webhook_url: str, message: str) -> str:
    """
    Send a test message to an n8n Chat Trigger webhook.

    Args:
        webhook_url: The Chat Trigger webhook URL
        message: The test message to send
    """
    from .chat_trigger_client import send_chat_message as _send

    result = _send(webhook_url, message)
    return json.dumps(result)


def get_executions(workflow_id: str) -> str:
    """
    Get recent execution history for a workflow to check for errors.

    Args:
        workflow_id: The n8n workflow ID
    """
    logger.debug("get_executions called: workflow_id=%s", workflow_id)
    from ..tools.n8n_api_client import get_n8n_client

    client = get_n8n_client()
    executions = client.get_executions(workflow_id, limit=5)
    return json.dumps(executions[:5] if executions else [])


__all__ = [
    "load_template",
    "assemble_section",
    "deploy_workflow",
    "activate_workflow",
    "deactivate_workflow",
    "delete_workflow",
    "get_chat_trigger_url",
    "send_chat_message",
    "get_executions",
]
