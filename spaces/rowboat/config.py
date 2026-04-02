"""
Roarboot Space Configuration

Configuration for the Rowboat Knowledge Graph integration.
Rowboat runs as a Docker container and VibeMind communicates
via its HTTP API (Python SDK).
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RoarbootConfig:
    """Configuration for Roarboot Space (Rowboat integration)."""

    # Rowboat API
    rowboat_url: str = "http://localhost:3000"
    rowboat_api_key: str = ""
    rowboat_project_id: str = ""

    # OpenAI (required by Rowboat)
    openai_api_key: str = ""

    # Docker
    docker_compose_path: str = ""
    auto_start_docker: bool = False

    # Feature flags
    rowboat_enabled: bool = True

    # Redis Stream
    redis_stream_roarboot: str = "events:tasks:roarboot"

    @classmethod
    def from_env(cls) -> "RoarbootConfig":
        """Load configuration from environment variables."""
        return cls(
            # Rowboat API
            rowboat_url=os.getenv("ROWBOAT_URL", "http://localhost:3000"),
            rowboat_api_key=os.getenv("ROWBOAT_API_KEY", ""),
            rowboat_project_id=os.getenv("ROWBOAT_PROJECT_ID", ""),

            # OpenAI
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),

            # Docker
            docker_compose_path=os.getenv(
                "ROWBOAT_DOCKER_COMPOSE",
                os.path.join(os.path.dirname(__file__), "rowboat", "docker-compose.yml")
            ),
            auto_start_docker=os.getenv("ROWBOAT_AUTO_START", "false").lower() in ("true", "1"),

            # Feature flags
            rowboat_enabled=os.getenv("ROWBOAT_ENABLED", "true").lower() in ("true", "1"),

            # Redis Stream
            redis_stream_roarboot=os.getenv("REDIS_STREAM_ROARBOOT", "events:tasks:roarboot"),
        )


# Singleton config instance
_config: Optional[RoarbootConfig] = None


def get_config() -> RoarbootConfig:
    """Get Roarboot configuration singleton."""
    global _config
    if _config is None:
        _config = RoarbootConfig.from_env()
    return _config


__all__ = ["RoarbootConfig", "get_config"]
