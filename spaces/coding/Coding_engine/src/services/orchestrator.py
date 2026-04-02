"""
Event-based Orchestrator Service.

Subscribes to EventBus events (TASK_COMPLETED, TASK_FAILED, BUILD_FAILED, etc.)
and dispatches work to OpenClaw bots via Discord channel messages.

The OpenClaw bots in Discord channels do the actual work:
- Fix-Bot in #fixes → prisma push, eslint --fix, GPT code fix
- Verify-Bot in #testing → build check, file verification, E2E tests
- PR-Bot in #prs → git commit, push, gh pr create
- DevOps-Bot in #orchestrator → container recovery, log analysis

Flow:
  EventBus Event → Orchestrator.think() → Discord Channel Message
  → OpenClaw Bot executes → Posts result → Orchestrator reads → DB update
"""

import asyncio
import logging
import os
import json
from typing import Optional

import httpx

logger = logging.getLogger("orchestrator")


class DiscordPoster:
    """Posts messages to Discord channels via REST API."""

    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://discord.com/api/v10"

    async def post(self, channel_id: str, message: str):
        """Post a message to a Discord channel."""
        if not channel_id or not self.token:
            logger.warning("Cannot post to Discord: missing channel_id or token")
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "%s/channels/%s/messages" % (self.base_url, channel_id),
                    headers={"Authorization": "Bot %s" % self.token},
                    json={"content": message[:2000]},
                )
                if resp.status_code not in (200, 201):
                    logger.warning("Discord post failed: %d %s", resp.status_code, resp.text[:100])
        except Exception as e:
            logger.error("Discord post error: %s", e)


