"""
MiroFish Space Configuration

Configuration for the MiroFish-Offline prediction engine integration.
MiroFish runs as a Docker container (Flask + Neo4j + Ollama) and
VibeMind communicates via its HTTP API.
"""

import os
from dataclasses import dataclass
from typing import Optional

from llm_config import get_model


@dataclass
class MiroFishConfig:
    """Configuration for MiroFish Space (prediction engine integration)."""

    # MiroFish API
    mirofish_url: str = "http://localhost:5001"

    # Neo4j (used by MiroFish internally)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "mirofish"

    # LLM (OpenRouter free model, or any OpenAI-compatible API)
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model_name: str = ""
    llm_api_key: str = ""

    # Docker
    docker_compose_path: str = ""
    auto_start_docker: bool = False

    # Feature flags
    mirofish_enabled: bool = False

    # Redis Stream
    redis_stream_mirofish: str = "events:tasks:mirofish_pred"

    # Timeouts (seconds)
    build_timeout: int = 300
    simulation_timeout: int = 600
    report_timeout: int = 300

    @classmethod
    def from_env(cls) -> "MiroFishConfig":
        """Load configuration from environment variables."""
        return cls(
            # MiroFish API
            mirofish_url=os.getenv("MIROFISH_URL", "http://localhost:5001"),

            # Neo4j
            neo4j_uri=os.getenv("MIROFISH_NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("MIROFISH_NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("MIROFISH_NEO4J_PASSWORD", "mirofish"),

            # LLM
            llm_base_url=os.getenv("MIROFISH_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            llm_model_name=os.getenv("MIROFISH_LLM_MODEL") or get_model("mirofish_openrouter"),
            llm_api_key=os.getenv("MIROFISH_LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", "")),

            # Docker
            docker_compose_path=os.getenv(
                "MIROFISH_DOCKER_COMPOSE",
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "mirofish", "docker-compose.yml")
            ),
            auto_start_docker=os.getenv("MIROFISH_AUTO_START", "false").lower() in ("true", "1"),

            # Feature flags
            mirofish_enabled=os.getenv("MIROFISH_ENABLED", "false").lower() in ("true", "1"),

            # Redis Stream
            redis_stream_mirofish=os.getenv("REDIS_STREAM_MIROFISH", "events:tasks:mirofish_pred"),

            # Timeouts
            build_timeout=int(os.getenv("MIROFISH_BUILD_TIMEOUT", "300")),
            simulation_timeout=int(os.getenv("MIROFISH_SIMULATION_TIMEOUT", "600")),
            report_timeout=int(os.getenv("MIROFISH_REPORT_TIMEOUT", "300")),
        )


# Singleton config instance
_config: Optional[MiroFishConfig] = None


def get_config() -> MiroFishConfig:
    """Get MiroFish configuration singleton."""
    global _config
    if _config is None:
        _config = MiroFishConfig.from_env()
    return _config


__all__ = ["MiroFishConfig", "get_config"]
