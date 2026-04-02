"""
Desktop Domain Sub-Agent Factories - Specialized sub-agents for Desktop Automation.

Creates:
- desktop_planner: Decompose complex tasks into atomic actions
- desktop_verifier: Screenshot-based verification of actions
- desktop_recorder: Record successful sequences for replay
"""

import logging

logger = logging.getLogger(__name__)


def create_desktop_planner(model_client):
    """
    Create the Task Planner sub-agent for Desktop domain.

    Decomposes complex desktop tasks into atomic actions.
    """
    from autogen_agentchat.agents import AssistantAgent

    agent = AssistantAgent(
        name="desktop_planner",
        model_client=model_client,
        tools=[],  # Uses LLM reasoning for task decomposition
        handoffs=["desktop_agent"],
        system_message=(
            "Du bist der Task Planner Sub-Agent fuer Desktop Automation.\n\n"
            "**Deine Aufgabe:** Zerlege komplexe Desktop-Tasks in atomare Aktionen.\n\n"
            "**Beispiel:**\n"
            "User: 'Oeffne Chrome, gehe zu github.com und erstelle ein neues Repository'\n"
            "Plan:\n"
            "1. open_app('Chrome')\n"
            "2. Warte 2 Sekunden\n"
            "3. type_text('github.com') in Adressleiste\n"
            "4. press_key('enter')\n"
            "5. Warte 3 Sekunden\n"
            "6. click_element('New Repository Button')\n\n"
            "Gib den Plan als strukturierte Liste an desktop_agent zurueck."
        ),
    )

    logger.info("Created desktop_planner sub-agent")
    return agent


def create_desktop_verifier(model_client):
    """
    Create the Vision Verifier sub-agent for Desktop domain.

    Takes screenshots to verify action results, detect errors.
    """
    from autogen_agentchat.agents import AssistantAgent

    try:
        from spaces.desktop.tools.adapted_desktop_tools import take_screenshot
        tools = [take_screenshot]
    except ImportError:
        tools = []
        logger.warning("desktop_verifier: Could not load screenshot tool")

    agent = AssistantAgent(
        name="desktop_verifier",
        model_client=model_client,
        tools=tools,
        handoffs=["desktop_agent"],
        system_message=(
            "Du bist der Vision Verifier Sub-Agent fuer Desktop Automation.\n\n"
            "**Deine Aufgabe:** Verifiziere ob Desktop-Aktionen erfolgreich waren.\n\n"
            "**Ablauf:**\n"
            "1. Vor Aktion: Screenshot 'vorher'\n"
            "2. Nach Aktion: Screenshot 'nachher'\n"
            "3. Vergleiche: Ist erwartetes Ergebnis sichtbar?\n"
            "4. Bei Fehler: Bericht an desktop_agent mit Analyse\n\n"
            "Gib nach Abschluss an desktop_agent zurueck."
        ),
    )

    logger.info("Created desktop_verifier sub-agent")
    return agent


def create_desktop_recorder(model_client):
    """
    Create the Automation Recorder sub-agent for Desktop domain.

    Records successful action sequences for replay.
    """
    from autogen_agentchat.agents import AssistantAgent

    agent = AssistantAgent(
        name="desktop_recorder",
        model_client=model_client,
        tools=[],  # Recording tools would be added here
        handoffs=["desktop_agent"],
        system_message=(
            "Du bist der Automation Recorder Sub-Agent.\n\n"
            "**Deine Aufgabe:** Zeichne erfolgreiche Desktop-Ablaeufe auf.\n\n"
            "**Wann wirst du gerufen:**\n"
            "- User: 'Merk dir das' -> Aufzeichnung starten\n"
            "- User: 'Mach das nochmal' -> Letzte Sequenz abspielen\n"
            "- User: 'Zeig meine Automationen' -> Liste anzeigen\n\n"
            "Gib nach Abschluss an desktop_agent zurueck."
        ),
    )

    logger.info("Created desktop_recorder sub-agent")
    return agent


__all__ = [
    "create_desktop_planner",
    "create_desktop_verifier",
    "create_desktop_recorder",
]
