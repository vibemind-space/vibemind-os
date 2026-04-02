"""
Global LLM Configuration — Single source of truth for all model selections.

All model names, providers, and API keys are defined in config/llm_models.yml.
This module loads that YAML once and provides accessor functions.

Roles:
    primary      — Anthropic SDK direct (base agent, vision, monitor)
    cli          — Claude CLI / Kilo CLI --model flag
    mcp_standard — AutoGen teams, EventFix orchestrator, task executor
    mcp_agent    — Individual MCP plugin agents (filesystem, docker, etc.)
    judge        — MCMP judge, fungus agents, differential analysis
    reasoning    — Complex reasoning, architecture analysis
    enrichment   — Phase 30 schema discovery, task mapping

Environment variable overrides (optional):
    LLM_MODEL_PRIMARY=claude-opus-4-20250514
    LLM_MODEL_JUDGE=anthropic/claude-sonnet-4.5
    etc.

Usage:
    from src.llm_config import get_model, get_model_config

    model_name = get_model("primary")       # "claude-sonnet-4-20250514"
    config = get_model_config("judge")       # {model, provider, api_key, base_url, max_tokens}
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ── Hardcoded fallback defaults (used if YAML is missing) ──────────────────

_FALLBACK_CONFIG: Dict[str, Any] = {
    "providers": {
        "anthropic": {"base_url": None, "api_key_env": "ANTHROPIC_API_KEY"},
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
        },
    },
    "models": {
        "primary": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_tokens": 16384,
        },
        "cli": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_tokens": 16384,
        },
        "mcp_standard": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_tokens": 8192,
        },
        "mcp_agent": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
        },
        "judge": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5",
            "max_tokens": 4096,
        },
        "reasoning": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_tokens": 8192,
        },
        "enrichment": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
        },
    },
}

# ── Module-level cache (loaded once) ──────────────────────────────────────

_config_cache: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """Load config from YAML file, falling back to hardcoded defaults."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    # Try loading from config/llm_models.yml relative to project root
    config_path = Path(__file__).parent.parent / "config" / "llm_models.yml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            if loaded and "models" in loaded:
                _config_cache = loaded
                return _config_cache
        except Exception:
            pass  # Fall through to defaults

    _config_cache = _FALLBACK_CONFIG
    return _config_cache


def reload_config() -> None:
    """Force reload of the configuration (useful for testing)."""
    global _config_cache
    _config_cache = None
    _load_config()


# ── Public API ─────────────────────────────────────────────────────────────


def get_model(role: str) -> str:
    """
    Get model ID for a given role.

    Args:
        role: One of primary, cli, mcp_standard, mcp_agent, judge, reasoning, enrichment

    Returns:
        Model ID string (e.g. "claude-sonnet-4-20250514", "anthropic/claude-sonnet-4.5")
    """
    config = _load_config()
    model_cfg = config.get("models", {}).get(role, {})
    model = model_cfg.get("model", "")

    # Check for environment variable override: LLM_MODEL_PRIMARY, LLM_MODEL_JUDGE, etc.
    env_key = f"LLM_MODEL_{role.upper()}"
    env_override = os.environ.get(env_key)
    if env_override:
        return env_override

    if not model:
        # Fallback to hardcoded defaults
        fallback = _FALLBACK_CONFIG.get("models", {}).get(role, {})
        model = fallback.get("model", "claude-sonnet-4-6")

    return model


def get_provider(role: str) -> str:
    """Get provider name for a role ('anthropic' or 'openrouter')."""
    config = _load_config()
    model_cfg = config.get("models", {}).get(role, {})
    return model_cfg.get("provider", "openrouter")


def get_max_tokens(role: str) -> int:
    """Get default max_tokens for a role."""
    config = _load_config()
    model_cfg = config.get("models", {}).get(role, {})
    return model_cfg.get("max_tokens", 4096)


def get_api_key(role: str) -> Optional[str]:
    """
    Resolve API key for a role from environment variables.

    Returns:
        API key string or None if not set
    """
    config = _load_config()
    provider_name = get_provider(role)
    providers = config.get("providers", {})
    provider_cfg = providers.get(provider_name, {})
    env_var = provider_cfg.get("api_key_env", "")
    if env_var:
        return os.environ.get(env_var)
    return None


def get_base_url(role: str) -> Optional[str]:
    """
    Get base URL for a role's provider.

    Returns:
        URL string for OpenRouter, None for Anthropic SDK
    """
    config = _load_config()
    provider_name = get_provider(role)
    providers = config.get("providers", {})
    provider_cfg = providers.get(provider_name, {})
    return provider_cfg.get("base_url")


def get_model_config(role: str) -> Dict[str, Any]:
    """
    Get full model configuration for a role.

    Returns:
        Dict with keys: model, provider, api_key, base_url, max_tokens
    """
    return {
        "model": get_model(role),
        "provider": get_provider(role),
        "api_key": get_api_key(role),
        "base_url": get_base_url(role),
        "max_tokens": get_max_tokens(role),
    }


def get_openrouter_headers() -> Dict[str, str]:
    """Get standard OpenRouter HTTP headers."""
    return {
        "HTTP-Referer": "https://coding-engine.local",
        "X-Title": "Coding Engine",
    }
