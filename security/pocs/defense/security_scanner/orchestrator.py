"""
OrchestratorAgent - Scan Planning via OpenAI Function Calling
==============================================================
Receives a ScanTarget, uses GPT-4o with tools parameter to decide
which scans to run. Dispatches ScanTasks to ScannerAgent, collects
results, then forwards to AnalyzerAgent and ReporterAgent.
"""

import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

from openai import AsyncOpenAI

from autogen_core import (
    AgentId,
    RoutedAgent,
    message_handler,
    MessageContext,
)

from messages import (
    ScanTarget, ScanTask, ScanResult,
    AnalysisRequest, SecurityAnalysis,
    ReportRequest, SecurityReport,
)
from tools import TOOL_DEFINITIONS, think


class OrchestratorAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("OrchestratorAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_scan_target(
        self, message: ScanTarget, ctx: MessageContext
    ) -> SecurityReport:
        print(f"\n  [ORCHESTRATOR] Scan target: {message.host}", flush=True)
        print(f"  [ORCHESTRATOR] Port range: {message.port_range}", flush=True)
        print(f"  [ORCHESTRATOR] Scan types: {message.scan_types}", flush=True)

        system_prompt = (
            "You are a security scanning orchestrator. You have tools to scan "
            "network targets for security vulnerabilities.\n\n"
            "Your job:\n"
            "1. Use the available tools to thoroughly scan the target\n"
            "2. Check for open ports, missing TLS, unauthenticated gRPC, exposed Docker APIs\n"
            "3. Use the 'think' tool to reason about findings after collecting scan data\n"
            "4. When done, respond with text (no tool call) summarizing findings\n\n"
            "Available scan types: " + message.scan_types + "\n"
            "Be thorough but efficient. Scan each requested port individually."
        )

        user_prompt = (
            f"Scan target: {message.host}\n"
            f"Ports to check: {message.port_range}\n"
            f"Requested scans: {message.scan_types}\n\n"
            f"Start scanning this target for security vulnerabilities."
        )

        messages_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        all_scan_results = []
        max_iterations = 15

        for iteration in range(max_iterations):
            print(f"\n  [ORCHESTRATOR] OpenAI call #{iteration + 1}...", flush=True)

            response = await self._llm_client.chat.completions.create(
                model=get_model("default", "poc_security_scanner"),
                temperature=0,
                messages=messages_history,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # If model is done (no tool calls), break
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                print(f"  [ORCHESTRATOR] Model finished. {len(all_scan_results)} scan results collected.", flush=True)
                messages_history.append({
                    "role": "assistant",
                    "content": choice.message.content or "",
                })
                break

            # Add assistant message with tool_calls to history
            messages_history.append(choice.message.model_dump())

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                task_id = str(uuid.uuid4())[:8]

                print(f"  [ORCHESTRATOR] Tool call: {fn_name}({json.dumps(fn_args)})", flush=True)

                if fn_name == "think":
                    # Execute think tool locally
                    think_result = await think(
                        fn_args["reasoning_prompt"], self._llm_client
                    )
                    tool_output = json.dumps(think_result)
                    print(f"  [ORCHESTRATOR] Think: severity={think_result['severity_assessment']}", flush=True)

                else:
                    # Dispatch to ScannerAgent
                    scan_task = ScanTask(
                        tool_name=fn_name,
                        arguments_json=json.dumps(fn_args),
                        task_id=task_id,
                    )

                    try:
                        scan_result: ScanResult = await self.send_message(
                            scan_task,
                            recipient=AgentId("scanner_agent", "default"),
                        )
                        result_data = json.loads(scan_result.result_json)
                        all_scan_results.append({
                            "task_id": scan_result.task_id,
                            "tool_name": scan_result.tool_name,
                            "success": scan_result.success,
                            "result": result_data,
                        })
                        tool_output = scan_result.result_json
                        print(f"  [ORCHESTRATOR] Result: {fn_name} -> {result_data.get('state', result_data.get('vulnerability', 'ok')[:60] if result_data.get('vulnerability') else 'ok')}", flush=True)
                    except Exception as e:
                        tool_output = json.dumps({"error": str(e)})
                        print(f"  [ORCHESTRATOR] Scan error: {e}", flush=True)

                # Feed result back to OpenAI
                messages_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output,
                })

        # Phase 2: Send to AnalyzerAgent
        print(f"\n  [ORCHESTRATOR] Sending {len(all_scan_results)} results to analyzer...", flush=True)

        analysis: SecurityAnalysis = await self.send_message(
            AnalysisRequest(
                target_host=message.host,
                all_results_json=json.dumps(all_scan_results, indent=2),
            ),
            recipient=AgentId("analyzer_agent", "default"),
        )
        print(f"  [ORCHESTRATOR] Analysis complete. Severity: {analysis.severity}", flush=True)

        # Phase 3: Send to ReporterAgent
        print(f"  [ORCHESTRATOR] Sending to reporter...", flush=True)

        report: SecurityReport = await self.send_message(
            ReportRequest(
                target_host=message.host,
                scan_results_json=json.dumps(all_scan_results, indent=2),
                analysis_reasoning=analysis.reasoning,
                analysis_severity=analysis.severity,
                analysis_findings_json=analysis.findings_json,
            ),
            recipient=AgentId("reporter_agent", "default"),
        )
        print(f"  [ORCHESTRATOR] Report ready. {report.finding_count} findings.", flush=True)

        return report
