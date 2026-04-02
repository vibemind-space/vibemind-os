"""
Desktop Agent for VibeMind Swarm

Handles desktop automation and system tasks.
This is the primary agent for the Desktop/Automation Space.
"""

import logging
from typing import List, Callable

logger = logging.getLogger(__name__)

# System message for the Desktop Agent
DESKTOP_SYSTEM_MESSAGE = """You are the Desktop Agent - I automate your computer.

**What I can do:**
- Open and control apps
- Click, type, scroll
- Take screenshots
- Track tasks

**Response Style:**
- Always respond in natural language, never raw JSON
- Be conversational: "I'll open Chrome for you..."
- Describe actions briefly, confirm when done

**Handoffs:**
- When done → handoff to user
- Need ideas/spaces → handoff to shuttle_agent

Ask what the user wants automated if the request is unclear."""


def create_desktop_agent(model_client, handoff_targets: List[str] = None):
    """
    Create the Desktop Agent for automation tasks, plus sub-agents.

    Args:
        model_client: The LLM client (Ollama or OpenAI-compatible)
        handoff_targets: List of agent names this agent can hand off to

    Returns:
        Tuple of (AssistantAgent, list of sub-agent AssistantAgents)
    """
    from autogen_agentchat.agents import AssistantAgent
    from spaces.desktop.tools.adapted_desktop_tools import DESKTOP_TOOLS

    # Import sub-agent factories
    from swarm.sub_agents.base_sub_agent import (
        create_memory_sub_agent,
        create_context_sub_agent,
    )
    from spaces.desktop.sub_agents.desktop_sub_agents import (
        create_desktop_planner,
        create_desktop_verifier,
        create_desktop_recorder,
    )

    # Create sub-agents
    memory_sub = create_memory_sub_agent("desktop_agent", "desktop", model_client)
    context_sub = create_context_sub_agent("desktop_agent", "desktop", model_client)
    planner = create_desktop_planner(model_client)
    verifier = create_desktop_verifier(model_client)
    recorder = create_desktop_recorder(model_client)

    sub_agents = [memory_sub, context_sub, planner, verifier, recorder]
    sub_agent_names = [sa.name for sa in sub_agents]

    # Default handoff targets
    if handoff_targets is None:
        handoff_targets = ["shuttle_agent", "user"]

    # Extend handoffs with sub-agent names
    all_handoffs = handoff_targets + sub_agent_names

    agent = AssistantAgent(
        name="desktop_agent",
        model_client=model_client,
        tools=DESKTOP_TOOLS,
        handoffs=all_handoffs,
        system_message=DESKTOP_SYSTEM_MESSAGE,
    )

    logger.info(
        f"Created Desktop Agent with {len(DESKTOP_TOOLS)} tools, "
        f"{len(sub_agents)} sub-agents, handoffs: {all_handoffs}"
    )
    return agent, sub_agents


def get_desktop_tools() -> List[Callable]:
    """Get all tools for Desktop Agent."""
    from spaces.desktop.tools.adapted_desktop_tools import DESKTOP_TOOLS
    return DESKTOP_TOOLS


__all__ = [
    "create_desktop_agent",
    "get_desktop_tools",
    "DESKTOP_SYSTEM_MESSAGE",
]
