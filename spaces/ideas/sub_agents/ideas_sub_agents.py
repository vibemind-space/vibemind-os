"""
Ideas Domain Sub-Agent Factories - Specialized sub-agents for the Ideas Space.

Creates:
- ideas_link_analyst: Connection analysis, graph health, linking strategies
- ideas_structurer: Batch formatting, format recommendations
- ideas_summarizer: Summaries at idea/bubble/workspace level
"""

import logging

logger = logging.getLogger(__name__)


def create_ideas_link_analyst(model_client):
    """
    Create the Link Analyst sub-agent for Ideas domain.

    Analyzes connection patterns, suggests link strategies,
    monitors graph health.
    """
    from autogen_agentchat.agents import AssistantAgent

    # Use existing connection tools
    try:
        from spaces.ideas.adapted.idea_tools import (
            auto_link_ideas,
            analyze_and_suggest_links,
            connect_ideas,
            disconnect_ideas,
        )
        tools = [auto_link_ideas, analyze_and_suggest_links, connect_ideas, disconnect_ideas]
    except ImportError:
        tools = []
        logger.warning("ideas_link_analyst: Could not load connection tools")

    agent = AssistantAgent(
        name="ideas_link_analyst",
        model_client=model_client,
        tools=tools,
        handoffs=["ideas_agent"],
        system_message=(
            "Du bist der Link Analyst Sub-Agent fuer den Ideas Space.\n\n"
            "**Deine Aufgabe:** Analysiere und optimiere Verbindungen zwischen Ideen.\n\n"
            "**Tools:**\n"
            "- auto_link_ideas: Semantisch aehnliche Ideen automatisch verlinken\n"
            "- analyze_and_suggest_links: Verlinkungen vorschlagen (ohne Erstellung)\n"
            "- connect_ideas: Zwei Ideen verbinden\n"
            "- disconnect_ideas: Verbindung entfernen\n\n"
            "**Wann wirst du gerufen:**\n"
            "- User fragt nach Verbindungen: 'Welche Ideen gehoeren zusammen?'\n"
            "- Nach Batch-Erstellung: Automatisches Linking vorschlagen\n"
            "- Bei Graph-Analyse-Anfragen\n\n"
            "Gib nach Abschluss an ideas_agent zurueck."
        ),
    )

    logger.info("Created ideas_link_analyst sub-agent")
    return agent


def create_ideas_structurer(model_client):
    """
    Create the Content Structurer sub-agent for Ideas domain.

    Converts raw ideas into structured formats, batch operations,
    format recommendations.
    """
    from autogen_agentchat.agents import AssistantAgent

    try:
        from spaces.ideas.adapted.idea_tools import format_idea_as_table
        tools = [format_idea_as_table]

        # Add format dispatcher tools if available
        try:
            from spaces.ideas.swarm.ideas_swarm import convert_format, list_available_formats
            tools.extend([convert_format, list_available_formats])
        except ImportError:
            pass
    except ImportError:
        tools = []
        logger.warning("ideas_structurer: Could not load format tools")

    agent = AssistantAgent(
        name="ideas_structurer",
        model_client=model_client,
        tools=tools,
        handoffs=["ideas_agent"],
        system_message=(
            "Du bist der Content Structurer Sub-Agent fuer den Ideas Space.\n\n"
            "**Deine Aufgabe:** Konvertiere rohe Ideen in strukturierte Formate.\n\n"
            "**Verfuegbare Formate:**\n"
            "note, table, action_list, pros_cons, hierarchy, specs, "
            "kanban, mindmap, swot, user_story, flowchart\n\n"
            "**Wann wirst du gerufen:**\n"
            "- User bittet um Formatierung: 'Mach daraus eine Aktionsliste'\n"
            "- Batch-Operationen: 'Formatiere alle Ideen als Kanban'\n"
            "- Format-Empfehlungen basierend auf Inhalt\n\n"
            "Gib nach Abschluss an ideas_agent zurueck."
        ),
    )

    logger.info("Created ideas_structurer sub-agent")
    return agent


def create_ideas_summarizer(model_client):
    """
    Create the Summarizer sub-agent for Ideas domain.

    Generates summaries at idea, bubble, and workspace levels.
    """
    from autogen_agentchat.agents import AssistantAgent

    try:
        from spaces.ideas.adapted.idea_tools import (
            summarize_idea,
            generate_white_paper,
            explain_idea,
        )
        tools = [summarize_idea, generate_white_paper, explain_idea]
    except ImportError:
        tools = []
        logger.warning("ideas_summarizer: Could not load summary tools")

    agent = AssistantAgent(
        name="ideas_summarizer",
        model_client=model_client,
        tools=tools,
        handoffs=["ideas_agent"],
        system_message=(
            "Du bist der Summarizer Sub-Agent fuer den Ideas Space.\n\n"
            "**Deine Aufgabe:** Erstelle Zusammenfassungen auf verschiedenen Ebenen.\n\n"
            "**Tools:**\n"
            "- summarize_idea: Einzelne Idee zusammenfassen\n"
            "- generate_white_paper: Whitepaper aus verlinkten Ideen\n"
            "- explain_idea: Idee erklaeren\n\n"
            "**Wann wirst du gerufen:**\n"
            "- User fragt: 'Was ist in diesem Space?', 'Zusammenfassung bitte'\n"
            "- Nach Exploration: Ergebnisse zusammenfassen\n"
            "- Session-Ende: Workspace-Digest erstellen\n\n"
            "Gib nach Abschluss an ideas_agent zurueck."
        ),
    )

    logger.info("Created ideas_summarizer sub-agent")
    return agent


__all__ = [
    "create_ideas_link_analyst",
    "create_ideas_structurer",
    "create_ideas_summarizer",
]
