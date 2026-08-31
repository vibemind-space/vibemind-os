"""
OrchestratorAgent - Site Verification via OpenAI Function Calling
==================================================================
Receives a VerifyTarget, uses GPT-4o with tools to decide which checks
to run. Dispatches CheckTasks to CheckerAgent, collects results, then
forwards to AnalyzerAgent and ReporterAgent for final verdict.
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
    VerifyTarget, CheckTask, CheckResult,
    AnalysisRequest, AuthenticityAnalysis,
    ReportRequest, AuthenticityReport,
)
from tools import TOOL_DEFINITIONS, think


class OrchestratorAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("OrchestratorAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_verify_target(
        self, message: VerifyTarget, ctx: MessageContext
    ) -> AuthenticityReport:
        print(f"\n  [ORCHESTRATOR] Verifying: {message.url}", flush=True)
        print(f"  [ORCHESTRATOR] Domain: {message.domain}", flush=True)
        print(f"  [ORCHESTRATOR] Checks: {message.check_types}", flush=True)

        system_prompt = (
            "You are a website authenticity verification orchestrator.\n\n"
            "Your mission: Determine whether a website is AUTHENTIC, SUSPICIOUS, or FAKE.\n\n"
            "You have OSINT tools to check:\n"
            "- WHOIS data (domain age, registrant, registrar)\n"
            "- SSL/TLS certificates (issuer, validity, CN match)\n"
            "- DNS records (A, MX, TXT/SPF/DMARC)\n"
            "- HTTP headers (security headers, server, redirects)\n"
            "- Wayback Machine archives (site history)\n"
            "- Page content (impressum, privacy policy, suspicious patterns)\n"
            "- Reverse IP lookup (hosting provider)\n\n"
            "Strategy:\n"
            "1. Start with whois_lookup and check_ssl_cert for quick signals\n"
            "2. Then dns_records and http_headers for deeper inspection\n"
            "3. Use wayback_check to verify site history\n"
            "4. Use page_content_scan to check for legal pages and red flags\n"
            "5. Use reverse_ip_lookup if hosting seems suspicious\n"
            "6. Use 'think' to reason about all findings and form a verdict\n\n"
            "Be thorough. When done, respond with a text summary (no tool call).\n"
        )

        user_prompt = (
            f"Verify this website for authenticity:\n"
            f"URL: {message.url}\n"
            f"Domain: {message.domain}\n"
            f"Requested checks: {message.check_types}\n\n"
            f"Start the verification process."
        )

        messages_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        all_check_results = []
        max_iterations = 20

        for iteration in range(max_iterations):
            print(f"\n  [ORCHESTRATOR] OpenAI call #{iteration + 1}...", flush=True)

            response = await self._llm_client.chat.completions.create(
                model=get_model("default", "poc_site_verifier"),
                temperature=0,
                messages=messages_history,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # If model is done (no tool calls), break
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                print(
                    f"  [ORCHESTRATOR] Model finished. "
                    f"{len(all_check_results)} check results collected.",
                    flush=True,
                )
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

                print(
                    f"  [ORCHESTRATOR] Tool call: {fn_name}({json.dumps(fn_args, ensure_ascii=False)})",
                    flush=True,
                )

                if fn_name == "think":
                    # Execute think tool locally (needs LLM client)
                    think_result = await think(
                        fn_args["reasoning_prompt"], self._llm_client
                    )
                    tool_output = json.dumps(think_result)
                    print(
                        f"  [ORCHESTRATOR] Think verdict: {think_result['verdict']}",
                        flush=True,
                    )
                else:
                    # Dispatch to CheckerAgent
                    check_task = CheckTask(
                        tool_name=fn_name,
                        arguments_json=json.dumps(fn_args),
                        task_id=task_id,
                    )

                    try:
                        check_result: CheckResult = await self.send_message(
                            check_task,
                            recipient=AgentId("checker_agent", "default"),
                        )
                        result_data = json.loads(check_result.result_json)
                        all_check_results.append({
                            "task_id": check_result.task_id,
                            "tool_name": check_result.tool_name,
                            "success": check_result.success,
                            "result": result_data,
                        })
                        tool_output = check_result.result_json

                        # Log key findings
                        warning = result_data.get("warning")
                        if warning:
                            print(f"  [ORCHESTRATOR]   WARNING: {warning[:80]}", flush=True)
                        else:
                            print(f"  [ORCHESTRATOR]   OK", flush=True)

                    except Exception as e:
                        tool_output = json.dumps({"error": str(e)})
                        print(f"  [ORCHESTRATOR] Check error: {e}", flush=True)

                # Feed result back to OpenAI
                messages_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output,
                })

        # ---- Phase 2: Analyzer ----
        print(
            f"\n  [ORCHESTRATOR] Sending {len(all_check_results)} results to analyzer...",
            flush=True,
        )

        analysis: AuthenticityAnalysis = await self.send_message(
            AnalysisRequest(
                url=message.url,
                domain=message.domain,
                all_results_json=json.dumps(all_check_results, indent=2, default=str),
            ),
            recipient=AgentId("analyzer_agent", "default"),
        )
        print(
            f"  [ORCHESTRATOR] Analysis complete. "
            f"Verdict: {analysis.verdict} (Confidence: {analysis.confidence})",
            flush=True,
        )

        # ---- Phase 3: Reporter ----
        print(f"  [ORCHESTRATOR] Generating report...", flush=True)

        report: AuthenticityReport = await self.send_message(
            ReportRequest(
                url=message.url,
                domain=message.domain,
                check_results_json=json.dumps(all_check_results, indent=2, default=str),
                analysis_reasoning=analysis.reasoning,
                analysis_verdict=analysis.verdict,
                analysis_confidence=analysis.confidence,
                analysis_findings_json=analysis.findings_json,
            ),
            recipient=AgentId("reporter_agent", "default"),
        )
        print(
            f"  [ORCHESTRATOR] Report ready. "
            f"{report.finding_count} findings, {report.red_flag_count} red flags.",
            flush=True,
        )

        return report
