"""
Database Agent - Generates database schemas from contracts.

This agent is responsible for:
- Generating Prisma/SQLAlchemy/Drizzle schemas from TypeScript contracts
- Creating migrations
- Generating seed data
- Ensuring NO mock/fake data implementations

Trigger Events:
- CONTRACTS_GENERATED: After Phase 1 Architect completes
- SCHEMA_UPDATE_NEEDED: When model changes require schema updates
"""

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from ..mind.event_bus import (
    Event, EventType,
    database_schema_generated_event,
    database_schema_failed_event,
    system_error_event,
)

if TYPE_CHECKING:
    from ..mind.event_bus import EventBus
    from ..mind.shared_state import SharedState
    from ..skills.registry import SkillRegistry

logger = structlog.get_logger(__name__)


class DatabaseAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for database schema generation.

    Uses the 'database-schema-generation' skill to:
    - Parse TypeScript interfaces from contracts
    - Generate Prisma/SQLAlchemy schemas
    - Create proper relations (1:1, 1:n, n:m)
    - Generate migrations and seed data

    CRITICAL: This agent NEVER generates mock data arrays.
    All generated code connects to real databases.
    """

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        db_type: str = "prisma",  # prisma, sqlalchemy, drizzle, typeorm
        **kwargs,
    ):
        """
        Initialize the DatabaseAgent.

        Args:
            name: Agent name (typically "DatabaseAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            db_type: Database ORM type (prisma, sqlalchemy, drizzle, typeorm)
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
        self.db_type = db_type
        self._contracts_data: Optional[dict] = None
        self._last_schema_hash: Optional[str] = None

        self.logger = logger.bind(agent=name, db_type=db_type)

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "database"

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.CONTRACTS_GENERATED,
            EventType.SCHEMA_UPDATE_NEEDED,
            EventType.DATABASE_MIGRATION_NEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to generate database schema.

        Acts when:
        - Contracts are generated (primary trigger)
        - Schema update is explicitly requested
        - Migration is needed
        """
        for event in events:
            # Primary trigger: Contracts generated from Phase 1
            if event.type == EventType.CONTRACTS_GENERATED:
                self._contracts_data = event.data
                self.logger.info(
                    "contracts_received",
                    entities=len(event.data.get("entities", [])) if event.data else 0,
                )
                return True

            # Explicit schema update request
            if event.type == EventType.SCHEMA_UPDATE_NEEDED:
                self._contracts_data = event.data
                return True

            # Migration needed (schema changed)
            if event.type == EventType.DATABASE_MIGRATION_NEEDED:
                return True

        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate database schema from contracts.

        Uses autogen team (SchemaOperator + SchemaValidator) if available,
        falls back to ClaudeCodeTool for legacy mode.
        """
        self.logger.info(
            "DATABASE_SCHEMA_GENERATING",
            db_type=self.db_type,
            has_contracts=self._contracts_data is not None,
            chain_position="1/4 (Database -> API -> Auth -> Infrastructure)",
            mode="autogen" if self.is_autogen_available() else "legacy",
        )

        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """Generate schema using autogen Operator + QA Validator team."""
        try:
            # ===== NEW: Get rich context via AgentContextBridge =====
            # This combines static context (RichContextProvider) with dynamic RAG search
            context = await self.get_task_context(
                query=f"database schema {self.db_type} prisma entities relations ORM models",
                epic_id=events[0].data.get("epic_id") if events and events[0].data else None,
            )

            # Build schema prompt (reuses existing method)
            schema_prompt = self._build_schema_prompt()

            # Inject RAG context (code examples from similar projects)
            if context and context.rag_results:
                schema_prompt += "\n\n## Relevant Code Examples (from RAG)\n"
                schema_prompt += "Use these as reference for patterns and conventions:\n"
                for result in context.rag_results[:3]:  # Top 3 RAG results
                    file_path = result.get("relative_path", result.get("file_path", "unknown"))
                    content = result.get("content", "")[:800]  # Truncate long content
                    score = result.get("score", 0)
                    schema_prompt += f"\n### {file_path} (relevance: {score:.2f})\n```\n{content}\n```\n"
                self.logger.info(
                    "rag_context_injected",
                    rag_results_count=len(context.rag_results),
                )

            # Build task prompt with event context
            task = self.build_task_prompt(events, extra_context=schema_prompt)

            # Create combined tools: MCP tools (prisma, docker) + Claude Code
            # - prisma: schema generation, migration, client generation
            # - docker: verify/start PostgreSQL container
            # - npm: install prisma dependencies
            # - filesystem: read/write schema files
            # - claude_code: generate complex code when MCP tools aren't sufficient
            tools = self._create_combined_tools(
                mcp_categories=["prisma", "docker", "npm", "filesystem"],
                include_claude_code=True,
            )

            self.logger.info(
                "database_agent_tools_created",
                tool_count=len(tools),
                tool_names=[getattr(t, 'name', str(t)) for t in tools[:10]],
            )

            # Create team with combined tools
            team = self.create_team(
                operator_name="SchemaOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="SchemaValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=tools,  # Use explicit tools instead of tool_categories
                max_turns=20,
                task=task,
            )

            # Execute team
            result = await self.run_team(team, task)

            if result["success"]:
                # Validate Prisma schema
                prisma_valid = True
                if self.db_type == "prisma":
                    prisma_valid = await self._validate_prisma_schema()
                    if not prisma_valid:
                        self.logger.warning("prisma_schema_invalid",
                                            msg="Schema has errors, attempting fix pass")
                        prisma_valid = await self._fix_and_revalidate_prisma()

                self.logger.info("DATABASE_SCHEMA_GENERATED",
                                 db_type=self.db_type,
                                 next_agent="APIAgent",
                                 prisma_valid=prisma_valid,
                                 mode="autogen")

                await self.shared_state.update_backend_chain(database_schema_generated=True)

                return database_schema_generated_event(
                    source=self.name,
                    db_type=self.db_type,
                    tables_created=len(result.get("files_mentioned", [])),
                    schema_valid=prisma_valid,
                )
            else:
                self.logger.error("database_schema_generation_failed",
                                  error=result["result_text"][:500])
                return database_schema_failed_event(
                    source=self.name,
                    error_message=result["result_text"][:500],
                    db_type=self.db_type,
                )

        except Exception as e:
            self.logger.error("database_agent_autogen_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"DatabaseAgent autogen error: {str(e)}",
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Generate schema using ClaudeCodeTool (legacy fallback)."""
        from ..tools.claude_code_tool import ClaudeCodeTool
        from ..skills.loader import SkillLoader

        try:
            # Load database-schema-generation skill
            skill = None
            try:
                engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                loader = SkillLoader(engine_root)
                skill = loader.load_skill("database-schema-generation")
                if skill:
                    self.logger.info("skill_loaded", skill_name=skill.name, tokens=skill.instruction_tokens)
            except Exception as e:
                self.logger.debug("skill_load_failed", error=str(e))

            skill_prompt = self._build_schema_prompt()

            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=300,
                skill=skill,
            )

            result = await tool.execute(
                prompt=skill_prompt,
                context=f"Generating {self.db_type} database schema from contracts",
                agent_type="database",
            )

            if result.success:
                prisma_valid = True
                if self.db_type == "prisma":
                    prisma_valid = await self._validate_prisma_schema()
                    if not prisma_valid:
                        self.logger.warning("prisma_schema_invalid",
                                            msg="Schema has errors, attempting fix pass")
                        prisma_valid = await self._fix_and_revalidate_prisma()

                self.logger.info("DATABASE_SCHEMA_GENERATED",
                                 files_created=len(result.files) if result.files else 0,
                                 db_type=self.db_type,
                                 next_agent="APIAgent",
                                 prisma_valid=prisma_valid)

                await self.shared_state.update_backend_chain(database_schema_generated=True)

                return database_schema_generated_event(
                    source=self.name,
                    db_type=self.db_type,
                    tables_created=len(result.files) if result.files else 0,
                    schema_valid=prisma_valid,
                )
            else:
                self.logger.error("database_schema_generation_failed", error=result.error)
                return database_schema_failed_event(
                    source=self.name,
                    error_message=result.error,
                    db_type=self.db_type,
                )

        except Exception as e:
            self.logger.error("database_agent_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"DatabaseAgent error: {str(e)}",
            )

    def _get_operator_system_prompt(self) -> str:
        """System prompt for the SchemaOperator autogen agent."""
        return f"""You are a database schema expert specializing in {self.db_type.upper()}.

Your role is to generate production-ready database schemas from TypeScript contracts.

## Available MCP Tools

You have access to these tools for database operations:

### Prisma Tools
- `prisma_generate` - Generate Prisma Client from schema
- `prisma_db_push` - Push schema changes to database
- `prisma_migrate_dev` - Create and apply migrations
- `prisma_migrate_status` - Check migration status
- `prisma_format` - Format schema.prisma file

### Docker Tools
- `docker_list_containers` - List running containers (check if PostgreSQL is up)
- `docker_start_container` - Start a stopped container
- `docker_logs` - View container logs for debugging

### Filesystem Tools
- `filesystem_read_file` - Read existing schema or config files
- `filesystem_write_file` - Write schema files
- `filesystem_list_files` - List files in directory

### NPM Tools
- `npm_install` - Install packages (e.g., @prisma/client, prisma)
- `npm_run` - Run npm scripts

### Claude Code Tool
- `claude_code` - For complex code generation beyond simple file writes

## Workflow

1. Use `filesystem_list_files` to check current project structure
2. Use `filesystem_read_file` to read existing contracts/interfaces
3. Use `claude_code` to generate the Prisma schema
4. Use `prisma_format` to format the schema
5. Use `docker_list_containers` to verify PostgreSQL is running
6. Use `prisma_generate` to create the Prisma Client
7. Use `prisma_migrate_dev` to create migrations

## CRITICAL RULES

- NEVER generate mock data arrays or in-memory stores
- NEVER use TODO/FIXME placeholders
- ALL data must come from real database connections
- Use environment variables for credentials (DATABASE_URL)
- Generate COMPLETE files, not partial snippets

When done, say TASK_COMPLETE."""

    def _get_validator_system_prompt(self) -> str:
        """System prompt for the SchemaValidator autogen agent."""
        return f"""You are a database schema QA validator.

Review the {self.db_type} schema generated by the operator and verify:

1. **Completeness**: All entities from contracts are represented
2. **Relations**: Foreign keys, join tables, cascades are correct
3. **Types**: Proper types for each field (UUID, DateTime, String, etc.)
4. **No Mocks**: NO hardcoded data arrays, NO in-memory stores
5. **Best Practices**: Proper indexes, unique constraints, timestamps

If the schema passes validation, say TASK_COMPLETE.
If issues are found, describe them clearly for the operator to fix."""

    def _build_schema_prompt(self) -> str:
        """
        Build the prompt for database schema generation.

        Combines:
        1. Skill instructions (from SKILL.md)
        2. Contract data (entities, interfaces)
        3. Database type specific instructions
        """
        parts = []

        # 1. Get skill instructions if available
        if self.skill:
            parts.append(f"## Skill: {self.skill.name}")
            parts.append(self.skill.instructions)
            parts.append("\n---\n")
        elif self.skill_registry:
            skill = self.skill_registry.get_skill("database-schema-generation")
            if skill:
                parts.append(f"## Skill: {skill.name}")
                parts.append(skill.instructions)
                parts.append("\n---\n")

        # 2. Database type specific context
        parts.append(f"## Target Database ORM: {self.db_type.upper()}")
        parts.append(self._get_db_type_instructions())
        parts.append("\n")

        # 3. Contract data
        parts.append("## Contracts to Process")
        if self._contracts_data:
            parts.append(self._format_contracts())
        else:
            parts.append("No contracts provided. Analyze the project for TypeScript interfaces.")
        parts.append("\n")

        # 3.5 Rich Context: ER Diagrams and Entity Definitions from RichContextProvider
        if hasattr(self.shared_state, 'context_provider') and self.shared_state.context_provider:
            try:
                # Check if it's a RichContextProvider with database context
                if hasattr(self.shared_state.context_provider, 'for_database_agent'):
                    db_context = self.shared_state.context_provider.for_database_agent()

                    # Include ER diagrams in prompt
                    er_diagrams = [d for d in db_context.diagrams if d.get("diagram_type") in ["erDiagram", "classDiagram"]]
                    if er_diagrams:
                        parts.append("## Entity-Relationship Diagrams")
                        parts.append("Use these diagrams to understand the data model and relationships:\n")
                        for diagram in er_diagrams[:3]:  # Limit to top 3 diagrams
                            title = diagram.get("title", "ER Diagram")
                            content = diagram.get("content", "")
                            parts.append(f"### {title}")
                            parts.append(f"```mermaid\n{content}\n```")
                        parts.append("\n")

                    # Include entity definitions with relationships
                    if db_context.entities:
                        parts.append(f"## Data Entities from Documentation ({len(db_context.entities)})")
                        for entity in db_context.entities[:20]:  # Limit to 20 entities
                            name = entity.get("name", "Unknown")
                            desc = entity.get("description", "")
                            attrs = entity.get("attributes", [])
                            relations = entity.get("relationships", [])

                            parts.append(f"\n### {name}")
                            if desc:
                                parts.append(f"_{desc}_")
                            if attrs:
                                parts.append("**Attributes:**")
                                for attr in attrs[:10]:
                                    attr_name = attr.get("name", "")
                                    attr_type = attr.get("type", "string")
                                    required = "required" if attr.get("required") else "optional"
                                    parts.append(f"- {attr_name}: {attr_type} ({required})")
                            if relations:
                                parts.append("**Relationships:**")
                                for rel in relations:
                                    rel_type = rel.get("type", "relates to")
                                    target = rel.get("target", "?")
                                    parts.append(f"- {rel_type} → {target}")
                        parts.append("\n")

                    self.logger.info(
                        "rich_context_injected",
                        er_diagrams_count=len(er_diagrams),
                        entities_count=len(db_context.entities),
                    )
            except Exception as e:
                self.logger.debug("rich_context_extraction_failed", error=str(e))

        # 4. Task instructions
        parts.append("## Task")
        parts.append(self._get_task_instructions())

        # 5. Anti-Mock Policy (CRITICAL)
        parts.append("\n## ⚠️ ANTI-MOCK POLICY (CRITICAL)")
        parts.append("""
You MUST NOT generate:
- Hardcoded data arrays as "database"
- TODO/FIXME placeholders
- Mock/fake/dummy implementations
- In-memory Maps or Objects as data stores

You MUST generate:
- Real Prisma/SQLAlchemy/Drizzle schemas
- Proper database connections
- Real migrations
- Environment variable references for credentials
""")

        return "\n".join(parts)

    def _get_db_type_instructions(self) -> str:
        """Get instructions specific to the database type."""
        instructions = {
            "prisma": """
Create files:
- prisma/schema.prisma - Full Prisma schema with models
- src/db/client.ts - PrismaClient setup
- prisma/seed.ts - Seed data script (real data, not mocks)

Use Prisma conventions:
- @id @default(uuid()) for IDs
- @unique for email, username fields
- @relation for foreign keys
- DateTime with @default(now()) for timestamps
""",
            "sqlalchemy": """
Create files:
- src/db/models.py - SQLAlchemy models
- src/db/database.py - Engine and session setup
- src/db/seed.py - Seed data script

Use SQLAlchemy conventions:
- Column(UUID, primary_key=True, default=uuid4)
- relationship() for relations
- ForeignKey for foreign keys
""",
            "drizzle": """
Create files:
- src/db/schema.ts - Drizzle schema
- src/db/index.ts - Database connection
- drizzle.config.ts - Drizzle configuration

Use Drizzle conventions:
- pgTable/mysqlTable for tables
- serial/uuid for primary keys
- relations() for relationships
""",
            "typeorm": """
Create files:
- src/entities/*.ts - TypeORM entities
- src/db/data-source.ts - DataSource configuration
- src/db/seed.ts - Seed data

Use TypeORM conventions:
- @Entity() decorator
- @PrimaryGeneratedColumn('uuid')
- @ManyToOne, @OneToMany for relations
""",
        }
        return instructions.get(self.db_type, instructions["prisma"])

    def _get_task_instructions(self) -> str:
        """Get the main task instructions."""
        return f"""
Generate a complete {self.db_type} database schema based on the contracts above.

Steps:
1. Analyze TypeScript interfaces to identify entities
2. Detect relationships:
   - Arrays of type → One-to-Many
   - Single references → Many-to-One or One-to-One
   - Cross-references → Many-to-Many (junction table)
3. Generate the schema files with proper types
4. Create a seed file with realistic sample data
5. Ensure all connections use environment variables

Output the complete files. Do NOT use placeholder comments or TODOs.
"""

    def _format_contracts(self) -> str:
        """Format contract data for the prompt."""
        if not self._contracts_data:
            return "No contract data available."

        parts = []

        # Entities
        entities = self._contracts_data.get("entities", [])
        if entities:
            parts.append("### Entities Detected")
            for entity in entities:
                parts.append(f"- {entity.get('name', 'Unknown')}")
                if "fields" in entity:
                    for field in entity["fields"]:
                        parts.append(f"  - {field.get('name')}: {field.get('type')}")

        # Interfaces
        interfaces = self._contracts_data.get("interfaces", [])
        if interfaces:
            parts.append("\n### TypeScript Interfaces")
            for interface in interfaces[:10]:  # Limit to avoid token overflow
                parts.append(f"```typescript\n{interface}\n```")

        # Relations
        relations = self._contracts_data.get("relations", [])
        if relations:
            parts.append("\n### Detected Relations")
            for rel in relations:
                parts.append(f"- {rel.get('from')} → {rel.get('to')} ({rel.get('type', '1:n')})")

        return "\n".join(parts) if parts else "Contract data present but no entities detected."

    def _extract_entities_from_contracts(self) -> list[str]:
        """Extract entity names from contracts data."""
        if not self._contracts_data:
            return []

        entities = self._contracts_data.get("entities", [])
        return [e.get("name", "Unknown") for e in entities if isinstance(e, dict)]

    async def _validate_prisma_schema(self) -> bool:
        """
        Run prisma generate to validate the schema compiles.

        Uses MCP Prisma tools when available, falls back to subprocess.
        Returns True if schema is valid, False if there are errors.
        """
        self.logger.info("validating_prisma_schema")

        try:
            # Check if prisma schema exists
            schema_path = Path(self.working_dir) / "prisma" / "schema.prisma"
            if not schema_path.exists():
                schema_path = Path(self.working_dir) / "schema.prisma"
                if not schema_path.exists():
                    self.logger.warning("prisma_schema_not_found")
                    return False

            # Try to use MCP Prisma tool first
            try:
                from src.mcp.tool_registry import get_tool_registry
                registry = get_tool_registry()

                # Use prisma.generate via MCP
                result = registry.call_tool("prisma.generate", cwd=str(self.working_dir))

                if isinstance(result, str):
                    import json
                    try:
                        result = json.loads(result)
                    except json.JSONDecodeError:
                        result = {"success": "error" not in result.lower(), "output": result}

                if result.get("success", False):
                    self.logger.info("prisma_schema_valid", method="mcp")
                    return True
                else:
                    self.logger.warning(
                        "prisma_generate_failed",
                        method="mcp",
                        stderr=str(result.get("output", result.get("error", "")))[:1000],
                    )
                    return False

            except Exception as mcp_err:
                self.logger.debug("mcp_prisma_not_available", error=str(mcp_err))

                # Fallback to direct subprocess
                import subprocess
                env = os.environ.copy()

                # Load .env if exists
                env_file = Path(self.working_dir) / ".env"
                if env_file.exists():
                    for line in env_file.read_text().splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env[key.strip()] = value.strip().strip('"').strip("'")

                proc = subprocess.run(
                    ["npx", "prisma", "generate"],
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=120,
                )

                if proc.returncode == 0:
                    self.logger.info("prisma_schema_valid", method="subprocess")
                    return True
                else:
                    self.logger.warning(
                        "prisma_generate_failed",
                        method="subprocess",
                        stderr=proc.stderr[:1000],
                    )
                    return False

        except Exception as e:
            self.logger.error("prisma_validation_error", error=str(e))
            return False

    async def _fix_and_revalidate_prisma(self) -> bool:
        """
        Attempt to fix Prisma schema errors and revalidate.

        Uses MCP tools to read schema, get error output, and fix via Claude Code.
        """
        self.logger.info("attempting_prisma_schema_fix")

        try:
            from src.mcp.tool_registry import get_tool_registry
            registry = get_tool_registry()

            # Read current schema using MCP filesystem tool
            schema_path = Path(self.working_dir) / "prisma" / "schema.prisma"
            if not schema_path.exists():
                schema_path = Path(self.working_dir) / "schema.prisma"

            if not schema_path.exists():
                return False

            # Try to read via MCP, fallback to direct read
            try:
                schema_result = registry.call_tool("filesystem.read_file", path=str(schema_path))
                if isinstance(schema_result, str):
                    import json
                    try:
                        parsed = json.loads(schema_result)
                        schema_content = parsed.get("content", schema_result)
                    except json.JSONDecodeError:
                        schema_content = schema_result
                else:
                    schema_content = schema_result.get("content", str(schema_result))
            except Exception:
                schema_content = schema_path.read_text()

            # Get the error output from prisma generate
            try:
                error_result = registry.call_tool("prisma.generate", cwd=str(self.working_dir))
                if isinstance(error_result, str):
                    error_output = error_result
                else:
                    error_output = str(error_result.get("output", error_result.get("error", "")))
            except Exception as e:
                error_output = str(e)

            # Use Claude Code tool to fix the schema
            from ..tools.claude_code_tool import ClaudeCodeTool

            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=120,
            )

            fix_prompt = f"""Fix the Prisma schema errors.

## Current Schema (prisma/schema.prisma):
```prisma
{schema_content[:3000]}
```

## Prisma Generate Errors:
```
{error_output[:2000]}
```

## Instructions:
1. Analyze the error messages
2. Fix ALL schema errors
3. Ensure proper relation annotations
4. Keep all existing models and fields
5. Write the COMPLETE fixed schema to prisma/schema.prisma

Do NOT simplify the schema. Fix the actual errors.
"""

            fix_result = await tool.execute(
                prompt=fix_prompt,
                context="Fixing Prisma schema errors",
                agent_type="database",
            )

            if fix_result.success:
                # Revalidate
                revalidate_result = await self._validate_prisma_schema()
                if revalidate_result:
                    self.logger.info("prisma_schema_fixed_successfully")
                    return True
                else:
                    self.logger.warning("prisma_schema_fix_failed_still_invalid")
                    return False
            else:
                self.logger.warning("prisma_fix_execution_failed", error=fix_result.error)
                return False

        except Exception as e:
            self.logger.error("prisma_fix_error", error=str(e))
            return False

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Generating {self.db_type} database schema"
