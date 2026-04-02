"""
Tool Safety Classification for Remote Execution Mode.

Categorizes each tool by risk level to determine how it should be
executed when the backend runs in Docker (remote mode):
- SAFE: Runs in container (no desktop interaction needed)
- DELEGATED: Sent to desktop client via WebSocket, ACK required
- APPROVAL: Requires user confirmation before execution
"""

from enum import Enum
from typing import Dict


class ToolRisk(str, Enum):
    SAFE = "safe"
    DELEGATED = "delegated"
    APPROVAL = "approval"


TOOL_RISK_MAP: Dict[str, ToolRisk] = {
    # SAFE - run in container (cache, memory, API calls)
    "screen_read": ToolRisk.SAFE,
    "screen_find": ToolRisk.SAFE,
    "screen_layout": ToolRisk.SAFE,
    "recall_element": ToolRisk.SAFE,
    "memory_stats": ToolRisk.SAFE,
    "wait": ToolRisk.SAFE,
    "update_tasks": ToolRisk.SAFE,
    "search_contacts": ToolRisk.SAFE,
    "get_contact_info": ToolRisk.SAFE,
    "vision_analyze": ToolRisk.SAFE,
    "plan_task": ToolRisk.SAFE,

    # DELEGATED - send to desktop client, wait for ACK
    "action_click": ToolRisk.DELEGATED,
    "action_type": ToolRisk.DELEGATED,
    "action_press": ToolRisk.DELEGATED,
    "action_hotkey": ToolRisk.DELEGATED,
    "action_scroll": ToolRisk.DELEGATED,
    "mouse_move": ToolRisk.DELEGATED,
    "get_focus": ToolRisk.DELEGATED,
    "set_focus": ToolRisk.DELEGATED,
    "list_windows": ToolRisk.DELEGATED,
    "browser_open": ToolRisk.DELEGATED,
    "browser_search": ToolRisk.DELEGATED,
    "browser_read_page": ToolRisk.DELEGATED,
    "execute_plan": ToolRisk.DELEGATED,
    "full_task": ToolRisk.DELEGATED,

    # APPROVAL - user must confirm before execution
    "shell_exec": ToolRisk.APPROVAL,
    "send_message": ToolRisk.APPROVAL,
    "report_findings": ToolRisk.APPROVAL,
}


def get_tool_risk(tool_name: str) -> ToolRisk:
    """Get the risk level for a tool. Defaults to SAFE for unknown tools."""
    return TOOL_RISK_MAP.get(tool_name, ToolRisk.SAFE)
