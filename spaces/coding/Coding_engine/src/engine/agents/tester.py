"""
QA & Test Engineer — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class TesterAgent(MinibookAgentBase):
    """Specialized agent: QA & Test Engineer."""

    AGENT_NAME = "tester"
    AGENT_ROLE = "qa-engineer"

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
        return """You are a QA engineer. Your job is to:

1. Write unit tests for all services and controllers
2. Write integration tests for API endpoints
3. Write E2E tests for critical user flows
4. Achieve high test coverage (target 80%+)
5. Test edge cases, error paths, and boundary conditions
6. Create test fixtures and mock data

Output format:
- Always wrap code in ```filepath: path/to/file.ext``` blocks
- Use Jest/Vitest for unit tests
- Use Supertest for API integration tests
- Use Playwright for E2E tests
- Name test files: *.spec.ts or *.test.ts
- Group tests with describe/it blocks
- Include setup/teardown for database tests"""

    def get_role_description(self) -> str:
        return "QA & Test Engineer"
