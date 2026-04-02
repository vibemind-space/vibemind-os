"""
Ideas Swarm - AutoGen 0.4 Swarm for the Ideas Space

Replaces the direct event→tool dispatch of IdeasAgent with a multi-agent
Swarm that uses LLM reasoning to select and execute tools.

Architecture:
    IdeaCoordinator (0 tools, handoffs to all)
    ├── IdeaManager (~8 tools: CRUD)
    ├── IdeaConnector (~6 tools: links/connections)
    ├── IdeaEnricher (~5 tools: AI analysis)
    ├── IdeaFormatter (~4 tools: format conversion)
    └── IdeaExplorer (~10 tools: AI-Scientist tree search)

Usage:
    swarm = create_ideas_swarm()
    result = await swarm.run(task="Erstelle eine Idee: API Design")
    response = result.messages[-1].content
"""

import os
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


# --- Typed wrappers for format_dispatcher (Dict-based originals) ---

def convert_format(idea_name: str = "", target_format: str = "", columns: str = "") -> str:
    """
    Convert an idea to a different format.

    Args:
        idea_name: Name of the idea to convert
        target_format: Target format (table, action_list, pros_cons, hierarchy, specs, note)
        columns: Optional column names for table format

    Returns:
        Success or error message
    """
    if not target_format:
        return "Bitte gib ein Zielformat an (table, action_list, pros_cons, hierarchy, specs, note)."
    from tools.format_dispatcher import convert_format as _convert_format
    return _convert_format({
        "idea_name": idea_name,
        "target_format": target_format,
        "columns": columns,
    })


def list_available_formats() -> str:
    """
    List all available format types for ideas.

    Returns:
        List of formats with descriptions
    """
    from tools.format_dispatcher import list_available_formats as _list_available_formats
    return _list_available_formats({})


# --- Swarm Creation ---

def _get_model_client():
    """Get OpenRouter model client for AG2 agents."""
    from swarm.cloud_client import get_model_client
    return get_model_client()


