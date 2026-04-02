"""Configuration settings for the application."""

from typing import Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings
import os


class Settings(BaseSettings):
    """Application settings."""

    # API Settings
    api_title: str = "TRAE Backend API"
    api_version: str = "1.0.0"
    api_description: str = "Backend API for TRAE automation platform"

    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS Settings
    cors_origins: list = ["*"]
    cors_methods: list = ["*"]
    cors_headers: list = ["*"]

    # Storage Settings
    storage_path: str = "./storage"
    snapshots_path: str = "./storage/snapshots"
    templates_path: str = "./storage/templates"

    # OCR Settings
    ocr_language: str = "eng"
    ocr_confidence_threshold: float = 0.8

    # Performance Settings
    max_workers: int = 4
    request_timeout: int = 30

    # Security Settings
    secret_key: str = "your-secret-key-here"
    access_token_expire_minutes: int = 30

    # Logging Settings
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()

        # Ensure storage directories exist
        os.makedirs(_settings.storage_path, exist_ok=True)
        os.makedirs(_settings.snapshots_path, exist_ok=True)
        os.makedirs(_settings.templates_path, exist_ok=True)

    return _settings


# Convenience function for common settings
def get_storage_path() -> str:
    """Get storage path."""
    return get_settings().storage_path


def get_snapshots_path() -> str:
    """Get snapshots storage path."""
    return get_settings().snapshots_path


def get_templates_path() -> str:
    """Get templates storage path."""
    return get_settings().templates_path


# Create global settings instance for direct import
settings = get_settings()
