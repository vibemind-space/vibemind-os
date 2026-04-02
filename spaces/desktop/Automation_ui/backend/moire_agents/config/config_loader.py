"""
Configuration Loader for Handoff MCP Production Deployment

Handles loading and validating configuration from environment files
with support for multiple environment types (development, production).
"""

import os
import sys
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv


@dataclass
class ProductionConfig:
    """Production configuration settings for Handoff MCP"""

    # Required
    openrouter_api_key: str = ""

    # MoireServer Connection
    moire_host: str = "localhost"
    moire_port: int = 8766
    moire_reconnect_attempts: int = 10
    moire_reconnect_interval: int = 2000  # milliseconds

    # Tesseract Fallback (auto-detect or use TESSERACT_PATH env var)
    tesseract_path: str = ""  # Will be auto-detected if empty

    # Logging
    log_level: str = "INFO"
    log_file: str = ""
    log_to_console: bool = True
    log_to_file: bool = True

    # Performance
    planning_max_rounds: int = 3
    validation_confidence_threshold: float = 0.7
    execution_inter_step_delay: float = 0.3

    # Paths
    project_root: str = ""
    python_root: str = ""

    # Health Check
    health_check_interval: int = 30  # seconds
    auto_restart_on_failure: bool = True
    max_restart_attempts: int = 3

    def __post_init__(self):
        """Set default paths if not provided"""
        if not self.project_root:
            # Default to MoireTracker_v2 root
            self.project_root = str(Path(__file__).parent.parent.parent)
        if not self.python_root:
            self.python_root = str(Path(__file__).parent.parent)
        if not self.log_file:
            self.log_file = str(Path(self.python_root) / "logs" / "handoff_mcp.log")

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors"""
        errors = []

        if not self.openrouter_api_key:
            errors.append("OPENROUTER_API_KEY is required but not set")

        if self.moire_port < 1 or self.moire_port > 65535:
            errors.append(f"Invalid MOIRE_PORT: {self.moire_port}")

        if self.validation_confidence_threshold < 0 or self.validation_confidence_threshold > 1:
            errors.append(f"Invalid VALIDATION_CONFIDENCE_THRESHOLD: {self.validation_confidence_threshold}")

        if self.log_to_file:
            log_dir = Path(self.log_file).parent
            if not log_dir.exists():
                try:
                    log_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"Cannot create log directory {log_dir}: {e}")

        return errors

    def is_valid(self) -> bool:
        """Check if configuration is valid"""
        return len(self.validate()) == 0


# Global config instance
_config: Optional[ProductionConfig] = None


def load_config(force_reload: bool = False) -> ProductionConfig:
    """
    Load configuration from environment files.

    Priority order:
    1. Environment variables (highest)
    2. .env.local (project-specific overrides)
    3. .env.production (production defaults)
    4. .env (development defaults)
    5. Built-in defaults (lowest)
    """
    global _config

    if _config is not None and not force_reload:
        return _config

    # Determine paths
    python_root = Path(__file__).parent.parent
    project_root = python_root.parent
    user_home = Path.home()

    # Load env files in reverse priority order (last loaded wins)
    env_files = [
        python_root / ".env",                          # Development defaults
        python_root / ".env.production",               # Production defaults
        python_root / ".env.local",                    # Local overrides
        user_home / ".handoff_mcp" / ".env",          # User-specific
    ]

    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=True)

    # Build config from environment
    _config = ProductionConfig(
        # Required
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),

        # MoireServer
        moire_host=os.getenv("MOIRE_HOST", "localhost"),
        moire_port=int(os.getenv("MOIRE_PORT", "8765")),
        moire_reconnect_attempts=int(os.getenv("MOIRE_RECONNECT_ATTEMPTS", "10")),
        moire_reconnect_interval=int(os.getenv("MOIRE_RECONNECT_INTERVAL", "2000")),

        # Tesseract (auto-detect or use TESSERACT_PATH env var)
        tesseract_path=os.getenv("TESSERACT_PATH") or shutil.which("tesseract") or "",

        # Logging
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE", ""),
        log_to_console=os.getenv("LOG_TO_CONSOLE", "true").lower() == "true",
        log_to_file=os.getenv("LOG_TO_FILE", "true").lower() == "true",

        # Performance
        planning_max_rounds=int(os.getenv("PLANNING_MAX_ROUNDS", "3")),
        validation_confidence_threshold=float(os.getenv("VALIDATION_CONFIDENCE_THRESHOLD", "0.7")),
        execution_inter_step_delay=float(os.getenv("EXECUTION_INTER_STEP_DELAY", "0.3")),

        # Paths
        project_root=os.getenv("PROJECT_ROOT", str(project_root)),
        python_root=os.getenv("PYTHON_ROOT", str(python_root)),

        # Health Check
        health_check_interval=int(os.getenv("HEALTH_CHECK_INTERVAL", "30")),
        auto_restart_on_failure=os.getenv("AUTO_RESTART_ON_FAILURE", "true").lower() == "true",
        max_restart_attempts=int(os.getenv("MAX_RESTART_ATTEMPTS", "3")),
    )

    return _config


def get_config() -> ProductionConfig:
    """Get the current configuration (loads if not already loaded)"""
    if _config is None:
        return load_config()
    return _config


def print_config_status():
    """Print configuration status for debugging"""
    config = get_config()
    errors = config.validate()

    print("=" * 60)
    print("Handoff MCP Configuration Status")
    print("=" * 60)
    print(f"Project Root:      {config.project_root}")
    print(f"Python Root:       {config.python_root}")
    print(f"MoireServer:       {config.moire_host}:{config.moire_port}")
    print(f"Log Level:         {config.log_level}")
    print(f"Log File:          {config.log_file}")
    print(f"API Key Set:       {'Yes' if config.openrouter_api_key else 'NO - REQUIRED!'}")
    print(f"Tesseract Path:    {config.tesseract_path}")
    print(f"Tesseract Exists:  {Path(config.tesseract_path).exists()}")
    print("-" * 60)

    if errors:
        print("CONFIGURATION ERRORS:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Configuration is valid!")

    print("=" * 60)


if __name__ == "__main__":
    # Run configuration check
    print_config_status()
