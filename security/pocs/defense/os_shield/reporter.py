"""
ReporterAgent - Formats Final Security Report
================================================
Takes analysis results and enforcement outcomes,
produces a human-readable console report.
"""

import json
from datetime import datetime

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import ReportRequest, SecurityReport


SEVERITY_MARKERS = {
    "CRITICAL": "[!!!]",
    "HIGH": "[!! ]",
    "MEDIUM": "[ ! ]",
    "LOW": "[ . ]",
    "INFO": "[ i ]",
}


class ReporterAgent(RoutedAgent):

    def __init__(self):
        super().__init__("ReporterAgent")

    @message_handler
    async def handle_report(
        self, message: ReportRequest, ctx: MessageContext
    ) -> SecurityReport:
        print(f"  [REPORTER] Generating report...", flush=True)

        lines = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Header
        lines.append("")
        lines.append("=" * 60)
        lines.append("  OS SHIELD - SECURITY REPORT")
        lines.append("=" * 60)
        lines.append(f"  Target:    localhost (Windows 11)")
        lines.append(f"  Date:      {now}")
        lines.append(f"  Severity:  {message.analysis_severity}")
        lines.append("=" * 60)

        # Findings
        findings = []
        try:
            findings = json.loads(message.analysis_findings_json)
        except (json.JSONDecodeError, TypeError):
            pass

        finding_count = len(findings)

        lines.append("")
        lines.append(f"  FINDINGS ({finding_count})")
        lines.append(f"  {'-' * 54}")

        for f in findings:
            sev = f.get("severity", "INFO")
            marker = SEVERITY_MARKERS.get(sev, "[ ? ]")
            title = f.get("title", "Unknown")
            desc = f.get("description", "")
            lines.append(f"  {marker} {sev:<10} {title}")
            if desc:
                # Wrap description
                for i in range(0, len(desc), 50):
                    lines.append(f"               {desc[i:i+50]}")

        if not findings:
            lines.append("  No findings.")

        # Enforcement Actions
        enforcements = []
        try:
            enforcements = json.loads(message.enforcement_results_json)
        except (json.JSONDecodeError, TypeError):
            pass

        actions_taken = len([e for e in enforcements if e.get("success")])

        if enforcements:
            lines.append("")
            lines.append(f"  ENFORCEMENT ACTIONS ({len(enforcements)})")
            lines.append(f"  {'-' * 54}")

            for e in enforcements:
                status = "OK" if e.get("success") else "FAILED"
                action = e.get("action_type", "unknown")
                details = e.get("details", "")
                lines.append(f"  [{status:>6}] {action}: {details[:60]}")

        # Analysis Reasoning (condensed)
        lines.append("")
        lines.append("  ANALYSIS")
        lines.append(f"  {'-' * 54}")
        reasoning_lines = message.analysis_reasoning.split("\n")
        for rl in reasoning_lines[:20]:
            lines.append(f"  {rl.rstrip()}")
        if len(reasoning_lines) > 20:
            lines.append(f"  ... ({len(reasoning_lines) - 20} more lines)")

        # Footer
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"  Findings: {finding_count} | Actions: {actions_taken}")
        lines.append("=" * 60)
        lines.append("")

        report_text = "\n".join(lines)

        return SecurityReport(
            report_text=report_text,
            overall_severity=message.analysis_severity,
            finding_count=finding_count,
            actions_taken=actions_taken,
        )
