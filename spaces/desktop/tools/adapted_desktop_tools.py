"""
Adapted Desktop Tools - BACKWARD COMPATIBILITY STUB

Real implementation migrated to: spaces/desktop/adapted/desktop_tools.py
This file re-exports for backward compatibility.
"""

import logging

logger = logging.getLogger(__name__)

from spaces.desktop.adapted.desktop_tools import (
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
    DESKTOP_TOOLS,
)

__all__ = [
    "execute_desktop_task",
    "click_element",
    "type_text",
    "press_key",
    "take_screenshot",
    "scroll_screen",
    "open_app",
    "create_task_node",
    "update_task_status",
    "get_task_list",
    "moire_scan",
    "moire_find_element",
    "DESKTOP_TOOLS",
]
