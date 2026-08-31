"""
MonitorAgent - Executes OS Security Checks
============================================
Receives MonitorTask messages, calls the appropriate tool function,
returns MonitorResult. No LLM needed — pure I/O.
"""

import json

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import MonitorTask, MonitorResult
from tools import TOOL_DISPATCH


class MonitorAgent(RoutedAgent):

    def __init__(self):
        super().__init__("MonitorAgent")

    @message_handler
    async def handle_monitor_task(
        self, message: MonitorTask, ctx: MessageContext
    ) -> MonitorResult:
        print(f"    [MONITOR] Task {message.task_id}: {message.tool_name}", flush=True)

        tool_fn = TOOL_DISPATCH.get(message.tool_name)
        if not tool_fn:
            return MonitorResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": f"Unknown tool: {message.tool_name}"}),
            )

        try:
            args = json.loads(message.arguments_json)
            result_dict = await tool_fn(**args)

            return MonitorResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=True,
                result_json=json.dumps(result_dict, default=str),
            )

        except Exception as e:
            print(f"    [MONITOR] Task {message.task_id} error: {e}", flush=True)
            return MonitorResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": str(e)}),
            )
