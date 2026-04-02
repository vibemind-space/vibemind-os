"""
API Agent - Generates REST API endpoints from contracts.

This agent is responsible for:
- Generating REST endpoints from contract definitions
- Creating CRUD routes with proper validation
- Generating type-safe API clients
- Ensuring proper error handling

Trigger Events:
- CONTRACTS_GENERATED: After Phase 1 Architect completes
- DATABASE_SCHEMA_GENERATED: After database schema is ready
- API_UPDATE_NEEDED: When endpoints need updates
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
    api_routes_generated_event,
    api_generation_failed_event,
    system_error_event,
)

if TYPE_CHECKING:
    from ..mind.event_bus import EventBus
    from ..mind.shared_state import SharedState
    from ..skills.registry import SkillRegistry

logger = structlog.get_logger(__name__)


class APIAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for REST API generation.

    Uses the 'api-generation' skill to:
    - Generate CRUD endpoints from contracts
    - Create Zod validation schemas
    - Implement proper error handling
    - Generate type-safe API clients

    Supports:
    - Next.js API Routes (App Router)
    - Express.js
    - FastAPI
    - tRPC

    CRITICAL: This agent NEVER generates mock API responses.
    All endpoints connect to real database operations.
    """

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        api_framework: str = "nextjs",  # nextjs, express, fastapi, trpc
        **kwargs,
    ):
        """
        Initialize the APIAgent.

        Args:
            name: Agent name (typically "APIAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            api_framework: Target API framework
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
        self.api_framework = api_framework
        self._contracts_data: Optional[dict] = None
        self._db_schema_data: Optional[dict] = None
        self._wait_for_db: bool = True

        self.logger = logger.bind(agent=name, api_framework=api_framework)

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "api"

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.CONTRACTS_GENERATED,
            EventType.DATABASE_SCHEMA_GENERATED,
            EventType.API_UPDATE_NEEDED,
            EventType.API_ENDPOINT_FAILED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to generate API routes.

        Acts when:
        - Database schema is generated AND valid (primary trigger)
        - API update is explicitly requested
        - Contracts are generated AND db schema already exists

        Phase 5B: Only acts if schema validation succeeded.
        """
        for event in events:
            # Primary trigger: DB schema generated, now generate API
            if event.type == EventType.DATABASE_SCHEMA_GENERATED:
                self._db_schema_data = event.data

                # Phase 5B: Check if schema is valid before acting
                schema_valid = event.success and event.data.get("schema_valid", True)
                if not schema_valid:
                    self.logger.warning(
                        "skipping_api_generation",
                        msg="Database schema has validation errors, waiting for fix",
                        schema_valid=event.data.get("schema_valid") if event.data else None,
                    )
                    return False

                self.logger.info(
                    "db_schema_received",
                    entities=event.data.get("entities", []) if event.data else [],
                    schema_valid=schema_valid,
                )
                return True

            # Store contracts for later use
            if event.type == EventType.CONTRACTS_GENERATED:
                self._contracts_data = event.data
                # Only act immediately if we already have DB schema
                if self._db_schema_data is not None:
                    return True
                # Otherwise wait for DB schema
                self.logger.info("contracts_stored_waiting_for_db_schema")

            # Explicit API update request
            if event.type == EventType.API_UPDATE_NEEDED:
                return True

            # API endpoint failed - regenerate
            if event.type == EventType.API_ENDPOINT_FAILED:
                return True

        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate REST API endpoints from contracts.

        Uses autogen team (APIOperator + APIValidator) if available,
        falls back to ClaudeCodeTool for legacy mode.
        """
        self.logger.info(
            "API_ROUTES_GENERATING",
            framework=self.api_framework,
            has_contracts=self._contracts_data is not None,
            has_db_schema=self._db_schema_data is not None,
            chain_position="2/4 (Database -> API -> Auth -> Infrastructure)",
            mode="autogen" if self.is_autogen_available() else "legacy",
        )

        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """Generate API routes using autogen Operator + QA Validator team."""
        try:
            # ===== NEW: Get rich context via AgentContextBridge =====
            # This combines static context (RichContextProvider) with dynamic RAG search
            context = await self.get_task_context(
                query=f"API endpoints REST routes {self.api_framework} CRUD controllers validation",
                epic_id=events[0].data.get("epic_id") if events and events[0].data else None,
            )

            api_prompt = self._build_api_prompt()

            # Inject RAG context (code examples from similar API implementations)
            if context and context.rag_results:
                api_prompt += "\n\n## Relevant Code Examples (from RAG)\n"
                api_prompt += "Use these as reference for API patterns and conventions:\n"
                for result in context.rag_results[:3]:  # Top 3 RAG results
                    file_path = result.get("relative_path", result.get("file_path", "unknown"))
                    content = result.get("content", "")[:800]  # Truncate long content
                    score = result.get("score", 0)
                    api_prompt += f"\n### {file_path} (relevance: {score:.2f})\n```\n{content}\n```\n"
                self.logger.info(
                    "rag_context_injected",
                    rag_results_count=len(context.rag_results),
                )

            task = self.build_task_prompt(events, extra_context=api_prompt)

            # Create combined tools: MCP tools + Claude Code
            # - npm: install dependencies (express, zod, etc.)
            # - filesystem: read/write API route files
            # - prisma: verify database connection/models
            # - claude_code: generate complex API code
            tools = self._create_combined_tools(
                mcp_categories=["npm", "filesystem", "prisma"],
                include_claude_code=True,
            )

            self.logger.info(
                "api_agent_tools_created",
                tool_count=len(tools),
                tool_names=[getattr(t, 'name', str(t)) for t in tools[:10]],
            )

            team = self.create_team(
                operator_name="APIOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="APIValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=tools,  # Use explicit combined tools
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                self.logger.info("API_ROUTES_GENERATED",
                                 framework=self.api_framework,
                                 next_agent="AuthAgent",
                                 mode="autogen")
                await self.shared_state.update_backend_chain(api_routes_generated=True)
                return api_routes_generated_event(
                    source=self.name,
                    framework=self.api_framework,
                    routes_count=len(result.get("files_mentioned", [])),
                    endpoints=self._extract_endpoints(),
                )
            else:
                self.logger.error("api_generation_failed",
                                  error=result["result_text"][:500])
                return api_generation_failed_event(
                    source=self.name,
                    error_message=result["result_text"][:500],
                    framework=self.api_framework,
                )
        except Exception as e:
            self.logger.error("api_agent_autogen_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"APIAgent autogen error: {str(e)}",
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Generate API routes using ClaudeCodeTool (legacy fallback)."""
        from ..tools.claude_code_tool import ClaudeCodeTool
        from ..skills.loader import SkillLoader

        try:
            skill = None
            try:
                engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                loader = SkillLoader(engine_root)
                skill = loader.load_skill("api-generation")
                if skill:
                    self.logger.info("skill_loaded", skill_name=skill.name, tokens=skill.instruction_tokens)
            except Exception as e:
                self.logger.debug("skill_load_failed", error=str(e))

            prompt = self._build_api_prompt()
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=300, skill=skill)

            result = await tool.execute(
                prompt=prompt,
                context=f"Generating {self.api_framework} API routes from contracts",
                agent_type="api",
            )

            if result.success:
                self.logger.info("API_ROUTES_GENERATED",
                                 files_created=len(result.files) if result.files else 0,
                                 framework=self.api_framework, next_agent="AuthAgent")
                await self.shared_state.update_backend_chain(api_routes_generated=True)
                return api_routes_generated_event(
                    source=self.name, framework=self.api_framework,
                    routes_count=len(result.files) if result.files else 0,
                    endpoints=self._extract_endpoints(),
                )
            else:
                self.logger.error("api_generation_failed", error=result.error)
                return api_generation_failed_event(
                    source=self.name, error_message=result.error,
                    framework=self.api_framework,
                )
        except Exception as e:
            self.logger.error("api_agent_error", error=str(e))
            return system_error_event(
                source=self.name, error_message=f"APIAgent error: {str(e)}",
            )

    def _build_api_prompt(self) -> str:
        """
        Build the prompt for API generation.

        Combines:
        1. Skill instructions (from SKILL.md)
        2. Contract data (endpoints, types)
        3. Database schema context
        4. Framework-specific instructions
        """
        parts = []

        # 1. Get skill instructions if available
        if self.skill:
            parts.append(f"## Skill: {self.skill.name}")
            parts.append(self.skill.instructions)
            parts.append("\n---\n")
        elif self.skill_registry:
            skill = self.skill_registry.get_skill("api-generation")
            if skill:
                parts.append(f"## Skill: {skill.name}")
                parts.append(skill.instructions)
                parts.append("\n---\n")

        # 2. Framework specific context
        parts.append(f"## Target Framework: {self.api_framework.upper()}")
        parts.append(self._get_framework_instructions())
        parts.append("\n")

        # 3. Database schema context
        if self._db_schema_data:
            parts.append("## Database Schema Context")
            parts.append(self._format_db_schema())
            parts.append("\n")

        # 3.5 Rich Context: Sequence Diagrams and API Endpoints from RichContextProvider
        if hasattr(self.shared_state, 'context_provider') and self.shared_state.context_provider:
            try:
                # Check if it's a RichContextProvider with API context
                if hasattr(self.shared_state.context_provider, 'for_api_agent'):
                    api_context = self.shared_state.context_provider.for_api_agent()

                    # Include sequence diagrams for API flow understanding
                    seq_diagrams = [d for d in api_context.diagrams if d.get("diagram_type") in ["sequence", "flowchart"]]
                    if seq_diagrams:
                        parts.append("## API Flow Diagrams")
                        parts.append("Use these diagrams to understand the API flows and interactions:\n")
                        for diagram in seq_diagrams[:5]:  # Limit to top 5 diagrams
                            title = diagram.get("title", "Sequence Diagram")
                            content = diagram.get("content", "")
                            parts.append(f"### {title}")
                            parts.append(f"```mermaid\n{content}\n```")
                        parts.append("\n")

                    # Include documented API endpoints with schemas
                    if api_context.api_endpoints:
                        parts.append(f"## Documented API Endpoints ({len(api_context.api_endpoints)})")
                        parts.append("These endpoints are specified in the documentation and MUST be implemented:\n")
                        for endpoint in api_context.api_endpoints[:30]:  # Limit to 30 endpoints
                            method = endpoint.get("method", "GET").upper()
                            path = endpoint.get("path", "/")
                            desc = endpoint.get("description", "")
                            auth = "🔒" if endpoint.get("auth_required", True) else "🔓"
                            parts.append(f"- {auth} `{method} {path}` - {desc[:80]}")

                            # Include request/response schema hints
                            if endpoint.get("request_schema"):
                                parts.append(f"  - Request: {endpoint['request_schema'].get('$ref', 'object')}")
                            if endpoint.get("response_schema"):
                                parts.append(f"  - Response: {endpoint['response_schema'].get('$ref', 'object')}")
                        parts.append("\n")

                    self.logger.info(
                        "rich_context_injected",
                        sequence_diagrams_count=len(seq_diagrams),
                        api_endpoints_count=len(api_context.api_endpoints),
                    )
            except Exception as e:
                self.logger.debug("rich_context_extraction_failed", error=str(e))

        # 4. Contract data
        parts.append("## Contracts to Process")
        if self._contracts_data:
            parts.append(self._format_contracts())
        else:
            parts.append("Analyze the project for API contract definitions.")
        parts.append("\n")

        # 5. Task instructions
        parts.append("## Task")
        parts.append(self._get_task_instructions())

        # 6. Anti-Mock Policy (CRITICAL)
        parts.append("\n## ⚠️ ANTI-MOCK POLICY (CRITICAL)")
        parts.append("""
You MUST NOT generate:
- Hardcoded response data
- Fake success responses without DB operations
- TODO/FIXME placeholders
- Mock data arrays

You MUST generate:
- Real database queries (Prisma, SQLAlchemy, etc.)
- Proper error handling with real error codes
- Zod/Pydantic validation
- Environment variable usage for secrets
""")

        return "\n".join(parts)

    def _get_framework_instructions(self) -> str:
        """Get instructions specific to the API framework."""
        instructions = {
            "nextjs": """
Create files in App Router structure:
- src/app/api/[resource]/route.ts - CRUD endpoints
- src/app/api/[resource]/[id]/route.ts - Single resource
- src/lib/api-client.ts - Type-safe fetch wrapper
- src/lib/validations/[resource].ts - Zod schemas

Use Next.js App Router conventions:
- export async function GET/POST/PUT/DELETE(request: Request)
- NextResponse.json() for responses
- Dynamic routes with [id] folders
""",
            "express": """
Create files:
- src/routes/[resource].routes.ts - Express Router
- src/controllers/[resource].controller.ts - Controller logic
- src/middleware/validation.ts - Validation middleware
- src/lib/api-client.ts - Type-safe client

Use Express conventions:
- Router() for route grouping
- async/await with error handling
- express-validator or Zod for validation
""",
            "fastapi": """
Create files:
- src/api/routes/[resource].py - FastAPI router
- src/api/schemas/[resource].py - Pydantic models
- src/api/deps.py - Dependencies (DB, auth)

Use FastAPI conventions:
- APIRouter() for route grouping
- async def endpoints
- Depends() for dependency injection
- HTTPException for errors
""",
            "trpc": """
Create files:
- src/server/routers/[resource].ts - tRPC router
- src/server/routers/_app.ts - Root router
- src/utils/trpc.ts - tRPC client setup

Use tRPC conventions:
- createTRPCRouter() for routers
- publicProcedure/protectedProcedure
- Zod for input validation
- Query/Mutation procedures
""",
        }
        return instructions.get(self.api_framework, instructions["nextjs"])

    def _get_task_instructions(self) -> str:
        """Get the main task instructions."""
        return f"""
Generate complete {self.api_framework} API routes based on the contracts and database schema.

Steps:
1. Analyze entities from contracts/database schema
2. Generate CRUD endpoints for each entity:
   - GET /api/[entity] - List all (with pagination)
   - GET /api/[entity]/[id] - Get single
   - POST /api/[entity] - Create new
   - PUT /api/[entity]/[id] - Update
   - DELETE /api/[entity]/[id] - Delete
3. Add Zod/Pydantic validation for all inputs
4. Implement proper error handling (400, 401, 403, 404, 500)
5. Generate type-safe API client for frontend use

Output complete files. Do NOT use placeholder responses or TODOs.
"""

    def _format_contracts(self) -> str:
        """Format contract data for the prompt."""
        if not self._contracts_data:
            return "No contract data available."

        parts = []

        # API endpoints from contracts
        endpoints = self._contracts_data.get("api_endpoints", [])
        if endpoints:
            parts.append("### API Endpoints")
            for ep in endpoints:
                parts.append(f"- {ep.get('method', 'GET')} {ep.get('path', '/')}")
                if ep.get("description"):
                    parts.append(f"  Description: {ep['description']}")

        # Interfaces
        interfaces = self._contracts_data.get("interfaces", [])
        if interfaces:
            parts.append("\n### TypeScript Interfaces")
            for interface in interfaces[:10]:
                parts.append(f"```typescript\n{interface}\n```")

        return "\n".join(parts) if parts else "Contract data present but no endpoints detected."

    def _format_db_schema(self) -> str:
        """Format database schema context."""
        if not self._db_schema_data:
            return "No database schema available."

        parts = []

        # Entities from DB
        entities = self._db_schema_data.get("entities", [])
        if entities:
            parts.append("### Database Entities")
            for entity in entities:
                if isinstance(entity, str):
                    parts.append(f"- {entity}")
                elif isinstance(entity, dict):
                    parts.append(f"- {entity.get('name', 'Unknown')}")

        # DB type
        db_type = self._db_schema_data.get("db_type", "prisma")
        parts.append(f"\n### ORM: {db_type}")
        parts.append("Use the appropriate ORM methods in your API routes.")

        return "\n".join(parts)

    def _extract_endpoints(self) -> list[dict]:
        """Extract endpoint definitions for the result event."""
        endpoints = []

        if self._contracts_data:
            for ep in self._contracts_data.get("api_endpoints", []):
                endpoints.append({
                    "method": ep.get("method", "GET"),
                    "path": ep.get("path", "/"),
                })

        # Add inferred CRUD endpoints from entities
        if self._db_schema_data:
            for entity in self._db_schema_data.get("entities", []):
                entity_name = entity if isinstance(entity, str) else entity.get("name", "")
                if entity_name:
                    resource = entity_name.lower()
                    endpoints.extend([
                        {"method": "GET", "path": f"/api/{resource}"},
                        {"method": "GET", "path": f"/api/{resource}/[id]"},
                        {"method": "POST", "path": f"/api/{resource}"},
                        {"method": "PUT", "path": f"/api/{resource}/[id]"},
                        {"method": "DELETE", "path": f"/api/{resource}/[id]"},
                    ])

        return endpoints

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Generating {self.api_framework} API routes"

    def _get_operator_system_prompt(self) -> str:
        """System prompt for the APIOperator autogen agent."""
        return f"""You are a REST API expert specializing in {self.api_framework.upper()}.

Your role is to generate production-ready API endpoints from contracts and database schemas.

## Available MCP Tools

You have access to these tools for API generation:

### NPM Tools
- `npm_install` - Install packages (e.g., express, zod, @prisma/client)
- `npm_run` - Run npm scripts (build, lint, test)
- `npm_list` - List installed packages

### Filesystem Tools
- `filesystem_read_file` - Read existing files (contracts, schemas)
- `filesystem_write_file` - Write API route files
- `filesystem_list_files` - List files in directory

### Prisma Tools
- `prisma_generate` - Regenerate Prisma client if needed
- `prisma_migrate_status` - Check migration status

### Claude Code Tool
- `claude_code` - For complex code generation beyond simple file writes

## Workflow

1. Use `filesystem_list_files` to check current project structure
2. Use `filesystem_read_file` to read Prisma schema and contracts
3. Use `npm_list` to check installed packages
4. Use `npm_install` if dependencies are missing
5. Use `claude_code` or `filesystem_write_file` to generate API routes
6. Validate generated code compiles

## CRITICAL RULES

- NEVER generate mock/fake API responses
- ALL endpoints must use real database queries (Prisma)
- Use Zod for ALL input validation
- Environment variables for ALL secrets
- Generate COMPLETE files, not partial snippets

When done, say TASK_COMPLETE."""

    def _get_validator_system_prompt(self) -> str:
        """System prompt for the APIValidator autogen agent."""
        return f"""You are an API QA validator for {self.api_framework.upper()}.

Review the generated API routes and verify:

## Validation Checklist

1. **CRUD Completeness**:
   - GET /api/[entity] (list with pagination)
   - GET /api/[entity]/[id] (single resource)
   - POST /api/[entity] (create)
   - PUT /api/[entity]/[id] (update)
   - DELETE /api/[entity]/[id] (delete)

2. **Input Validation**:
   - Zod schemas for all request bodies
   - Path parameter validation
   - Query parameter validation

3. **Error Handling**:
   - 400 Bad Request for validation errors
   - 401 Unauthorized for auth failures
   - 403 Forbidden for permission denials
   - 404 Not Found for missing resources
   - 500 Internal Server Error with safe messages

4. **No Mocks**:
   - All endpoints use real Prisma queries
   - No hardcoded data arrays
   - No TODO/FIXME placeholders

5. **Type Safety**:
   - TypeScript types for request/response
   - Proper error type definitions

If the API passes validation, say TASK_COMPLETE.
If issues are found, describe them clearly for the operator to fix."""
