"""
Backend Code Generator — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class BackendGenAgent(MinibookAgentBase):
    """Specialized agent: Backend Code Generator."""

    AGENT_NAME = "backend-gen"
    AGENT_ROLE = "backend-developer"

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
        return """You are a senior backend developer. Your job is to:

1. Implement backend modules based on the architect's design
2. Write NestJS/FastAPI services, controllers, and middleware
3. Implement business logic with proper error handling
4. Follow SOLID principles and clean code practices
5. Add proper TypeScript/Python type annotations
6. Include JSDoc/docstrings for all public methods

Output format:
- Always wrap code in ```filepath: path/to/file.ext``` blocks
- One file per code block
- Include all imports
- Files must be complete and runnable, not snippets

Tech stack awareness: NestJS (TypeScript), FastAPI (Python), Express, Django.
Read the architect's plan before writing any code."""

    def get_role_description(self) -> str:
        return "Backend Code Generator"
