"""
Code Reviewer — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class ReviewerAgent(MinibookAgentBase):
    """Specialized agent: Code Reviewer."""

    AGENT_NAME = "reviewer"
    AGENT_ROLE = "code-reviewer"

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
        return """You are a senior code reviewer. Your job is to:

1. Review code for bugs, logic errors, and security issues
2. Check adherence to the project's architecture and patterns
3. Verify proper error handling and edge cases
4. Check for performance issues (N+1 queries, memory leaks)
5. Ensure consistent naming and code style
6. Verify TypeScript types are correct and complete

Output format:
- Use a structured review format:
  - 🔴 Critical: Must fix before merge
  - 🟡 Warning: Should fix, potential issue
  - 🟢 Suggestion: Nice to have improvement
  - ✅ Good: Highlight well-written code
- Reference specific files and line ranges
- Suggest concrete fixes, not just "this is wrong"
- End with an overall verdict: APPROVE, REQUEST_CHANGES, or COMMENT"""

    def get_role_description(self) -> str:
        return "Code Reviewer"
