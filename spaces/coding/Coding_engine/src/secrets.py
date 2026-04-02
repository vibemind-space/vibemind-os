"""
Docker Secrets Reader.

Reads secrets from /run/secrets/ (Docker Swarm/Compose secrets)
with fallback to environment variables for local development.

Usage:
    from src.secrets import get_secret
    api_key = get_secret("openai_api_key")  # reads /run/secrets/openai_api_key or $OPENAI_API_KEY
"""

import os
from pathlib import Path
from functools import lru_cache

SECRETS_DIR = Path("/run/secrets")

# Mapping: secret name → env var fallback
SECRET_ENV_MAP = {
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "github_token": "GITHUB_TOKEN",
    "discord_bot_token": "DISCORD_BOT_TOKEN",
    "discord_bot_token_analyzer": "DISCORD_BOT_TOKEN_ANALYZER",
    "jwt_secret_key": "JWT_SECRET_KEY",
    "github_client_secret": "GITHUB_CLIENT_SECRET",
    "google_client_secret": "GOOGLE_CLIENT_SECRET",
    "admin_password": "ADMIN_PASSWORD",
}


@lru_cache(maxsize=32)
def get_secret(name: str, default: str = "") -> str:
    """
    Read a secret. Priority:
    1. /run/secrets/{name} (Docker secret)
    2. Environment variable (mapped name)
    3. Default value
    """
    # 1. Try Docker secret file
    secret_file = SECRETS_DIR / name
    if secret_file.exists():
        try:
            return secret_file.read_text().strip()
        except Exception:
            pass

    # 2. Try environment variable
    env_name = SECRET_ENV_MAP.get(name, name.upper())
    env_val = os.environ.get(env_name, "")
    if env_val:
        return env_val

    return default


def get_all_secrets() -> dict:
    """Get all configured secrets (masked for logging)."""
    result = {}
    for name in SECRET_ENV_MAP:
        val = get_secret(name)
        if val:
            result[name] = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
        else:
            result[name] = "(not set)"
    return result
