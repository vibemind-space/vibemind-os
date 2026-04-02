"""
AgentFarm Submodule Wrapper — Import Bridge + LLM Override

Provides clean imports from the git submodule at spaces/autogen/farm/
while overriding LLM config and Minibook URL to use VibeMind's global config.

Usage:
    from spaces.autogen.wrapper import SwarmPipeline, ForgeOrchestrator, knowledge
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Add submodule to sys.path so internal relative imports work
# ---------------------------------------------------------------------------

_FARM_ROOT = Path(__file__).resolve().parents[1] / "farm" / "minibook"
_SWARM_ROOT = _FARM_ROOT / "swarm"

# Set LLM_PROVIDER BEFORE any submodule import (constants.py reads it at import time)
try:
    from llm_config import get_model as _early_get_model
    _early_model = _early_get_model("agentfarm")
    os.environ["LLM_PROVIDER"] = "openai" if "gpt" in _early_model else "anthropic"
    os.environ.setdefault("OPENAI_MODEL", _early_model)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 2. Import submodule modules via importlib (avoids sys.path pollution)
# ---------------------------------------------------------------------------
import importlib.util


def _load_farm_module(name: str, subpath: str):
    """Load a module from the farm submodule without touching sys.path."""
    file_path = _SWARM_ROOT / subpath
    spec = importlib.util.spec_from_file_location(f"farm_swarm.{name}", str(file_path),
                                                    submodule_search_locations=[str(_SWARM_ROOT)])
    if spec is None:
        raise ImportError(f"Cannot find {file_path}")
    mod = importlib.util.module_from_spec(spec)
    # Register under farm_swarm.* namespace to avoid collision with vibemind's swarm/
    sys.modules[f"farm_swarm.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


# Load critical modules — these are the ones we need
_mod_constants = _load_farm_module("constants", "constants.py")
_mod_llm = _load_farm_module("llm", "llm.py")
_mod_knowledge = _load_farm_module("knowledge", "knowledge.py")
_mod_api_client = _load_farm_module("api_client", "api_client.py")

# Re-export what we need
farm_constants = _mod_constants
farm_llm = _mod_llm
AGENT_ROLES = _mod_knowledge.AGENT_ROLES
FORGE_AGENT_ROLES = getattr(_mod_knowledge, "FORGE_AGENT_ROLES", {})
register_agent = _mod_api_client.register_agent
load_credentials = _mod_api_client.load_credentials
save_credentials = _mod_api_client.save_credentials
api_post = _mod_api_client.api_post
api_get = _mod_api_client.api_get

# Heavy modules loaded lazily to avoid import chain issues
SwarmPipeline = None
ForgeOrchestrator = None
ForgePostTracker = None


def _ensure_pipeline_loaded():
    """Lazy-load SwarmPipeline (has deep import chain)."""
    global SwarmPipeline, ForgeOrchestrator, ForgePostTracker
    if SwarmPipeline is not None:
        return

    # For pipeline/forge we need full sys.path (they import each other internally)
    _added = str(_FARM_ROOT) not in sys.path
    if _added:
        sys.path.insert(0, str(_FARM_ROOT))
    try:
        # Patch constants BEFORE importing pipeline (it reads values at import time)
        import swarm.constants as _sc
        _sc.MINIBOOK_URL = os.getenv("MINIBOOK_URL", "http://localhost:3480")
        _sc.CREDS_FILE = Path(__file__).resolve().parents[1] / "config" / "swarm_agents.json"

        # Patch api_client (imports MINIBOOK_URL from constants at module level)
        import swarm.api_client as _sac
        _sac.MINIBOOK_URL = _sc.MINIBOOK_URL
        _sac.CREDS_FILE = _sc.CREDS_FILE

        # Patch LLM provider + model (llm.py reads from constants at import time)
        try:
            from llm_config import get_model as _gm
            _model = _gm("agentfarm")
            _sc.LLM_PROVIDER = "openai" if "gpt" in _model else "anthropic"
            if _sc.LLM_PROVIDER == "openai":
                _sc.OPENAI_MODEL = _model
            else:
                _sc.ANTHROPIC_MODEL = _model
        except ImportError:
            pass

        import swarm.llm as _sllm
        _sllm.LLM_PROVIDER = _sc.LLM_PROVIDER
        if hasattr(_sc, "OPENAI_MODEL"):
            _sllm.OPENAI_MODEL = _sc.OPENAI_MODEL
        if hasattr(_sc, "ANTHROPIC_MODEL"):
            _sllm.ANTHROPIC_MODEL = _sc.ANTHROPIC_MODEL
        # Ensure OPENAI_API_KEY is available
        _openai_key = os.getenv("OPENAI_API_KEY", "")
        if _openai_key and hasattr(_sllm, "OPENAI_API_KEY"):
            _sllm.OPENAI_API_KEY = _openai_key

        from swarm.pipeline import SwarmPipeline as _SP
        from swarm.forge_orchestrator import ForgeOrchestrator as _FO, ForgePostTracker as _FPT
        SwarmPipeline = _SP
        ForgeOrchestrator = _FO
        ForgePostTracker = _FPT
    finally:
        if _added and str(_FARM_ROOT) in sys.path:
            sys.path.remove(str(_FARM_ROOT))
        # Restore VibeMind's swarm package by re-importing it
        # Farm's swarm stays under sys.modules["swarm.*"] but VibeMind's
        # swarm package is found via sys.path (python/ dir is first)
        # Force VibeMind's swarm to be importable again
        _vibemind_swarm_path = Path(__file__).resolve().parents[3] / "swarm"
        if _vibemind_swarm_path.is_dir():
            import importlib
            # Remove the farm's "swarm" top-level entry so VibeMind's wins
            if "swarm" in sys.modules:
                farm_swarm = sys.modules.pop("swarm")
                sys.modules["_farm_swarm"] = farm_swarm  # Keep under alias

# ---------------------------------------------------------------------------
# 3. Override LLM config → VibeMind global config
# ---------------------------------------------------------------------------

try:
    from llm_config import get_model, get_provider, get_api_key

    # Patch the farm's LLM module to use VibeMind's global config
    _model = get_model("agentfarm")
    _provider = get_provider("agentfarm")

    # Override constants
    farm_constants.LLM_PROVIDER = "openai" if "gpt" in _model else "anthropic"

    if farm_constants.LLM_PROVIDER == "openai":
        farm_constants.OPENAI_MODEL = _model
        farm_llm.OPENAI_MODEL = _model
    else:
        farm_constants.ANTHROPIC_MODEL = _model
        farm_llm.ANTHROPIC_MODEL = _model

except ImportError:
    pass  # llm_config not available, use farm defaults

# ---------------------------------------------------------------------------
# 4. Override Minibook URL → VibeMind's Minibook
# ---------------------------------------------------------------------------

_minibook_url = os.getenv("MINIBOOK_URL", "http://localhost:3480")
farm_constants.MINIBOOK_URL = _minibook_url

# Patch api_client's MINIBOOK_URL directly (it imports from constants at load time)
_mod_api_client.MINIBOOK_URL = _minibook_url

# Also patch api_client if it has a module-level URL
if hasattr(farm_llm, "MINIBOOK_URL"):
    farm_llm.MINIBOOK_URL = _minibook_url

# ---------------------------------------------------------------------------
# 5. Override config file paths → VibeMind's config dir
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

farm_constants.CREDS_FILE = str(_CONFIG_DIR / "swarm_agents.json")
farm_constants.FORGE_STATE_FILE = str(_CONFIG_DIR / "forge_state.json")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Pipeline
    "SwarmPipeline",
    "ForgeOrchestrator",
    "ForgePostTracker",
    # Knowledge
    "AGENT_ROLES",
    "FORGE_AGENT_ROLES",
    # Docker/MCP
    "start_mcp_gateway",
    "stop_mcp_gateway",
    "get_mcp_catalog",
    "get_installed_mcp_servers",
    "enable_mcp_servers",
    "docker_build_test",
    "docker_run_test",
    # Code
    "parse_yaml_blocks",
    "test_generated_code",
    "write_output",
    # API
    "register_agent",
    "load_credentials",
    "save_credentials",
    "api_post",
    "api_get",
    # Input
    "input_parser",
    "input_designer",
    # Company
    "company_builder",
    # Todo
    "todo_implementer",
    # Config
    "farm_constants",
    "farm_llm",
]
