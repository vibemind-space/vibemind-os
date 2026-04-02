"""
Rate Limit Handler for Claude CLI

Handles API rate limit errors with:
- Configurable initial wait period (default: 4 hours)
- Periodic retry with test ping (default: every 30 minutes)
- Maximum retry attempts before giving up

Usage:
    handler = RateLimitHandler(
        initial_wait_hours=4.0,
        retry_interval_minutes=30.0,
        max_retries=10,
    )

    # When rate limit detected
    recovered = await handler.handle_rate_limit()
    if recovered:
        # Resume generation
    else:
        # Max retries exceeded, save and exit
"""

import asyncio
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Callable, Optional

import structlog

from ..tools.claude_agent_tool import find_claude_executable

logger = structlog.get_logger(__name__)


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str = "API rate limit exceeded", retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds until retry, if provided by API


class RateLimitHandler:
    """
    Handles rate limit errors with wait and retry logic.

    Flow:
    1. Rate limit detected -> save checkpoint
    2. Wait initial_wait_hours (4h by default)
    3. Test CLI with minimal prompt
    4. If still rate limited -> wait retry_interval_minutes (30min)
    5. Repeat until success or max_retries exceeded
    """

    def __init__(
        self,
        initial_wait_hours: float = 4.0,
        retry_interval_minutes: float = 30.0,
        max_retries: int = 10,
        on_wait_start: Optional[Callable[[float], None]] = None,
        on_retry: Optional[Callable[[int, int], None]] = None,
    ):
        """
        Initialize rate limit handler.

        Args:
            initial_wait_hours: Hours to wait after first rate limit hit
            retry_interval_minutes: Minutes to wait between retries
            max_retries: Maximum number of retry attempts
            on_wait_start: Callback when wait period starts (receives hours)
            on_retry: Callback on each retry (receives attempt, max_retries)
        """
        self.initial_wait = timedelta(hours=initial_wait_hours)
        self.retry_interval = timedelta(minutes=retry_interval_minutes)
        self.max_retries = max_retries
        self.on_wait_start = on_wait_start
        self.on_retry = on_retry

        # State
        self.rate_limit_hit_at: Optional[datetime] = None
        self.retry_count: int = 0
        self.last_test_at: Optional[datetime] = None

    async def handle_rate_limit(self) -> bool:
        """
        Handle rate limit with wait and retry.

        Returns True if rate limit cleared and ready to resume.
        Returns False if max retries exceeded.
        """
        self.rate_limit_hit_at = datetime.utcnow()
        self.retry_count = 0

        logger.warning(
            "rate_limit_detected",
            initial_wait_hours=self.initial_wait.total_seconds() / 3600,
            max_retries=self.max_retries,
        )

        # Initial wait
        wait_hours = self.initial_wait.total_seconds() / 3600
        if self.on_wait_start:
            self.on_wait_start(wait_hours)

        logger.info(
            "rate_limit_initial_wait",
            wait_hours=wait_hours,
            resume_at=(datetime.utcnow() + self.initial_wait).isoformat(),
        )

        await self._wait_with_progress(self.initial_wait)

        # Retry loop
        while self.retry_count < self.max_retries:
            self.retry_count += 1

            if self.on_retry:
                self.on_retry(self.retry_count, self.max_retries)

            logger.info(
                "rate_limit_testing",
                attempt=self.retry_count,
                max_retries=self.max_retries,
            )

            if await self.test_cli_available():
                logger.info(
                    "rate_limit_cleared",
                    total_wait_hours=(datetime.utcnow() - self.rate_limit_hit_at).total_seconds() / 3600,
                    retry_count=self.retry_count,
                )
                return True

            if self.retry_count < self.max_retries:
                wait_minutes = self.retry_interval.total_seconds() / 60
                logger.info(
                    "rate_limit_still_active",
                    next_retry_minutes=wait_minutes,
                    attempt=self.retry_count,
                )
                await self._wait_with_progress(self.retry_interval)

        logger.error(
            "rate_limit_max_retries_exceeded",
            retry_count=self.retry_count,
            total_wait_hours=(datetime.utcnow() - self.rate_limit_hit_at).total_seconds() / 3600,
        )
        return False

    async def test_cli_available(self) -> bool:
        """
        Test if Claude CLI is available (rate limit cleared).

        Sends a minimal prompt to check if API responds without rate limit.
        Uses --max-turns 1 to minimize token usage.
        """
        self.last_test_at = datetime.utcnow()

        try:
            # Minimal test command
            claude_exe = find_claude_executable() or "claude"
            cmd = [
                claude_exe,
                "-p", "Reply with just: OK",
                "--max-turns", "1",
                "--output-format", "text",
            ]

            logger.debug("rate_limit_test_cmd", cmd=" ".join(cmd))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=60.0,  # 1 minute timeout for test
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.warning("rate_limit_test_timeout")
                return False

            stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""

            # Check for rate limit in output
            combined = (stdout_text + stderr_text).lower()
            if "rate limit" in combined or "rate_limit" in combined:
                logger.debug(
                    "rate_limit_test_failed",
                    stderr=stderr_text[:200] if stderr_text else None,
                )
                return False

            # Check for success
            if process.returncode == 0:
                logger.debug(
                    "rate_limit_test_success",
                    response=stdout_text[:100] if stdout_text else None,
                )
                return True

            # Non-zero exit but not rate limit - might be other error
            logger.warning(
                "rate_limit_test_error",
                returncode=process.returncode,
                stderr=stderr_text[:200] if stderr_text else None,
            )
            return False

        except FileNotFoundError:
            logger.error("claude_cli_not_found")
            return False
        except Exception as e:
            logger.error(
                "rate_limit_test_exception",
                error=str(e),
            )
            return False

    async def _wait_with_progress(self, duration: timedelta) -> None:
        """
        Wait for duration with periodic progress logging.

        Logs progress every 15 minutes.
        """
        total_seconds = duration.total_seconds()
        start_time = datetime.utcnow()
        end_time = start_time + duration

        # Log every 15 minutes
        log_interval = 15 * 60  # 15 minutes in seconds
        next_log = log_interval

        elapsed = 0
        while elapsed < total_seconds:
            # Sleep in 60-second chunks for responsiveness
            sleep_time = min(60, total_seconds - elapsed)
            await asyncio.sleep(sleep_time)
            elapsed += sleep_time

            # Log progress
            if elapsed >= next_log:
                remaining = total_seconds - elapsed
                remaining_hours = remaining / 3600
                logger.info(
                    "rate_limit_waiting",
                    elapsed_minutes=elapsed / 60,
                    remaining_hours=round(remaining_hours, 1),
                    resume_at=end_time.isoformat(),
                )
                next_log += log_interval

    def get_status(self) -> dict:
        """Get current rate limit handler status."""
        return {
            "rate_limit_hit_at": self.rate_limit_hit_at.isoformat() if self.rate_limit_hit_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "last_test_at": self.last_test_at.isoformat() if self.last_test_at else None,
            "initial_wait_hours": self.initial_wait.total_seconds() / 3600,
            "retry_interval_minutes": self.retry_interval.total_seconds() / 60,
        }


async def test_rate_limit_handler():
    """Test the rate limit handler (for development)."""
    handler = RateLimitHandler(
        initial_wait_hours=0.001,  # ~3.6 seconds for testing
        retry_interval_minutes=0.05,  # ~3 seconds for testing
        max_retries=3,
    )

    # Test CLI availability
    available = await handler.test_cli_available()
    print(f"CLI available: {available}")

    # If you want to test the full flow (warning: will wait)
    # recovered = await handler.handle_rate_limit()
    # print(f"Recovered: {recovered}")


if __name__ == "__main__":
    # Run test
    asyncio.run(test_rate_limit_handler())
