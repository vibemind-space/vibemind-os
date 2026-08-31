"""
Shared Message Types for Site Verifier
=======================================
All agents import these types for inter-agent communication.
"""

from dataclasses import dataclass


@dataclass
class VerifyTarget:
    """Initial verification request."""
    url: str
    domain: str
    check_types: str  # "whois,ssl,dns,http,wayback,content,ip"


@dataclass
class CheckTask:
    """Individual check task sent to CheckerAgent."""
    tool_name: str
    arguments_json: str
    task_id: str


@dataclass
class CheckResult:
    """Result from a single check task."""
    task_id: str
    tool_name: str
    success: bool
    result_json: str


@dataclass
class AnalysisRequest:
    """Request for AnalyzerAgent to evaluate all findings."""
    url: str
    domain: str
    all_results_json: str


@dataclass
class AuthenticityAnalysis:
    """AnalyzerAgent's chain-of-thought assessment."""
    reasoning: str
    verdict: str          # AUTHENTIC / SUSPICIOUS / FAKE / INCONCLUSIVE
    confidence: str       # HIGH / MEDIUM / LOW
    findings_json: str    # JSON array of structured findings


@dataclass
class ReportRequest:
    """Request for ReporterAgent to format the final report."""
    url: str
    domain: str
    check_results_json: str
    analysis_reasoning: str
    analysis_verdict: str
    analysis_confidence: str
    analysis_findings_json: str


@dataclass
class AuthenticityReport:
    """Final formatted authenticity report."""
    report_text: str
    url: str
    domain: str
    verdict: str
    confidence: str
    finding_count: int
    red_flag_count: int
