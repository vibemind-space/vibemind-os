"""
Claude Init Tool - Generates project-specific CLAUDE.md using Claude CLI /init.

This tool runs the Claude CLI with the /init command to analyze the project
and generate a comprehensive CLAUDE.md file that documents:
- Project structure
- Key files and their purposes
- Commands and workflows
- Architecture overview

The generated CLAUDE.md is project-specific, not the engine's architecture docs.
"""

import asyncio
import subprocess
import structlog
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .claude_agent_tool import find_claude_executable


@dataclass
class ClaudeInitResult:
    """Result from running Claude /init."""

    success: bool
    claude_md_path: Optional[Path] = None
    content: Optional[str] = None
    error: Optional[str] = None


class ClaudeInitTool:
    """
    Tool for generating project-specific CLAUDE.md using Claude CLI /init.

    This creates documentation tailored to the generated project, not the
    Coding Engine's architecture. The resulting CLAUDE.md describes:
    - The generated project's structure
    - Its components and APIs
    - How to run/build/test the project
    """

    def __init__(
        self,
        working_dir: str,
        timeout: int = 120,
    ):
        """
        Initialize the Claude Init Tool.

        Args:
            working_dir: The project directory to analyze
            timeout: Timeout in seconds for the /init command
        """
        self.working_dir = Path(working_dir)
        self.timeout = timeout
        self.logger = structlog.get_logger(__name__)

    async def run_init(self) -> ClaudeInitResult:
        """
        Run Claude CLI /init to generate CLAUDE.md for the project.

        Returns:
            ClaudeInitResult with the generated CLAUDE.md path and content
        """
        self.logger.info(
            "claude_init_starting",
            working_dir=str(self.working_dir),
        )

        # Check if working directory exists
        if not self.working_dir.exists():
            return ClaudeInitResult(
                success=False,
                error=f"Working directory does not exist: {self.working_dir}",
            )

        try:
            # Run claude with /init command
            # The /init command analyzes the project and creates CLAUDE.md
            claude_exe = find_claude_executable() or "claude"
            process = await asyncio.create_subprocess_exec(
                claude_exe,
                "--print",  # Print output instead of interactive mode
                "-p", "/init",  # Run /init command
                cwd=str(self.working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ClaudeInitResult(
                    success=False,
                    error=f"Claude /init timed out after {self.timeout}s",
                )

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace')
                self.logger.warning(
                    "claude_init_failed",
                    returncode=process.returncode,
                    stderr=error_msg[:500],
                )
                return ClaudeInitResult(
                    success=False,
                    error=f"Claude /init failed: {error_msg[:200]}",
                )

            # Check for generated CLAUDE.md
            claude_md_path = self.working_dir / "CLAUDE.md"
            if not claude_md_path.exists():
                # Try .claude directory
                claude_md_path = self.working_dir / ".claude" / "CLAUDE.md"

            if claude_md_path.exists():
                content = claude_md_path.read_text(encoding='utf-8', errors='replace')
                self.logger.info(
                    "claude_init_success",
                    claude_md_path=str(claude_md_path),
                    content_length=len(content),
                )
                return ClaudeInitResult(
                    success=True,
                    claude_md_path=claude_md_path,
                    content=content,
                )
            else:
                # /init might have output to stdout instead of file
                output = stdout.decode('utf-8', errors='replace')
                if output.strip():
                    # Write to CLAUDE.md
                    claude_md_path = self.working_dir / "CLAUDE.md"
                    claude_md_path.write_text(output, encoding='utf-8')
                    self.logger.info(
                        "claude_init_created_from_output",
                        claude_md_path=str(claude_md_path),
                        content_length=len(output),
                    )
                    return ClaudeInitResult(
                        success=True,
                        claude_md_path=claude_md_path,
                        content=output,
                    )

                return ClaudeInitResult(
                    success=False,
                    error="CLAUDE.md was not generated",
                )

        except FileNotFoundError:
            return ClaudeInitResult(
                success=False,
                error="Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
            )
        except Exception as e:
            self.logger.exception("claude_init_error", error=str(e))
            return ClaudeInitResult(
                success=False,
                error=str(e),
            )

    async def ensure_claude_md(self) -> ClaudeInitResult:
        """
        Ensure CLAUDE.md exists for the project.

        If it already exists, returns the existing content.
        Otherwise, runs /init to generate it.

        Returns:
            ClaudeInitResult with CLAUDE.md path and content
        """
        # Check existing CLAUDE.md locations
        for path in [
            self.working_dir / "CLAUDE.md",
            self.working_dir / ".claude" / "CLAUDE.md",
        ]:
            if path.exists():
                content = path.read_text(encoding='utf-8', errors='replace')
                self.logger.debug(
                    "claude_md_exists",
                    path=str(path),
                    content_length=len(content),
                )
                return ClaudeInitResult(
                    success=True,
                    claude_md_path=path,
                    content=content,
                )

        # Generate new CLAUDE.md
        return await self.run_init()


async def run_claude_init(working_dir: str, timeout: int = 120) -> ClaudeInitResult:
    """
    Convenience function to run Claude /init.

    Args:
        working_dir: Project directory to analyze
        timeout: Timeout in seconds

    Returns:
        ClaudeInitResult with generated CLAUDE.md
    """
    tool = ClaudeInitTool(working_dir=working_dir, timeout=timeout)
    return await tool.run_init()


async def ensure_project_claude_md(working_dir: str) -> ClaudeInitResult:
    """
    Ensure project has a CLAUDE.md, generating if needed.

    Args:
        working_dir: Project directory

    Returns:
        ClaudeInitResult with CLAUDE.md path and content
    """
    tool = ClaudeInitTool(working_dir=working_dir)
    return await tool.ensure_claude_md()
