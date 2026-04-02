"""
Configuration and credentials management for Cell CLI.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Config file locations
CONFIG_DIR = Path.home() / ".cell"
CONFIG_FILE = CONFIG_DIR / "config.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
CELL_MANIFEST_FILE = "cell.json"


def ensure_config_dir() -> None:
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> Dict[str, Any]:
    """Load configuration from file."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a specific config value."""
    config = get_config()
    return config.get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """Set a specific config value."""
    config = get_config()
    config[key] = value
    save_config(config)


def get_credentials() -> Optional[Dict[str, Any]]:
    """Load credentials from file."""
    ensure_config_dir()
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE) as f:
                creds = json.load(f)
                # Check if token exists
                if creds.get("token"):
                    return creds
        except (json.JSONDecodeError, IOError):
            pass
    return None


def save_credentials(credentials: Dict[str, Any]) -> None:
    """Save credentials to file."""
    ensure_config_dir()
    # Set restrictive permissions on credentials file
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(credentials, f, indent=2)

    # Try to set file permissions (Unix-like systems)
    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod the same way


def clear_credentials() -> None:
    """Remove stored credentials."""
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()


def get_active_tenant() -> Optional[str]:
    """Get the active tenant ID."""
    config = get_config()
    return config.get("active_tenant")


def set_active_tenant(tenant_id: str) -> None:
    """Set the active tenant ID."""
    set_config_value("active_tenant", tenant_id)


def get_api_url() -> str:
    """Get the API URL from config or environment."""
    # Environment variable takes precedence
    env_url = os.environ.get("CELL_API_URL")
    if env_url:
        return env_url

    # Then check config
    config = get_config()
    return config.get("api_url", "http://localhost:8000")


def set_api_url(url: str) -> None:
    """Set the API URL in config."""
    set_config_value("api_url", url)


def get_default_namespace() -> Optional[str]:
    """Get default namespace for cell operations."""
    config = get_config()
    return config.get("default_namespace")


def set_default_namespace(namespace: str) -> None:
    """Set default namespace for cell operations."""
    set_config_value("default_namespace", namespace)


def load_cell_manifest(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load cell.json manifest from current directory or specified path."""
    manifest_path = path or Path.cwd() / CELL_MANIFEST_FILE

    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_cell_manifest(manifest: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Save cell.json manifest to current directory or specified path."""
    manifest_path = path or Path.cwd() / CELL_MANIFEST_FILE

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def get_installed_cells() -> Dict[str, Dict[str, Any]]:
    """Get list of locally installed cells."""
    config = get_config()
    return config.get("installed_cells", {})


def add_installed_cell(namespace: str, version: str, path: str) -> None:
    """Track a locally installed cell."""
    config = get_config()
    installed = config.get("installed_cells", {})
    installed[namespace] = {
        "version": version,
        "path": path,
        "installed_at": __import__("datetime").datetime.now().isoformat(),
    }
    config["installed_cells"] = installed
    save_config(config)


def remove_installed_cell(namespace: str) -> bool:
    """Remove a cell from installed tracking."""
    config = get_config()
    installed = config.get("installed_cells", {})
    if namespace in installed:
        del installed[namespace]
        config["installed_cells"] = installed
        save_config(config)
        return True
    return False


def get_recent_cells() -> list:
    """Get list of recently accessed cells."""
    config = get_config()
    return config.get("recent_cells", [])


def add_recent_cell(namespace: str) -> None:
    """Add a cell to recent list."""
    config = get_config()
    recent = config.get("recent_cells", [])

    # Remove if already exists
    if namespace in recent:
        recent.remove(namespace)

    # Add to front
    recent.insert(0, namespace)

    # Keep only last 10
    config["recent_cells"] = recent[:10]
    save_config(config)


def get_cli_settings() -> Dict[str, Any]:
    """Get CLI-specific settings."""
    config = get_config()
    return config.get("cli_settings", {
        "output_format": "table",
        "color": True,
        "verbose": False,
        "confirm_destructive": True,
    })


def set_cli_setting(key: str, value: Any) -> None:
    """Set a CLI setting."""
    config = get_config()
    settings = config.get("cli_settings", {})
    settings[key] = value
    config["cli_settings"] = settings
    save_config(config)
