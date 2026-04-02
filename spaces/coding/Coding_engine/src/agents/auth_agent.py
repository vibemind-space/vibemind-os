"""
Auth Agent - Generates authentication and authorization systems.

This agent is responsible for:
- JWT token generation and verification
- OAuth2 provider integration (Google, GitHub, etc.)
- RBAC (Role-Based Access Control) implementation
- Password hashing and verification
- Auth middleware and hooks

Trigger Events:
- CONTRACTS_GENERATED: When auth requirements are detected
- API_ROUTES_GENERATED: After API routes, add auth
- AUTH_REQUIRED: Explicit auth setup request
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from ..mind.event_bus import (
    Event, EventType,
    auth_setup_complete_event,
    auth_setup_failed_event,
    system_error_event,
)

if TYPE_CHECKING:
    from ..mind.event_bus import EventBus
    from ..mind.shared_state import SharedState
    from ..skills.registry import SkillRegistry

logger = structlog.get_logger(__name__)


class AuthAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for authentication/authorization setup.

    Uses the 'auth-setup' skill to:
    - Implement JWT token handling
    - Set up OAuth2 providers
    - Create RBAC permission system
    - Generate auth middleware
    - Create React auth hooks

    Supports:
    - JWT (JSON Web Tokens)
    - OAuth2 (Google, GitHub, Microsoft, Discord)
    - Session-based auth
    - RBAC with fine-grained permissions

    CRITICAL: This agent NEVER generates fake tokens or passwords.
    All auth uses real cryptographic operations.
    """

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        auth_type: str = "jwt",  # jwt, oauth2, session
        enable_rbac: bool = True,
        oauth_providers: Optional[list[str]] = None,
        **kwargs,
    ):
        """
        Initialize the AuthAgent.

        Args:
            name: Agent name (typically "AuthAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            auth_type: Primary authentication type
            enable_rbac: Whether to implement RBAC
            oauth_providers: List of OAuth providers to configure
            **kwargs: Additional args for AutonomousAgent
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.skill_registry = skill_registry
        self.auth_type = auth_type
        self.enable_rbac = enable_rbac
        self.oauth_providers = oauth_providers or []
        self._contracts_data: Optional[dict] = None
        self._auth_requirements: Optional[dict] = None

        self.logger = logger.bind(
            agent=name,
            auth_type=auth_type,
            rbac=enable_rbac,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.CONTRACTS_GENERATED,
            EventType.API_ROUTES_GENERATED,
            EventType.AUTH_REQUIRED,
            EventType.ROLE_DEFINITION_NEEDED,
            EventType.AUTH_CONFIG_UPDATED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to set up authentication.

        Acts when:
        - API routes are generated (add auth middleware)
        - Auth is explicitly required
        - Role definitions are needed
        - Contracts indicate auth requirements
        """
        for event in events:
            # Primary trigger: API routes generated, add auth
            if event.type == EventType.API_ROUTES_GENERATED:
                self.logger.info("api_routes_ready_adding_auth")
                return True

            # Store contracts and check for auth requirements
            if event.type == EventType.CONTRACTS_GENERATED:
                self._contracts_data = event.data
                if self._detect_auth_requirements(event.data):
                    self.logger.info("auth_requirements_detected")
                    return True

            # Explicit auth setup request
            if event.type == EventType.AUTH_REQUIRED:
                self._auth_requirements = event.data
                return True

            # RBAC roles needed
            if event.type == EventType.ROLE_DEFINITION_NEEDED:
                return True

            # Auth config update
            if event.type == EventType.AUTH_CONFIG_UPDATED:
                return True

        return False

    def _detect_auth_requirements(self, contracts_data: Optional[dict]) -> bool:
        """Detect if contracts require authentication."""
        if not contracts_data:
            return False

        # Check for auth-related keywords in contracts
        auth_keywords = [
            "login", "logout", "register", "password",
            "authentication", "authorization", "role",
            "permission", "jwt", "token", "session",
            "user", "admin", "oauth",
        ]

        # Check interfaces
        interfaces = contracts_data.get("interfaces", [])
        for interface in interfaces:
            if isinstance(interface, str):
                lower = interface.lower()
                if any(kw in lower for kw in auth_keywords):
                    return True

        # Check entities
        entities = contracts_data.get("entities", [])
        for entity in entities:
            name = entity.get("name", "") if isinstance(entity, dict) else str(entity)
            if name.lower() in ["user", "role", "permission", "session"]:
                return True

        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Set up authentication and authorization.

        Uses autogen team (AuthOperator + AuthValidator) if available,
        falls back to ClaudeCodeTool for legacy mode.
        """
        self.logger.info(
            "AUTH_SETUP_STARTING",
            auth_type=self.auth_type,
            rbac=self.enable_rbac,
            oauth_providers=self.oauth_providers,
            chain_position="3/4 (Database -> API -> Auth -> Infrastructure)",
            mode="autogen" if self.is_autogen_available() else "legacy",
        )

        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """Set up auth using autogen AuthOperator + AuthValidator team."""
        try:
            auth_prompt = self._build_auth_prompt()
            task = self.build_task_prompt(events, extra_context=auth_prompt)

            rbac_note = " with RBAC permission system" if self.enable_rbac else ""
            oauth_note = f" and OAuth providers ({', '.join(self.oauth_providers)})" if self.oauth_providers else ""

            team = self.create_team(
                operator_name="AuthOperator",
                operator_prompt=f"""You are an authentication/authorization expert specializing in {self.auth_type}.

