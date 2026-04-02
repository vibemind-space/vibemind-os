"""
VibeMind Desktop Space Tools

Desktop automation, task management, quick actions, and Moire vision tools.
Migrated from: tools/desktop_tools.py, tools/quickaction_tools.py,
               tools/task_tools.py, tools/moire_tools.py
"""

from .desktop_tools import (
    execute_desktop_task,
    click_element,
    type_text,
    press_key,
    take_screenshot,
    scroll_screen,
    handle_desktop_tool_call,
    cleanup_desktop_tools,
    register_desktop_tools,
    DESKTOP_TOOLS,
)

from .quickaction_tools import (
    open_app,
    use_app,
    APP_SHORTCUTS,
    QUICKACTION_TOOLS,
    register_quickaction_tools,
)

from .task_tools import (
    create_task_node,
    update_task_status,
    get_task_list,
    mark_task_complete,
    watch_task_progress,
    set_electron_sender,
    TASK_TOOLS,
    register_task_tools,
    TaskStatus,
    DesktopTask,
)

from .moire_tools import (
    moire_scan,
    moire_find_element,
    moire_get_ui_context,
    MoireServerClient,
    get_moire_client,
    MOIRE_TOOLS,
    register_moire_tools,
)

__all__ = [
    # Desktop tools
    "execute_desktop_task",
    "click_element",
    "type_text",
    "press_key",
    "take_screenshot",
    "scroll_screen",
    "handle_desktop_tool_call",
    "cleanup_desktop_tools",
    "register_desktop_tools",
    "DESKTOP_TOOLS",
    # Quick action tools
    "open_app",
    "use_app",
    "APP_SHORTCUTS",
    "QUICKACTION_TOOLS",
    "register_quickaction_tools",
    # Task tools
    "create_task_node",
    "update_task_status",
    "get_task_list",
    "mark_task_complete",
    "watch_task_progress",
    "set_electron_sender",
    "TASK_TOOLS",
    "register_task_tools",
    "TaskStatus",
    "DesktopTask",
    # Moire tools
    "moire_scan",
    "moire_find_element",
    "moire_get_ui_context",
    "MoireServerClient",
    "get_moire_client",
    "MOIRE_TOOLS",
    "register_moire_tools",
]
