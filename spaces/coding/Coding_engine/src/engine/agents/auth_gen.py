"""
Authentication & Security Engineer — Minibook Agent for the Coding Engine.
"""
from src.engine.minibook_agent import MinibookAgentBase
from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient
from typing import Optional


class AuthGenAgent(MinibookAgentBase):
    """Specialized agent: Authentication & Security Engineer."""

    AGENT_NAME = "auth-gen"
    AGENT_ROLE = "security-engineer"

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
        return """You are a security engineer specializing in authentication. Your job is to:

1. Implement JWT token generation and validation
2. Build 2FA (TOTP, SMS verification) flows
3. Implement session management with secure cookies
4. Add biometric authentication endpoints
5. Implement rate limiting for auth endpoints
6. Build password hashing with bcrypt/argon2
7. Create auth guards and middleware

Output format:
- Always wrap code in ```filepath: path/to/file.ext``` blocks
- NEVER hardcode secrets — use environment variables
- Include proper error messages without leaking security info
- Follow OWASP security guidelines
- Implement proper token refresh mechanisms"""

    def get_role_description(self) -> str:
        return "Authentication & Security Engineer"
