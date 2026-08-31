"""
Schedule Space Configuration.

Manages settings for APScheduler-based task scheduling.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduleConfig:
    """Configuration for the Schedule Space."""
    schedule_enabled: bool = False
    default_timezone: str = "Europe/Berlin"
    max_concurrent_jobs: int = 5
    misfire_grace_time: int = 60              # seconds
    redis_stream_schedule: str = "events:tasks:schedule"

    @classmethod
    def from_env(cls) -> "ScheduleConfig":
        """Create config from environment variables."""
        return cls(
            schedule_enabled=os.getenv(
                "SCHEDULE_ENABLED", "false"
            ).lower() in ("true", "1"),
            default_timezone=os.getenv(
                "SCHEDULE_TIMEZONE", "Europe/Berlin"
            ),
            max_concurrent_jobs=int(os.getenv(
                "SCHEDULE_MAX_CONCURRENT", "5"
            )),
            misfire_grace_time=int(os.getenv(
                "SCHEDULE_MISFIRE_GRACE", "60"
            )),
        )


_config: Optional[ScheduleConfig] = None


def get_config() -> ScheduleConfig:
    """Get or create the global ScheduleConfig singleton."""
    global _config
    if _config is None:
        _config = ScheduleConfig.from_env()
    return _config
