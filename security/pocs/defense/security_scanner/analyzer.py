"""
AnalyzerAgent - Deep Security Analysis via Chain-of-Thought
=============================================================
Receives all scan results, uses GPT-4o to reason about severity
and identify critical vulnerability patterns.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

from openai import AsyncOpenAI

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import AnalysisRequest, SecurityAnalysis


class AnalyzerAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("AnalyzerAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_analysis(
        self, message: AnalysisRequest, ctx: MessageContext
    ) -> SecurityAnalysis:
        print(f"  [ANALYZER] Analyzing findings for {message.target_host}...", flush=True)

        response = await self._llm_client.chat.completions.create(
            model=get_model("default", "poc_security_scanner"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior security analyst performing a thorough assessment.\n\n"
                        "Analyze the scan results and provide:\n"
                        "1. REASONING: Step-by-step analysis of what the findings mean\n"
                        "   - What attack vectors do these findings enable?\n"
                        "   - Are there compound vulnerabilities?\n"
                        "   - What is the blast radius if exploited?\n\n"
                        "2. FINDINGS: A JSON array of structured findings, each with:\n"
                        "   {\"title\": str, \"severity\": \"CRITICAL|HIGH|MEDIUM|LOW|INFO\",\n"
                        "    \"description\": str, \"remediation\": str}\n\n"
                        "3. OVERALL_SEVERITY: The worst severity found\n\n"
                        "Format exactly as:\n"
                        "REASONING:\n<analysis>\n\n"
                        "FINDINGS:\n```json\n[...]\n```\n\n"
                        "OVERALL_SEVERITY: <level>\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Target: {message.target_host}\n\n"
                        f"Scan Results:\n{message.all_results_json}\n\n"
                        f"Analyze these findings."
                    ),
                },
            ],
        )

        text = response.choices[0].message.content.strip()
        print(f"  [ANALYZER] Got analysis ({len(text)} chars)", flush=True)

        # Parse structured response
        reasoning = text
        findings_json = "[]"
        severity = "INFO"

        if "REASONING:" in text:
            parts = text.split("FINDINGS:")
            reasoning = parts[0].replace("REASONING:", "").strip()

            if len(parts) > 1:
                findings_part = parts[1]
                # Extract JSON from markdown code block
                if "```json" in findings_part:
                    json_start = findings_part.index("```json") + 7
                    json_end = findings_part.index("```", json_start)
                    findings_json = findings_part[json_start:json_end].strip()
                elif "```" in findings_part:
                    json_start = findings_part.index("```") + 3
                    json_end = findings_part.index("```", json_start)
                    findings_json = findings_part[json_start:json_end].strip()

                if "OVERALL_SEVERITY:" in findings_part:
                    severity_line = findings_part.split("OVERALL_SEVERITY:")[1].strip()
                    severity = severity_line.split()[0] if severity_line else "INFO"

        # Validate findings JSON
        try:
            json.loads(findings_json)
        except json.JSONDecodeError:
            findings_json = json.dumps([{
                "title": "Analysis Complete",
                "severity": severity,
                "description": reasoning[:500],
                "remediation": "See full analysis.",
            }])

        return SecurityAnalysis(
            reasoning=reasoning,
            severity=severity,
            findings_json=findings_json,
        )
