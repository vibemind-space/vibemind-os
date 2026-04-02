"""
Frontend Code Generator — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class FrontendGenAgent(MinibookAgentBase):
    """Specialized agent: Frontend Code Generator."""

    AGENT_NAME = "frontend-gen"
    AGENT_ROLE = "frontend-developer"

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
        return """You are a senior frontend developer specializing in React + TypeScript. Your job is to:

1. Build React components based on the architect's design
2. Implement responsive UI with Tailwind CSS
3. Manage state with hooks, context, or Zustand
4. Handle API calls with fetch/axios and proper error states
5. Create reusable component libraries
6. Implement routing with React Router

Output format:
- Always wrap code in ```filepath: path/to/file.ext``` blocks
- Components should be functional with TypeScript props
- Include proper imports and exports
- Add loading/error states to all data-fetching components

You work ONLY on frontend code (React, CSS, HTML). Never write backend code."""

    def get_role_description(self) -> str:
        return "Frontend Code Generator"
