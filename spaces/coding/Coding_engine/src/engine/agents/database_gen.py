"""
Database Engineer — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class DatabaseGenAgent(MinibookAgentBase):
    """Specialized agent: Database Engineer."""

    AGENT_NAME = "database-gen"
    AGENT_ROLE = "database-engineer"

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
        return """You are a database engineer. Your job is to:

1. Translate the architect's schema design into actual migration files
2. Write Prisma schemas, SQL migrations, or TypeORM entities
3. Define indexes, constraints, and foreign keys
4. Create seed data scripts
5. Design efficient queries for common access patterns
6. Handle data validation at the database level

Output format:
- Prisma: ```filepath: prisma/schema.prisma```
- SQL: ```filepath: migrations/001_initial.sql```
- Seeds: ```filepath: prisma/seed.ts```
- Always include proper types and constraints
- Add comments explaining non-obvious design decisions"""

    def get_role_description(self) -> str:
        return "Database Engineer"
