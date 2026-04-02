"""
Recovery Agent - Fixes failing tests and errors.

This agent:
1. Analyzes test failures
2. Searches memory for similar fixes
3. Generates targeted fixes
4. Validates the fix works
"""
from dataclasses import dataclass
from typing import Optional
import structlog

from src.engine.contracts import InterfaceContracts
from src.tools.claude_code_tool import ClaudeCodeTool, CodeGenerationResult
from src.tools.test_runner_tool import TestFailure
from src.tools.supermemory_tools import SupermemoryTools

logger = structlog.get_logger()


@dataclass
class RecoveryResult:
    """Result from a recovery attempt."""
    success: bool
    fix_applied: bool = False
    error: Optional[str] = None
    files_modified: int = 0


RECOVERY_SYSTEM_PROMPT = """You are a Recovery Agent specialized in fixing code errors.

Your task is to analyze test failures and generate targeted fixes.

When fixing an error:
1. Read the error message carefully
2. Identify the root cause (not just the symptom)
3. Generate the minimal fix needed
4. Ensure the fix doesn't break other functionality
5. Follow the existing code style

If you've seen similar errors before (provided in context), use that knowledge.

Output ONLY the fixed code files. Do not explain - just fix."""


class RecoveryAgent:
    """
    Agent that fixes failing tests and recovers from errors.

    Uses:
    - Error analysis to identify root cause
    - Memory search for similar past fixes
    - Claude Code to generate fixes
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        max_fix_attempts: int = 2,
    ):
        self.working_dir = working_dir
        self.max_fix_attempts = max_fix_attempts
        self.code_tool = ClaudeCodeTool(working_dir=working_dir)
        self.memory_tool = SupermemoryTools()
        self.logger = logger.bind(agent="recovery")

    async def fix_failure(
        self,
        failure: TestFailure,
        contracts: Optional[InterfaceContracts] = None,
        similar_fixes: Optional[list[dict]] = None,
    ) -> RecoveryResult:
        """
        Attempt to fix a test failure.

        Args:
            failure: The test failure details
            contracts: Interface contracts for context
            similar_fixes: Similar fixes from memory

        Returns:
            RecoveryResult
        """
        self.logger.info(
            "attempting_fix",
            test=failure.test_name,
            file=failure.file_path,
            error_type=failure.error_type,
        )

        # Build fix prompt
        prompt = self._build_fix_prompt(failure, contracts, similar_fixes)

        # Attempt fix
        for attempt in range(self.max_fix_attempts):
            self.logger.debug("fix_attempt", attempt=attempt + 1)

            result = await self.code_tool.execute(
                prompt=prompt,
                context=contracts.to_prompt_context("general") if contracts else None,
                agent_type="general",
            )

            if result.success and result.files:
                self.logger.info(
                    "fix_generated",
                    files=len(result.files),
                )

                # Store successful fix in memory
                await self._store_fix(failure, result)

                return RecoveryResult(
                    success=True,
                    fix_applied=True,
                    files_modified=len(result.files),
                )

            # If first attempt failed, enhance prompt
            if attempt == 0:
                prompt = self._enhance_prompt(prompt, failure)

        self.logger.warning("fix_failed", test=failure.test_name)
        return RecoveryResult(
            success=False,
            error="Failed to generate fix after max attempts",
        )

    def _build_fix_prompt(
        self,
        failure: TestFailure,
        contracts: Optional[InterfaceContracts],
        similar_fixes: Optional[list[dict]],
    ) -> str:
        """Build the fix prompt."""
        parts = [RECOVERY_SYSTEM_PROMPT, "\n\n## Error Details\n"]

        parts.append(f"**Test:** {failure.test_name}\n")
        parts.append(f"**File:** {failure.file_path}\n")
        if failure.line_number:
            parts.append(f"**Line:** {failure.line_number}\n")
        parts.append(f"**Error Type:** {failure.error_type}\n")
        parts.append(f"**Error Message:** {failure.error_message}\n")

        if failure.traceback:
            parts.append(f"\n**Traceback:**\n```\n{failure.traceback[:1000]}\n```\n")

        # Add similar fixes from memory
        if similar_fixes:
            parts.append("\n## Similar Fixes from Past\n")
            for fix in similar_fixes[:2]:
                content = fix.get("content", "")[:500]
                parts.append(f"```\n{content}\n```\n")

        parts.append("\n## Your Task\n")
        parts.append("Fix the error by modifying the necessary files.\n")
        parts.append("Output the complete fixed file(s) using the standard format:\n")
        parts.append("```language:path/to/file.ext\n// fixed content\n```\n")

        return "".join(parts)

    def _enhance_prompt(self, original_prompt: str, failure: TestFailure) -> str:
        """Enhance prompt after first failure."""
        return f"""{original_prompt}

