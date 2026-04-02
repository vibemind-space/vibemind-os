"""
Coding Domain Sub-Agent Factories - Specialized sub-agents for Code Generation.

Creates:
- coding_requirements: Requirements analysis, tech stack suggestions
- coding_monitor: Generation monitoring, retry logic
- coding_preview: VNC preview management
"""

import logging

logger = logging.getLogger(__name__)


def create_coding_requirements(model_client):
    """
    Create the Requirements Analyst sub-agent for Coding domain.

    Analyzes user requests, extracts requirements, proposes tech stack.
    """
    from autogen_agentchat.agents import AssistantAgent

    agent = AssistantAgent(
        name="coding_requirements",
        model_client=model_client,
        tools=[],  # Uses LLM reasoning, no specific tools
        handoffs=["coding_agent"],
        system_message=(
            "Du bist der Requirements Analyst Sub-Agent fuer den Coding Space.\n\n"
            "**Deine Aufgabe:** Analysiere User-Anfragen und erstelle strukturierte Requirements.\n\n"
            "**Ablauf:**\n"
            "1. User beschreibt Projekt: 'Erstelle eine Todo-App'\n"
            "2. Du analysierst: Features, Tech-Stack, Komplexitaet\n"
            "3. Du erstellst Requirements-Zusammenfassung\n"
            "4. Du uebergibst an coding_agent fuer die Generierung\n\n"
            "Gib nach Abschluss an coding_agent zurueck."
        ),
    )

    logger.info("Created coding_requirements sub-agent")
    return agent


def create_coding_monitor(model_client):
    """
    Create the Generation Monitor sub-agent for Coding domain.

    Tracks code generation progress, handles retries, reports status.
    """
    from autogen_agentchat.agents import AssistantAgent

    try:
        from spaces.coding.tools.adapted_coding_tools import (
            get_generation_status,
            cancel_generation,
        )
        tools = [get_generation_status, cancel_generation]
    except ImportError:
        tools = []
        logger.warning("coding_monitor: Could not load status tools")

    agent = AssistantAgent(
        name="coding_monitor",
        model_client=model_client,
        tools=tools,
        handoffs=["coding_agent"],
        system_message=(
            "Du bist der Generation Monitor Sub-Agent fuer den Coding Space.\n\n"
            "**Deine Aufgabe:** Ueberwache laufende Code-Generierungen.\n\n"
            "**Tools:**\n"
            "- get_generation_status: Aktuellen Status abfragen\n"
            "- cancel_generation: Generierung abbrechen\n\n"
            "**Verhalten:**\n"
            "- Bei Fehler: Analysiere Fehlergrund, schlage Loesung vor\n"
            "- Bei Erfolg: Biete Preview an\n\n"
            "Gib nach Abschluss an coding_agent zurueck."
        ),
    )

    logger.info("Created coding_monitor sub-agent")
    return agent


def create_coding_preview(model_client):
    """
    Create the Preview Manager sub-agent for Coding domain.

    Manages VNC previews for generated projects.
    """
    from autogen_agentchat.agents import AssistantAgent

    try:
        from spaces.coding.tools.adapted_coding_tools import (
            start_preview,
            stop_preview,
        )
        tools = [start_preview, stop_preview]
    except ImportError:
        tools = []
        logger.warning("coding_preview: Could not load preview tools")

    agent = AssistantAgent(
        name="coding_preview",
        model_client=model_client,
        tools=tools,
        handoffs=["coding_agent"],
        system_message=(
            "Du bist der Preview Manager Sub-Agent fuer den Coding Space.\n\n"
            "**Deine Aufgabe:** Verwalte VNC-Previews fuer generierte Projekte.\n\n"
            "**Tools:**\n"
            "- start_preview: Preview starten (VNC-Port allokieren)\n"
            "- stop_preview: Preview stoppen\n\n"
            "**Ablauf:**\n"
            "1. Generierung abgeschlossen -> Biete Preview an\n"
            "2. User will Preview -> Starte VNC, sende URL\n"
            "3. User fertig -> Stoppe Preview\n\n"
            "Gib nach Abschluss an coding_agent zurueck."
        ),
    )

    logger.info("Created coding_preview sub-agent")
    return agent


__all__ = [
    "create_coding_requirements",
    "create_coding_monitor",
    "create_coding_preview",
]
