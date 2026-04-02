"""
Chat Trigger Client for n8n Workflow Testing

Extracts the Chat Trigger webhook URL from a deployed workflow
and sends test messages to it.
"""

import logging
import uuid
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


def get_chat_trigger_url(
    workflow_id: str,
    n8n_client,
) -> Dict[str, Any]:
    """
    Extract the Chat Trigger webhook URL from a deployed workflow.

    The Chat Trigger node has a webhookId that maps to:
    - Test mode: {base_url}/webhook-test/{webhookId}/chat
    - Production mode: {base_url}/webhook/{webhookId}/chat

    Since we activate the workflow, we use production mode.
    """
    logger.debug("get_chat_trigger_url called: workflow_id=%s", workflow_id)
    workflow = n8n_client.get_workflow(workflow_id)
    if "error" in workflow:
        return {"error": f"Failed to fetch workflow: {workflow.get('error')}"}

    nodes = workflow.get("nodes", [])
    chat_trigger = None
    for node in nodes:
        node_type = node.get("type", "")
        if "chatTrigger" in node_type or "chattrigger" in node_type.lower():
            chat_trigger = node
            break

    if not chat_trigger:
        return {"error": "No Chat Trigger node found in workflow"}

    webhook_id = chat_trigger.get("webhookId", "")
    if not webhook_id:
        return {"error": "Chat Trigger has no webhookId"}

    # Production webhook URL (workflow must be active)
    webhook_url = f"{n8n_client.base_url}/webhook/{webhook_id}/chat"

    return {
        "success": True,
        "webhook_url": webhook_url,
        "webhook_id": webhook_id,
        "node_name": chat_trigger.get("name", "Chat Trigger"),
    }


def send_chat_message(
    webhook_url: str,
    message: str,
    session_id: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Send a chat message to an n8n Chat Trigger webhook.

    Args:
        webhook_url: The Chat Trigger webhook URL
        message: The message to send
        session_id: Optional session ID for conversation continuity
        timeout: Request timeout in seconds

    Returns:
        Dict with success, response_text, status_code
    """
    if not session_id:
        session_id = f"society-test-{uuid.uuid4().hex[:8]}"

    payload = {
        "chatInput": message,
        "sessionId": session_id,
    }

    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

        if resp.ok:
            # n8n Chat Trigger can return JSON or plain text
            try:
                data = resp.json()
                # Extract text from various response formats
                if isinstance(data, dict):
                    response_text = (
                        data.get("output", "")
                        or data.get("text", "")
                        or data.get("response", "")
                        or str(data)
                    )
                elif isinstance(data, list) and data:
                    response_text = str(data[0])
                else:
                    response_text = str(data)
            except ValueError:
                response_text = resp.text

            return {
                "success": True,
                "response_text": response_text,
                "status_code": resp.status_code,
                "session_id": session_id,
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                "status_code": resp.status_code,
            }

    except requests.Timeout:
        return {
            "success": False,
            "error": f"Timeout after {timeout}s — workflow may need credentials configured",
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}",
        }


__all__ = ["get_chat_trigger_url", "send_chat_message"]
