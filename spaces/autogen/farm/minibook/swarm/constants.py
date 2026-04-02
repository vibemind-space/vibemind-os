"""Configuration constants for the AutoGen Swarm pipeline."""

import os
from pathlib import Path
from dataclasses import dataclass, field


# --- CascadeContext ---

@dataclass
class CascadeContext:
    """Loaded state from a previous pipeline iteration for cascade mode."""
    source_dir: Path
    project_yml: dict
    agent_yamls: dict          # {filepath: parsed_yaml}
    tools_py: str              # Raw content of src/tools.py
    yaml_files_raw: dict       # {filepath: raw_yaml_string}
    iteration_number: int = 0
    cascade_history: list = field(default_factory=list)


# --- Minibook / Pipeline Config ---

MINIBOOK_URL = os.getenv("MINIBOOK_URL", "http://localhost:3480")
POLL_INTERVAL = 2
STEP_TIMEOUT = 120
MAX_REVISIONS = 2
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
CREDS_FILE = Path(__file__).parent.parent.parent.parent / "config" / "swarm_agents.json"

# --- LLM Provider Config ---
# Switch provider via env: LLM_PROVIDER=anthropic (default) or openai
# Anthropic: set ANTHROPIC_API_KEY in .env (Max subscription)
# OpenAI:    set OPENAI_API_KEY in .env

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    for _line in env_path.read_text().strip().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()

# --- Zentrale LLM-Config via vibemind_shared ---
try:
    from vibemind_shared import get_model as _shared_get_model
    _HAS_SHARED_CONFIG = True
except ImportError:
    _HAS_SHARED_CONFIG = False


def _resolve_model(role: str, env_var: str, fallback: str) -> str:
    """Modell aus zentraler Config, env-var oder Fallback."""
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val
    if _HAS_SHARED_CONFIG:
        try:
            return _shared_get_model(role)
        except Exception:
            pass
    return fallback


if LLM_PROVIDER == "anthropic":
    from anthropic import AsyncAnthropic  # noqa: E402
    anthropic_client = AsyncAnthropic()
    openai_client = None
    DEFAULT_MODEL = _resolve_model("agentfarm_anthropic", "ANTHROPIC_MODEL", "claude-sonnet-4-6")
else:
    from openai import AsyncOpenAI  # noqa: E402
    openai_client = AsyncOpenAI()
    anthropic_client = None
    DEFAULT_MODEL = _resolve_model("agentfarm", "OPENAI_MODEL", "gpt-5.4")

# --- MCP Gateway ---

MCP_GATEWAY_PORT = 8808

# --- Forge Config ---

FORGE_STATE_FILE = Path(__file__).parent.parent / "forge_state.json"
FORGE_METRICS_FILE = Path(__file__).parent.parent / "forge_metrics.json"
FORGE_API_PORT = 8890
STALL_THRESHOLD = 300  # seconds before a conversation is considered stalled
MAX_CASCADE_DEPTH = 3
FORGE_SCHEDULE = {
    "pipeline_run": 45 * 60,    # 45 minutes
    "benchmark": 20 * 60,       # 20 minutes
    "arch_review": 90 * 60,     # 90 minutes
    "doc_research": 60 * 60,    # 60 minutes
    "security_scan": 120 * 60,  # 120 minutes
    "dep_check": 30 * 60,       # 30 minutes
    "grand_plan": 15 * 60,      # 15 minutes
    "repo_commit": 10 * 60,     # 10 minutes
    "company_forge": 5 * 60,    # 5 minutes between team builds
}

# --- CompanyForge Config ---
COMPANY_MAX_TEAMS = 20          # circuit breaker: max teams per company
COMPANY_FORGE_COOLDOWN = 300    # seconds between builds
FORGE_HOURLY_BUDGET = {
    "ForgeOrchestrator": 20,
    "DocResearcherAgent": 6,
    "BenchmarkAgent": 4,
    "SecurityAgent": 8,
    "DependencyAgent": 8,
    "RepoAgent": 10,
    "CompanyForgeAgent": 12,
}
DOC_RESEARCH_TOPICS = [
    "autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_swarm_group_chat.py",
    "autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_selector_group_chat.py",
    "autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_round_robin_group_chat.py",
    "autogen-agentchat/src/autogen_agentchat/agents/__init__.py",
    "autogen-agentchat/src/autogen_agentchat/tools/__init__.py",
    "autogen-agentchat/src/autogen_agentchat/conditions/__init__.py",
    "autogen-ext/src/autogen_ext/models/openai/__init__.py",
    "autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_base_group_chat.py",
]
