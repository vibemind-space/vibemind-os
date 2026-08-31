"""
AttackAgent - Pure I/O Tool Executor for Red Team
=====================================================
Mirrors MonitorAgent from poc_os_shield. Receives AttackTask,
executes the corresponding attack tool, returns AttackResult.
"""

import json

from autogen_core import RoutedAgent, message_handler, MessageContext

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from attack_tools import RED_TOOL_DISPATCH
from messages import AttackTask, AttackResult

# Load VM tools if available
try:
    from vm_attack_tools import VM_TOOL_DISPATCH
except ImportError:
    VM_TOOL_DISPATCH = {}

# Load Spy Agent tools
try:
    from spy_agent import SPY_TOOL_DISPATCH
except ImportError:
    SPY_TOOL_DISPATCH = {}

# Merge all dispatchers
ALL_TOOL_DISPATCH = {**RED_TOOL_DISPATCH, **VM_TOOL_DISPATCH, **SPY_TOOL_DISPATCH}


class AttackAgent(RoutedAgent):

    def __init__(self):
        super().__init__("AttackAgent")

    @message_handler
    async def handle_attack_task(
        self, message: AttackTask, ctx: MessageContext
    ) -> AttackResult:
        tool_fn = ALL_TOOL_DISPATCH.get(message.tool_name)

        if tool_fn is None:
            return AttackResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": f"Unknown tool: {message.tool_name}"}),
                category=message.category,
            )

        try:
            args = json.loads(message.arguments_json) if message.arguments_json else {}
            result = await tool_fn(**args)

            # Remove non-serializable items from artifact
            if result.get("artifact"):
                clean_artifact = {
                    k: v for k, v in result["artifact"].items()
                    if not k.startswith("_")
                }
                result["artifact"] = clean_artifact

            return AttackResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=result.get("success", False),
                result_json=json.dumps(result, default=str),
                category=message.category,
            )

        except Exception as e:
            return AttackResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": f"{type(e).__name__}: {e}"}),
                category=message.category,
            )
