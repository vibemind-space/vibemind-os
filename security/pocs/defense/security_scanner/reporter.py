"""
ReporterAgent - Formats Final Security Report
===============================================
Compiles scan results + analysis into a formatted text report.
No LLM needed — pure formatting.
"""

import json
from datetime import datetime

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import ReportRequest, SecurityReport


class ReporterAgent(RoutedAgent):

    def __init__(self):
        super().__init__("ReporterAgent")

    @message_handler
    async def handle_report(
        self, message: ReportRequest, ctx: MessageContext
    ) -> SecurityReport:
        print(f"  [REPORTER] Generating report for {message.target_host}...", flush=True)

        try:
            findings = json.loads(message.analysis_findings_json)
        except json.JSONDecodeError:
            findings = []

        try:
            scan_results = json.loads(message.scan_results_json)
        except json.JSONDecodeError:
            scan_results = []

        lines = []
        lines.append("")
        lines.append("=" * 70)
        lines.append("  SECURITY SCAN REPORT")
        lines.append("=" * 70)
        lines.append(f"  Target:     {message.target_host}")
        lines.append(f"  Date:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Severity:   {message.analysis_severity}")
        lines.append(f"  Findings:   {len(findings)}")
        lines.append("=" * 70)

        # Executive Summary
        lines.append("")
        lines.append("  EXECUTIVE SUMMARY")
        lines.append("  " + "-" * 50)

        severity_marker = {
            "CRITICAL": "[!!!]",
            "HIGH": "[!! ]",
            "MEDIUM": "[ ! ]",
            "LOW": "[ . ]",
            "INFO": "[ i ]",
        }

        for finding in findings:
            sev = finding.get("severity", "INFO")
            marker = severity_marker.get(sev, "[ ? ]")
            lines.append(f"  {marker} [{sev}] {finding.get('title', 'Untitled')}")

        # Detailed Findings
        lines.append("")
        lines.append("  DETAILED FINDINGS")
        lines.append("  " + "-" * 50)

        for i, finding in enumerate(findings, 1):
            lines.append(f"")
            lines.append(f"  Finding #{i}: {finding.get('title', 'Untitled')}")
            lines.append(f"  Severity:      {finding.get('severity', 'INFO')}")
            lines.append(f"  Description:   {finding.get('description', 'N/A')}")
            lines.append(f"  Remediation:   {finding.get('remediation', 'N/A')}")

        # Raw Scan Results
        lines.append("")
        lines.append("  RAW SCAN RESULTS")
        lines.append("  " + "-" * 50)

        for result in scan_results:
            status = "OK" if result.get("success") else "FAIL"
            lines.append(f"  [{result.get('tool_name', '?')}] "
                         f"Task {result.get('task_id', '?')}: {status}")
            result_data = result.get("result", {})
            if isinstance(result_data, dict):
                # Show key info
                state = result_data.get("state")
                if state:
                    port = result_data.get("port", "?")
                    service = result_data.get("service_hint", "?")
                    lines.append(f"    Port {port} ({service}): {state}")
                vuln = result_data.get("vulnerability")
                if vuln:
                    lines.append(f"    VULN: {vuln}")

        # Analysis Reasoning
        lines.append("")
        lines.append("  ANALYSIS REASONING (GPT-4o Chain-of-Thought)")
        lines.append("  " + "-" * 50)
        for line in message.analysis_reasoning.split("\n"):
            lines.append(f"  {line}")

        lines.append("")
        lines.append("=" * 70)
        lines.append("  END OF REPORT")
        lines.append("=" * 70)
        lines.append("")

        report_text = "\n".join(lines)
        print(f"  [REPORTER] Report: {len(lines)} lines, {len(findings)} findings", flush=True)

        return SecurityReport(
            report_text=report_text,
            target_host=message.target_host,
            overall_severity=message.analysis_severity,
            finding_count=len(findings),
        )