Your role is to set up production-ready auth for this project.

Capabilities:
- JWT token generation and verification with real crypto
- OAuth2 provider integration (Google, GitHub, Microsoft, Discord)
- RBAC with fine-grained permission checking
- Password hashing with bcrypt (cost factor 12)
- Auth middleware for protected routes
- React auth hooks with Zustand

CRITICAL RULES:
- NEVER generate hardcoded JWT tokens (eyJ...)
- NEVER use fake passwords or mock verification (return true)
- ALL secrets MUST use environment variables
- Use real JWT signing: jwt.sign(payload, process.env.JWT_SECRET)
- Use real password hashing: await bcrypt.hash(password, 12)

When done, say TASK_COMPLETE.""",
                validator_name="AuthValidator",
                validator_prompt=f"""You are an auth security validator for {self.auth_type} authentication{rbac_note}{oauth_note}.

Review the generated auth code and verify:
1. **Real Crypto**: JWT uses real signing (not hardcoded tokens)
2. **Password Hashing**: bcrypt with cost factor >= 12
3. **Environment Variables**: ALL secrets from env vars, never hardcoded
4. **RBAC Completeness**: Permission enum, role mappings, middleware guards
5. **Token Security**: Proper expiry, refresh rotation, secure storage
6. **No Mocks**: No fake auth, no placeholder credentials, no return-true guards

