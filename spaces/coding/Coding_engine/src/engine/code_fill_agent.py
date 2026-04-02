"""Wraps LLM tool for skeleton-fill operations."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    file_path: Path
    content: str
    tokens_used: int
    success: bool
    error: str | None = None


class CodeFillAgent:
    """Wraps an LLM code tool for filling skeleton files."""

    def __init__(self, tool=None):
        self.tool = tool  # ClaudeCodeTool or None for dry-run

    async def fill(self, skeleton_file: Path, context: str) -> FillResult:
        if self.tool is None:
            return FillResult(
                file_path=skeleton_file,
                content=skeleton_file.read_text(encoding="utf-8"),
                tokens_used=0,
                success=True,
            )

        prompt = (
            f"Fill the following skeleton file with production-ready NestJS implementation.\n"
            f"Replace all TODO comments and NotImplementedException with real logic.\n"
            f"Use ONLY the types, methods, and fields shown in the context below.\n\n"
            f"{context}"
        )
        try:
            result = await self.tool.execute(prompt=prompt, context=context)
            return FillResult(
                file_path=skeleton_file,
                content=result.code if hasattr(result, "code") else str(result),
                tokens_used=getattr(result, "tokens_used", 0),
                success=not getattr(result, "error", None),
                error=getattr(result, "error", None),
            )
        except Exception as e:
            logger.error("Agent fill failed for %s: %s", skeleton_file, e)
            return FillResult(
                file_path=skeleton_file,
                content=skeleton_file.read_text(encoding="utf-8"),
                tokens_used=0,
                success=False,
                error=str(e),
            )
