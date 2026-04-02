"""
Discord -> CLI Trigger Service.

Monitors Discord #fixes and #testing channels for error messages.
When an error is detected:
1. Posts to N8N (Minibook) webhook to trigger a workflow
2. N8N routes to the appropriate CLI tool via @mentions:
   - @kilo -> Kilo CLI fix
   - @claude -> Claude CLI fix
   - @automation -> Automation UI debug
3. The fix result is posted back to Discord #fixes

This implements Dave's architecture where Discord is the MQ
and Minibook (N8N) is the workflow router.
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

MINIBOOK_URL = os.environ.get("MINIBOOK_URL", "http://localhost:3456")
MINIBOOK_WEBHOOK = os.environ.get("MINIBOOK_WEBHOOK_URL", "%s/webhook/discord-error" % MINIBOOK_URL)

# Discord channel IDs (same as discord_mq.py)
CHANNELS = {
    "fixes": os.environ.get("DISCORD_CH_FIXES", "1484193412679733302"),
    "testing": os.environ.get("DISCORD_CH_TESTING", "1484193415364214958"),
    "general": os.environ.get("DISCORD_CH_GENERAL", "1484160715580510242"),
}

ENGINE_BOT = os.environ.get("DISCORD_BOT_TOKEN", "")


class DiscordCLITrigger:
    """Watches Discord for errors and triggers CLI tools via N8N."""

    def __init__(self):
        self._running = False
        self._poll_task = None

    async def start(self):
        """Start polling Discord for error messages."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("[DiscordCLI] Trigger started, watching #fixes and #testing")

    async def stop(self):
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    async def _poll_loop(self):
        """Poll Discord channels for error messages."""
        last_message_ids = {}

        while self._running:
            try:
                for channel_name in ["fixes", "testing"]:
                    channel_id = CHANNELS.get(channel_name)
                    if not channel_id or not ENGINE_BOT:
                        continue

                    async with httpx.AsyncClient(timeout=10) as client:
                        params = {"limit": 5}
                        last_id = last_message_ids.get(channel_name)
                        if last_id:
                            params["after"] = last_id

                        resp = await client.get(
                            "https://discord.com/api/v10/channels/%s/messages" % channel_id,
                            headers={"Authorization": "Bot %s" % ENGINE_BOT},
                            params=params,
                        )

                        if resp.status_code != 200:
                            continue

                        messages = resp.json()
                        if not messages:
                            continue

                        # Update last seen
                        last_message_ids[channel_name] = messages[0]["id"]

                        for msg in messages:
                            content = msg.get("content", "")
                            # Look for error patterns
                            if any(kw in content.lower() for kw in ["error", "failed", "fix_needed", "fix_and_retest"]):
                                await self._trigger_n8n(channel_name, content, msg.get("id"))

            except Exception as e:
                logger.warning("[DiscordCLI] Poll error: %s", e)

            await asyncio.sleep(15)  # Poll every 15 seconds

    async def _trigger_n8n(self, channel: str, error_content: str, message_id: str = ""):
        """Send error to N8N webhook for routing to CLI tools."""
        try:
            # Detect which tool to route to based on @mentions or content
            tool = "openrouter"  # default
            if "@kilo" in error_content.lower():
                tool = "kilo"
            elif "@claude" in error_content.lower():
                tool = "claude"
            elif "@automation" in error_content.lower() or "visual" in error_content.lower():
                tool = "automation_ui"

            payload = {
                "source": "discord",
                "channel": channel,
                "message_id": message_id,
                "error": error_content[:2000],
                "tool": tool,
                "timestamp": asyncio.get_event_loop().time(),
            }

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(MINIBOOK_WEBHOOK, json=payload)
                if resp.status_code in (200, 201):
                    logger.info("[DiscordCLI] Triggered N8N for %s error (tool=%s)", channel, tool)
                else:
                    # N8N not available -- handle locally
                    logger.warning("[DiscordCLI] N8N webhook returned %d, handling locally", resp.status_code)
                    await self._handle_locally(tool, error_content)
        except httpx.ConnectError:
            # N8N not running -- handle locally
            logger.info("[DiscordCLI] N8N not available, handling error locally with %s", tool)
            await self._handle_locally(tool, error_content)
        except Exception as e:
            logger.warning("[DiscordCLI] N8N trigger failed: %s", e)

    async def _handle_locally(self, tool: str, error_content: str):
        """Fallback: handle error locally when N8N is not available."""
        try:
            if tool == "automation_ui":
                # Call Automation UI debug endpoint
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "http://localhost:8007/api/llm/intent",
                        json={
                            "intent": "debug this error: %s" % error_content[:500],
                            "conversation_id": "discord-trigger",
                        },
                    )
                    logger.info("[DiscordCLI] Automation UI response: %d", resp.status_code)
            else:
                # Call generate-code endpoint with fix prompt
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        "http://localhost:8000/generate-code",
                        json={
                            "file_path": "src/fix.ts",
                            "task_description": "Fix this error: %s" % error_content[:500],
                            "backend": tool if tool in ("kilo", "claude") else "openrouter",
                        },
                    )
                    logger.info("[DiscordCLI] Fix via %s: %d", tool, resp.status_code)
        except Exception as e:
            logger.warning("[DiscordCLI] Local handling failed: %s", e)


# Singleton
_trigger_instance: Optional[DiscordCLITrigger] = None


def get_discord_cli_trigger() -> DiscordCLITrigger:
    global _trigger_instance
    if _trigger_instance is None:
        _trigger_instance = DiscordCLITrigger()
    return _trigger_instance
