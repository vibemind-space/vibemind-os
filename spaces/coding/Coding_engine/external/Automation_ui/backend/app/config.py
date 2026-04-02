"""
Configuration Management for TRAE Backend

Centralized configuration system with environment-based settings,
validation, and type safety.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Application
    app_name: str = Field(default="TRAE Backend", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")

    # Database Settings (PostgreSQL)
    database_url: str = Field(
        default="postgresql://localhost:5432/automation_ui",
        env="DATABASE_URL"
    )
    database_pool_size: int = Field(default=5, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, env="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, env="DATABASE_POOL_TIMEOUT")
    database_echo: bool = Field(default=False, env="DATABASE_ECHO")

    # Redis Settings
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_max_connections: int = Field(default=10, env="REDIS_MAX_CONNECTIONS")

    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    reload: bool = Field(default=True, env="RELOAD")
    workers: int = Field(default=1, env="WORKERS")

    # CORS
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3005",
            "http://localhost:5174",
            "http://localhost:8080",
        ],
        env="CORS_ORIGINS",
    )
    cors_credentials: bool = Field(default=True, env="CORS_CREDENTIALS")
    cors_methods: List[str] = Field(default=["*"], env="CORS_METHODS")
    cors_headers: List[str] = Field(default=["*"], env="CORS_HEADERS")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", env="LOG_FORMAT"
    )
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")

    # Services
    enable_ocr: bool = Field(default=True, env="ENABLE_OCR")
    enable_desktop_streaming: bool = Field(default=True, env="ENABLE_DESKTOP_STREAMING")
    enable_file_watching: bool = Field(default=True, env="ENABLE_FILE_WATCHING")
    enable_file_watcher: bool = Field(default=True, env="ENABLE_FILE_WATCHER")
    enable_click_automation: bool = Field(default=True, env="ENABLE_CLICK_AUTOMATION")
    enable_websockets: bool = Field(default=True, env="ENABLE_WEBSOCKETS")

    # Remote Execution (Brain-in-Docker mode)
    execution_mode: str = Field(default="local", env="EXECUTION_MODE")  # "local" or "remote"
    remote_desktop_client_id: str = Field(default="", env="REMOTE_DESKTOP_CLIENT_ID")
    remote_action_timeout: int = Field(default=30, env="REMOTE_ACTION_TIMEOUT")
    remote_frame_max_age_ms: int = Field(default=2000, env="REMOTE_FRAME_MAX_AGE_MS")

    # LLM Model Configuration (OpenRouter)
    llm_model: str = Field(default="anthropic/claude-opus-4", env="LLM_MODEL")
    vision_model: str = Field(default="nvidia/nemotron-nano-12b-v2-vl:free", env="VISION_MODEL")
    compaction_model: str = Field(default="anthropic/claude-sonnet-4", env="COMPACTION_MODEL")
    video_agent_default: bool = Field(default=True, env="VIDEO_AGENT_DEFAULT")

    # OCR Settings
    ocr_languages: List[str] = Field(
        default=["eng", "deu", "fra", "spa", "ita", "por", "rus", "chi_sim"],
        env="OCR_LANGUAGES",
    )
    ocr_confidence_threshold: float = Field(default=0.7, env="OCR_CONFIDENCE_THRESHOLD")
    ocr_timeout: int = Field(default=30, env="OCR_TIMEOUT")

    # Desktop Streaming Settings
    desktop_fps: int = Field(default=5, env="DESKTOP_FPS")
    desktop_quality: int = Field(default=80, env="DESKTOP_QUALITY")
    desktop_scale_factor: float = Field(default=1.0, env="DESKTOP_SCALE_FACTOR")
    max_desktop_clients: int = Field(default=10, env="MAX_DESKTOP_CLIENTS")

    # File Watching Settings
    file_watch_timeout: int = Field(default=60, env="FILE_WATCH_TIMEOUT")
    max_file_watchers: int = Field(default=50, env="MAX_FILE_WATCHERS")
    file_event_buffer_size: int = Field(default=1000, env="FILE_EVENT_BUFFER_SIZE")
    file_watcher_directory: str = Field(default="./data", env="FILE_WATCHER_DIRECTORY")
    file_watcher_patterns: List[str] = Field(
        default=["*.txt", "*.log", "*.json"], env="FILE_WATCHER_PATTERNS"
    )
    file_watcher_debounce_interval: float = Field(
        default=0.5, env="FILE_WATCHER_DEBOUNCE_INTERVAL"
    )

    # Click Automation Settings
    click_timeout: int = Field(default=5, env="CLICK_TIMEOUT")
    click_retry_count: int = Field(default=3, env="CLICK_RETRY_COUNT")
    click_delay_min: float = Field(default=0.01, env="CLICK_DELAY_MIN")
    click_delay_max: float = Field(default=5.0, env="CLICK_DELAY_MAX")

    # WebSocket Settings - Optimized for stability
    websocket_timeout: int = Field(
        default=300, env="WEBSOCKET_TIMEOUT"
    )  # Increased from 60 to 300 seconds
    max_websocket_connections: int = Field(default=100, env="MAX_WEBSOCKET_CONNECTIONS")
    websocket_message_buffer_size: int = Field(
        default=1000, env="WEBSOCKET_MESSAGE_BUFFER_SIZE"
    )
    websocket_ping_interval: int = Field(
        default=60, env="WEBSOCKET_PING_INTERVAL"
    )  # Increased from 30 to 60 seconds
    websocket_ping_timeout: int = Field(
        default=30, env="WEBSOCKET_PING_TIMEOUT"
    )  # Increased from 10 to 30 seconds
    websocket_close_timeout: int = Field(
        default=15, env="WEBSOCKET_CLOSE_TIMEOUT"
    )  # Increased from 5 to 15 seconds
    websocket_max_consecutive_errors: int = Field(
        default=10, env="WEBSOCKET_MAX_CONSECUTIVE_ERRORS"
    )  # Increased from 3 to 10
    websocket_connection_stability_delay: float = Field(
        default=0.5, env="WEBSOCKET_CONNECTION_STABILITY_DELAY"
    )  # Increased from 0.1 to 0.5
    websocket_enable_compression: bool = Field(
        default=True, env="WEBSOCKET_ENABLE_COMPRESSION"
    )
    websocket_max_message_size: int = Field(
        default=2097152, env="WEBSOCKET_MAX_MESSAGE_SIZE"
    )  # Increased from 1MB to 2MB

    # OCR Monitoring Settings
    webhook_url: str = Field(default="", env="WEBHOOK_URL")
    ocr_monitoring_interval: int = Field(default=30, env="OCR_MONITORING_INTERVAL")
    ocr_monitoring_similarity_threshold: float = Field(
        default=0.85, env="OCR_MONITORING_SIMILARITY_THRESHOLD"
    )
    ocr_monitoring_enabled: bool = Field(default=True, env="OCR_MONITORING_ENABLED")

    # Webhook Settings
    webhook_timeout: int = Field(default=10, env="WEBHOOK_TIMEOUT")
    webhook_retry_count: int = Field(default=3, env="WEBHOOK_RETRY_COUNT")
    webhook_retry_delay: int = Field(default=5, env="WEBHOOK_RETRY_DELAY")

    # Performance Settings
    max_concurrent_executions: int = Field(default=10, env="MAX_CONCURRENT_EXECUTIONS")
    execution_timeout: int = Field(default=300, env="EXECUTION_TIMEOUT")
    memory_limit_mb: int = Field(default=1024, env="MEMORY_LIMIT_MB")

    # Proxmox VM Integration Settings
    proxmox_host: str = Field(default="", env="PROXMOX_HOST")
    proxmox_port: int = Field(default=8006, env="PROXMOX_PORT")
    proxmox_username: str = Field(default="", env="PROXMOX_USERNAME")
    proxmox_password: str = Field(default="", env="PROXMOX_PASSWORD")
    proxmox_verify_ssl: bool = Field(default=False, env="PROXMOX_VERIFY_SSL")
    proxmox_default_node: str = Field(
        default="ubuntu-2gb-nbg1-1", env="PROXMOX_DEFAULT_NODE"
    )

    # VM Management Settings
    vm_startup_timeout: int = Field(default=120, env="VM_STARTUP_TIMEOUT")
    vm_shutdown_timeout: int = Field(default=60, env="VM_SHUTDOWN_TIMEOUT")
    vm_vnc_timeout: int = Field(default=30, env="VM_VNC_TIMEOUT")
    vm_auto_start_enabled: bool = Field(default=False, env="VM_AUTO_START_ENABLED")
    vm_backup_enabled: bool = Field(default=True, env="VM_BACKUP_ENABLED")

    # VM ID Ranges
    vm_windows_id_start: int = Field(default=200, env="VM_WINDOWS_ID_START")
    vm_windows_id_end: int = Field(default=299, env="VM_WINDOWS_ID_END")
    vm_linux_id_start: int = Field(default=300, env="VM_LINUX_ID_START")
    vm_linux_id_end: int = Field(default=399, env="VM_LINUX_ID_END")
    vm_template_id_start: int = Field(default=100, env="VM_TEMPLATE_ID_START")
    vm_template_id_end: int = Field(default=199, env="VM_TEMPLATE_ID_END")

    # Security & Authentication Settings
    jwt_secret_key: str = Field(
        default="", env="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS"
    )

    # API Key Settings
    api_key_enabled: bool = Field(default=True, env="API_KEY_ENABLED")
    api_key_header_name: str = Field(default="X-API-Key", env="API_KEY_HEADER_NAME")
    default_api_keys: List[str] = Field(
        default=[], env="DEFAULT_API_KEYS"
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_requests_per_minute: int = Field(
        default=60, env="RATE_LIMIT_REQUESTS_PER_MINUTE"
    )
    rate_limit_burst_size: int = Field(default=10, env="RATE_LIMIT_BURST_SIZE")

    # Paths (use str to avoid Pydantic/Path compatibility issues)
    data_dir: str = Field(default="data", env="DATA_DIR")
    logs_dir: str = Field(default="logs", env="LOGS_DIR")
    temp_dir: str = Field(default="temp", env="TEMP_DIR")
    screenshots_dir: str = Field(default="desktop_screenshots", env="SCREENSHOTS_DIR")
    vm_configs_dir: str = Field(default="vm_configs", env="VM_CONFIGS_DIR")
    auth_keys_dir: str = Field(default="auth_keys", env="AUTH_KEYS_DIR")

    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list
        - Removed legacy Vite fallback port 5173 per project decision
        """
        try:
            if v is None or v == "":
                # Return default if None or empty string
                return [
                    "http://localhost:3000",
                    "http://localhost:3005",
                    "http://localhost:5174",
                    "http://localhost:8080",
                ]
            if isinstance(v, str):
                if v.strip():
                    origins = [
                        origin.strip() for origin in v.split(",") if origin.strip()
                    ]
                    # Validate each origin
                    valid_origins = []
                    for origin in origins:
                        if origin.startswith(("http://", "https://")):
                            valid_origins.append(origin)
                        else:
                            # Skip invalid origins and log warning
                            print(f"Warning: Skipping invalid CORS origin: {origin}")
                    return (
                        valid_origins
                        if valid_origins
                        else [
                            "http://localhost:3000",
                            "http://localhost:3005",
                            "http://localhost:5174",
                            "http://localhost:8080",
                        ]
                    )
                else:
                    # Return default if empty string
                    return [
                        "http://localhost:3000",
                        "http://localhost:3005",
                        "http://localhost:5174",
                        "http://localhost:8080",
                    ]
            return v
        except Exception as e:
            print(f"Warning: Error parsing CORS origins '{v}': {e}. Using defaults.")
            return [
                "http://localhost:3000",
                "http://localhost:3005",
                "http://localhost:5174",
                "http://localhost:8080",
            ]

    @validator("ocr_languages", pre=True)
    def parse_ocr_languages(cls, v):
        """Parse OCR languages from string or list"""
        if isinstance(v, str):
            return [lang.strip() for lang in v.split(",")]
        return v

    @validator("default_api_keys", pre=True)
    def parse_default_api_keys(cls, v):
        """Parse default API keys from string or list"""
        if isinstance(v, str):
            return [key.strip() for key in v.split(",") if key.strip()]
        return v

    @validator("jwt_secret_key")
    def validate_jwt_secret_key(cls, v):
        """Validate JWT secret key length"""
        if v and len(v) < 32:
            raise ValueError("JWT secret key must be at least 32 characters long")
        return v

    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()

    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment"""
        valid_envs = ["development", "testing", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Invalid environment. Must be one of: {valid_envs}")
        return v.lower()

    @validator("desktop_fps")
    def validate_desktop_fps(cls, v):
        """Validate desktop FPS"""
        if not 1 <= v <= 60:
            raise ValueError("Desktop FPS must be between 1 and 60")
        return v

    @validator("desktop_quality")
    def validate_desktop_quality(cls, v):
        """Validate desktop quality"""
        if not 1 <= v <= 100:
            raise ValueError("Desktop quality must be between 1 and 100")
        return v

    @validator("desktop_scale_factor")
    def validate_desktop_scale_factor(cls, v):
        """Validate desktop scale factor"""
        if not 0.1 <= v <= 2.0:
            raise ValueError("Desktop scale factor must be between 0.1 and 2.0")
        return v

    @validator("ocr_confidence_threshold")
    def validate_ocr_confidence_threshold(cls, v):
        """Validate OCR confidence threshold"""
        if not 0.0 <= v <= 1.0:
            raise ValueError("OCR confidence threshold must be between 0.0 and 1.0")
        return v

    @validator("webhook_url")
    def validate_webhook_url(cls, v):
        """Validate webhook URL"""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")
        return v

    @validator("ocr_monitoring_interval")
    def validate_ocr_monitoring_interval(cls, v):
        """Validate OCR monitoring interval"""
        if not 1 <= v <= 3600:
            raise ValueError(
                "OCR monitoring interval must be between 1 and 3600 seconds"
            )
        return v

    @validator("ocr_monitoring_similarity_threshold")
    def validate_ocr_monitoring_similarity_threshold(cls, v):
        """Validate OCR monitoring similarity threshold"""
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                "OCR monitoring similarity threshold must be between 0.0 and 1.0"
            )
        return v

    @validator("webhook_timeout")
    def validate_webhook_timeout(cls, v):
        """Validate webhook timeout"""
        if not 1 <= v <= 300:
            raise ValueError("Webhook timeout must be between 1 and 300 seconds")
        return v

    def create_directories(self):
        """Create necessary directories"""
        for path_attr in ["data_dir", "logs_dir", "temp_dir", "screenshots_dir"]:
            p = getattr(self, path_attr)
            Path(p).mkdir(parents=True, exist_ok=True)

    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration"""
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {"format": self.log_format, "datefmt": "%Y-%m-%d %H:%M:%S"},
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": self.log_level,
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": self.log_level, "handlers": ["console"]},
            "loggers": {
                "trae": {
                    "level": self.log_level,
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn": {
                    "level": "INFO",
                    "handlers": ["console"],
                    "propagate": False,
                },
            },
        }

        # Add file handler if log file is specified
        if self.log_file:
            log_file_path = self.logs_dir / self.log_file
            config["handlers"]["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": self.log_level,
                "formatter": "detailed",
                "filename": str(log_file_path),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
            }
            config["root"]["handlers"].append("file")
            config["loggers"]["trae"]["handlers"].append("file")

        return config

    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == "development"

    def is_testing(self) -> bool:
        """Check if running in testing"""
        return self.environment == "testing"

    class Config:
        """Pydantic config"""

        # Load from root .env if it exists (local dev), env vars override (Docker)
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore VITE_*, OPENROUTER_*, etc. from shared .env
        # Environment variables enabled for proper configuration
        env_prefix = ""


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get global settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.create_directories()
    return _settings


def reload_settings() -> Settings:
    """Reload settings (useful for testing)"""
    global _settings
    _settings = None
    return get_settings()


# Convenience function for common use
settings = get_settings()
