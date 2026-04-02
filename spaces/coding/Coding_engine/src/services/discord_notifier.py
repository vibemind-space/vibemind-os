"""
Discord Notifier — Posts generation status and error events to Discord.

Subscribes to EventBus events in the API container and sends formatted
messages to #dev-tasks via DiscordAgent.

Features:
1. Generation Status: STARTED / PROGRESS / COMPLETE
2. Error Notifications: BUILD_FAILED / TEST_FAILED / E2E_FAILED
3. Convergence: Posts when system converges successfully
"""

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

DISCORD_CH_DEV_TASKS = os.environ.get("DISCORD_CH_DEV_TASKS", "1484193408955322399")
COOLDOWN_SECONDS = 30  # Dedup: skip same event type within 30s


class DiscordNotifier:
    """EventBus subscriber that forwards critical events to Discord."""

    def __init__(self, event_bus=None):
        self._discord = None
        self._event_bus = event_bus
        self._project_name = ""
        self._start_time = 0.0
        self._phase_counter = 0
        self._last_post: dict[str, float] = {}
        self._total_tasks = 0
        self._completed_tasks = 0
        self._failed_tasks = 0

        if event_bus:
            self._subscribe(event_bus)
            logger.info("DiscordNotifier initialized with EventBus")

    def _get_discord(self):
        """Lazy-init DiscordAgent."""
        if self._discord is None:
            try:
                from src.tools.discord_agent import DiscordAgent
                self._discord = DiscordAgent()
            except Exception as e:
                logger.warning("DiscordAgent init failed: %s", e)
        return self._discord

    def _subscribe(self, event_bus):
        """Subscribe to relevant EventBus events."""
        try:
            from src.mind.event_bus import EventType

            subscriptions = {
                EventType.GENERATION_REQUESTED: self._on_generation_start,
                EventType.BUILD_SUCCEEDED: self._on_build_success,
                EventType.BUILD_FAILED: self._on_build_failed,
                EventType.TEST_FAILED: self._on_test_failed,
                EventType.E2E_TEST_FAILED: self._on_e2e_failed,
                EventType.CONVERGENCE_ACHIEVED: self._on_convergence,
                EventType.GENERATION_COMPLETE: self._on_generation_complete,
                EventType.SANDBOX_TEST_FAILED: self._on_sandbox_failed,
            }

            for event_type, handler in subscriptions.items():
                try:
                    event_bus.subscribe(event_type, handler)
                except Exception:
                    pass  # Some event types may not exist

            logger.info("DiscordNotifier subscribed to %d events", len(subscriptions))
        except ImportError:
            logger.warning("EventBus not available, DiscordNotifier passive")

    def _should_post(self, event_key: str) -> bool:
        """Cooldown check: skip duplicate events within COOLDOWN_SECONDS."""
        now = time.time()
        last = self._last_post.get(event_key, 0)
        if now - last < COOLDOWN_SECONDS:
            return False
        self._last_post[event_key] = now
        return True

    def _elapsed(self) -> str:
        """Format elapsed time since generation start."""
        if not self._start_time:
            return "0s"
        secs = int(time.time() - self._start_time)
        if secs < 60:
            return "%ds" % secs
        return "%dm %ds" % (secs // 60, secs % 60)

    async def _post(self, message: str):
        """Post message to #dev-tasks channel."""
        discord = self._get_discord()
        if not discord:
            logger.debug("Discord not available, skipping: %s", message[:60])
            return
        try:
            await discord.send(message, channel_id=DISCORD_CH_DEV_TASKS)
        except Exception as e:
            logger.warning("Discord post failed: %s", e)

    # ─── Event Handlers ─────────────────────────────────────

    async def _on_generation_start(self, event):
        """GENERATION_REQUESTED → post start message."""
        if not self._should_post("gen_start"):
            return

        data = event.data or {}
        self._project_name = data.get("project_name", data.get("project_id", "project"))
        self._start_time = time.time()
        self._phase_counter = 0
        self._completed_tasks = 0
        self._failed_tasks = 0

        backend = os.environ.get("LLM_BACKEND", "openrouter")
        msg = (
            "**GENERATION STARTED** | %s\n"
            "Backend: `%s` | Started: <t:%d:T>"
        ) % (self._project_name, backend, int(self._start_time))
        await self._post(msg)

    async def _on_build_success(self, event):
        """BUILD_SUCCEEDED → post progress milestone."""
        self._phase_counter += 1
        self._completed_tasks += 1

        # Post progress at milestones (every 5 builds)
        if self._phase_counter % 5 != 0:
            return
        if not self._should_post("progress"):
            return

        msg = (
            "**PROGRESS** | %s [%d builds]\n"
            "Elapsed: %s | Completed: %d"
        ) % (self._project_name, self._phase_counter, self._elapsed(), self._completed_tasks)
        await self._post(msg)

    async def _on_build_failed(self, event):
        """BUILD_FAILED → post error."""
        self._failed_tasks += 1
        if not self._should_post("build_failed"):
            return

        data = event.data or {}
        error = data.get("error_message", data.get("error", "Unknown error"))
        if isinstance(error, str) and len(error) > 200:
            error = error[:200] + "..."

        msg = (
            "**BUILD FAILED** | %s\n"
            "```\n%s\n```\n"
            "Elapsed: %s"
        ) % (self._project_name, error, self._elapsed())
        await self._post(msg)

    async def _on_test_failed(self, event):
        """TEST_FAILED → post test failure summary."""
        if not self._should_post("test_failed"):
            return

        data = event.data or {}
        test_name = data.get("test_name", data.get("test_file", "unknown"))
        error = data.get("error_message", data.get("failure_reason", ""))
        if isinstance(error, str) and len(error) > 150:
            error = error[:150] + "..."

        msg = (
            "**TEST FAILED** | %s\n"
            "Test: `%s`\n"
            "```\n%s\n```"
        ) % (self._project_name, test_name, error)
        await self._post(msg)

    async def _on_e2e_failed(self, event):
        """E2E_TEST_FAILED → post E2E failure."""
        if not self._should_post("e2e_failed"):
            return

        data = event.data or {}
        test_name = data.get("test_name", "E2E test")
        error = data.get("error_message", data.get("failure_reason", ""))
        if isinstance(error, str) and len(error) > 150:
            error = error[:150] + "..."

        msg = (
            "**E2E FAILED** | %s\n"
            "Test: `%s`\n"
            "```\n%s\n```"
        ) % (self._project_name, test_name, error)
        await self._post(msg)

    async def _on_sandbox_failed(self, event):
        """SANDBOX_TEST_FAILED → post sandbox failure."""
        if not self._should_post("sandbox_failed"):
            return

        data = event.data or {}
        error = data.get("error_message", data.get("error", "Sandbox test failed"))
        if isinstance(error, str) and len(error) > 200:
            error = error[:200] + "..."

        msg = (
            "**SANDBOX FAILED** | %s\n"
            "```\n%s\n```"
        ) % (self._project_name, error)
        await self._post(msg)

    async def _on_convergence(self, event):
        """CONVERGENCE_ACHIEVED → post success summary."""
        if not self._should_post("convergence"):
            return

        data = event.data or {}
        reasons = data.get("reasons", [])
        iteration = data.get("iteration", "?")

        msg = (
            "**CONVERGENCE ACHIEVED** | %s\n"
            "Iteration: %s | Elapsed: %s\n"
            "Builds: %d | Failures: %d\n"
            "Reasons: %s"
        ) % (
            self._project_name,
            iteration,
            self._elapsed(),
            self._phase_counter,
            self._failed_tasks,
            ", ".join(reasons[:3]) if reasons else "all criteria met",
        )
        await self._post(msg)

    async def _on_generation_complete(self, event):
        """GENERATION_COMPLETE → post completion summary."""
        if not self._should_post("gen_complete"):
            return

        data = event.data or {}
        files_count = data.get("files_generated", data.get("files_count", "?"))

        msg = (
            "**GENERATION COMPLETE** | %s\n"
            "Files: %s | Elapsed: %s\n"
            "Builds: %d | Failures: %d"
        ) % (
            self._project_name,
            files_count,
            self._elapsed(),
            self._phase_counter,
            self._failed_tasks,
        )
        await self._post(msg)


# ─── Singleton for easy import ───────────────────────────────

_notifier: Optional[DiscordNotifier] = None


def init_discord_notifier(event_bus=None) -> DiscordNotifier:
    """Initialize the global DiscordNotifier. Call from API startup."""
    global _notifier
    if _notifier is None:
        _notifier = DiscordNotifier(event_bus=event_bus)
    return _notifier


def get_discord_notifier() -> Optional[DiscordNotifier]:
    """Get the global DiscordNotifier instance."""
    return _notifier
