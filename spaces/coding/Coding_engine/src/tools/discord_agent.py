"""
Discord Agent — Send/receive messages via Discord API directly.

Uses the Discord REST API with bot token for reliable message delivery.
No OpenClaw agent processing — messages are sent exactly as provided.

Env vars:
    DISCORD_BOT_TOKEN: Bot token from Discord Developer Portal
    DISCORD_CHANNEL_ID: Default channel to post to
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

from src.utils.secrets import get_secret

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
DISCORD_BOT_TOKEN = get_secret("discord_bot_token_engine", env_fallback="DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")


@dataclass
class DiscordMessage:
    message_id: str
    channel_id: str
    content: str


class DiscordAgent:
    """Send and receive Discord messages via REST API."""

    def __init__(
        self,
        bot_token: str = "",
        channel_id: str = "",
    ):
        self.bot_token = bot_token or DISCORD_BOT_TOKEN
        self.channel_id = channel_id or DISCORD_CHANNEL_ID
        self.headers = {
            "Authorization": "Bot %s" % self.bot_token,
            "Content-Type": "application/json",
        }

    async def send(
        self,
        message: str,
        channel_id: str = "",
    ) -> Optional[DiscordMessage]:
        """Send a message to a Discord channel."""
        target = channel_id or self.channel_id
        if not target or not self.bot_token:
            logger.error("Discord not configured: token=%s channel=%s",
                         bool(self.bot_token), target)
            return None

        url = "%s/channels/%s/messages" % (DISCORD_API, target)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self.headers,
                    json={"content": message[:2000]},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("Discord sent: %s", message[:80])
                    return DiscordMessage(
                        message_id=data["id"],
                        channel_id=target,
                        content=message,
                    )
                else:
                    logger.error("Discord send failed: %d %s",
                                 resp.status_code, resp.text[:200])
                    return None
        except Exception as e:
            logger.error("Discord send error: %s", e)
            return None

    async def read_recent(
        self,
        limit: int = 10,
        channel_id: str = "",
    ) -> list:
        """Read recent messages from a channel."""
        target = channel_id or self.channel_id
        url = "%s/channels/%s/messages?limit=%d" % (DISCORD_API, target, limit)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
                return []
        except Exception as e:
            logger.error("Discord read error: %s", e)
            return []

    async def wait_for_reply(
        self,
        after_message_id: str,
        timeout: int = 300,
        poll_interval: int = 5,
        channel_id: str = "",
    ) -> Optional[str]:
        """Wait for a new message after a specific message ID."""
        target = channel_id or self.channel_id
        url = "%s/channels/%s/messages?after=%s&limit=5" % (
            DISCORD_API, target, after_message_id
        )
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, headers=self.headers, timeout=10)
                    if resp.status_code == 200:
                        messages = resp.json()
                        for msg in messages:
                            # Skip bot messages
                            if not msg.get("author", {}).get("bot", False):
                                logger.info("Discord reply: %s", msg["content"][:100])
                                return msg["content"]
            except Exception:
                pass
        logger.warning("Discord reply timeout after %ds", timeout)
        return None

    async def send_and_wait(
        self,
        message: str,
        timeout: int = 300,
        channel_id: str = "",
    ) -> Optional[str]:
        """Send message and wait for human reply."""
        sent = await self.send(message, channel_id)
        if not sent:
            return None
        return await self.wait_for_reply(sent.message_id, timeout, channel_id=channel_id)

    # --- Convenience methods for task pipeline ---

    async def send_task_failure(
        self,
        task_id: str,
        task_name: str,
        error: str,
        file_path: str = "",
    ) -> Optional[DiscordMessage]:
        """Send formatted task failure."""
        parts = [
            "**TASK FAILED**",
            "ID: `%s`" % task_id,
            "Name: %s" % task_name,
            "Error: ```%s```" % error[:1000],
        ]
        if file_path:
            parts.append("File: `%s`" % file_path)
        parts.append("_Reply with fix suggestion or 'skip'_")
        return await self.send("\n".join(parts))

    async def send_task_approved(self, task_id: str, task_name: str) -> None:
        """Send brief approval."""
        await self.send("**TASK APPROVED** %s (`%s`)" % (task_name, task_id))

    async def send_generation_summary(
        self,
        project: str,
        total: int,
        passed: int,
        failed: int,
    ) -> None:
        """Send end-of-generation summary."""
        await self.send(
            "**GENERATION COMPLETE: %s**\n"
            "Total: %d | Passed: %d | Failed: %d"
            % (project, total, passed, failed)
        )

    async def send_status(self, message: str) -> None:
        """Send a status update."""
        await self.send("**STATUS** %s" % message)
