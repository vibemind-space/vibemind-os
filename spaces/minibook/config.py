"""
Minibook Space Configuration

Configuration for the Minibook inter-space collaboration layer.
Minibook runs locally and VibeMind communicates via its REST API.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from llm_config import get_model

logger = logging.getLogger(__name__)


@dataclass
class MinibookConfig:
    """Configuration for Minibook Space (inter-space collaboration)."""

    # Minibook API
    minibook_url: str = "http://localhost:3480"
    minibook_frontend_url: str = "http://localhost:3481"

    # Collaboration project (auto-created on startup)
    collaboration_project_name: str = "VibeMind Collaboration"

    # Feature flags
    minibook_enabled: bool = False
    auto_register_spaces: bool = True

    # Polling
    poll_interval_seconds: float = 2.0
    collaboration_timeout_seconds: float = 120.0

    # Redis Stream
    redis_stream_minibook: str = "events:tasks:minibook"

    # ── MinibookHub (central execution) ──────────────────────────────
    hub_enabled: bool = False                      # USE_MINIBOOK_HUB
    hub_sync_timeout: float = 10.0                 # Seconds for single-space wait
    hub_async_timeout: float = 120.0               # Seconds for multi-space
    enrichment_model: str = "openai/gpt-4o-mini"   # LLM for SpaceRouter
    enrichment_enabled: bool = True                # LLM routing on/off
    rachel_prompt_enabled: bool = True             # Rachel metadata on/off

    @classmethod
    def from_env(cls) -> "MinibookConfig":
        """Load configuration from environment variables."""
        return cls(
            minibook_url=os.getenv("MINIBOOK_URL", "http://localhost:3480"),
            minibook_frontend_url=os.getenv("MINIBOOK_FRONTEND_URL", "http://localhost:3481"),
            minibook_enabled=os.getenv("MINIBOOK_ENABLED", "false").lower() in ("true", "1"),
            auto_register_spaces=os.getenv("MINIBOOK_AUTO_REGISTER", "true").lower() in ("true", "1"),
            poll_interval_seconds=float(os.getenv("MINIBOOK_POLL_INTERVAL", "2.0")),
            collaboration_timeout_seconds=float(os.getenv("MINIBOOK_COLLABORATION_TIMEOUT", "120.0")),
            # MinibookHub settings
            hub_enabled=os.getenv("USE_MINIBOOK_HUB", "false").lower() in ("true", "1"),
            hub_sync_timeout=float(os.getenv("MINIBOOK_HUB_SYNC_TIMEOUT", "10.0")),
            hub_async_timeout=float(os.getenv("MINIBOOK_HUB_ASYNC_TIMEOUT", "120.0")),
            enrichment_model=get_model("space_router"),
            enrichment_enabled=os.getenv("MINIBOOK_ENRICHMENT_LLM", "true").lower() in ("true", "1"),
            rachel_prompt_enabled=os.getenv("MINIBOOK_RACHEL_PROMPT", "true").lower() in ("true", "1"),
        )


# Singleton config instance
_config: Optional[MinibookConfig] = None


def get_config() -> MinibookConfig:
    """Get Minibook configuration singleton."""
    global _config
    if _config is None:
        _config = MinibookConfig.from_env()
    return _config


__all__ = ["MinibookConfig", "get_config"]
