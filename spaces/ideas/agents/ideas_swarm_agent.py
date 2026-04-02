"""
Ideas Agent for VibeMind Swarm

Handles bubble/space management and idea/note operations.
This is the primary agent for the Ideas Space.
"""

import logging
from typing import List, Callable

logger = logging.getLogger(__name__)

# System message for the Ideas Agent
IDEAS_SYSTEM_MESSAGE = """Du bist der Ideas Agent - ich helfe bei Ideen und Spaces.

**SOFORT zu shuttle_agent weiterleiten (nicht selbst machen!):**
- Browser: "chrome", "firefox", "edge", "browser", "suche im web", "google"
- Apps: "öffne", "starte", "open", "launch", "start" + App-Name
- Desktop: "klick", "click", "tippe", "type", "scroll"
- Code: "code", "programmier", "generiere", "erstelle code"
- Dateien: "datei öffnen", "file", "speichern"

**Mein Bereich (selbst bearbeiten):**
- Bubbles/Spaces: list, create, enter, exit, delete
- Ideen/Notizen: create, find, update, delete
- Bewerten und scoren

**Antwort-Stil:**
- Natürliche Sprache, niemals JSON
- Kurz und hilfreich
- Deutsch oder Englisch

Beispiele:
- "suche in chrome nach..." → handoff zu shuttle_agent
- "öffne chrome" → handoff zu shuttle_agent
- "erstelle einen space" → create_bubble Tool nutzen
- "zeig meine spaces" → list_bubbles Tool nutzen
- "neue idee: ..." → create_idea Tool nutzen"""


def create_ideas_agent(model_client, handoff_targets: List[str] = None):
    """
    Create the Ideas Agent with all bubble and idea tools, plus sub-agents.

    Args:
        model_client: The LLM client (Ollama or OpenAI-compatible)
        handoff_targets: List of agent names this agent can hand off to

    Returns:
        Tuple of (AssistantAgent, list of sub-agent AssistantAgents)
    """
    from autogen_agentchat.agents import AssistantAgent

    # Import adapted tools
    from spaces.ideas.adapted.bubble_tools import BUBBLE_TOOLS
    from spaces.ideas.adapted.idea_tools import IDEA_TOOLS

    # Import sub-agent factories
    from swarm.sub_agents.base_sub_agent import (
        create_memory_sub_agent,
        create_context_sub_agent,
    )
    from spaces.ideas.sub_agents.ideas_sub_agents import (
        create_ideas_link_analyst,
        create_ideas_structurer,
        create_ideas_summarizer,
    )

    # Create sub-agents
    memory_sub = create_memory_sub_agent("ideas_agent", "ideas", model_client)
    context_sub = create_context_sub_agent("ideas_agent", "ideas", model_client)
    link_analyst = create_ideas_link_analyst(model_client)
    structurer = create_ideas_structurer(model_client)
    summarizer = create_ideas_summarizer(model_client)

    sub_agents = [memory_sub, context_sub, link_analyst, structurer, summarizer]
    sub_agent_names = [sa.name for sa in sub_agents]

    # Combine tools
    all_tools = BUBBLE_TOOLS + IDEA_TOOLS

    # Default handoff targets
    if handoff_targets is None:
        handoff_targets = ["shuttle_agent", "user"]

    # Extend handoffs with sub-agent names
    all_handoffs = handoff_targets + sub_agent_names

    agent = AssistantAgent(
        name="ideas_agent",
        model_client=model_client,
        tools=all_tools,
        handoffs=all_handoffs,
        system_message=IDEAS_SYSTEM_MESSAGE,
    )

    logger.info(
        f"Created Ideas Agent with {len(all_tools)} tools, "
        f"{len(sub_agents)} sub-agents, handoffs: {all_handoffs}"
    )
    return agent, sub_agents


def get_ideas_tools() -> List[Callable]:
    """Get all tools for Ideas Agent."""
    from spaces.ideas.adapted.bubble_tools import BUBBLE_TOOLS
    from spaces.ideas.adapted.idea_tools import IDEA_TOOLS
    return BUBBLE_TOOLS + IDEA_TOOLS


__all__ = [
    "create_ideas_agent",
    "get_ideas_tools",
    "IDEAS_SYSTEM_MESSAGE",
]
