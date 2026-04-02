"""
Infrastructure Agent - Generates environment configuration and infrastructure.

This agent is responsible for:
- .env file generation with proper secrets
- Docker Compose configuration
- GitHub Actions CI/CD pipelines
- Deployment configurations

Trigger Events:
- PROJECT_SCAFFOLDED: After Phase 0
- DATABASE_SCHEMA_GENERATED: DB connection strings needed
- AUTH_SETUP_COMPLETE: Auth secrets needed
"""

import asyncio
import os
import secrets
import base64
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from ..mind.event_bus import (
    Event, EventType,
    env_config_generated_event,
    infrastructure_failed_event,
    system_error_event,
)

if TYPE_CHECKING:
    from ..mind.event_bus import EventBus
    from ..mind.shared_state import SharedState
    from ..skills.registry import SkillRegistry

logger = structlog.get_logger(__name__)


class InfrastructureAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for infrastructure and environment setup.

    Uses the 'environment-config' skill to:
    - Generate .env files with auto-generated secrets
    - Create Docker Compose for local development
    - Set up GitHub Actions CI/CD
    - Configure deployment settings

    Features:
    - Auto-generates secure secrets (JWT, API keys)
    - Database connection string generation
    - Multi-environment support (dev, staging, prod)
    - CI/CD pipeline templates

    CRITICAL: This agent generates REAL secrets.
    Never uses placeholder or mock values in production configs.
    """

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        enable_docker: bool = True,
        enable_ci: bool = True,
        ci_provider: str = "github",  # github, gitlab, azure
        **kwargs,
    ):
        """
        Initialize the InfrastructureAgent.

        Args:
            name: Agent name (typically "InfrastructureAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            enable_docker: Generate Docker Compose files
            enable_ci: Generate CI/CD pipelines
            ci_provider: CI/CD provider (github, gitlab, azure)
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
        self.enable_docker = enable_docker
        self.enable_ci = enable_ci
        self.ci_provider = ci_provider
        self._collected_config: dict = {}

        self.logger = logger.bind(
            agent=name,
            docker=enable_docker,
            ci=enable_ci,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.GENERATION_COMPLETE,
            EventType.DATABASE_SCHEMA_GENERATED,
            EventType.AUTH_SETUP_COMPLETE,
            EventType.ENV_UPDATE_NEEDED,
            EventType.DOCKER_CONFIG_NEEDED,
            EventType.CI_PIPELINE_NEEDED,
            # From FungusCompletenessAgent validation
            EventType.REQUIREMENT_ENV_MISSING,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to generate infrastructure config.

        Acts when:
        - Code generation is complete (main trigger)
        - Database schema is generated (update DB vars)
        - Auth is set up (update auth vars)
        - Explicit config requests
        """
        for event in events:
            # Primary trigger: Generation complete, finalize infra
            if event.type == EventType.GENERATION_COMPLETE:
                self.logger.info("generation_complete_setting_up_infra")
                return True

            # Database generated - need connection strings
            if event.type == EventType.DATABASE_SCHEMA_GENERATED:
                self._collected_config["database"] = event.data
                self.logger.info("db_config_received")
                return True

            # Auth set up - need auth secrets
            if event.type == EventType.AUTH_SETUP_COMPLETE:
                self._collected_config["auth"] = event.data
                self.logger.info("auth_config_received")
                return True

            # Explicit requests
            if event.type in [
                EventType.ENV_UPDATE_NEEDED,
                EventType.DOCKER_CONFIG_NEEDED,
                EventType.CI_PIPELINE_NEEDED,
            ]:
                return True

            # Fungus validation found missing ENV vars
            if event.type == EventType.REQUIREMENT_ENV_MISSING:
                missing_vars = event.data.get("env_vars", [])
                self.logger.info(
                    "fungus_env_missing_detected",
                    requirement=event.data.get("requirement_name"),
                    missing_vars=missing_vars,
                )
                # Store missing vars for generation
                self._collected_config["missing_env"] = missing_vars
                return True

        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate infrastructure configuration.

        Uses autogen team (InfraOperator + InfraValidator) if available,
        falls back to ClaudeCodeTool for legacy mode.
        """
        self.logger.info(
            "INFRASTRUCTURE_CONFIGURING",
            docker=self.enable_docker,
            ci=self.enable_ci,
            ci_provider=self.ci_provider,
            chain_position="4/4 (Database -> API -> Auth -> Infrastructure) - FINAL",
            mode="autogen" if self.is_autogen_available() else "legacy",
        )

        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """Generate infrastructure using autogen InfraOperator + InfraValidator team."""
        try:
            infra_prompt = self._build_infra_prompt()
            task = self.build_task_prompt(events, extra_context=infra_prompt)

            # Create combined tools: MCP tools + Claude Code
            # - docker: manage containers, compose, logs
            # - git: commit configs, manage .gitignore
            # - filesystem: read/write config files
            # - npm: verify dependencies, run scripts
            # - claude_code: generate complex configs
            tools = self._create_combined_tools(
                mcp_categories=["docker", "git", "filesystem", "npm"],
                include_claude_code=True,
            )

            self.logger.info(
                "infra_agent_tools_created",
                tool_count=len(tools),
                tool_names=[getattr(t, 'name', str(t)) for t in tools[:10]],
            )

            docker_note = " with Docker Compose" if self.enable_docker else ""
            ci_note = f" and {self.ci_provider} CI/CD" if self.enable_ci else ""

            team = self.create_team(
                operator_name="InfraOperator",
                operator_prompt=self._get_infra_operator_prompt(docker_note, ci_note),
                validator_name="InfraValidator",
                validator_prompt=self._get_infra_validator_prompt(),
                tools=tools,  # Use explicit combined tools
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                self.logger.info(
                    "INFRASTRUCTURE_READY",
                    backend_chain_complete=True,
                    mode="autogen",
                )
                await self.shared_state.update_backend_chain(infrastructure_ready=True)
                return env_config_generated_event(
                    source=self.name,
                    docker_enabled=self.enable_docker,
                    ci_enabled=self.enable_ci,
                    ci_provider=self.ci_provider,
                    files_created=result.get("files_mentioned", []),
                )
            else:
                self.logger.error(
                    "infrastructure_generation_failed",
                    error=result["result_text"][:500],
                )
                return infrastructure_failed_event(
                    source=self.name,
                    error_message=result["result_text"][:500],
                )
        except Exception as e:
            self.logger.error("infra_agent_autogen_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"InfrastructureAgent autogen error: {str(e)}",
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Generate infrastructure using ClaudeCodeTool (legacy fallback)."""
        from ..tools.claude_code_tool import ClaudeCodeTool
        from ..skills.loader import SkillLoader

        try:
            skill = None
            try:
                engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                loader = SkillLoader(engine_root)
                skill = loader.load_skill("environment-config")
                if skill:
                    self.logger.info("skill_loaded", skill_name=skill.name, tokens=skill.instruction_tokens)
            except Exception as e:
                self.logger.debug("skill_load_failed", error=str(e))

            prompt = self._build_infra_prompt()
            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=300,
                skill=skill,
            )

            result = await tool.execute(
                prompt=prompt,
                context="Generating infrastructure configuration",
                agent_type="infrastructure",
            )

            if result.success:
                self.logger.info(
                    "INFRASTRUCTURE_READY",
                    files_created=len(result.files) if result.files else 0,
                    backend_chain_complete=True,
                )
                await self.shared_state.update_backend_chain(infrastructure_ready=True)
                return env_config_generated_event(
                    source=self.name,
                    docker_enabled=self.enable_docker,
                    ci_enabled=self.enable_ci,
                    ci_provider=self.ci_provider,
                    files_created=result.files or [],
                )
            else:
                self.logger.error("infrastructure_generation_failed", error=result.error)
                return infrastructure_failed_event(
                    source=self.name,
                    error_message=result.error,
                )
        except Exception as e:
            self.logger.error("infrastructure_agent_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"InfrastructureAgent error: {str(e)}",
            )

    def _build_infra_prompt(self) -> str:
        """
        Build the prompt for infrastructure generation.

        Combines:
        1. Skill instructions (from SKILL.md)
        2. Collected configuration (DB, Auth)
        3. Infrastructure options
        4. Secret generation
        """
        parts = []

        # 1. Get skill instructions if available
        if self.skill:
            parts.append(f"## Skill: {self.skill.name}")
            parts.append(self.skill.instructions)
            parts.append("\n---\n")
        elif self.skill_registry:
            skill = self.skill_registry.get_skill("environment-config")
            if skill:
                parts.append(f"## Skill: {skill.name}")
                parts.append(skill.instructions)
                parts.append("\n---\n")

        # 2. Generated secrets to use
        parts.append("## Pre-Generated Secrets (Use These)")
        parts.append(self._generate_secrets())
        parts.append("\n")

        # 3. Collected configuration
        if self._collected_config:
            parts.append("## Collected Configuration")
            parts.append(self._format_collected_config())
            parts.append("\n")

        # 4. Docker configuration
        if self.enable_docker:
            parts.append("## Docker Configuration")
            parts.append(self._get_docker_instructions())
            parts.append("\n")

        # 5. CI/CD configuration
        if self.enable_ci:
            parts.append(f"## CI/CD Configuration ({self.ci_provider.upper()})")
            parts.append(self._get_ci_instructions())
            parts.append("\n")

        # 6. Task instructions
        parts.append("## Task")
        parts.append(self._get_task_instructions())

        # 7. Anti-Mock Policy
        parts.append("\n## ⚠️ ANTI-MOCK POLICY (CRITICAL)")
        parts.append("""
You MUST NOT generate:
- TODO/FIXME placeholder comments
- Generic "your-secret-here" values
- Empty environment variables

You MUST generate:
- Use the pre-generated secrets provided above
- Real database connection strings with host/port/db
- Complete Docker Compose with working services
- Functional CI/CD pipelines
""")

        return "\n".join(parts)

    def _generate_secrets(self) -> str:
        """Generate real secrets for environment files."""
        jwt_secret = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode()
        api_key = secrets.token_urlsafe(32)
        encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        session_secret = secrets.token_urlsafe(48)

        return f"""
Use these pre-generated secrets in your .env files:

```
# Authentication
JWT_SECRET={jwt_secret}
SESSION_SECRET={session_secret}

# API Keys
API_KEY={api_key}

# Encryption
ENCRYPTION_KEY={encryption_key}

# Database (use these as defaults for local dev)
POSTGRES_USER=dev
POSTGRES_PASSWORD={secrets.token_urlsafe(16)}
POSTGRES_DB=app_dev

# Redis
REDIS_PASSWORD={secrets.token_urlsafe(16)}
```

IMPORTANT: Include ALL these values in .env.local for local development.
For .env.example, use placeholder format like JWT_SECRET=your-jwt-secret-here
"""

    def _format_collected_config(self) -> str:
        """Format collected configuration from other agents."""
        parts = []

        if "database" in self._collected_config:
            db_config = self._collected_config["database"]
            parts.append("### Database Configuration")
            parts.append(f"- Type: {db_config.get('db_type', 'prisma')}")
            parts.append(f"- Entities: {db_config.get('entities', [])}")

        if "auth" in self._collected_config:
            auth_config = self._collected_config["auth"]
            parts.append("\n### Auth Configuration")
            parts.append(f"- Type: {auth_config.get('auth_type', 'jwt')}")
            parts.append(f"- RBAC: {auth_config.get('rbac_enabled', False)}")
            parts.append(f"- OAuth: {auth_config.get('oauth_providers', [])}")

        return "\n".join(parts) if parts else "No configuration collected from other agents."

    def _get_docker_instructions(self) -> str:
        """Get Docker Compose instructions."""
        return """
Create Docker Compose files:

1. docker-compose.yml (production):
   - postgres: PostgreSQL 15 with persistent volume
   - redis: Redis 7 Alpine
   - app: Node.js application

2. docker-compose.dev.yml (development):
   - Override for hot-reload
   - Expose debug ports
   - Mount source volumes

Services to include:
```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-dev}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-app}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```
"""

    def _get_ci_instructions(self) -> str:
        """Get CI/CD pipeline instructions."""
        if self.ci_provider == "github":
            return """
Create GitHub Actions workflows:

1. .github/workflows/ci.yml:
   - Trigger: push, pull_request
   - Jobs: lint, test, build
   - Cache: node_modules, pnpm-store
   - Services: postgres, redis (for integration tests)

2. .github/workflows/deploy.yml:
   - Trigger: push to main
   - Jobs: build, deploy
   - Environments: staging, production
   - Secrets: Use GitHub secrets

Example ci.yml:
```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
        with:
          version: 8
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
      - run: pnpm install
      - run: pnpm lint
      - run: pnpm test
      - run: pnpm build
```
"""
        elif self.ci_provider == "gitlab":
            return """
Create GitLab CI/CD:

.gitlab-ci.yml:
- Stages: test, build, deploy
- Cache: node_modules
- Services: postgres, redis
"""
        else:
            return "Create CI/CD pipeline for your platform."

    def _get_task_instructions(self) -> str:
        """Get the main task instructions."""
        docker_note = "Generate Docker Compose files." if self.enable_docker else ""
        ci_note = f"Generate {self.ci_provider} CI/CD pipelines." if self.enable_ci else ""

        return f"""
Generate complete infrastructure configuration for this project.

Files to create:
1. .env.example - Template with placeholder values
2. .env.local - Local development with REAL generated secrets
3. {docker_note}
4. {ci_note}

Use the pre-generated secrets from above.
Ensure all environment variables are properly referenced.
Do NOT use placeholder comments or TODOs in .env.local.
"""

    def _get_infra_operator_prompt(self, docker_note: str, ci_note: str) -> str:
        """System prompt for InfraOperator autogen agent."""
        return f"""You are a DevOps/infrastructure expert.

Your role is to generate production-ready infrastructure configuration for this project{docker_note}{ci_note}.

## Available MCP Tools

### Docker Tools
- `docker_list_containers` - List running containers
- `docker_compose_up` - Start Docker Compose services
- `docker_compose_down` - Stop Docker Compose services
- `docker_logs` - View container logs
- `docker_build` - Build Docker images
- `docker_exec` - Execute commands in containers

### Git Tools
- `git_status` - Check repository status
- `git_add` - Stage files
- `git_commit` - Commit changes
- `git_diff` - View changes

### Filesystem Tools
- `filesystem_read_file` - Read existing configs
- `filesystem_write_file` - Write new configs
- `filesystem_list_files` - List directory contents

### NPM Tools
- `npm_run` - Run npm scripts
- `npm_install` - Install dependencies

### Claude Code Tool
- `claude_code` - For complex infrastructure code generation

## Workflow

1. Use `filesystem_list_files` to check current project structure
2. Use `filesystem_read_file` to read package.json for dependencies
3. Use `claude_code` or `filesystem_write_file` to create configs:
   - .env.example (template with placeholders)
   - .env.local (real secrets from prompt)
   - docker-compose.yml (if Docker enabled)
   - CI/CD pipelines
4. Use `docker_compose_up` to verify Docker configuration
5. Use `git_status` to check what needs to be committed

## CRITICAL RULES

- NEVER generate placeholder or TODO values in .env.local
- Use the pre-generated secrets provided in the prompt
- ALL Docker services must have health checks
- CI/CD must include lint, test, and build steps
- Environment variables for ALL secrets

When done, say TASK_COMPLETE."""

    def _get_infra_validator_prompt(self) -> str:
        """System prompt for InfraValidator autogen agent."""
        return """You are an infrastructure/DevOps validator.

Review the generated infrastructure configuration and verify:

## Validation Checklist

1. **Secrets**:
   - .env.local has real cryptographic values (no placeholders)
   - JWT_SECRET is a proper base64 string
   - Passwords are randomly generated

2. **Docker Compose**:
   - All services have health checks
   - Volumes are properly defined
   - Networks are configured
   - Ports don't conflict

3. **CI/CD Pipeline**:
   - Lint step included
   - Test step with service dependencies (postgres, redis)
   - Build step that creates artifacts
   - Proper caching configured

4. **Environment Separation**:
   - .env.example uses placeholder format: KEY=your-value-here
   - .env.local uses real generated values
   - Both files have same variable names

5. **Database Config**:
   - Connection string format is correct
   - Host, port, database name are present
   - User and password are set

6. **No TODOs**:
   - No placeholder comments
   - No FIXME notes
   - No "your-xxx-here" patterns in .env.local

If the infrastructure passes validation, say TASK_COMPLETE.
If issues are found, describe them clearly for the operator to fix."""

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return "Generating infrastructure configuration"
