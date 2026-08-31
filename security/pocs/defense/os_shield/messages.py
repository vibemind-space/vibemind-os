"""
Shared Message Types for OS Shield
====================================
All agents import these types for inter-agent communication.
"""

from dataclasses import dataclass


@dataclass
class ShieldRequest:
    """Initial request to scan the local OS."""
    scan_domains: str   # comma-separated: "process,file,network,usb,binary,registry"
    mode: str           # "oneshot" or "continuous"
    baseline_json: str  # JSON string of baseline state (or empty)


@dataclass
class MonitorTask:
    """Single monitoring task sent to MonitorAgent."""
    tool_name: str
    arguments_json: str
    task_id: str


@dataclass
class MonitorResult:
    """Result from a single monitoring tool."""
    task_id: str
    tool_name: str
    success: bool
    result_json: str


@dataclass
class ThreatAnalysisRequest:
    """All findings sent to ThreatAnalyzerAgent."""
    all_results_json: str
    context: str  # "oneshot" or "continuous_cycle_N"


@dataclass
class ThreatAnalysis:
    """ThreatAnalyzerAgent's chain-of-thought assessment."""
    reasoning: str
    severity: str                   # CRITICAL / HIGH / MEDIUM / LOW / INFO
    findings_json: str              # JSON array of structured findings
    recommended_actions_json: str   # JSON array of enforcer actions


@dataclass
class EnforceRequest:
    """Request for EnforcerAgent to take action."""
    action_type: str            # kill_process, add_firewall_rule, quarantine_file, disable_autorun
    parameters_json: str
    severity: str
    requires_confirmation: bool


@dataclass
class EnforceResult:
    """Result of enforcement action."""
    action_type: str
    success: bool
    details: str


@dataclass
class ReportRequest:
    """Request for ReporterAgent to format the final report."""
    scan_results_json: str
    analysis_reasoning: str
    analysis_severity: str
    analysis_findings_json: str
    enforcement_results_json: str


@dataclass
class SecurityReport:
    """Final formatted security report."""
    report_text: str
    overall_severity: str
    finding_count: int
    actions_taken: int
