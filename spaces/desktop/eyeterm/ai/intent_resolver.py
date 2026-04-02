"""Resolve freeform voice commands via Claude CLI when regex grammar doesn't match."""

import json
import logging
import subprocess
from typing import Optional

from ..audio.command_parser import ParsedCommand

logger = logging.getLogger(__name__)


class IntentResolver:
    """Resolves freeform transcripts to structured commands via Claude CLI."""

    def __init__(self, claude_cli_path: str = "claude"):
        self._claude_cli = claude_cli_path

    def resolve(self, context: str, transcript: str) -> Optional[ParsedCommand]:
        """Send context + transcript to Claude CLI for intent resolution.

        Args:
            context: Structured context string from ContextBuilder.
            transcript: Raw voice transcript.

        Returns:
            ParsedCommand if intent was resolved, None otherwise.
        """
        prompt = self._build_prompt(context, transcript)

        try:
            result = subprocess.run(
                [
                    self._claude_cli,
                    "-p", prompt,
                    "--output-format", "json",
                    "--max-turns", "1",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                logger.warning(
                    "Claude CLI returned code %d: %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return None

            return self._parse_response(result.stdout.strip())

        except FileNotFoundError:
            logger.error(
                "Claude CLI not found at '%s'. Install with: npm install -g @anthropic-ai/claude-code",
                self._claude_cli,
            )
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Claude CLI timed out after 15s")
            return None
        except Exception as e:
            logger.error("Intent resolution failed: %s", e)
            return None

    def _build_prompt(self, context: str, transcript: str) -> str:
        """Build a prompt that asks Claude to classify the intent."""
        return f"""You are an intent classifier for a voice-controlled desktop automation system.

Given the UI context and voice transcript below, determine the user's intended action.

{context}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "action": "<one of: click, type, read, select, edit, scroll, toggle, ask, cancel, apply, undo>",
  "target": "<element description or null>",
  "prompt": "<text to type or instruction, or null>",
  "instruction": "<edit instruction or null>"
}}

Rules:
- "click" if the user wants to press/activate something
- "type" if the user wants to enter text
- "read" if the user wants to hear/know the content
- "select" if the user wants to highlight/select an element
- "edit" if the user wants to modify existing content
- "scroll" with target "up"/"down"/"left"/"right" for scrolling
- "toggle" for checkboxes, switches, expand/collapse
- "ask" for questions about the UI or general queries
- "cancel"/"apply"/"undo" for control commands

Voice transcript: "{transcript}"
"""

    def _parse_response(self, raw_output: str) -> Optional[ParsedCommand]:
        """Parse Claude CLI JSON response into a ParsedCommand."""
        try:
            # Claude CLI with --output-format json wraps in a result object
            data = json.loads(raw_output)

            # Handle Claude CLI wrapper format
            if "result" in data:
                inner = data["result"]
                if isinstance(inner, str):
                    inner = json.loads(inner)
                data = inner

            action = data.get("action")
            if not action:
                logger.warning("No action in Claude response: %s", raw_output[:200])
                return None

            return ParsedCommand(
                action=action,
                target=data.get("target"),
                prompt=data.get("prompt"),
                instruction=data.get("instruction"),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Claude response: %s — raw: %s", e, raw_output[:200])
            return None