## IMPORTANT: Previous fix attempt failed

Please try a different approach:
1. Check if the error is a syntax error
2. Check for missing imports
3. Check for type mismatches
4. Consider if the test expectation is correct

Be more careful this time and ensure the code is syntactically correct.
"""

    async def _store_fix(
        self,
        failure: TestFailure,
        result: CodeGenerationResult,
    ):
        """Store successful fix in memory."""
        # Build fix summary
        fix_content = "\n".join([
            f"# Fix for {failure.error_type}",
            f"# Error: {failure.error_message}",
            "",
            *[f"# File: {f.path}\n{f.content[:500]}" for f in result.files[:2]]
        ])

        await self.memory_tool.store(
            content=fix_content,
            description=f"Fix for {failure.error_type} in {failure.file_path}",
            category="error_fix",
            tags=[failure.error_type, "fix", "recovery"],
            context={
                "test_name": failure.test_name,
                "error_message": failure.error_message,
            },
        )

    async def analyze_errors(
        self,
        failures: list[TestFailure],
    ) -> dict[str, list[TestFailure]]:
        """
        Analyze and group failures by root cause.

        Args:
            failures: List of test failures

        Returns:
            Dict mapping root cause to failures
        """
        # Group by error type
        by_type: dict[str, list[TestFailure]] = {}

        for failure in failures:
            error_type = failure.error_type or "unknown"
            if error_type not in by_type:
                by_type[error_type] = []
            by_type[error_type].append(failure)

        # Group by file
        by_file: dict[str, list[TestFailure]] = {}
        for failure in failures:
            if failure.file_path not in by_file:
                by_file[failure.file_path] = []
            by_file[failure.file_path].append(failure)

        # Determine best grouping (fewer groups = likely related)
        if len(by_type) < len(by_file):
            return by_type
        return by_file

    async def fix_multiple(
        self,
        failures: list[TestFailure],
        contracts: Optional[InterfaceContracts] = None,
    ) -> list[RecoveryResult]:
        """
        Fix multiple failures, grouping related ones.

        Args:
            failures: List of test failures
            contracts: Interface contracts

        Returns:
            List of recovery results
        """
        # Group failures
        grouped = await self.analyze_errors(failures)

        results = []
        for group_key, group_failures in grouped.items():
            self.logger.info(
                "fixing_group",
                key=group_key,
                failures=len(group_failures),
            )

            # Fix the first failure in each group
            # (often fixes related failures)
            result = await self.fix_failure(
                failure=group_failures[0],
                contracts=contracts,
            )
            results.append(result)

        return results


async def fix_test_failure(
    failure: TestFailure,
    contracts: Optional[InterfaceContracts] = None,
    working_dir: Optional[str] = None,
) -> RecoveryResult:
    """
    Convenience function to fix a test failure.

    Args:
        failure: The failure to fix
        contracts: Interface contracts
        working_dir: Working directory

    Returns:
        RecoveryResult
    """
    agent = RecoveryAgent(working_dir=working_dir)
    return await agent.fix_failure(failure, contracts)