class OrchestratorService:
    """
    Event-based orchestrator that dispatches work to OpenClaw bots via Discord.

    State machine: IDLE → THINKING → DISPATCHING → WAITING → EVALUATING → IDLE
    """

    def __init__(self, event_bus=None, settings: dict = None):
        self.event_bus = event_bus
        self.state = "IDLE"
        self.settings = settings or {}

        # Discord poster
        token = os.environ.get("DISCORD_BOT_TOKEN", "")
        self.discord = DiscordPoster(token)

        # Channel IDs from engine_settings
        discord_cfg = self.settings.get("discord", {})
        channels = discord_cfg.get("channels", {})
        self.channels = {
            "orchestrator": channels.get("orchestrator", ""),
            "fixes": channels.get("fixes", ""),
            "testing": channels.get("testing", ""),
            "prs": channels.get("prs", ""),
            "done": channels.get("done", ""),
            "dev_tasks": channels.get("dev_tasks", ""),
        }

        # Model for think/plan
        models = self.settings.get("models", {})
        self.model = models.get("orchestrator", {}).get("model", "gpt-5.4")

        # OpenAI API key for think()
        self.openai_key = os.environ.get("OPENAI_API_KEY", "")

        # Pending fix/verify requests (task_id → asyncio.Event)
        self._pending = {}

        # Subscribe to EventBus if available
        if event_bus:
            self._subscribe()

        logger.info("OrchestratorService initialized | model=%s | channels=%d",
                     self.model, sum(1 for v in self.channels.values() if v))

    def _subscribe(self):
        """Subscribe to EventBus events."""
        try:
            from src.mind.event_bus import EventType
            self.event_bus.subscribe(EventType.GENERATION_COMPLETE, self._on_generation_complete)
            # Task events are emitted during generation
            self.event_bus.subscribe(EventType.BUILD_FAILED, self._on_build_failed)
            self.event_bus.subscribe(EventType.APP_CRASHED, self._on_app_crashed)
            logger.info("Subscribed to EventBus events")
        except Exception as e:
            logger.warning("Could not subscribe to EventBus: %s", e)

    # ── Event Handlers ──────────────────────────────────────

    async def _on_generation_complete(self, event):
        """Generation finished → orchestrate fix/verify/PR pipeline."""
        data = event.data if hasattr(event, "data") else {}
        completed = data.get("completed", 0)
        failed = data.get("failed", 0)
        project = data.get("project_id", "")

        self.state = "THINKING"
        await self.discord.post(self.channels["orchestrator"],
            "🏁 **GENERATION_COMPLETE** [%s]\n✅ %d completed | ❌ %d failed\n\n"
            "🧠 Orchestrator analyzing results..." % (project, completed, failed))

        if failed > 0:
            self.state = "DISPATCHING"
            await self.discord.post(self.channels["fixes"],
                "🔧 **FIXALL_REQUEST** [%s]\n"
                "%d failed tasks detected. Please fix all.\n"
                "Use: smart fix (prisma → eslint → build → gpt)" % (project, failed))

            await self.discord.post(self.channels["orchestrator"],
                "📋 **PLAN**: Dispatched %d failed tasks to #fixes\n"
                "Waiting for Fix-Bot to complete..." % failed)
            self.state = "WAITING"
        else:
            # No failures → go to verify
            await self._dispatch_verify(project, completed)

    async def _on_build_failed(self, event):
        """Build failed → dispatch to #fixes."""
        data = event.data if hasattr(event, "data") else {}
        error = data.get("error", "Build failed")
        task_id = data.get("task_id", "unknown")

        await self.discord.post(self.channels["fixes"],
            "🔧 **FIX_REQUEST**: `%s`\n"
            "Strategy: `build_fix`\n"
            "Error: ```%s```" % (task_id, error[:500]))

    async def _on_app_crashed(self, event):
        """Container crashed → dispatch to #orchestrator for DevOps-Bot."""
        data = event.data if hasattr(event, "data") else {}
        container = data.get("container", "unknown")
        logs = data.get("logs", "No logs available")

        await self.discord.post(self.channels["orchestrator"],
            "🚨 **CRASH_DETECTED**: Container `%s`\n"
            "```\n%s\n```\n"
            "DevOps-Bot: please analyze and recover." % (container, logs[:500]))

    # ── Dispatch Methods ────────────────────────────────────

    async def _dispatch_verify(self, project: str, task_count: int):
        """Dispatch verification to #testing."""
        self.state = "DISPATCHING"
        await self.discord.post(self.channels["testing"],
            "🔍 **VERIFY_REQUEST** [%s]\n"
            "%d tasks completed. Please verify:\n"
            "1. Files exist\n"
            "2. Build passes\n"
            "3. App starts\n"
            "4. Basic E2E check" % (project, task_count))
        self.state = "WAITING"

    async def _dispatch_pr(self, project: str, title: str = ""):
        """Dispatch PR creation to #prs."""
        self.state = "DISPATCHING"
        pr_title = title or "feat: generated code for %s" % project
        await self.discord.post(self.channels["prs"],
            "📝 **PR_REQUEST** [%s]\n"
            "Title: `%s`\n"
            "Please: git add → commit → push → gh pr create" % (project, pr_title))
        self.state = "WAITING"

    async def _dispatch_review(self, pr_url: str):
        """Dispatch PR review to #prs."""
        await self.discord.post(self.channels["prs"],
            "🔍 **REVIEW_REQUEST**\n"
            "PR: %s\n"
            "Please: review diff → check build → approve/request changes" % pr_url)

    # ── Think (GPT-5.4 Analysis) ────────────────────────────

    async def think(self, situation: str) -> dict:
        """Use GPT to analyze a situation and create a plan."""
        if not self.openai_key:
            return {"strategy": "default", "details": "No API key for thinking"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % self.openai_key},
                    json={
                        "model": self.model if "gpt" in self.model else "gpt-4.1",
                        "messages": [
                            {"role": "system", "content": (
                                "You are a code generation orchestrator. "
                                "Analyze the situation and output a JSON plan: "
                                '{"strategy": "prisma_push|eslint_fix|gpt_fix|build_check|verify|pr", '
                                '"details": "what to do", "priority": "high|medium|low"}'
                            )},
                            {"role": "user", "content": situation[:3000]},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.1,
                    },
                )

                if resp.status_code != 200:
                    return {"strategy": "default", "details": "GPT error: %d" % resp.status_code}

                content = resp.json()["choices"][0]["message"]["content"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"strategy": "default", "details": content[:200]}
        except Exception as e:
            return {"strategy": "default", "details": str(e)[:200]}

    # ── Process Bot Responses ───────────────────────────────

    async def process_bot_response(self, channel: str, message: str):
        """
        Called when an OpenClaw bot posts a response in a channel.
        Parses the response and takes next action.
        """
        msg_upper = message.upper()

        if "FIX_COMPLETE" in msg_upper or "SMART FIX COMPLETE" in msg_upper:
            self.state = "EVALUATING"
            await self.discord.post(self.channels["orchestrator"],
                "✅ **Fix-Bot completed.** Evaluating results...")

            # Check if there are still failed tasks
            # (The status loop in discord_listener will handle this)
            self.state = "IDLE"

        elif "FIX_FAILED" in msg_upper or "PERMANENT_FAIL" in msg_upper:
            self.state = "EVALUATING"
            await self.discord.post(self.channels["orchestrator"],
                "❌ **Fix-Bot reported failures.** Manual intervention may be needed.")
            self.state = "IDLE"

        elif "VERIFY_PASSED" in msg_upper:
            self.state = "EVALUATING"
            await self.discord.post(self.channels["orchestrator"],
                "✅ **Verification passed!** Dispatching PR creation...")
            await self._dispatch_pr("")
            self.state = "IDLE"

        elif "VERIFY_FAILED" in msg_upper:
            self.state = "EVALUATING"
            await self.discord.post(self.channels["orchestrator"],
                "❌ **Verification failed.** Dispatching fixes...")
            # Could dispatch back to fix-bot
            self.state = "IDLE"

        elif "PR_CREATED" in msg_upper:
            # Extract PR URL if present
            import re
            url_match = re.search(r'https://github\.com/\S+', message)
            if url_match:
                await self._dispatch_review(url_match.group())
            self.state = "IDLE"

        elif "PR_APPROVED" in msg_upper or "PR_MERGED" in msg_upper:
            await self.discord.post(self.channels["done"],
                "🎉 **Pipeline Complete!**\n"
                "Generation → Fix → Verify → PR → Merged ✅")
            self.state = "IDLE"

    # ── Manual Triggers ─────────────────────────────────────

    async def trigger_fixall(self, project: str, failed_count: int):
        """Manually trigger fix-all pipeline (from UI or Discord command)."""
        self.state = "DISPATCHING"
        await self.discord.post(self.channels["orchestrator"],
            "🔧 **Manual FIXALL triggered** [%s] — %d failed tasks" % (project, failed_count))
        await self.discord.post(self.channels["fixes"],
            "🔧 **FIXALL_REQUEST** [%s]\n%d failed tasks. Please fix all." % (project, failed_count))
        self.state = "WAITING"

    async def trigger_verify(self, project: str):
        """Manually trigger verification pipeline."""
        await self._dispatch_verify(project, 0)

    async def trigger_pr(self, project: str, title: str = ""):
        """Manually trigger PR creation."""
        await self._dispatch_pr(project, title)


# ── Singleton ─────────────────────────────────────────────

_instance: Optional[OrchestratorService] = None


def get_orchestrator(event_bus=None, settings=None) -> OrchestratorService:
    """Get or create the orchestrator singleton."""
    global _instance
    if _instance is None:
        _instance = OrchestratorService(event_bus=event_bus, settings=settings or {})
    return _instance
