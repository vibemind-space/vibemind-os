"""Logging configuration for the application."""

import logging
import sys
from typing import Optional

from .config import get_settings

# Global logger instance
_logger: Optional[logging.Logger] = None


def setup_logging() -> None:
    """Setup application logging configuration."""
    settings = get_settings()

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=settings.log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_logger(name: str = "trae-backend") -> logging.Logger:
    """Get or create a logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    global _logger

    if _logger is None:
        setup_logging()
        _logger = logging.getLogger(name)

    return _logger


def get_module_logger(module_name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        module_name: Name of the module

    Returns:
        Logger instance for the module
    """
    return logging.getLogger(f"trae-backend.{module_name}")
