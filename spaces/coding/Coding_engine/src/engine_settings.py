"""
Central settings loader for DaveFelix Coding Engine.

Reads config/engine_settings.yml with auto-reload on file change.
All components (API, Bot, Generation) should use get_setting() to read config.

Usage:
    from src.config.engine_settings import get_setting, get_settings, update_setting

    model = get_setting("models.fixing.model", "gpt-5.4")
    channels = get_setting("discord.channels")
    all_settings = get_settings()
    update_setting("models.fixing.model", "o4-mini")
"""

import os
import copy
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

# ── Paths ──
_CONFIG_DIR = Path(__file__).parent.parent / "config"
_SETTINGS_FILE = _CONFIG_DIR / "engine_settings.yml"

# ── Cache ──
_settings: Optional[dict] = None
_last_mtime: float = 0
_lock = threading.Lock()


def _resolve_path() -> Path:
    """Find the settings file, checking multiple locations."""
    # Docker: /app/config/engine_settings.yml
    docker_path = Path("/app/config/engine_settings.yml")
    if docker_path.exists():
        return docker_path
    # Local: relative to repo root
    if _SETTINGS_FILE.exists():
        return _SETTINGS_FILE
    # Fallback: create default
    return _SETTINGS_FILE


def get_settings() -> dict:
    """
    Load and return the full settings dict.
    Auto-reloads if the file has been modified since last read.
    """
    global _settings, _last_mtime

    path = _resolve_path()
    if not path.exists():
        return _default_settings()

    mtime = path.stat().st_mtime
    if _settings is not None and mtime == _last_mtime:
        return _settings

    with _lock:
        # Double-check after acquiring lock
        if _settings is not None and mtime == _last_mtime:
            return _settings

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _settings = data
            _last_mtime = mtime
            return _settings
        except Exception as e:
            print(f"[engine_settings] Error loading {path}: {e}")
            if _settings is not None:
                return _settings
            return _default_settings()


def get_setting(path: str, default: Any = None) -> Any:
    """
    Get a setting value by dot-notation path.

    Examples:
        get_setting("models.fixing.model") → "gpt-5.4"
        get_setting("discord.channels.dev_tasks") → "1484193408955322399"
        get_setting("generation.max_parallel_tasks", 4) → 4
    """
    settings = get_settings()
    keys = path.split(".")
    current = settings

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current if current is not None else default


def update_setting(path: str, value: Any) -> bool:
    """
    Update a single setting value and write back to YAML.

    Examples:
        update_setting("models.fixing.model", "o4-mini")
        update_setting("discord.auto_status.interval_seconds", 120)
    """
    global _settings, _last_mtime

    settings = copy.deepcopy(get_settings())
    keys = path.split(".")

    # Navigate to parent
    current = settings
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    # Set value
    current[keys[-1]] = value

    # Write back
    file_path = _resolve_path()
    try:
        with _lock:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            _settings = settings
            _last_mtime = file_path.stat().st_mtime
        return True
    except Exception as e:
        print(f"[engine_settings] Error writing {file_path}: {e}")
        return False


def get_project(project_name: str = "") -> Optional[dict]:
    """
    Get project config by name. If no name given, returns the first/default project.

    Returns dict with: id, name, requirements_path, output_dir, db_job_id, tech_stack, preview_url
    """
    projects = get_setting("projects", {})
    if not projects:
        return None

    if project_name:
        # Exact match
        if project_name in projects:
            p = projects[project_name]
            p["key"] = project_name
            return p
        # Partial match
        for key, proj in projects.items():
            if project_name in key or project_name in proj.get("id", "") or project_name in proj.get("name", ""):
                proj["key"] = key
                return proj
        return None

    # Return first project as default
    key = next(iter(projects))
    p = projects[key]
    p["key"] = key
    return p


def get_model_for_role(role: str) -> dict:
    """
    Get model config for a specific role.

    Roles: generation, fixing, schema, review, planning, reasoning
    Returns: {"provider": "openai", "model": "gpt-5.4", "max_tokens": 32768}
    """
    return get_setting(f"models.{role}", {
        "provider": "openai",
        "model": "gpt-5.4",
        "max_tokens": 16384,
    })


def get_fix_strategy(task_type: str) -> dict:
    """
    Get fix strategy for a task type.

    Types: migration, lint, build, code, verify
    Returns: {"method": "prisma_push", "fallback": "gpt_schema_fix", "max_attempts": 5}
    """
    return get_setting(f"fix_strategies.{task_type}", {
        "method": "gpt_fix",
        "max_retries": 3,
    })


def _default_settings() -> dict:
    """Fallback settings if YAML file doesn't exist."""
    return {
        "models": {
            "generation": {"provider": "openai", "model": "gpt-5.4", "max_tokens": 32768},
            "fixing": {"provider": "openai", "model": "gpt-5.4", "max_tokens": 16384},
            "schema": {"provider": "openai", "model": "gpt-5.4", "max_tokens": 8000},
            "review": {"provider": "openai", "model": "gpt-5.4", "max_tokens": 8000},
            "planning": {"provider": "openai", "model": "gpt-5.4-mini", "max_tokens": 16384},
            "reasoning": {"provider": "openai", "model": "o4-mini", "max_tokens": 32768},
        },
        "providers": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
            "anthropic": {"base_url": None, "api_key_env": "ANTHROPIC_API_KEY"},
        },
        "discord": {
            "channels": {
                "dev_tasks": "1484193408955322399",
                "fixes": "1484193412679733302",
                "prs": "1485666130474303562",
            },
            "auto_status": {"enabled": True, "interval_seconds": 180, "channel": "dev_tasks"},
            "auto_fix": {"enabled": True, "max_rounds": 3, "trigger_on_idle": True},
        },
        "generation": {
            "backend": "openai",
            "max_parallel_tasks": 4,
            "task_timeout_seconds": 300,
            "feature_based_ordering": True,
        },
        "fix_strategies": {
            "migration": {"method": "prisma_push", "fallback": "gpt_schema_fix", "max_attempts": 5},
            "lint": {"method": "eslint_fix"},
            "build": {"method": "build_check", "fallback": "gpt_fix"},
            "code": {"method": "gpt_fix", "max_retries": 3},
        },
        "projects": {},
    }
