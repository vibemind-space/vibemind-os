"""
ReporterAgent - Formats Final Authenticity Report
===================================================
Takes analysis results and produces a human-readable report
with verdict, findings table, and recommendations.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

from openai import AsyncOpenAI

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import ReportRequest, AuthenticityReport


class ReporterAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("ReporterAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_report(
        self, message: ReportRequest, ctx: MessageContext
    ) -> AuthenticityReport:
        print(f"  [REPORTER] Generating report for {message.domain}...", flush=True)

        response = await self._llm_client.chat.completions.create(
            model=get_model("default", "poc_site_verifier"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a security report writer. Create a clear, structured "
                        "authenticity report from the analysis results.\n\n"
                        "Format the report as:\n\n"
                        "========================================\n"
                        "WEBSITE AUTHENTICITY REPORT\n"
                        "========================================\n"
                        "Target: <url>\n"
                        "Domain: <domain>\n"
                        "Date: <current date>\n\n"
                        "VERDICT: <verdict> (Confidence: <level>)\n\n"
                        "SUMMARY:\n<2-3 sentence summary>\n\n"
                        "FINDINGS:\n"
                        "<table-style list of each finding with indicator emoji>\n"
                        "  ✅ = authentic indicator\n"
                        "  ⚠️ = suspicious indicator\n"
                        "  🚩 = red flag\n\n"
                        "DETAILS:\n<expanded reasoning>\n\n"
                        "RECOMMENDATIONS:\n<actionable next steps>\n\n"
                        "========================================\n\n"
                        "Use German where the domain is .de, otherwise English."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"URL: {message.url}\n"
                        f"Domain: {message.domain}\n"
                        f"Verdict: {message.analysis_verdict}\n"
                        f"Confidence: {message.analysis_confidence}\n\n"
                        f"Reasoning:\n{message.analysis_reasoning}\n\n"
                        f"Findings:\n{message.analysis_findings_json}\n\n"
                        f"Raw Check Results:\n{message.check_results_json}\n\n"
                        f"Create the final report."
                    ),
                },
            ],
        )

        report_text = response.choices[0].message.content.strip()

        # Count findings and red flags
        finding_count = 0
        red_flag_count = 0
        try:
            findings = json.loads(message.analysis_findings_json)
            finding_count = len(findings)
            red_flag_count = sum(
                1 for f in findings
                if f.get("indicator") == "red_flag"
            )
        except (json.JSONDecodeError, TypeError):
            pass

        return AuthenticityReport(
            report_text=report_text,
            url=message.url,
            domain=message.domain,
            verdict=message.analysis_verdict,
            confidence=message.analysis_confidence,
            finding_count=finding_count,
            red_flag_count=red_flag_count,
        )
