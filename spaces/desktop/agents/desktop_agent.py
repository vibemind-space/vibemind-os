"""
Desktop Agent - Backend agent for Desktop Automation tools

Listens to events:tasks:desktop stream and executes:
- Desktop tools: open_app, click, type, press_key, screenshot, scroll
- Task tools: create_task_node, update_task_status, get_task_list
- Moire tools: moire_scan, moire_find_element

Migrated from: swarm/backend_agents/desktop_agent.py
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent
from swarm.event_bus import EventBus

logger = logging.getLogger(__name__)


class DesktopAgent(BaseBackendAgent):
    """
    Backend agent for Desktop Automation domain.

    Handles 19 tools: 12 desktop automation (app launching, UI interaction,
    Moire vision) + 7 messaging/web tools (Clawdbot bridge).
    """

    # Event type to tool name mapping
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
        # Messaging (Clawdbot bridge)
        "messaging.whatsapp": "send_whatsapp",
        "messaging.telegram": "send_telegram",
        "messaging.send": "send_message",
        "web.search": "web_search",
        "web.fetch": "web_fetch",
        "openclaw.status": "get_clawdbot_status",
        "openclaw.notifications": "get_notifications",
        # eyeTerm gaze/cursor control
        "desktop.eyeterm.toggle": "eyeterm_toggle",
        "desktop.eyeterm.calibrate": "eyeterm_calibrate",
    }

    # Parameter normalization: map classifier output to tool expected params
    PARAM_MAPPING = {
        # open_app expects "app_name"
        "desktop.open_app": {"name": "app_name", "application": "app_name", "app": "app_name"},
        # click_element expects "element_description"
        "desktop.click": {"description": "element_description", "target": "element_description", "element": "element_description"},
        # type_text expects "text"
        "desktop.type": {"content": "text", "string": "text", "message": "text", "input": "text"},
        # press_key expects "key"
        "desktop.press_key": {"button": "key", "taste": "key"},
        # execute_desktop_task expects "task_description"
        "desktop.task": {"description": "task_description", "task": "task_description", "action": "task_description"},
        # create_task_node expects "title"
        "desktop.task.create": {"name": "title", "task_name": "title"},
        # update_task_status expects "task_name" and "status"
        "desktop.task.update": {"name": "task_name", "title": "task_name"},
        # moire_find_element expects "element_description"
        "desktop.moire.find": {"description": "element_description", "target": "element_description", "element": "element_description"},
        # messaging: send_whatsapp/send_telegram expect "recipient" + "message"
        "messaging.whatsapp": {"name": "recipient", "contact": "recipient", "text": "message", "content": "message"},
        "messaging.telegram": {"name": "recipient", "contact": "recipient", "text": "message", "content": "message"},
        "messaging.send": {"name": "recipient", "contact": "recipient", "text": "message", "content": "message"},
        # web.search expects "query"
        "web.search": {"text": "query", "search": "query", "term": "query"},
        # web.fetch expects "url"
        "web.fetch": {"link": "url", "address": "url", "page": "url"},
    }

    @property
    def stream(self) -> str:
        return EventBus.STREAM_TASKS_DESKTOP

    @property
    def name(self) -> str:
        return "DesktopAgent"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load desktop automation and messaging tools."""
        tools = {}

        try:
            from spaces.desktop.adapted import (
                execute_desktop_task, click_element, type_text, press_key,
                take_screenshot, scroll_screen, open_app,
                create_task_node, update_task_status, get_task_list,
                moire_scan, moire_find_element
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

        # Messaging tools (Clawdbot bridge)
        try:
            from spaces.desktop.adapted.messaging_tools import (
                send_whatsapp, send_telegram, send_message,
                web_search, web_fetch,
                get_clawdbot_status, get_notifications,
            )
            tools.update({
                "send_whatsapp": send_whatsapp,
                "send_telegram": send_telegram,
                "send_message": send_message,
                "web_search": web_search,
                "web_fetch": web_fetch,
                "get_clawdbot_status": get_clawdbot_status,
                "get_notifications": get_notifications,
            })
            logger.info(f"{self.name}: Loaded 7 messaging tools (Clawdbot)")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load messaging tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton instance
_desktop_agent: Optional[DesktopAgent] = None


def get_desktop_agent() -> DesktopAgent:
    """Get or create DesktopAgent singleton."""
    global _desktop_agent
    if _desktop_agent is None:
        _desktop_agent = DesktopAgent()
    return _desktop_agent


__all__ = ["DesktopAgent", "get_desktop_agent"]
