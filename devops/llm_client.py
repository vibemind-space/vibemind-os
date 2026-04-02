"""
LLM Client Factory — Multi-Provider Support
================================================
Zentrale Fabrik die aus llm_config.yml den richtigen
Client + Model fuer jede Rolle liefert.

Usage:
    from llm_client import get_client, get_model, get_temperature

    client = get_client("red_team")          # AsyncOpenAI mit richtigem Provider
    model = get_model("red_team")            # "gpt-5.4"
    temp = get_temperature("red_team")       # 0.7

    # Per-directory override:
    model = get_model("default", "poc_security_scanner")  # "gpt-4o"

    # Sync client:
    client = get_client_sync("issue_agent")  # OpenAI (sync)
"""

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).parent
load_dotenv(_PROJECT_ROOT / ".env")


def _resolve_env(value):
    """Resolve ${ENV_VAR} references in config values."""
    if not isinstance(value, str):
        return value
    pattern = re.compile(r"\$\{(\w+)\}")
    def replacer(match):
        return os.environ.get(match.group(1), "")
    return pattern.sub(replacer, value)


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """Load and cache llm_config.yml."""
    config_path = _PROJECT_ROOT / "llm_config.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"LLM config not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_config() -> dict:
    """Get the full LLM configuration."""
    return _load_config()


def _resolve_role(role: str, directory: str = "") -> dict:
    """Resolve the config for a role, respecting overrides.

    Priority: overrides[dir][role] > roles[role] > default
    """
    cfg = _load_config()

    # Start with default
    result = dict(cfg.get("default", {}))

    # Override with role-specific
    if role != "default" and role in cfg.get("roles", {}):
        result.update(cfg["roles"][role])

    # Override with directory-specific
    if directory:
        dir_name = directory.replace("\\", "/").rstrip("/").split("/")[-1]
        overrides = cfg.get("overrides", {}).get(dir_name, {})
        if role in overrides:
            result.update(overrides[role])
        elif "default" in overrides and role == "default":
            result.update(overrides["default"])
        elif "default" in overrides and role not in cfg.get("roles", {}):
            result.update(overrides["default"])

    return result


def _get_api_key(provider_name: str) -> str:
    """Get API key for a provider."""
    cfg = _load_config()
    provider = cfg.get("providers", {}).get(provider_name, {})
    key_ref = provider.get("key_ref")
    if not key_ref:
        return ""
    keys = cfg.get("keys", {})
    raw = keys.get(key_ref, "")
    return _resolve_env(raw) if raw else ""


def _get_base_url(provider_name: str) -> str:
    """Get base URL for a provider."""
    cfg = _load_config()
    provider = cfg.get("providers", {}).get(provider_name, {})
    return provider.get("base_url", "https://api.openai.com/v1")


def _get_provider_type(provider_name: str) -> str:
    """Get provider type (openai or anthropic)."""
    cfg = _load_config()
    provider = cfg.get("providers", {}).get(provider_name, {})
    return provider.get("type", "openai")


def get_model(role: str = "default", directory: str = "") -> str:
    """Get the model name for a role.

    Args:
        role: Role name (red_team, blue_team, judge, analyzer, think, etc.)
        directory: Optional directory name for per-dir overrides
    """
    resolved = _resolve_role(role, directory)
    return resolved.get("model", "gpt-4.1")


def get_temperature(role: str = "default", directory: str = "") -> float:
    """Get the temperature setting for a role."""
    resolved = _resolve_role(role, directory)
    return float(resolved.get("temperature", 0))


def get_client(role: str = "default", directory: str = ""):
    """Get an async OpenAI-compatible client for a role.

    Works for: OpenAI, OpenRouter, Gemini, Ollama (all OpenAI-compatible).
    For Anthropic: returns anthropic.AsyncAnthropic.

    Returns: AsyncOpenAI or AsyncAnthropic
    """
    resolved = _resolve_role(role, directory)
    provider_name = resolved.get("provider", "openai")
    provider_type = _get_provider_type(provider_name)

    if provider_type == "anthropic":
        try:
            import anthropic
            api_key = _get_api_key(provider_name)
            return anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise ImportError("pip install anthropic  — required for Anthropic provider")

    # OpenAI-compatible (openai, openrouter, gemini, ollama)
    from openai import AsyncOpenAI
    api_key = _get_api_key(provider_name)
    base_url = _get_base_url(provider_name)

    kwargs = {"base_url": base_url}
    if api_key:
        kwargs["api_key"] = api_key
    else:
        kwargs["api_key"] = "not-needed"  # Ollama doesn't need a key

    return AsyncOpenAI(**kwargs)


def get_client_sync(role: str = "default", directory: str = ""):
    """Get a sync OpenAI-compatible client for a role.

    Same as get_client but returns sync client.
    """
    resolved = _resolve_role(role, directory)
    provider_name = resolved.get("provider", "openai")
    provider_type = _get_provider_type(provider_name)

    if provider_type == "anthropic":
        try:
            import anthropic
            api_key = _get_api_key(provider_name)
            return anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("pip install anthropic  — required for Anthropic provider")

    from openai import OpenAI
    api_key = _get_api_key(provider_name)
    base_url = _get_base_url(provider_name)

    kwargs = {"base_url": base_url}
    if api_key:
        kwargs["api_key"] = api_key
    else:
        kwargs["api_key"] = "not-needed"

    return OpenAI(**kwargs)


def get_provider_info(role: str = "default", directory: str = "") -> dict:
    """Get full provider info for display purposes."""
    resolved = _resolve_role(role, directory)
    provider_name = resolved.get("provider", "openai")
    return {
        "provider": provider_name,
        "model": resolved.get("model", "gpt-4.1"),
        "temperature": resolved.get("temperature", 0),
        "base_url": _get_base_url(provider_name),
        "type": _get_provider_type(provider_name),
    }
