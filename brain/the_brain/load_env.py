"""
Load environment variables from .env file

Usage:
    from load_env import get_openrouter_key

    api_key = get_openrouter_key()
"""

import os
from pathlib import Path


def load_env_file(env_path='.env'):
    """
    Load environment variables from .env file

    Args:
        env_path: Path to .env file
    """
    env_file = Path(env_path)

    if not env_file.exists():
        print(f"Warning: {env_path} not found")
        return

    # .env files are UTF-8 (may contain non-ASCII in values). Without an
    # explicit encoding Python uses the platform default (cp1252 on Windows)
    # and a UTF-8 multibyte char raises UnicodeDecodeError — which previously
    # broke config.get_secret()'s .env layer on Windows. errors='replace'
    # makes a malformed line degrade gracefully instead of killing boot.
    with open(env_file, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Set environment variable if not already set
                if key and not os.getenv(key):
                    os.environ[key] = value


def get_openrouter_key():
    """
    Get OpenRouter API key from environment

    Returns:
        str: OpenRouter API key or None if not found
    """
    # Try to load from .env first
    load_env_file()

    # Get from environment
    api_key = os.getenv('OPENROUTER_API_KEY')

    if not api_key:
        print("Warning: OPENROUTER_API_KEY not found in environment or .env file")
        print("Please set it in .env file or as environment variable")

    return api_key


def get_supermemory_key():
    """
    Get Supermemory API key from environment

    Returns:
        str: Supermemory API key or None if not found
    """
    load_env_file()
    api_key = os.getenv('SUPERMEMORY_API_KEY')

    if not api_key:
        print("Warning: SUPERMEMORY_API_KEY not found")
        print("Get your API key from https://console.supermemory.ai")

    return api_key


def get_supabase_credentials():
    """
    Get Supabase credentials from environment

    Returns:
        tuple: (project_url, secret_key) or (None, None) if not found
    """
    load_env_file()
    project_url = os.getenv('SUPABASE_URL')
    secret_key = os.getenv('SUPABASE_SECRET_KEY')

    if not project_url or not secret_key:
        print("Warning: SUPABASE_URL or SUPABASE_SECRET_KEY not found")

    return project_url, secret_key


# Auto-load on import
load_env_file()


if __name__ == "__main__":
    print("=" * 70)
    print("ENVIRONMENT LOADER")
    print("=" * 70)
    print()

    # OpenRouter
    api_key = get_openrouter_key()
    if api_key:
        masked = api_key[:10] + "..." + api_key[-10:] if len(api_key) > 20 else "***"
        print(f"[OK] OpenRouter API Key: {masked}")
    else:
        print("[MISSING] OpenRouter API Key")

    # Supermemory
    print()
    supermemory_key = get_supermemory_key()
    if supermemory_key:
        masked = supermemory_key[:8] + "..." + supermemory_key[-8:] if len(supermemory_key) > 16 else "***"
        print(f"[OK] Supermemory API Key: {masked}")
    else:
        print("[MISSING] Supermemory API Key")

    # Supabase
    print()
    supabase_url, supabase_key = get_supabase_credentials()
    if supabase_url and supabase_key:
        print(f"[OK] Supabase URL: {supabase_url}")
        masked_key = supabase_key[:8] + "..." + supabase_key[-8:] if len(supabase_key) > 16 else "***"
        print(f"[OK] Supabase Secret Key: {masked_key}")
    else:
        print("[MISSING] Supabase credentials")

    print()
    print("=" * 70)
    print("To add missing keys to .env file:")
    print("  OPENROUTER_API_KEY=your-key-here")
    print("  SUPERMEMORY_API_KEY=your-key-here  # Get from console.supermemory.ai")
    print("  SUPABASE_URL=https://your-project.supabase.co")
    print("  SUPABASE_SECRET_KEY=your-secret-key")
    print("=" * 70)
