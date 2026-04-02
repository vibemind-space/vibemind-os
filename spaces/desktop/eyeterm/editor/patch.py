"""Parse, validate, and apply unified diffs produced by Claude Code."""

import logging
import re
import subprocess
import tempfile
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class PatchHandler:
    """Parse, validate, and apply unified diffs."""

    @staticmethod
    def extract_diff(claude_response: str) -> Optional[str]:
        """Extract unified diff from Claude's response.

        Looks for lines starting with 'diff --git', '---', '+++', '@@', '+', '-'.
        Also handles ```diff ... ``` code blocks.
        """
        logger.debug("extract_diff called: response length=%s", len(claude_response))
        # Try to extract from a fenced code block first
        fenced_match = re.search(
            r"```(?:diff)?\s*\n(.*?)```", claude_response, re.DOTALL
        )
        if fenced_match:
            candidate = fenced_match.group(1).strip()
            if _looks_like_diff(candidate):
                return candidate

        # Try to find a raw diff in the response
        lines = claude_response.splitlines()
        diff_lines: List[str] = []
        in_diff = False

        for line in lines:
            if line.startswith("diff --git ") or line.startswith("--- a/"):
                in_diff = True
            if in_diff:
                # Stop collecting if we hit a clearly non-diff line
                if (
                    line
                    and not line.startswith(("diff ", "---", "+++", "@@", "+", "-", " ", "\\"))
                    and not line.strip() == ""
                ):
                    break
                diff_lines.append(line)

        if diff_lines and _looks_like_diff("\n".join(diff_lines)):
            return "\n".join(diff_lines)

        return None

    @staticmethod
    def validate_diff(diff_text: str, workdir: str) -> Tuple[bool, str]:
        """Check that diff applies cleanly via git apply --check.

        Returns (valid, message).
        """
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, dir=workdir
            ) as tmp:
                tmp.write(diff_text)
                tmp_path = tmp.name

            result = subprocess.run(
                ["git", "apply", "--check", tmp_path],
                cwd=workdir,
                capture_output=True,
                text=True,
            )

            os.unlink(tmp_path)

            if result.returncode == 0:
                return True, "Diff applies cleanly"
            return False, result.stderr.strip() or "Diff does not apply cleanly"

        except FileNotFoundError:
            return False, "git not found on PATH"
        except Exception as exc:
            return False, f"Validation error: {exc}"

    @staticmethod
    def apply_diff(diff_text: str, workdir: str) -> Tuple[bool, str]:
        """Apply diff via git apply. Returns (success, message)."""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, dir=workdir
            ) as tmp:
                tmp.write(diff_text)
                tmp_path = tmp.name

            result = subprocess.run(
                ["git", "apply", tmp_path],
                cwd=workdir,
                capture_output=True,
                text=True,
            )

            os.unlink(tmp_path)

            if result.returncode == 0:
                logger.info("Patch applied successfully in %s", workdir)
                return True, "Patch applied successfully"
            msg = result.stderr.strip() or "git apply failed"
            logger.error("Patch failed in %s: %s", workdir, msg)
            return False, msg

        except FileNotFoundError:
            return False, "git not found on PATH"
        except Exception as exc:
            return False, f"Apply error: {exc}"

    @staticmethod
    def format_for_preview(diff_text: str, max_lines: int = 25) -> List[str]:
        """Format diff lines for OpenCV overlay.

        Each line is prefixed with '+' or '-' for coloring.
        Context lines (starting with ' ') are kept as-is.
        Truncates to max_lines and appends a truncation notice if needed.
        """
        lines = diff_text.splitlines()
        preview: List[str] = []

        for line in lines:
            # Skip diff metadata headers (keep hunk headers)
            if line.startswith("diff --git"):
                continue
            if line.startswith("index "):
                continue
            preview.append(line)

        if len(preview) > max_lines:
            preview = preview[:max_lines]
            remaining = len(lines) - max_lines
            preview.append(f"  ... +{remaining} more lines")

        return preview


def _looks_like_diff(text: str) -> bool:
    """Heuristic check: does the text look like a unified diff?"""
    has_hunk = "@@" in text
    has_add_or_del = any(
        line.startswith("+") or line.startswith("-")
        for line in text.splitlines()
        if not line.startswith("---") and not line.startswith("+++")
    )
    return has_hunk and has_add_or_del
