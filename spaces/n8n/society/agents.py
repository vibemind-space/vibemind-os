"""
Agent factory functions for the n8n Society of Mind.

Creates 6 specialized AssistantAgent instances with their
system prompts and tool bindings.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool

from . import prompts
from . import tools

logger = logging.getLogger(__name__)

# Template directory for catalog generation
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_template_catalog() -> str:
    """Generate a text catalog of all available templates."""
    if not TEMPLATES_DIR.exists():
        return "(keine Templates gefunden)"

    lines = []
    import json
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            desc = data.get("_meta", {}).get("description", "")
            ntype = data.get("type", "")
            lines.append(f"- {f.stem}: {desc} (type: {ntype})")
        except (json.JSONDecodeError, KeyError):
            continue
    return "\n".join(lines) if lines else "(keine Templates gefunden)"


# ── Tool Definitions ───────────────────────────────────────────────────

_load_template_tool = FunctionTool(
    tools.load_template,
    description="Load an n8n node template JSON by name to check exact parameters and types.",
)

_assemble_section_tool = FunctionTool(
    tools.assemble_section,
    description="Safely merge customizations into a node template. Only applies keys that exist in the template.",
)

_deploy_workflow_tool = FunctionTool(
    tools.deploy_workflow,
    description="Deploy a complete workflow JSON to the n8n instance.",
)

_activate_workflow_tool = FunctionTool(
    tools.activate_workflow,
    description="Activate a deployed workflow so its webhooks become live.",
)

_deactivate_workflow_tool = FunctionTool(
    tools.deactivate_workflow,
    description="Deactivate a workflow.",
)

_delete_workflow_tool = FunctionTool(
    tools.delete_workflow,
    description="Delete a workflow from n8n (cleanup after failed tests).",
)

_get_chat_trigger_url_tool = FunctionTool(
    tools.get_chat_trigger_url,
    description="Get the Chat Trigger webhook URL for a deployed workflow.",
)

_send_chat_message_tool = FunctionTool(
    tools.send_chat_message,
    description="Send a test message to an n8n Chat Trigger webhook and get the response.",
)

_get_executions_tool = FunctionTool(
    tools.get_executions,
    description="Get recent execution history to check for errors.",
)


# ── Agent Factories ────────────────────────────────────────────────────


def create_architect(model_client) -> AssistantAgent:
    """Create the Workflow Architect agent."""
    catalog = _get_template_catalog()
    return AssistantAgent(
        name="workflow_architect",
        description="Plans n8n workflow structure from natural language descriptions. Produces structured JSON plans with nodes, connections, and data flow.",
        system_message=prompts.ARCHITECT_PROMPT.format(available_templates=catalog),
        model_client=model_client,
    )


def create_docs_expert(model_client) -> AssistantAgent:
    """Create the n8n Docs Expert agent."""
    return AssistantAgent(
        name="n8n_docs_expert",
        description="Validates n8n node types, parameters, and connection types. Corrects errors in workflow plans using template knowledge.",
        system_message=prompts.DOCS_EXPERT_PROMPT,
        model_client=model_client,
        tools=[_load_template_tool],
    )


def create_builder(model_client) -> AssistantAgent:
    """Create the Workflow Builder agent."""
    return AssistantAgent(
        name="workflow_builder",
        description="Assembles valid n8n workflow JSON from validated plans using templates. Handles positions, connections, and safe parameter merging.",
        system_message=prompts.BUILDER_PROMPT,
        model_client=model_client,
        tools=[_load_template_tool, _assemble_section_tool],
    )


def create_tester(model_client) -> AssistantAgent:
    """Create the Workflow Tester agent."""
    return AssistantAgent(
        name="workflow_tester",
        description="Deploys workflows to n8n, activates them, tests via Chat Trigger webhook, and reports pass/fail results.",
        system_message=prompts.TESTER_PROMPT,
        model_client=model_client,
        tools=[
            _deploy_workflow_tool,
            _activate_workflow_tool,
            _deactivate_workflow_tool,
            _delete_workflow_tool,
            _get_chat_trigger_url_tool,
            _send_chat_message_tool,
            _get_executions_tool,
        ],
    )


def create_reviewer(model_client) -> AssistantAgent:
    """Create the Workflow Reviewer agent (quality gate)."""
    return AssistantAgent(
        name="workflow_reviewer",
        description="Quality gate: reviews workflow completeness, error handling, naming, and test results. Emits WORKFLOW_APPROVED or requests changes.",
        system_message=prompts.REVIEWER_PROMPT,
        model_client=model_client,
    )


def create_ux_agent(model_client) -> AssistantAgent:
    """Create the UX Agent."""
    return AssistantAgent(
        name="ux_agent",
        description="Reviews workflow from user perspective: Chat Trigger greeting, node naming, description clarity, German text quality.",
        system_message=prompts.UX_AGENT_PROMPT,
        model_client=model_client,
    )


def create_all_agents(model_client) -> List[AssistantAgent]:
    """Create all 6 Society of Mind agents in conversation order."""
    return [
        create_architect(model_client),
        create_docs_expert(model_client),
        create_builder(model_client),
        create_tester(model_client),
        create_ux_agent(model_client),
        create_reviewer(model_client),
    ]


__all__ = [
    "create_architect",
    "create_docs_expert",
    "create_builder",
    "create_tester",
    "create_reviewer",
    "create_ux_agent",
    "create_all_agents",
]
