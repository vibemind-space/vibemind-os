"""
Step Registry — Maps pipeline steps to their orchestration layer.

Each step is classified as:
- "swarm"      → LLM reasoning via Minibook Swarm agents
- "openclaw"   → Sandboxed execution via OpenClaw (Docker, user interaction)
- "claude_cli" → Code generation via Claude CLI (ACP)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StepConfig:
    name: str
    orchestrator: str          # "swarm", "openclaw", "claude_cli"
    needs_user_input: bool     # True = no timeout, waits for user
    needs_docker: bool         # True = Docker sandbox required
    needs_claude_cli: bool     # True = Claude CLI via ACP
    timeout: Optional[float]   # None = no timeout
    description: str


PIPELINE_STEPS = {
    "swarm_manager": StepConfig(
        name="SwarmManager",
        orchestrator="swarm",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=False,
        timeout=120.0,
        description="LLM generiert JSON-Spezifikation aus Task-Beschreibung",
    ),
    "catalog": StepConfig(
        name="CatalogAgent",
        orchestrator="openclaw",
        needs_user_input=True,
        needs_docker=True,
        needs_claude_cli=False,
        timeout=None,  # Kein Timeout — User antwortet wann er will
        description="MCP-Server Discovery + User wählt Server + gibt Secrets ein",
    ),
    "architect": StepConfig(
        name="ArchitectAgent",
        orchestrator="swarm",
        needs_user_input=True,   # Optional review
        needs_docker=False,
        needs_claude_cli=False,
        timeout=None,  # User-Review hat kein Timeout
        description="LLM designt YAML-Architektur, User reviewt optional",
    ),
    "coder": StepConfig(
        name="CoderAgent",
        orchestrator="claude_cli",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=True,
        timeout=300.0,
        description="Claude CLI generiert tools.py (besser als GPT-4o, kein Truncation)",
    ),
    "reviewer": StepConfig(
        name="ReviewerAgent",
        orchestrator="swarm",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=False,
        timeout=120.0,
        description="LLM prüft Code-YAML-Konsistenz, max 2 Revisionen",
    ),
    "tester": StepConfig(
        name="TesterAgent",
        orchestrator="swarm",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=False,
        timeout=120.0,
        description="Lokale Syntax/YAML-Tests + LLM-Analyse",
    ),
    "validator": StepConfig(
        name="ValidatorAgent",
        orchestrator="swarm",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=False,
        timeout=120.0,
        description="Output auf Disk schreiben + LLM-Summary",
    ),
    "builder": StepConfig(
        name="BuilderAgent",
        orchestrator="openclaw",
        needs_user_input=False,
        needs_docker=True,
        needs_claude_cli=False,
        timeout=None,  # Docker Build kann Minuten dauern
        description="Docker Build (sandboxed) + Gordon Auto-Fix bei Fehler",
    ),
    "executor": StepConfig(
        name="ExecutorAgent",
        orchestrator="openclaw",
        needs_user_input=False,
        needs_docker=True,
        needs_claude_cli=False,
        timeout=None,  # Docker Run kann Minuten dauern
        description="Docker Run (sandboxed) + Gordon Auto-Fix bei Runtime-Fehler",
    ),
    "output_eval": StepConfig(
        name="OutputEvalAgent",
        orchestrator="openclaw",
        needs_user_input=False,
        needs_docker=True,
        needs_claude_cli=True,
        timeout=None,  # Docker + Claude CLI
        description="Claude CLI generiert Test-Task, OpenClaw führt in Docker aus",
    ),
    "todo_implement": StepConfig(
        name="TodoImplementer",
        orchestrator="claude_cli",
        needs_user_input=False,
        needs_docker=True,
        needs_claude_cli=True,
        timeout=300.0,
        description="Claude CLI implementiert Mock→Real Tools, Docker Rebuild",
    ),
    "eval_reporter": StepConfig(
        name="EvalReporterAgent",
        orchestrator="swarm",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=False,
        timeout=120.0,
        description="LLM generiert Abschlussbericht",
    ),
    "export": StepConfig(
        name="ExportAgent",
        orchestrator="openclaw",
        needs_user_input=False,
        needs_docker=False,
        needs_claude_cli=False,
        timeout=60.0,
        description="Git Push + Filesystem-Export",
    ),
}


def get_step(name: str) -> StepConfig:
    """Get step config by name."""
    return PIPELINE_STEPS[name]


def get_steps_by_orchestrator(orchestrator: str) -> list:
    """Get all steps for a given orchestrator type."""
    return [s for s in PIPELINE_STEPS.values() if s.orchestrator == orchestrator]


def get_step_order() -> list:
    """Return steps in execution order."""
    return list(PIPELINE_STEPS.keys())
