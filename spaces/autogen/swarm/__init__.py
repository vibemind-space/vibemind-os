"""
Wrapper layer for AgentFarm swarm modules.

Re-exports from the submodule at spaces/autogen/farm/minibook/swarm/
with VibeMind-specific overrides (LLM config, Minibook URL).
"""
import sys
import os
from pathlib import Path

# Add submodule to Python path so its internal imports work
_farm_root = Path(__file__).resolve().parent.parent / "farm" / "minibook"
if str(_farm_root) not in sys.path:
    sys.path.insert(0, str(_farm_root))

# Override constants before any swarm module imports
os.environ.setdefault("MINIBOOK_URL", os.getenv("MINIBOOK_URL", "http://localhost:3480"))

# Wire LLM to global config
try:
    from llm_config import get_model
    _agentfarm_model = get_model("agentfarm")
    os.environ.setdefault("ANTHROPIC_MODEL", _agentfarm_model)
    os.environ.setdefault("OPENAI_MODEL", _agentfarm_model)
except ImportError:
    pass

# Re-export key classes
from swarm.pipeline import SwarmPipeline
from swarm.forge_orchestrator import ForgeOrchestrator
from swarm.knowledge import AGENT_ROLES
from swarm.api_client import register_agent, load_credentials, save_credentials, api_post
from swarm.docker_ops import start_mcp_gateway, stop_mcp_gateway

__all__ = [
    "SwarmPipeline",
    "ForgeOrchestrator",
    "AGENT_ROLES",
    "register_agent",
    "load_credentials",
    "save_credentials",
    "api_post",
    "start_mcp_gateway",
    "stop_mcp_gateway",
]