If the auth passes validation, say TASK_COMPLETE.
If security issues are found, describe them for the operator to fix.""",
                tool_categories=["npm", "filesystem"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                self.logger.info(
                    "AUTH_SETUP_COMPLETE",
                    auth_type=self.auth_type,
                    next_agent="InfrastructureAgent",
                    mode="autogen",
                )
                await self.shared_state.update_backend_chain(auth_setup_complete=True)
                return auth_setup_complete_event(
                    source=self.name,
                    auth_type=self.auth_type,
                    features=["rbac"] if self.enable_rbac else [],
                )
            else:
                self.logger.error(
                    "auth_setup_failed",
                    error=result["result_text"][:500],
                )
                return auth_setup_failed_event(
                    source=self.name,
                    error_message=result["result_text"][:500],
                    auth_type=self.auth_type,
                )
        except Exception as e:
            self.logger.error("auth_agent_autogen_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"AuthAgent autogen error: {str(e)}",
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Set up auth using ClaudeCodeTool (legacy fallback)."""
        from ..tools.claude_code_tool import ClaudeCodeTool
        from ..skills.loader import SkillLoader

        try:
            skill = None
            try:
                engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                loader = SkillLoader(engine_root)
                skill = loader.load_skill("auth-setup")
                if skill:
                    self.logger.info("skill_loaded", skill_name=skill.name, tokens=skill.instruction_tokens)
            except Exception as e:
                self.logger.debug("skill_load_failed", error=str(e))

            prompt = self._build_auth_prompt()
            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=300,
                skill=skill,
            )

            result = await tool.execute(
                prompt=prompt,
                context=f"Setting up {self.auth_type} authentication with RBAC={self.enable_rbac}",
                agent_type="auth",
            )

            if result.success:
                self.logger.info(
                    "AUTH_SETUP_COMPLETE",
                    files_created=len(result.files) if result.files else 0,
                    auth_type=self.auth_type,
                    next_agent="InfrastructureAgent",
                )
                await self.shared_state.update_backend_chain(auth_setup_complete=True)
                return auth_setup_complete_event(
                    source=self.name,
                    auth_type=self.auth_type,
                    features=["rbac"] if self.enable_rbac else [],
                )
            else:
                self.logger.error("auth_setup_failed", error=result.error)
                return auth_setup_failed_event(
                    source=self.name,
                    error_message=result.error,
                    auth_type=self.auth_type,
                )
        except Exception as e:
            self.logger.error("auth_agent_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"AuthAgent error: {str(e)}",
            )

    def _build_auth_prompt(self) -> str:
        """
        Build the prompt for auth setup.

        Combines:
        1. Skill instructions (from SKILL.md)
        2. Auth type specific instructions
        3. RBAC configuration
        4. OAuth provider setup
        """
        parts = []

        # 1. Get skill instructions if available
        if self.skill:
            parts.append(f"## Skill: {self.skill.name}")
            parts.append(self.skill.instructions)
            parts.append("\n---\n")
        elif self.skill_registry:
            skill = self.skill_registry.get_skill("auth-setup")
            if skill:
                parts.append(f"## Skill: {skill.name}")
                parts.append(skill.instructions)
                parts.append("\n---\n")

        # 2. Auth type context
        parts.append(f"## Authentication Type: {self.auth_type.upper()}")
        parts.append(self._get_auth_type_instructions())
        parts.append("\n")

        # 3. RBAC configuration
        if self.enable_rbac:
            parts.append("## RBAC Configuration")
            parts.append(self._get_rbac_instructions())
            parts.append("\n")

        # 4. OAuth providers
        if self.oauth_providers:
            parts.append("## OAuth2 Providers")
            parts.append(self._get_oauth_instructions())
            parts.append("\n")

        # 5. Task instructions
        parts.append("## Task")
        parts.append(self._get_task_instructions())

        # 6. Anti-Mock Policy (CRITICAL)
        parts.append("\n## ⚠️ ANTI-MOCK POLICY (CRITICAL)")
        parts.append("""
You MUST NOT generate:
- Hardcoded JWT tokens (eyJ...)
- Fake passwords or secrets
- Mock user verification (return true)
- Placeholder OAuth credentials

You MUST generate:
- Real JWT signing with crypto: jwt.sign(payload, process.env.JWT_SECRET)
- Real password hashing: await bcrypt.hash(password, 12)
- Environment variables for ALL secrets
- Proper token verification with error handling
""")

        return "\n".join(parts)

    def _get_auth_type_instructions(self) -> str:
        """Get instructions specific to the auth type."""
        instructions = {
            "jwt": """
Create files:
- src/lib/auth/jwt.ts - JWT sign/verify utilities
- src/lib/auth/middleware.ts - Auth middleware
- src/hooks/useAuth.ts - React auth hook with Zustand
- src/contexts/AuthContext.tsx - Auth provider (optional)

JWT Configuration:
- Use RS256 or HS256 algorithm
- Token expiry: 7 days for access, 30 days for refresh
- Store JWT_SECRET in environment variable
- Implement refresh token rotation
""",
            "oauth2": """
Create files:
- src/lib/auth/oauth.ts - OAuth2 flow handlers
- src/lib/auth/providers/[provider].ts - Provider configs
- src/app/api/auth/[...nextauth]/route.ts - NextAuth route
- src/hooks/useAuth.ts - Auth hook

OAuth2 Configuration:
- Use authorization code flow
- Store client secrets in env vars
- Implement PKCE for public clients
""",
            "session": """
Create files:
- src/lib/auth/session.ts - Session management
- src/lib/auth/middleware.ts - Session middleware
- src/hooks/useAuth.ts - Auth hook

Session Configuration:
- Use HTTP-only secure cookies
- Implement CSRF protection
- Session store: Redis or database
""",
        }
        return instructions.get(self.auth_type, instructions["jwt"])

    def _get_rbac_instructions(self) -> str:
        """Get RBAC implementation instructions."""
        return """
Implement RBAC with:

1. Permission Enum:
```typescript
enum Permission {
  READ_USERS = 'read:users',
  WRITE_USERS = 'write:users',
  DELETE_USERS = 'delete:users',
  MANAGE_ROLES = 'manage:roles',
  ADMIN = 'admin:*',
}
```

2. Role Definitions:
```typescript
const ROLE_PERMISSIONS = {
  admin: [Permission.ADMIN],
  manager: [Permission.READ_USERS, Permission.WRITE_USERS, Permission.MANAGE_ROLES],
  user: [Permission.READ_USERS],
  guest: [],
};
```

3. Permission Checking:
```typescript
function hasPermission(user: User, permission: Permission): boolean {
  const role = user.role as keyof typeof ROLE_PERMISSIONS;
  const permissions = ROLE_PERMISSIONS[role] || [];
  return permissions.includes(Permission.ADMIN) || permissions.includes(permission);
}
```

4. Protected Routes:
```typescript
export function withPermission(permission: Permission) {
  return async (req: Request) => {
    const user = await getUser(req);
    if (!hasPermission(user, permission)) {
      return new Response('Forbidden', { status: 403 });
    }
    // Continue...
  };
}
```
"""

    def _get_oauth_instructions(self) -> str:
        """Get OAuth provider setup instructions."""
        provider_configs = {
            "google": """
Google OAuth:
- CLIENT_ID: process.env.GOOGLE_CLIENT_ID
- CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET
- Scopes: email, profile, openid
""",
            "github": """
GitHub OAuth:
- CLIENT_ID: process.env.GITHUB_CLIENT_ID
- CLIENT_SECRET: process.env.GITHUB_CLIENT_SECRET
- Scopes: read:user, user:email
""",
            "microsoft": """
Microsoft OAuth:
- CLIENT_ID: process.env.MICROSOFT_CLIENT_ID
- CLIENT_SECRET: process.env.MICROSOFT_CLIENT_SECRET
- Scopes: openid, profile, email
""",
            "discord": """
Discord OAuth:
- CLIENT_ID: process.env.DISCORD_CLIENT_ID
- CLIENT_SECRET: process.env.DISCORD_CLIENT_SECRET
- Scopes: identify, email
""",
        }

        parts = ["Configure the following OAuth providers:\n"]
        for provider in self.oauth_providers:
            if provider.lower() in provider_configs:
                parts.append(provider_configs[provider.lower()])

        return "\n".join(parts)

    def _get_task_instructions(self) -> str:
        """Get the main task instructions."""
        rbac_note = "Include RBAC permission system." if self.enable_rbac else ""
        oauth_note = f"Configure OAuth providers: {', '.join(self.oauth_providers)}." if self.oauth_providers else ""

        return f"""
Set up complete {self.auth_type} authentication for this project.

Steps:
1. Create JWT/session utilities with proper cryptographic operations
2. Implement password hashing with bcrypt (cost factor 12)
3. Create auth middleware for protected routes
4. Generate React auth hook with Zustand store
5. {rbac_note}
6. {oauth_note}
7. Add environment variable placeholders to .env.example

Output complete files. ALL secrets MUST use environment variables.
Do NOT hardcode any tokens, passwords, or credentials.
"""

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Setting up {self.auth_type} authentication"
