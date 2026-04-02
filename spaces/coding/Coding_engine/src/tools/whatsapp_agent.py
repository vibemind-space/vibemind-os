"""
WhatsApp Agent — Send/receive messages via OpenClaw WhatsApp channel.

Uses the OpenClaw CLI inside the gateway container to deliver WhatsApp
notifications and wait for replies. This enables remote monitoring and
fix-suggestion workflows.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

import os
from src.utils.secrets import get_secret

OPENCLAW_CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw-openclaw-gateway-1")
DEFAULT_WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "+491749708452")
# Token loaded via get_secret for Swarm compatibility
_OPENCLAW_TOKEN = get_secret("openclaw_gateway_token", env_fallback="OPENCLAW_GATEWAY_TOKEN")


@dataclass
class WhatsAppSession:
    session_id: str
    recipient: str
    initial_message: str


class WhatsAppAgent:
    """Send and receive WhatsApp messages via OpenClaw gateway."""

    def __init__(
        self,
        container: str = OPENCLAW_CONTAINER,
        whatsapp_number: str = DEFAULT_WHATSAPP_NUMBER,
    ):
        self.container = container
        self.whatsapp_number = whatsapp_number

    async def _run_openclaw(self, args: list, timeout: int = 60) -> tuple:
        """Run an openclaw command inside the gateway container.
        Uses asyncio.create_subprocess_exec with explicit arg list
        to avoid shell injection (no shell=True)."""
        cmd = ["docker", "exec", self.container, "openclaw"] + args

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return (
                proc.returncode,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.error("OpenClaw command timed out after %ds", timeout)
            return (1, "", "TIMEOUT")
        except Exception as e:
            logger.error("OpenClaw command failed: %s", e)
            return (1, "", str(e))

    async def is_available(self) -> bool:
        """Check if WhatsApp channel is connected."""
        code, out, _ = await self._run_openclaw(
            ["channels", "status"], timeout=15
        )
        return code == 0 and "whatsapp" in out.lower()

    async def send_notification(
        self,
        message: str,
        recipient: Optional[str] = None,
    ) -> Optional[WhatsAppSession]:
        """Send a WhatsApp notification message."""
        to_number = recipient or self.whatsapp_number

        code, out, err = await self._run_openclaw([
            "agent",
            "--to", to_number,
            "--channel", "whatsapp",
            "--deliver",
            "--json",
            "-m", message,
        ], timeout=30)

        if code != 0:
            logger.error("WhatsApp send failed: %s %s", out, err)
            return None

        session_id = self._extract_session_id(out)

        logger.info("WhatsApp sent to %s, session: %s", to_number, session_id)
        return WhatsAppSession(
            session_id=session_id or "unknown",
            recipient=to_number,
            initial_message=message,
        )

    def _extract_session_id(self, output: str) -> Optional[str]:
        """Extract session ID from OpenClaw JSON or text output."""
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                meta = data.get("meta", {})
                agent_meta = meta.get("agentMeta", {})
                sid = agent_meta.get("sessionId", "")
                if sid:
                    return sid
        except json.JSONDecodeError:
            pass

        match = re.search(r"session[_-]?[iI]d[\":\s]+([a-f0-9-]+)", output)
        if match:
            return match.group(1)
        return None

    async def wait_for_reply(
        self,
        session: WhatsAppSession,
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> Optional[str]:
        """Wait for a WhatsApp reply on the given session."""
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            code, out, _ = await self._run_openclaw([
                "agent",
                "--session-id", session.session_id,
                "--channel", "whatsapp",
                "--json",
                "-m", "[POLL: check for new user reply]",
            ], timeout=20)

            if code == 0 and out.strip():
                try:
                    data = json.loads(out)
                    if isinstance(data, dict):
                        payloads = data.get("payloads", [])
                        for payload in payloads:
                            text = payload.get("text", "")
                            if text and text != session.initial_message:
                                logger.info("WhatsApp reply: %s", text[:100])
                                return text
                except json.JSONDecodeError:
                    pass

            logger.debug("No reply yet, waited %d/%ds", elapsed, timeout)

        logger.warning("WhatsApp reply timeout after %ds", timeout)
        return None

    async def send_and_wait(
        self,
        message: str,
        timeout: int = 300,
        recipient: Optional[str] = None,
    ) -> Optional[str]:
        """Send a message and wait for reply."""
        session = await self.send_notification(message, recipient)
        if not session:
            return None
        return await self.wait_for_reply(session, timeout)

    async def send_task_failure(
        self,
        task_id: str,
        task_name: str,
        error: str,
        file_path: str = "",
    ) -> Optional[WhatsAppSession]:
        """Send a formatted task failure notification."""
        parts = [
            "TASK FAILED",
            "ID: %s" % task_id,
            "Name: %s" % task_name,
            "Error: %s" % error[:500],
        ]
        if file_path:
            parts.append("File: %s" % file_path)
        parts.append("Reply with fix suggestion or 'skip' to skip.")

        return await self.send_notification("\n".join(parts))

    async def send_task_approved(self, task_id: str, task_name: str) -> None:
        """Send a brief approval notification."""
        await self.send_notification(
            "TASK APPROVED: %s (%s)" % (task_name, task_id)
        )

    async def send_generation_summary(
        self,
        project: str,
        total: int,
        passed: int,
        failed: int,
    ) -> None:
        """Send end-of-generation summary."""
        await self.send_notification(
            "GENERATION COMPLETE: %s\n"
            "Total: %d | Passed: %d | Failed: %d"
            % (project, total, passed, failed)
        )
