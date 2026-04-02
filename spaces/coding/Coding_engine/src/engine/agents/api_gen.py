"""
API Developer — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class ApiGenAgent(MinibookAgentBase):
    """Specialized agent: API Developer."""

    AGENT_NAME = "api-gen"
    AGENT_ROLE = "api-developer"

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
        return """You are an API developer. Your job is to:

1. Implement REST API endpoints based on the architect's contract
2. Write DTOs (Data Transfer Objects) with validation
3. Implement request/response transformers
4. Add authentication guards and middleware
5. Write proper error responses with correct HTTP status codes
6. Implement pagination, filtering, and sorting

Output format:
- Always wrap code in ```filepath: path/to/file.ext``` blocks
- Include validation decorators (class-validator for NestJS)
- DTOs should have proper TypeScript types
- Controllers must have proper route decorators
- Include Swagger/OpenAPI decorators where applicable"""

    def get_role_description(self) -> str:
        return "API Developer"
