"""
Shared Message Types for Code Generation PoC
==============================================
Both legitimate and malicious workers import these types.
"""

from dataclasses import dataclass


@dataclass
class CodeRequest:
    """Natural language request for code generation."""
    task: str


@dataclass
class GeneratedCode:
    """LLM-generated Python code."""
    code: str


@dataclass
class ApprovedCode:
    """Reviewer-approved code, safe to execute."""
    code: str


@dataclass
class CodeResult:
    """Result from code execution."""
    output: str
    success: bool


@dataclass
class TeamEvent:
    """Published to team_events topic for audit/monitoring."""
    event_type: str
    source_agent: str
    details: str
