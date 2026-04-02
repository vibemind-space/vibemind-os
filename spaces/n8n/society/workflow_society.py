"""
n8n Workflow Society of Mind

Main entry point: run_workflow_society(description) -> Dict

Uses AutoGen 0.4 SocietyOfMindAgent wrapping a SelectorGroupChat
of 6 specialized agents that iteratively plan, build, test, and
review n8n workflows.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional

from autogen_agentchat.agents import SocietyOfMindAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

from .agents import create_all_agents
from llm_config import get_model

logger = logging.getLogger(__name__)

# Max messages before forced termination (safety limit)
MAX_MESSAGES = 30


def _resolve_llm_config():
    """Resolve API key and base URL — prefer OpenAI, fallback to OpenRouter."""
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    # Try OpenAI first — but check if quota is likely exhausted
    # by looking at a marker env var set by the 2-phase generator
    if openai_key and not os.getenv("_OPENAI_QUOTA_EXHAUSTED"):
        return {
            "api_key": openai_key,
            "base_url": "https://api.openai.com/v1",
        }

    if openrouter_key:
        return {
            "api_key": openrouter_key,
            "base_url": "https://openrouter.ai/api/v1",
        }

    # Last resort: return OpenAI key even if potentially exhausted
    if openai_key:
        return {
            "api_key": openai_key,
            "base_url": "https://api.openai.com/v1",
        }

    return {"api_key": "", "base_url": "https://api.openai.com/v1"}


def _create_model_client() -> OpenAIChatCompletionClient:
    """Create the model client for agents. Prefers OpenAI, falls back to OpenRouter."""
    cfg = _resolve_llm_config()
    model = get_model("n8n_generator")
    if model.startswith("openai/"):
        model = model[len("openai/"):]

    return OpenAIChatCompletionClient(
        model=model,
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=0.3,
        model_info={
            "vision": True,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
        },
    )


def _create_selector_client() -> OpenAIChatCompletionClient:
    """Create a cheaper model client for the SelectorGroupChat's routing LLM."""
    cfg = _resolve_llm_config()
    selector_model = get_model("n8n_selector")

    return OpenAIChatCompletionClient(
        model=selector_model,
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=0.0,
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
        },
    )


SELECTOR_PROMPT = """Du bist der Koordinator eines n8n Workflow-Builder Teams.
Waehle den naechsten Agenten basierend auf dem Gespraechsverlauf.

Agenten:
- workflow_architect: Plant den Workflow (Nodes, Connections, Rollen)
- n8n_docs_expert: Validiert Node-Typen, Parameter, Connection-Typen
- workflow_builder: Assembliert valides n8n JSON aus dem Plan
- workflow_tester: Deployed und testet den Workflow in n8n
- ux_agent: Prueft UX (Naming, Greeting, Klarheit)
- workflow_reviewer: Finales Quality-Gate, gibt WORKFLOW_APPROVED

PFLICHT-REIHENFOLGE (NIEMALS ueberspringen!):
1. workflow_architect (Plan erstellen)
2. n8n_docs_expert (Plan validieren)
3. workflow_builder (JSON assemblieren)
4. workflow_tester (Deploy + Test)
5. ux_agent (UX Review)
6. workflow_reviewer (Final Approval)

Antworte NUR mit dem Namen des naechsten Agenten, z.B.: n8n_docs_expert

Bei Fehlern zurueck zum passenden Agenten:
- Deploy-Fehler → n8n_docs_expert
- JSON-Fehler → workflow_builder
- Test-Fehler → workflow_architect
"""


async def _run_society_async(description: str) -> Dict[str, Any]:
    """Run the Society of Mind asynchronously."""
    # Create model clients
    agent_client = _create_model_client()
    selector_client = _create_selector_client()

    # Create all 6 agents
    agents = create_all_agents(agent_client)

    # Termination conditions
    termination = (
        TextMentionTermination("WORKFLOW_APPROVED")
        | MaxMessageTermination(MAX_MESSAGES)
    )

    # Create SelectorGroupChat (inner team)
    inner_team = SelectorGroupChat(
        agents,
        model_client=selector_client,
        termination_condition=termination,
        selector_prompt=SELECTOR_PROMPT,
    )

    # Create SocietyOfMindAgent that wraps the team
    society = SocietyOfMindAgent(
        name="n8n_workflow_society",
        team=inner_team,
        model_client=agent_client,
        description="Generates n8n workflows via multi-agent collaboration",
    )

    # Run the society with the user's description
    task = TextMessage(
        content=f"Erstelle einen n8n Workflow fuer folgende Anforderung:\n\n{description}",
        source="user",
    )

    logger.info(f"[Society] Starting workflow generation for: {description[:80]}...")

    result = await society.on_messages([task], cancellation_token=None)

    # Extract workflow_id from conversation (Tester reports it)
    workflow_id = None
    workflow_name = None

    # The result contains the society's summary
    summary_text = result.chat_message.content if result.chat_message else ""

    # Try to extract workflow_id from the summary or inner messages
    id_match = re.search(r'"workflow_id"\s*:\s*"(\w+)"', summary_text)
    if id_match:
        workflow_id = id_match.group(1)

    name_match = re.search(r'"workflow_name"\s*:\s*"([^"]+)"', summary_text)
    if name_match:
        workflow_name = name_match.group(1)

    approved = "WORKFLOW_APPROVED" in summary_text

    if approved and workflow_id:
        logger.info(f"[Society] Workflow approved: {workflow_id} ({workflow_name})")
        return {
            "success": True,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name or "Generated Workflow",
            "approved": True,
            "summary": summary_text[:500],
        }
    elif workflow_id:
        logger.warning(f"[Society] Workflow deployed but not fully approved: {workflow_id}")
        return {
            "success": True,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name or "Generated Workflow",
            "approved": False,
            "summary": summary_text[:500],
            "warning": "Workflow deployed but review incomplete (max messages reached)",
        }
    else:
        logger.error(f"[Society] Failed to generate workflow. Summary: {summary_text[:200]}")
        return {
            "success": False,
            "error": "Society failed to produce a deployed workflow",
            "summary": summary_text[:500],
        }


def run_workflow_society(description: str) -> Dict[str, Any]:
    """
    Run the Society of Mind workflow generation (sync wrapper).

    This is the main entry point called from workflow_generator.py.

    Args:
        description: Natural language workflow description

    Returns:
        Dict with success, workflow_id, workflow_name, approved, summary
    """
    try:
        # Check if there's already a running event loop
        try:
            loop = asyncio.get_running_loop()
            # We're inside an async context — create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run_society_async(description))
                return future.result(timeout=180)  # 3 minute timeout
        except RuntimeError:
            # No running loop — safe to use asyncio.run
            return asyncio.run(_run_society_async(description))

    except Exception as e:
        logger.error(f"[Society] Unexpected error: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Society execution failed: {str(e)}",
        }


__all__ = ["run_workflow_society"]
