"""
DesktopBroadcastAgent - Fan-out agent for Desktop Automation + Messaging domain.

Migrated from: DesktopAgent (backend_agents/desktop_agent.py)
Extended with: OpenClaw/ClawedVoice messaging tools

Domain prefixes: desktop.*, messaging.*, web.*, openclaw.*
"""

import logging
from typing import Dict, Set, Callable, Optional

from swarm.broadcast.base_broadcast_agent import BaseBroadcastAgent

logger = logging.getLogger(__name__)


class DesktopBroadcastAgent(BaseBroadcastAgent):
    """
    Broadcast agent for Desktop Automation + Messaging domain.

    Handles 18 tools:
    - 12 Desktop tools: app launching, UI interaction, Moire vision
    - 6 Messaging tools: WhatsApp, Telegram, Web search (via OpenClaw)
    """

    EVENT_TO_TOOL = {
        # Basic desktop operations
        "desktop.open_app": "open_app",
        "desktop.click": "click_element",
        "desktop.type": "type_text",
        "desktop.press_key": "press_key",
        "desktop.screenshot": "take_screenshot",
        "desktop.scroll": "scroll_screen",
        "desktop.task": "execute_desktop_task",
        # Task management
        "desktop.task.create": "create_task_node",
        "desktop.task.update": "update_task_status",
        "desktop.task.list": "get_task_list",
        # Moire vision
        "desktop.moire.scan": "moire_scan",
        "desktop.moire.find": "moire_find_element",
        # Messaging (ClawedVoice/OpenClaw)
        "messaging.whatsapp": "send_whatsapp",
        "messaging.telegram": "send_telegram",
        "messaging.send": "send_whatsapp",
        "web.search": "web_search",
        "web.fetch": "web_fetch",
        "openclaw.status": "get_openclaw_status",
        "openclaw.notifications": "get_pending_notifications",
    }

    PARAM_MAPPING = {
        "desktop.open_app": {
            "name": "app_name",
            "application": "app_name",
            "app": "app_name",
        },
        "desktop.click": {
            "description": "element_description",
            "target": "element_description",
            "element": "element_description",
        },
        "desktop.type": {
            "content": "text",
            "string": "text",
            "message": "text",
            "input": "text",
        },
        "desktop.press_key": {
            "button": "key",
            "taste": "key",
        },
        "desktop.task": {
            "description": "task_description",
            "task": "task_description",
            "action": "task_description",
        },
        "desktop.task.create": {
            "name": "title",
            "task_name": "title",
        },
        "desktop.task.update": {
            "name": "task_name",
            "title": "task_name",
        },
        "desktop.moire.find": {
            "description": "element_description",
            "target": "element_description",
            "element": "element_description",
        },
        # Messaging param mappings
        "messaging.whatsapp": {
            "to": "recipient",
            "nummer": "recipient",
            "empfaenger": "recipient",
            "text": "message",
            "nachricht": "message",
            "content": "message",
        },
        "messaging.telegram": {
            "to": "recipient",
            "user": "recipient",
            "empfaenger": "recipient",
            "text": "message",
            "nachricht": "message",
            "content": "message",
        },
        "web.search": {
            "suche": "query",
            "anfrage": "query",
            "q": "query",
        },
        "web.fetch": {
            "seite": "url",
            "link": "url",
            "adresse": "url",
        },
    }

    @property
    def name(self) -> str:
        return "desktop_agent"

    @property
    def domain_prefixes(self) -> Set[str]:
        return {"desktop.", "messaging.", "web.", "openclaw."}

    @property
    def profiling_perspective(self) -> str:
        return (
            "Desktop/Automation/Messaging: App-Nutzungsgewohnheiten, Workflow-Muster, "
            "haeufig genutzte Anwendungen, Automatisierungs-Praeferenzen, "
            "Multitasking-Verhalten, Produktivitaetsmuster, Kommunikationspraeferenzen, "
            "bevorzugte Messaging-Plattformen (WhatsApp, Telegram)"
        )

    def _load_tools(self) -> Dict[str, Callable]:
        """Load desktop automation tools."""
        tools = {}

        try:
            from spaces.desktop.tools.adapted_desktop_tools import (
                execute_desktop_task,
                click_element,
                type_text,
                press_key,
                take_screenshot,
                scroll_screen,
                open_app,
                create_task_node,
                update_task_status,
                get_task_list,
                moire_scan,
                moire_find_element,
            )
            tools.update({
                "execute_desktop_task": execute_desktop_task,
                "click_element": click_element,
                "type_text": type_text,
                "press_key": press_key,
                "take_screenshot": take_screenshot,
                "scroll_screen": scroll_screen,
                "open_app": open_app,
                "create_task_node": create_task_node,
                "update_task_status": update_task_status,
                "get_task_list": get_task_list,
                "moire_scan": moire_scan,
                "moire_find_element": moire_find_element,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} desktop tools")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load desktop tools: {e}")

        return tools


# --- Singleton ---

_desktop_broadcast_agent: Optional[DesktopBroadcastAgent] = None


def get_desktop_broadcast_agent() -> DesktopBroadcastAgent:
    """Get or create DesktopBroadcastAgent singleton."""
    global _desktop_broadcast_agent
    if _desktop_broadcast_agent is None:
        _desktop_broadcast_agent = DesktopBroadcastAgent()
    return _desktop_broadcast_agent


__all__ = ["DesktopBroadcastAgent", "get_desktop_broadcast_agent"]