def create_ideas_swarm(model_client=None):
    """
    Create the Ideas Space AutoGen 0.4 Swarm.

    6 agents with ~10 tools each, coordinated by IdeaCoordinator.

    Args:
        model_client: Optional pre-configured model client.
                      Uses OpenRouter via cloud_client if not provided.

    Returns:
        Swarm team instance
    """
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import (
        HandoffTermination,
        TextMentionTermination,
        MaxMessageTermination,
    )
    from autogen_agentchat.teams import Swarm

    if model_client is None:
        model_client = _get_model_client()

    # --- Import typed tools ---

    # Core CRUD tools (adapted_idea_tools.py)
    from spaces.ideas.adapted.idea_tools import (
        list_ideas,
        count_ideas,
        create_idea,
        find_idea,
        update_idea,
        delete_idea,
        move_idea,
        get_current_space,
    )

    # Connection tools
    from spaces.ideas.adapted.idea_tools import (
        connect_ideas,
        disconnect_ideas,
        connect_ideas_multi,
        link_idea_to_root,
        auto_link_ideas,
        analyze_and_suggest_links,
    )

    # AI enrichment tools
    from spaces.ideas.adapted.idea_tools import (
        classify_idea,
        expand_ideas,
        explain_idea,
        summarize_idea,
        generate_white_paper,
    )

    # Format tools (adapted_idea_tools + local wrappers)
    from spaces.ideas.adapted.idea_tools import (
        format_idea_as_table,
        add_image,
    )

    # Exploration tools (already typed + async)
    from spaces.ideas.tools.exploration_tools import (
        start_exploration,
        stop_exploration,
        get_exploration_status,
        accept_connection,
        reject_connection,
        explore_deeper,
        visualize_exploration,
        respond_to_exploration_question,
        set_exploration_direction,
    )

    # --- Define Agents ---

    coordinator = AssistantAgent(
        name="idea_coordinator",
        model_client=model_client,
        handoffs=[
            "idea_manager",
            "idea_connector",
            "idea_enricher",
            "idea_formatter",
            "idea_explorer",
            "user",
        ],
        system_message=(
            "Du koordinierst den Ideas Space. Analysiere die Aufgabe und "
            "delegiere an den richtigen Spezialisten:\n\n"
            "- idea_manager: Ideen erstellen, finden, updaten, löschen, verschieben, auflisten\n"
            "- idea_connector: Verbindungen zwischen Ideen erstellen/entfernen/analysieren\n"
            "- idea_enricher: KI-Analyse (klassifizieren, erweitern, erklären, zusammenfassen, Whitepaper)\n"
            "- idea_formatter: Format-Konvertierung (Tabelle, Kanban, Mind Map, SWOT, Flowchart, etc.)\n"
            "- idea_explorer: AI-Scientist Exploration (Tree Search, interaktiv)\n\n"
            "Fasse Ergebnisse zusammen und gib an user zurück wenn fertig.\n"
            "Bei Unklarheit über die Absicht, frag beim user nach."
        ),
    )

    manager = AssistantAgent(
        name="idea_manager",
        model_client=model_client,
        handoffs=["idea_coordinator"],
        tools=[
            list_ideas,
            count_ideas,
            create_idea,
            find_idea,
            update_idea,
            delete_idea,
            move_idea,
            get_current_space,
        ],
        system_message=(
            "Du verwaltest Ideen im aktuellen Bubble-Space.\n"
            "Nutze die verfügbaren Tools für CRUD-Operationen:\n"
            "- list_ideas: Alle Ideen auflisten\n"
            "- count_ideas: Anzahl der Ideen\n"
            "- create_idea: Neue Idee erstellen (braucht title)\n"
            "- find_idea: Idee suchen (braucht query)\n"
            "- update_idea: Idee aktualisieren\n"
            "- delete_idea: Idee löschen\n"
            "- move_idea: Idee verschieben\n"
            "- get_current_space: Aktuellen Space anzeigen\n\n"
            "Gib nach Abschluss an idea_coordinator zurück."
        ),
    )

    connector = AssistantAgent(
        name="idea_connector",
        model_client=model_client,
        handoffs=["idea_coordinator"],
        tools=[
            connect_ideas,
            disconnect_ideas,
            connect_ideas_multi,
            link_idea_to_root,
            auto_link_ideas,
            analyze_and_suggest_links,
        ],
        system_message=(
            "Du verwaltest Verbindungen zwischen Ideen.\n"
            "- connect_ideas: Zwei Ideen verbinden\n"
            "- disconnect_ideas: Verbindung entfernen\n"
            "- connect_ideas_multi: Eine Idee mit mehreren verbinden\n"
            "- link_idea_to_root: Mit Root-Node verbinden\n"
            "- auto_link_ideas: Semantisch ähnliche automatisch verlinken\n"
            "- analyze_and_suggest_links: Verlinkungen vorschlagen (ohne Erstellung)\n\n"
            "Gib nach Abschluss an idea_coordinator zurück."
        ),
    )

    enricher = AssistantAgent(
        name="idea_enricher",
        model_client=model_client,
        handoffs=["idea_coordinator"],
        tools=[
            classify_idea,
            expand_ideas,
            explain_idea,
            summarize_idea,
            generate_white_paper,
        ],
        system_message=(
            "Du bereicherst Ideen mit KI-Analyse.\n"
            "- classify_idea: Idee kategorisieren\n"
            "- expand_ideas: Verwandte Ideen generieren\n"
            "- explain_idea: Idee erklären\n"
            "- summarize_idea: Zusammenfassung erstellen\n"
            "- generate_white_paper: Whitepaper aus verlinkten Ideen generieren\n\n"
            "Gib nach Abschluss an idea_coordinator zurück."
        ),
    )

    formatter = AssistantAgent(
        name="idea_formatter",
        model_client=model_client,
        handoffs=["idea_coordinator"],
        tools=[
            convert_format,
            list_available_formats,
            format_idea_as_table,
            add_image,
        ],
        system_message=(
            "Du konvertierst Ideen in verschiedene Formate.\n"
            "- convert_format: In Format konvertieren. Verfügbare Formate:\n"
            "  note, table, action_list, pros_cons, hierarchy, specs,\n"
            "  kanban, mindmap, swot, user_story, flowchart\n"
            "- list_available_formats: Verfügbare Formate anzeigen\n"
            "- format_idea_as_table: Als Tabelle formatieren\n"
            "- add_image: Bild hinzufügen\n\n"
            "Gib nach Abschluss an idea_coordinator zurück."
        ),
    )

    explorer = AssistantAgent(
        name="idea_explorer",
        model_client=model_client,
        handoffs=["idea_coordinator"],
        tools=[
            start_exploration,
            stop_exploration,
            get_exploration_status,
            accept_connection,
            reject_connection,
            explore_deeper,
            visualize_exploration,
            respond_to_exploration_question,
            set_exploration_direction,
        ],
        system_message=(
            "Du führst AI-Scientist Tree-Search Exploration durch.\n"
            "- start_exploration: Exploration starten (bubble_id, depth, mode)\n"
            "- stop_exploration: Exploration stoppen\n"
            "- get_exploration_status: Status abfragen\n"
            "- accept_connection: Entdeckte Verbindung akzeptieren\n"
            "- reject_connection: Verbindung ablehnen\n"
            "- explore_deeper: Eine Stufe tiefer gehen\n"
            "- visualize_exploration: Ergebnisse visualisieren\n"
            "- respond_to_exploration_question: Auf Rückfrage antworten\n"
            "- set_exploration_direction: Richtung setzen (guided mode)\n\n"
            "Gib nach Abschluss an idea_coordinator zurück."
        ),
    )

    # --- Termination ---
    termination = (
        HandoffTermination(target="user")
        | TextMentionTermination("DONE")
        | MaxMessageTermination(max_messages=15)
    )

    # --- Create Swarm ---
    swarm = Swarm(
        participants=[
            coordinator,
            manager,
            connector,
            enricher,
            formatter,
            explorer,
        ],
        termination_condition=termination,
    )

    logger.info(
        "Created Ideas Swarm: 6 agents "
        "(coordinator + manager + connector + enricher + formatter + explorer)"
    )
    return swarm


# --- Singleton ---
_ideas_swarm = None


def get_ideas_swarm(model_client=None):
    """Get or create the Ideas Swarm singleton."""
    global _ideas_swarm
    if _ideas_swarm is None:
        _ideas_swarm = create_ideas_swarm(model_client)
    return _ideas_swarm


__all__ = [
    "create_ideas_swarm",
    "get_ideas_swarm",
]
