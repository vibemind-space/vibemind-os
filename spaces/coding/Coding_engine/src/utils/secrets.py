"""
Docker Swarm Secrets Helper.

Reads secrets from /run/secrets/ (Swarm mode) with fallback to env vars
(docker-compose mode). This allows the same code to work in both modes.

Usage:
    from src.utils.secrets import get_secret
    api_key = get_secret("openrouter_api_key", env_fallback="OPENROUTER_API_KEY")
"""

import os
import logging

logger = logging.getLogger(__name__)

SECRETS_DIR = "/run/secrets"


def get_secret(name: str, env_fallback: str = "", default: str = "") -> str:
    """
    Read a secret value. Priority:
    1. Docker Swarm secret file (/run/secrets/<name>)
    2. Environment variable (env_fallback or NAME uppercased)
    3. Default value

    Args:
        name: Secret name (matches filename in /run/secrets/)
        env_fallback: Environment variable name to check as fallback
        default: Default value if neither source has the secret
    """
    # Try Swarm secret file first
    secret_path = os.path.join(SECRETS_DIR, name)
    try:
        with open(secret_path, "r") as f:
            value = f.read().strip()
            if value:
                logger.debug("Secret '%s' loaded from Swarm", name)
                return value
    except (FileNotFoundError, PermissionError):
        pass

    # Fallback to environment variable
    env_name = env_fallback or name.upper()
    value = os.environ.get(env_name, "")
    if value:
        logger.debug("Secret '%s' loaded from env var '%s'", name, env_name)
        return value

    if default:
        logger.debug("Secret '%s' using default", name)
    else:
        logger.warning("Secret '%s' not found in Swarm or env", name)

    return default


def get_database_url(
    secret_name: str = "postgres_password",
    user: str = "postgres",
    host: str = "postgres",
    port: int = 5432,
    db: str = "coding_engine",
    env_fallback: str = "DATABASE_URL",
) -> str:
    """Build database URL from Swarm secret or env var."""
    # Check for full DATABASE_URL first
    full_url = os.environ.get(env_fallback, "")
    if full_url:
        return full_url

    password = get_secret(secret_name, default=user)
    return "postgresql+asyncpg://%s:%s@%s:%d/%s" % (user, password, host, port, db)
