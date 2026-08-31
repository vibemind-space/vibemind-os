"""
AnalyzerAgent - Authenticity Verdict via Chain-of-Thought
==========================================================
Receives all check results, uses GPT-4o to reason about authenticity
and produce a structured verdict with confidence level.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

from openai import AsyncOpenAI

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import AnalysisRequest, AuthenticityAnalysis


class AnalyzerAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("AnalyzerAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_analysis(
        self, message: AnalysisRequest, ctx: MessageContext
    ) -> AuthenticityAnalysis:
        print(f"  [ANALYZER] Analyzing findings for {message.domain}...", flush=True)

        response = await self._llm_client.chat.completions.create(
            model=get_model("default", "poc_site_verifier"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior OSINT analyst performing a website authenticity assessment.\n\n"
                        "Analyze ALL check results and provide:\n\n"
                        "1. REASONING: Step-by-step analysis covering:\n"
                        "   - Domain legitimacy (age, registrant, registrar)\n"
                        "   - Certificate validity (issuer, CN match, expiry)\n"
                        "   - DNS configuration (SPF, DMARC, mail infrastructure)\n"
                        "   - HTTP security posture (headers, redirects)\n"
                        "   - Historical presence (Wayback Machine archives)\n"
                        "   - Content legitimacy (legal pages, suspicious patterns)\n"
                        "   - Hosting analysis (provider, location)\n"
                        "   - Cross-referencing: Do findings corroborate each other?\n\n"
                        "2. FINDINGS: A JSON array of findings, each with:\n"
                        '   {"category": str, "indicator": "authentic|suspicious|red_flag",\n'
                        '    "title": str, "description": str}\n\n'
                        "3. VERDICT: AUTHENTIC | SUSPICIOUS | FAKE | INCONCLUSIVE\n\n"
                        "4. CONFIDENCE: HIGH | MEDIUM | LOW\n\n"
                        "Format exactly as:\n"
                        "REASONING:\n<analysis>\n\n"
                        "FINDINGS:\n```json\n[...]\n```\n\n"
                        "VERDICT: <verdict>\n"
                        "CONFIDENCE: <level>\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Target URL: {message.url}\n"
                        f"Domain: {message.domain}\n\n"
                        f"Check Results:\n{message.all_results_json}\n\n"
                        f"Analyze these findings and determine authenticity."
                    ),
                },
            ],
        )

        text = response.choices[0].message.content.strip()
        print(f"  [ANALYZER] Got analysis ({len(text)} chars)", flush=True)

        # Parse structured response
        reasoning = text
        findings_json = "[]"
        verdict = "INCONCLUSIVE"
        confidence = "LOW"

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

                if "VERDICT:" in findings_part:
                    verdict_line = findings_part.split("VERDICT:")[1].strip()
                    verdict = verdict_line.split()[0] if verdict_line else "INCONCLUSIVE"

                if "CONFIDENCE:" in findings_part:
                    conf_line = findings_part.split("CONFIDENCE:")[1].strip()
                    confidence = conf_line.split()[0] if conf_line else "LOW"

        # Validate findings JSON
        try:
            json.loads(findings_json)
        except json.JSONDecodeError:
            findings_json = json.dumps([{
                "category": "General",
                "indicator": "suspicious",
                "title": "Analysis Complete",
                "description": reasoning[:500],
            }])

        return AuthenticityAnalysis(
            reasoning=reasoning,
            verdict=verdict,
            confidence=confidence,
            findings_json=findings_json,
        )
