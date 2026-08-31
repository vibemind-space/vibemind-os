"""
Shared Message Types for Security Scanner
==========================================
All agents import these types. Identical copy must exist
on every worker for gRPC serialization to work.
"""

from dataclasses import dataclass


@dataclass
class ScanTarget:
    """Initial scan request."""
    host: str
    port_range: str     # e.g. "22,80,443,8080,50051"
    scan_types: str     # "ports,grpc_auth,tls,docker_bind"


@dataclass
class ScanPlan:
    """Orchestrator's plan (JSON list of tool calls)."""
    plan_json: str
    target_host: str


@dataclass
class ScanTask:
    """Individual scan task sent to ScannerAgent."""
    tool_name: str
    arguments_json: str
    task_id: str


@dataclass
class ScanResult:
    """Result from a single scan task."""
    task_id: str
    tool_name: str
    success: bool
    result_json: str


@dataclass
class AnalysisRequest:
    """Request for AnalyzerAgent to reason about findings."""
    target_host: str
    all_results_json: str


@dataclass
class SecurityAnalysis:
    """AnalyzerAgent's chain-of-thought assessment."""
    reasoning: str
    severity: str           # CRITICAL/HIGH/MEDIUM/LOW/INFO
    findings_json: str


@dataclass
class ReportRequest:
    """Request for ReporterAgent to format the final report."""
    target_host: str
    scan_results_json: str
    analysis_reasoning: str
    analysis_severity: str
    analysis_findings_json: str


@dataclass
class SecurityReport:
    """Final formatted security report."""
    report_text: str
    target_host: str
    overall_severity: str
    finding_count: int


@dataclass
class ScanEvent:
    """Published to scan_events topic for monitoring."""
    event_type: str
    source_agent: str
    details: str
