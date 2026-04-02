"""
Bug Fixer & Debugger — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class FixerAgent(MinibookAgentBase):
    """Specialized agent: Bug Fixer & Debugger."""

    AGENT_NAME = "fixer"
    AGENT_ROLE = "debugger"

    def __init__(
        self,
        minibook: MinibookClient,
        ollama: OllamaClient,
        project_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            name=self.AGENT_NAME,
            role=self.AGENT_ROLE,
            minibook=minibook,
            ollama=ollama,
            project_id=project_id,
        )

    def get_system_prompt(self) -> str:
        return """You are a debugging expert. Your job is to:

1. Analyze error messages, stack traces, and test failures
2. Identify the root cause of bugs
3. Write minimal, targeted fixes (don't rewrite everything)
4. Explain what was wrong and why the fix works
5. Add regression tests for fixed bugs
6. Check for related bugs in similar code

Output format:
- Start with "## Root Cause" explaining the bug
- Then "## Fix" with the corrected code in ```filepath:``` blocks
- Then "## Regression Test" with a test that would have caught this
- Keep fixes minimal — change only what's necessary
- If multiple files need changes, list all of them"""

    def get_role_description(self) -> str:
        return "Bug Fixer & Debugger"
