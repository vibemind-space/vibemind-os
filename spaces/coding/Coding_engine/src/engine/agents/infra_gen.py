"""
Infrastructure & DevOps Engineer — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class InfraGenAgent(MinibookAgentBase):
    """Specialized agent: Infrastructure & DevOps Engineer."""

    AGENT_NAME = "infra-gen"
    AGENT_ROLE = "devops-engineer"

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
        return """You are a DevOps engineer. Your job is to:

1. Write Dockerfiles and docker-compose.yml
2. Create CI/CD pipeline configs (GitHub Actions)
3. Set up environment configuration (.env templates)
4. Write health check endpoints
5. Configure nginx reverse proxies
6. Create deployment scripts
7. Set up logging and monitoring

Output format:
- Always wrap code in ```filepath: path/to/file.ext``` blocks
- Dockerfiles should use multi-stage builds
- docker-compose should include all services (app, db, redis, etc.)
- Include .env.example with all required variables (no real secrets)
- GitHub Actions workflows should test, build, and deploy
- Add proper health checks to all services"""

    def get_role_description(self) -> str:
        return "Infrastructure & DevOps Engineer"
