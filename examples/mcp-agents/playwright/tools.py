# -*- coding: utf-8 -*-
"""
tools.py
Encapsulate model client initialization, tool listing/selection from MCP, and prompt/config loaders.
Follows same naming conventions and code style as other agents. Clear comments for easy debug.
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    SYSTEM_PROMPT_PATH,
    TASK_PROMPT_PATH,
    SERVERS_CONFIG_PATH,
    MODEL_CONFIG_PATH,
)

# Import shared ModelClient from core to allow reuse by other servers
try:
    # Robust import: add <project>/src to sys.path to access core.model_client
    import sys as _sys
    import os as _os
    _SRC_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    # _SRC_DIR should point to the 'src' root (parent of 'MCP PLUGINS')
    if _SRC_DIR not in _sys.path:
        _sys.path.insert(0, _SRC_DIR)
    from core.model_client import ModelClient, init_model_client as core_init_model_client  # type: ignore
except Exception:
    # Fallback: local stub kept for backward compatibility within Playwright server only
    core_init_model_client = None  # type: ignore
    class ModelClient:  # type: ignore
        def __init__(self, model: str, base_url: Optional[str] = None, api_key_env: Optional[str] = None):
            self.model = model
            self.base_url = base_url
            self.api_key_env = api_key_env
            self.api_key = os.getenv(api_key_env) if api_key_env else None
        def as_dict(self) -> Dict[str, Any]:
            return {
                "model": self.model,
                "base_url": self.base_url,
                "api_key_env": self.api_key_env,
                "has_api_key": bool(self.api_key),
            }

# ---------- Utility loaders ----------

def load_text(path: str) -> str:
    """Read UTF-8 text file, return empty string if missing."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def load_json(path: str) -> Dict[str, Any]:
    """Read JSON file; return empty dict if missing or invalid."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------- Model client init (adapter pattern) ----------

def init_model_client() -> ModelClient:
    """Initialize ModelClient using shared core initializer if available.

    Falls back to legacy local behavior if core initializer import fails.
    """
    if core_init_model_client is not None:
        # Use the shared config path specific to this server
        return core_init_model_client(MODEL_CONFIG_PATH)
    # Legacy fallback (kept to avoid runtime breakage if core not present)
    cfg = load_json(MODEL_CONFIG_PATH)
    model = cfg.get("model") or os.getenv("MODEL") or "gpt-4o"
    base_url = cfg.get("base_url") or os.getenv("OPENAI_BASE_URL")
    api_key_env = cfg.get("api_key_env") or "OPENAI_API_KEY"
    return ModelClient(model=model, base_url=base_url, api_key_env=api_key_env)


# ---------- Prompts ----------

def get_system_prompt(event_hint: Optional[str] = None) -> str:
    """Load system prompt and format with MCP event hint if provided."""
    text = load_text(SYSTEM_PROMPT_PATH)
    if event_hint:
        try:
            return text.replace("{MCP_EVENT}", str(event_hint))
        except Exception:
            return text
    return text


def get_task_prompt() -> str:
    return load_text(TASK_PROMPT_PATH)


# ---------- MCP servers/tools ----------

def load_servers_config() -> Dict[str, Any]:
    return load_json(SERVERS_CONFIG_PATH)


def list_mcp_tools_from_config(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool definitions or server descriptors used by MCP runtime.
    This is a placeholder that returns entries under cfg["servers"].
    """
    servers = cfg.get("servers") or []
    # Normalize minimal data
    return [
        {
            "name": s.get("name"),
            "active": bool(s.get("active", True)),
            "type": s.get("type"),
            "command": s.get("command"),
            "args": s.get("args", []),
            "read_timeout_seconds": s.get("read_timeout_seconds", 120),
        }
        for s in servers
    ]


def select_active_servers(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter active servers/tools."""
    return [s for s in servers if s.get("active")]