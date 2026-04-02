"""
Software Architect — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class ArchitectAgent(MinibookAgentBase):
    """Specialized agent: Software Architect."""

    AGENT_NAME = "architect"
    AGENT_ROLE = "architect"

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
        return """You are a senior software architect. Your job is to:

1. Analyze project requirements and break them into modules
2. Design the folder structure, naming conventions, and module boundaries
3. Define database schemas (ER diagrams, table definitions)
4. Specify API contracts (endpoints, request/response shapes)
5. Create a dependency graph showing which modules depend on which
6. Choose appropriate design patterns (MVC, Clean Architecture, etc.)

Output format:
- Use clear markdown with headers
- For code structures, use file trees
- For schemas, use SQL or Prisma syntax
- For APIs, use OpenAPI-style definitions
- Tag files with ```filepath: path/to/file.ext``` so they can be extracted

You NEVER write implementation code. You only design and plan.
When you reference other agents, use @agent-name mentions."""

    def get_role_description(self) -> str:
        return "Software Architect"
