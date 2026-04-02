# -*- coding: utf-8 -*-
"""
Logging utilities for MCP agents.
Provides consistent logging setup across all MCP server agents.
"""
import logging
import os
import sys
from pathlib import Path


def setup_logging(logger_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Set up a logger for an MCP agent with consistent formatting.

    Args:
        logger_name: Name for the logger (typically session_id or "agent_{tool}")
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance

    The logger:
        - Outputs to stderr for real-time monitoring
        - Uses consistent format: timestamp - name - level - message
        - UTF-8 encoding on Windows for Unicode support
        - Can be used across multiple modules with same name

    Examples:
        >>> logger = setup_logging("time_agent_abc123")
        >>> logger.info("Agent started")
        >>> logger.error("Task failed: %s", error)
    """
    # Get or create logger
    logger = logging.getLogger(logger_name)

    # Only configure if not already configured (prevents duplicate handlers)
    if not logger.handlers:
        # Set logging level
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        logger.setLevel(numeric_level)

        # Create console handler (stderr for real-time output)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(numeric_level)

        # Create formatter with timestamp
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)

        # Prevent propagation to root logger (avoid duplicate logs)
        logger.propagate = False

    return logger


def setup_file_logging(logger_name: str, log_file_path: str, log_level: str = "INFO") -> logging.Logger:
    """
    Set up a logger that writes to both console and file.

    Args:
        logger_name: Name for the logger
        log_file_path: Path to log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance with file and console handlers

    Examples:
        >>> logger = setup_file_logging("agent", "data/logs/agent.log")
        >>> logger.info("This goes to both console and file")
    """
    # Get or create logger
    logger = logging.getLogger(logger_name)

    # Only configure if not already configured
    if not logger.handlers:
        # Set logging level
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        logger.setLevel(numeric_level)

        # Create console handler
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)

        # Create file handler
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_file_path,
            mode='a',
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)

        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Add handlers to logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        # Prevent propagation to root logger
        logger.propagate = False

    return logger


def get_log_level_from_env() -> str:
    """
    Get logging level from environment variables.

    Returns:
        Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Environment Variables:
        LOG_LEVEL: Preferred log level
        MCP_LOG_LEVEL: Alternative log level variable

    Default:
        INFO
    """
    log_level = os.getenv("LOG_LEVEL") or os.getenv("MCP_LOG_LEVEL") or "INFO"
    return log_level.upper()


if __name__ == "__main__":
    # Test logging setup
    print("Testing logging utilities...")

    # Test basic logger
    logger1 = setup_logging("test_agent_1")
    logger1.info("This is an info message")
    logger1.warning("This is a warning")
    logger1.debug("This debug message won't appear (level=INFO)")

    # Test with DEBUG level
    logger2 = setup_logging("test_agent_2", log_level="DEBUG")
    logger2.debug("This debug message WILL appear")
    logger2.info("Test complete")

    print("\n✓ Logging utilities test complete")
