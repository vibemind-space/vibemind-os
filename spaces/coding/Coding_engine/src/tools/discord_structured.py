"""
Structured Discord Messages for Agent-to-Agent Communication.

Discord serves as the message bus between Coding Engine and Analyzer agents.
Messages are structured so agents can parse and act on them automatically,
while remaining human-readable in Discord.

Message Types:
  FIX_NEEDED     - Code error requiring fix (frontend/backend separated)
  TEST_FAILED    - Test failure with details
  INTEGRATION    - API contract mismatch between FE/BE
  BEHAVIOR       - Runtime behavior issue
  TIMING         - Performance/timing problem
  DEBUG_LOG      - Stack trace / debug output
  FIX_APPLIED    - Fix suggestion from Analyzer
  TASK_VERIFIED  - Task passed verification
  EPIC_DONE      - All tasks in epic verified
  GENERATION_SUMMARY - Full project summary

Each message has a parseable header block that agents can extract.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.tools.discord_agent import DiscordAgent, DiscordMessage

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    FIX_NEEDED = "FIX_NEEDED"
    TEST_FAILED = "TEST_FAILED"
    INTEGRATION = "INTEGRATION"
    BEHAVIOR = "BEHAVIOR"
    TIMING = "TIMING"
    DEBUG_LOG = "DEBUG_LOG"
    FIX_APPLIED = "FIX_APPLIED"
    TASK_VERIFIED = "TASK_VERIFIED"
    EPIC_DONE = "EPIC_DONE"
    GENERATION_SUMMARY = "GENERATION_SUMMARY"


class Scope(str, Enum):
    FRONTEND = "FRONTEND"
    BACKEND = "BACKEND"
    FULLSTACK = "FULLSTACK"
    DATABASE = "DATABASE"
    INFRA = "INFRA"


@dataclass
class StructuredMessage:
    """A structured message for Discord agent communication."""
    msg_type: MessageType
    scope: Scope = Scope.FULLSTACK
    epic_id: str = ""
    task_id: str = ""
    task_name: str = ""
    file_path: str = ""
    line_number: int = 0
    error: str = ""
    stack_trace: str = ""
    context: str = ""
    diff: str = ""
    action: str = ""
    status: str = ""
    details: dict = field(default_factory=dict)

    def to_discord(self) -> str:
        """Format as Discord message with parseable header."""
        lines = []

        # Emoji prefix by type
        emoji = {
            MessageType.FIX_NEEDED: "\u274c",
            MessageType.TEST_FAILED: "\U0001f6a8",
            MessageType.INTEGRATION: "\U0001f517",
            MessageType.BEHAVIOR: "\U0001f41b",
            MessageType.TIMING: "\u23f1\ufe0f",
            MessageType.DEBUG_LOG: "\U0001f4cb",
            MessageType.FIX_APPLIED: "\U0001f527",
            MessageType.TASK_VERIFIED: "\u2705",
            MessageType.EPIC_DONE: "\U0001f3c6",
            MessageType.GENERATION_SUMMARY: "\U0001f4ca",
        }.get(self.msg_type, "\U0001f4e8")

        lines.append("%s **%s** | %s" % (emoji, self.msg_type.value, self.scope.value))

        # Parseable header block
        header = {"type": self.msg_type.value, "scope": self.scope.value}
        if self.epic_id:
            header["epic"] = self.epic_id
            lines.append("Epic: `%s`" % self.epic_id)
        if self.task_id:
            header["task"] = self.task_id
            lines.append("Task: `%s`" % self.task_id)
        if self.task_name:
            lines.append("Name: %s" % self.task_name)
        if self.file_path:
            loc = self.file_path
            if self.line_number:
                loc = "%s:%d" % (self.file_path, self.line_number)
            header["file"] = loc
            lines.append("File: `%s`" % loc)
        if self.status:
            header["status"] = self.status
            lines.append("Status: **%s**" % self.status)

        # Content sections
        if self.error:
            lines.append("```\n%s\n```" % self.error[:800])
        if self.stack_trace:
            lines.append("**Stack:**\n```\n%s\n```" % self.stack_trace[:500])
        if self.context:
            lines.append("**Context:** %s" % self.context[:300])
        if self.diff:
            lines.append("**Diff:**\n```diff\n%s\n```" % self.diff[:500])
        if self.action:
            header["action"] = self.action
            lines.append("**Action:** `%s`" % self.action)

        # Hidden JSON for agent parsing
        lines.append("||`%s`||" % json.dumps(header))

        return "\n".join(lines)

    @classmethod
    def from_discord(cls, content: str) -> Optional["StructuredMessage"]:
        """Parse a structured message from Discord content."""
        # Extract JSON from spoiler tags ||`{...}`||
        import re
        match = re.search(r'\|\|`(\{[^`]+\})`\|\|', content)
        if not match:
            return None

        try:
            header = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

        msg = cls(
            msg_type=MessageType(header.get("type", "DEBUG_LOG")),
            scope=Scope(header.get("scope", "FULLSTACK")),
            epic_id=header.get("epic", ""),
            task_id=header.get("task", ""),
            file_path=header.get("file", ""),
            status=header.get("status", ""),
            action=header.get("action", ""),
        )

        # Extract error from code blocks
        code_blocks = re.findall(r'```\n?(.*?)\n?```', content, re.DOTALL)
        if code_blocks:
            msg.error = code_blocks[0]
        if len(code_blocks) > 1:
            msg.stack_trace = code_blocks[1]

        # Extract context
        ctx_match = re.search(r'\*\*Context:\*\* (.+)', content)
        if ctx_match:
            msg.context = ctx_match.group(1)

        return msg


class StructuredDiscord:
    """High-level API for structured Discord agent communication."""

    def __init__(self, bot_token: str = "", channel_id: str = ""):
        self.agent = DiscordAgent(bot_token=bot_token, channel_id=channel_id)

    async def post(self, msg: StructuredMessage) -> Optional[DiscordMessage]:
        """Post a structured message to Discord."""
        return await self.agent.send(msg.to_discord())

    async def read_structured(self, limit: int = 20) -> list:
        """Read and parse recent structured messages."""
        raw = await self.agent.read_recent(limit=limit)
        messages = []
        for m in raw:
            parsed = StructuredMessage.from_discord(m.get("content", ""))
            if parsed:
                parsed.details["discord_id"] = m.get("id", "")
                parsed.details["author"] = m.get("author", {}).get("username", "")
                parsed.details["timestamp"] = m.get("timestamp", "")
                messages.append(parsed)
        return messages

    async def read_actionable(self, for_scope: Scope = None) -> list:
        """Read messages that need action (FIX_NEEDED, TEST_FAILED, etc)."""
        all_msgs = await self.read_structured(limit=50)
        actionable_types = {
            MessageType.FIX_NEEDED,
            MessageType.TEST_FAILED,
            MessageType.INTEGRATION,
            MessageType.BEHAVIOR,
            MessageType.TIMING,
        }
        result = []
        for m in all_msgs:
            if m.msg_type in actionable_types:
                if for_scope and m.scope != for_scope:
                    continue
                result.append(m)
        return result

    # --- Convenience methods ---

    async def fix_needed(
        self, task_id: str, task_name: str, epic_id: str,
        scope: Scope, file_path: str, error: str,
        stack_trace: str = "", context: str = "", line: int = 0,
    ) -> Optional[DiscordMessage]:
        """Post a FIX_NEEDED message."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.FIX_NEEDED,
            scope=scope, epic_id=epic_id,
            task_id=task_id, task_name=task_name,
            file_path=file_path, line_number=line,
            error=error, stack_trace=stack_trace,
            context=context, action="FIX_AND_RETEST",
        ))

    async def test_failed(
        self, task_id: str, epic_id: str, scope: Scope,
        error: str, file_path: str = "",
    ) -> Optional[DiscordMessage]:
        """Post a TEST_FAILED message."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.TEST_FAILED,
            scope=scope, epic_id=epic_id, task_id=task_id,
            file_path=file_path, error=error,
            action="INVESTIGATE",
        ))

    async def integration_issue(
        self, task_id: str, epic_id: str,
        error: str, context: str,
    ) -> Optional[DiscordMessage]:
        """Post an INTEGRATION issue (FE/BE mismatch)."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.INTEGRATION,
            scope=Scope.FULLSTACK, epic_id=epic_id, task_id=task_id,
            error=error, context=context,
            action="ALIGN_CONTRACTS",
        ))

    async def behavior_issue(
        self, task_id: str, scope: Scope,
        error: str, context: str,
    ) -> Optional[DiscordMessage]:
        """Post a BEHAVIOR issue (runtime bug)."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.BEHAVIOR,
            scope=scope, task_id=task_id,
            error=error, context=context,
            action="DEBUG_AND_FIX",
        ))

    async def timing_issue(
        self, task_id: str, scope: Scope,
        error: str, context: str,
    ) -> Optional[DiscordMessage]:
        """Post a TIMING issue (performance)."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.TIMING,
            scope=scope, task_id=task_id,
            error=error, context=context,
            action="OPTIMIZE",
        ))

    async def debug_log(
        self, task_id: str, scope: Scope,
        error: str, stack_trace: str = "",
    ) -> Optional[DiscordMessage]:
        """Post a DEBUG_LOG with stack trace."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.DEBUG_LOG,
            scope=scope, task_id=task_id,
            error=error, stack_trace=stack_trace,
        ))

    async def fix_applied(
        self, task_id: str, file_path: str, diff: str,
    ) -> Optional[DiscordMessage]:
        """Post a FIX_APPLIED message (from Analyzer)."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.FIX_APPLIED,
            task_id=task_id, file_path=file_path,
            diff=diff, action="RETEST",
        ))

    async def task_verified(
        self, task_id: str, task_name: str, epic_id: str,
        passed: bool,
    ) -> Optional[DiscordMessage]:
        """Post task verification result."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.TASK_VERIFIED,
            epic_id=epic_id, task_id=task_id, task_name=task_name,
            status="PASS" if passed else "FAIL",
        ))

    async def epic_done(
        self, epic_id: str, epic_name: str,
        total: int, passed: int, failed: int,
    ) -> Optional[DiscordMessage]:
        """Post epic completion summary."""
        return await self.post(StructuredMessage(
            msg_type=MessageType.EPIC_DONE,
            epic_id=epic_id, task_name=epic_name,
            status="COMPLETE",
            context="Total: %d | Passed: %d | Failed: %d" % (total, passed, failed),
        ))

    async def generation_summary(
        self, project: str, epics: list,
        total_tasks: int, passed: int, failed: int,
    ) -> Optional[DiscordMessage]:
        """Post full generation summary."""
        epic_lines = []
        for e in epics:
            epic_lines.append(
                "  %s: %s (%d/%d)" % (
                    e.get("id", "?"), e.get("name", "?"),
                    e.get("passed", 0), e.get("total", 0)
                )
            )
        return await self.post(StructuredMessage(
            msg_type=MessageType.GENERATION_SUMMARY,
            task_name=project,
            status="COMPLETE" if failed == 0 else "PARTIAL",
            context="Tasks: %d | Passed: %d | Failed: %d\n%s" % (
                total_tasks, passed, failed, "\n".join(epic_lines)
            ),
        ))
