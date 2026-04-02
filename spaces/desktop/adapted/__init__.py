"""
Adapted Desktop Tools for AutoGen Swarm

Typed wrappers around the original Dict-based desktop tools.
These can be used directly as FunctionTool in AssistantAgent.
"""

from .desktop_tools import (
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
