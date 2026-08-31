"""
Brain Logger: Centralized Logging for the_brain

Provides structured logging with configurable levels, handlers,
and component-specific loggers.

Usage:
    from core.brain_logger import get_logger

    logger = get_logger('oscillator')
    logger.info("Processing tokens")
    logger.error("Failed to execute tool", exc_info=True)

Configuration:
    Set environment variables:
    - BRAIN_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
    - BRAIN_LOG_FILE: Path to log file (default: logs/brain.log)
    - BRAIN_LOG_FORMAT: compact, detailed, json (default: detailed)
"""

import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default settings
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "brain.log"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5

# Log format templates
LOG_FORMATS = {
    "compact": "%(levelname)s|%(name)s|%(message)s",
    "detailed": "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    "json": None,  # Handled by JSONFormatter
}

# Component colors (for console output)
COMPONENT_COLORS = {
    "oscillator": "\033[96m",     # Cyan
    "router": "\033[95m",         # Magenta
    "executor": "\033[93m",       # Yellow
    "checkpoint": "\033[92m",     # Green
    "dashboard": "\033[94m",      # Blue
    "adapter": "\033[91m",        # Red
    "bridge": "\033[97m",         # White
}
RESET_COLOR = "\033[0m"


# =============================================================================
# CUSTOM FORMATTERS
# =============================================================================

class ColoredFormatter(logging.Formatter):
    """Formatter that adds color codes for console output."""

    LEVEL_COLORS = {
        logging.DEBUG: "\033[37m",    # Light gray
        logging.INFO: "\033[32m",     # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[41m", # Red background
    }

    def format(self, record):
        # Add level color
        level_color = self.LEVEL_COLORS.get(record.levelno, "")

        # Add component color
        component = record.name.split('.')[-1]
        comp_color = COMPONENT_COLORS.get(component, "")

        # Format message
        original = super().format(record)

        if sys.stdout.isatty():
            # Add colors for terminal
            return f"{comp_color}[{component}]{RESET_COLOR} {level_color}{original}{RESET_COLOR}"
        else:
            return original


class JSONFormatter(logging.Formatter):
    """Formatter that outputs logs as JSON lines."""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        return json.dumps(log_data)


# =============================================================================
# LOGGER FACTORY
# =============================================================================

class BrainLoggerFactory:
    """Factory for creating and managing brain loggers."""

    _instance = None
    _loggers: Dict[str, logging.Logger] = {}
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._setup_root_logger()
            BrainLoggerFactory._initialized = True

    def _setup_root_logger(self):
        """Setup the root brain logger."""
        # Get configuration from environment
        log_level = os.environ.get("BRAIN_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
        log_format = os.environ.get("BRAIN_LOG_FORMAT", "detailed")
        log_file = os.environ.get("BRAIN_LOG_FILE")

        # Create root logger for brain
        root_logger = logging.getLogger("brain")
        root_logger.setLevel(getattr(logging, log_level, logging.INFO))

        # Prevent propagation to root logger
        root_logger.propagate = False

        # Clear existing handlers
        root_logger.handlers = []

        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        if log_format == "json":
            console_handler.setFormatter(JSONFormatter())
        else:
            fmt = LOG_FORMATS.get(log_format, LOG_FORMATS["detailed"])
            console_handler.setFormatter(ColoredFormatter(fmt))

        root_logger.addHandler(console_handler)

        # File handler (if log file specified or default)
        if log_file or os.environ.get("BRAIN_LOG_TO_FILE", "false").lower() == "true":
            self._add_file_handler(root_logger, log_file, log_format)

    def _add_file_handler(
        self,
        logger: logging.Logger,
        log_file: Optional[str],
        log_format: str
    ):
        """Add rotating file handler to logger."""
        # Determine log file path
        if log_file:
            log_path = Path(log_file)
        else:
            log_dir = Path(DEFAULT_LOG_DIR)
            log_dir.mkdir(exist_ok=True)
            log_path = log_dir / DEFAULT_LOG_FILE

        # Create rotating file handler
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        # Use JSON format for file logs (easier to parse)
        file_handler.setFormatter(JSONFormatter())

        logger.addHandler(file_handler)

    def get_logger(self, name: str) -> logging.Logger:
        """Get or create a logger for a component."""
        full_name = f"brain.{name}"

        if full_name not in self._loggers:
            logger = logging.getLogger(full_name)
            self._loggers[full_name] = logger

        return self._loggers[full_name]


# =============================================================================
# PUBLIC API
# =============================================================================

_factory = None


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a brain component.

    Args:
        name: Component name (e.g., 'oscillator', 'router', 'executor')

    Returns:
        Configured logger instance

    Example:
        logger = get_logger('oscillator')
        logger.info("Processing tokens", extra={'extra_data': {'count': 10}})
    """
    global _factory
    if _factory is None:
        _factory = BrainLoggerFactory()
    return _factory.get_logger(name)


def configure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_style: str = "detailed",
    enable_file_logging: bool = False
):
    """
    Configure brain logging system.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (optional)
        format_style: Format style (compact, detailed, json)
        enable_file_logging: Enable logging to file
    """
    os.environ["BRAIN_LOG_LEVEL"] = level
    os.environ["BRAIN_LOG_FORMAT"] = format_style

    if log_file:
        os.environ["BRAIN_LOG_FILE"] = log_file
    if enable_file_logging:
        os.environ["BRAIN_LOG_TO_FILE"] = "true"

    # Reinitialize factory
    global _factory
    _factory = BrainLoggerFactory()
    BrainLoggerFactory._initialized = False
    _factory._setup_root_logger()


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **context
):
    """
    Log a message with additional context data.

    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error)
        message: Log message
        **context: Additional context fields
    """
    log_func = getattr(logger, level.lower())
    log_func(message, extra={"extra_data": context})


# =============================================================================
# CONVENIENCE LOGGERS
# =============================================================================

# Pre-configured loggers for common components
oscillator_logger = None
router_logger = None
executor_logger = None
checkpoint_logger = None
dashboard_logger = None
adapter_logger = None
bridge_logger = None


def _init_convenience_loggers():
    """Initialize convenience loggers."""
    global oscillator_logger, router_logger, executor_logger
    global checkpoint_logger, dashboard_logger, adapter_logger, bridge_logger

    oscillator_logger = get_logger("oscillator")
    router_logger = get_logger("router")
    executor_logger = get_logger("executor")
    checkpoint_logger = get_logger("checkpoint")
    dashboard_logger = get_logger("dashboard")
    adapter_logger = get_logger("adapter")
    bridge_logger = get_logger("bridge")


# Initialize on import
_init_convenience_loggers()


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  BRAIN LOGGER TEST")
    print("=" * 60)

    # Configure with DEBUG level for testing
    configure_logging(level="DEBUG", format_style="detailed")

    # Test various loggers
    loggers = [
        ("oscillator", oscillator_logger),
        ("router", router_logger),
        ("executor", executor_logger),
        ("checkpoint", checkpoint_logger),
    ]

    for name, logger in loggers:
        logger.debug(f"Debug message from {name}")
        logger.info(f"Info message from {name}")
        logger.warning(f"Warning message from {name}")

    # Test error with exception
    try:
        raise ValueError("Test exception")
    except Exception:
        executor_logger.error("Error occurred", exc_info=True)

    # Test with context
    log_with_context(
        oscillator_logger,
        "info",
        "Token processed",
        token="deploy",
        channel="ADVANCE",
        amplitude=0.75
    )

    print("\n" + "=" * 60)
    print("  Logger test complete")
    print("=" * 60)
