"""
ScannerAgent - Executes Network Security Checks
=================================================
Receives ScanTask messages, calls the appropriate tool function,
returns ScanResult. No LLM needed — pure network I/O.
"""

import json

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import ScanTask, ScanResult
from tools import scan_port, check_grpc_auth, check_tls, check_docker_bind


TOOL_DISPATCH = {
    "scan_port": scan_port,
    "check_grpc_auth": check_grpc_auth,
    "check_tls": check_tls,
    "check_docker_bind": check_docker_bind,
}


class ScannerAgent(RoutedAgent):

    def __init__(self):
        super().__init__("ScannerAgent")

    @message_handler
    async def handle_scan_task(
        self, message: ScanTask, ctx: MessageContext
    ) -> ScanResult:
        print(f"    [SCANNER] Task {message.task_id}: {message.tool_name}", flush=True)

        tool_fn = TOOL_DISPATCH.get(message.tool_name)
        if not tool_fn:
            return ScanResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": f"Unknown tool: {message.tool_name}"}),
            )

        try:
            args = json.loads(message.arguments_json)
            result_dict = await tool_fn(**args)

            return ScanResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=True,
                result_json=json.dumps(result_dict),
            )

        except Exception as e:
            print(f"    [SCANNER] Task {message.task_id} error: {e}", flush=True)
            return ScanResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": str(e)}),
            )
