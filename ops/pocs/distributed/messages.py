"""
Shared Message Types for Distributed PoC
==========================================
Both legitimate and malicious workers import these types.
Matching type names are required for gRPC serialization.
"""

from dataclasses import dataclass


@dataclass
class UserQuery:
    """Natural language query from user."""
    text: str


@dataclass
class SqlQuery:
    """Generated SQL query to be reviewed by guard."""
    query: str


@dataclass
class ApprovedQuery:
    """Guard-approved query, safe to execute."""
    query: str


@dataclass
class QueryRejection:
    """Guard rejected the query."""
    reason: str


@dataclass
class QueryResult:
    """Result from database execution."""
    data: str


@dataclass
class TeamEvent:
    """Published to team_events topic for audit/monitoring."""
    event_type: str
    source_agent: str
    details: str
