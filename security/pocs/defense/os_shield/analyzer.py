"""
ThreatAnalyzerAgent - Threat Assessment via Chain-of-Thought
==============================================================
Receives all monitoring results, uses GPT-4o to reason about threats,
produce a structured verdict, and recommend enforcement actions.
"""

import json
import os
import sys

from openai import AsyncOpenAI

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import ThreatAnalysisRequest, ThreatAnalysis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model


class ThreatAnalyzerAgent(RoutedAgent):

    def __init__(self, llm_client: AsyncOpenAI):
        super().__init__("ThreatAnalyzerAgent")
        self._llm_client = llm_client

    @message_handler
    async def handle_analysis(
        self, message: ThreatAnalysisRequest, ctx: MessageContext
    ) -> ThreatAnalysis:
        print(f"  [ANALYZER] Analyzing threat findings ({message.context})...", flush=True)

        response = await self._llm_client.chat.completions.create(
            model=get_model("analyzer"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior Windows security analyst performing threat assessment.\n\n"
                        "Analyze ALL monitoring results and provide:\n\n"
                        "1. REASONING: Step-by-step analysis covering:\n"
                        "   - Process anomalies (unsigned binaries, suspicious names, new spawns)\n"
                        "   - Network threats (unknown IPs, suspicious ports, C2 indicators)\n"
                        "   - Persistence mechanisms (new autorun entries, registry changes)\n"
                        "   - File integrity (system file changes, new files in system dirs)\n"
                        "   - USB device risks (unauthorized devices)\n"
                        "   - Cross-correlation: do findings indicate a coordinated attack?\n\n"
                        "2. FINDINGS: A JSON array of findings, each with:\n"
                        '   {"category": str, "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",\n'
                        '    "title": str, "description": str, "indicator": str}\n\n'
                        "3. RECOMMENDED_ACTIONS: A JSON array of enforcement actions:\n"
                        '   {"action_type": "kill_process|add_firewall_rule|quarantine_file|disable_autorun",\n'
                        '    "parameters": {...}, "severity": str, "reason": str}\n'
                        "   Only recommend actions for HIGH or CRITICAL findings.\n"
                        "   Be conservative — do not recommend killing system processes.\n\n"
                        "   VM ENFORCEMENT (for VM-specific threats):\n"
                        "   - vm_kill_process (params: {pid})\n"
                        "   - vm_remove_backdoor (params: {service_name?})\n"
                        "   - vm_restart_service (params: {service_name})\n"
                        "   - vm_block_ip (params: {ip})\n"
                        "   - vm_rotate_vault_tokens (no params)\n"
                        "   - vm_restore_logs (no params)\n\n"
                        "4. OVERALL_SEVERITY: CRITICAL | HIGH | MEDIUM | LOW | INFO\n\n"
                        "Format exactly as:\n"
                        "REASONING:\n<analysis>\n\n"
                        "FINDINGS:\n```json\n[...]\n```\n\n"
                        "RECOMMENDED_ACTIONS:\n```json\n[...]\n```\n\n"
                        "OVERALL_SEVERITY: <level>\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Context: {message.context}\n\n"
                        f"Monitoring Results:\n{message.all_results_json}\n\n"
                        f"Analyze these findings and recommend actions."
                    ),
                },
            ],
        )

        text = response.choices[0].message.content.strip()
        print(f"  [ANALYZER] Got analysis ({len(text)} chars)", flush=True)

        # Parse structured response
        reasoning = text
        findings_json = "[]"
        actions_json = "[]"
        severity = "INFO"

        if "REASONING:" in text:
            parts = text.split("FINDINGS:")
            reasoning = parts[0].replace("REASONING:", "").strip()

            if len(parts) > 1:
                remainder = parts[1]

                # Extract findings JSON
                findings_json = _extract_json_block(remainder)

                # Extract actions JSON
                if "RECOMMENDED_ACTIONS:" in remainder:
                    actions_part = remainder.split("RECOMMENDED_ACTIONS:")[1]
                    actions_json = _extract_json_block(actions_part)

                # Extract severity
                if "OVERALL_SEVERITY:" in remainder:
                    sev_line = remainder.split("OVERALL_SEVERITY:")[1].strip()
                    severity = sev_line.split()[0] if sev_line else "INFO"

        # Validate JSON
        findings_json = _validate_json_array(findings_json)
        actions_json = _validate_json_array(actions_json)

        return ThreatAnalysis(
            reasoning=reasoning,
            severity=severity,
            findings_json=findings_json,
            recommended_actions_json=actions_json,
        )


def _extract_json_block(text: str) -> str:
    """Extract JSON from a markdown code block."""
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()
    return "[]"


def _validate_json_array(json_str: str) -> str:
    """Ensure valid JSON array, return '[]' if invalid."""
    try:
        json.loads(json_str)
        return json_str
    except (json.JSONDecodeError, TypeError):
        return "[]"
