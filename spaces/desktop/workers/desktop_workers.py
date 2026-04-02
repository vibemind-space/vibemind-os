"""
Desktop Space Workers

Workers for the Desktop Space:
- ClickWorker: Click/mouse operations
- TypeWorker: Typing operations
- AppWorker: App launching and control
"""

import logging
from typing import Any

from swarm.navigation import SpaceType
from swarm.event_buffer import TaskInfo
from swarm.workers.base_worker import BaseWorker, WorkerConfig

logger = logging.getLogger(__name__)


class ClickWorker(BaseWorker):
    """
    Worker for click/mouse operations.

    Handles: click, scroll, mouse movement
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="click_worker",
            space_type=SpaceType.DESKTOP,
            description="Handles click and mouse operations",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a click task."""
        text = task.input_event.text.lower()

        try:
            from spaces.desktop.tools.adapted_desktop_tools import (
                click_element, scroll_screen, moire_find_element,
            )

            if "scroll" in text:
                direction = "down" if "down" in text or "runter" in text else "up"
                await self._publish_progress(50, f"Scrolling {direction}...")
                result = scroll_screen(direction=direction)

            elif "click" in text or "klick" in text:
                element = self._extract_element(text)
                await self._publish_progress(30, f"Finding: {element}")

                # Try to find element first
                location = moire_find_element(element_description=element)
                await self._publish_progress(70, "Clicking...")

                result = click_element(element_description=element)

            else:
                result = "Unknown click operation"

            return result

        except ImportError as e:
            return f"Click tools not available: {e}"
        except Exception as e:
            logger.error(f"ClickWorker error: {e}")
            return f"Error: {e}"

    def _extract_element(self, text: str) -> str:
        """Extract element description from text."""
        for marker in ["click", "klick", "on", "auf"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) > 1:
                    return parts[-1].strip()
        return text


class TypeWorker(BaseWorker):
    """
    Worker for typing operations.

    Handles: type text, press keys
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="type_worker",
            space_type=SpaceType.DESKTOP,
            description="Handles typing and keyboard operations",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute a typing task."""
        text = task.input_event.text.lower()

        try:
            from spaces.desktop.tools.adapted_desktop_tools import (
                type_text, press_key,
            )

            if any(kw in text for kw in ["press", "drück", "taste"]):
                key = self._extract_key(text)
                await self._publish_progress(50, f"Pressing {key}...")
                result = press_key(key=key)

            elif any(kw in text for kw in ["type", "tippe", "schreib", "write"]):
                content = self._extract_text_to_type(text)
                await self._publish_progress(50, f"Typing: {content[:20]}...")
                result = type_text(text=content)

            else:
                result = "Unknown typing operation"

            return result

        except ImportError as e:
            return f"Type tools not available: {e}"
        except Exception as e:
            logger.error(f"TypeWorker error: {e}")
            return f"Error: {e}"

    def _extract_key(self, text: str) -> str:
        """Extract key name from text."""
        keys = {
            "enter": "enter",
            "tab": "tab",
            "escape": "escape",
            "esc": "escape",
            "space": "space",
            "backspace": "backspace",
            "delete": "delete",
        }
        for kw, key in keys.items():
            if kw in text:
                return key
        return "enter"

    def _extract_text_to_type(self, text: str) -> str:
        """Extract text to type."""
        import re
        # Look for quoted text
        quoted = re.search(r'["\']([^"\']+)["\']', text)
        if quoted:
            return quoted.group(1)

        for marker in ["type", "tippe", "schreib", "write"]:
            if marker in text:
                return text.split(marker)[-1].strip()

        return text


class AppWorker(BaseWorker):
    """
    Worker for app launching and control.

    Handles: open apps, browser navigation, screenshots
    """

    def __init__(self, event_manager=None):
        config = WorkerConfig(
            name="app_worker",
            space_type=SpaceType.DESKTOP,
            description="Handles app launching and browser control",
        )
        super().__init__(config, event_manager)

    async def execute_task(self, task: TaskInfo) -> str:
        """Execute an app task."""
        text = task.input_event.text.lower()

        try:
            from spaces.desktop.tools.adapted_desktop_tools import (
                open_app, take_screenshot, execute_desktop_task,
            )

            if "screenshot" in text or "bildschirmfoto" in text:
                await self._publish_progress(50, "Taking screenshot...")
                result = take_screenshot()

            elif any(kw in text for kw in ["open", "öffne", "start", "starte", "launch"]):
                app_name = self._detect_app(text)
                await self._publish_progress(50, f"Opening {app_name}...")
                result = open_app(app_name=app_name)

            elif any(kw in text for kw in ["suche", "search", "google", "navigate"]):
                # Complex browser task
                await self._publish_progress(30, "Preparing browser task...")
                result = execute_desktop_task(task_description=task.input_event.text)

            else:
                # General desktop task
                await self._publish_progress(30, "Executing task...")
                result = execute_desktop_task(task_description=task.input_event.text)

            return result

        except ImportError as e:
            return f"App tools not available: {e}"
        except Exception as e:
            logger.error(f"AppWorker error: {e}")
            return f"Error: {e}"

    def _detect_app(self, text: str) -> str:
        """Detect app name from text."""
        apps = {
            "chrome": "chrome",
            "firefox": "firefox",
            "edge": "edge",
            "browser": "chrome",  # default browser
            "word": "word",
            "excel": "excel",
            "powerpoint": "powerpoint",
            "vscode": "vscode",
            "code": "vscode",
            "visual studio": "vscode",
            "notepad": "notepad",
            "editor": "notepad",
            "terminal": "terminal",
            "cmd": "terminal",
            "explorer": "explorer",
            "datei": "explorer",
        }
        for kw, app in apps.items():
            if kw in text:
                return app
        return "chrome"  # default


def create_desktop_workers(event_manager=None) -> list:
    """Create all Desktop Space workers."""
    return [
        ClickWorker(event_manager),
        TypeWorker(event_manager),
        AppWorker(event_manager),
    ]


__all__ = [
    "ClickWorker",
    "TypeWorker",
    "AppWorker",
    "create_desktop_workers",
]
