"""
DatabaseSchemaAgent - Automatically manages database schema updates.

Supports multiple database/ORM tools:
- Prisma (TypeScript/JavaScript)
- SQLAlchemy/Alembic (Python)
- Drizzle ORM
- TypeORM
- Sequelize
- Mongoose (MongoDB)

Auto-detects the database tool based on project files and runs appropriate commands.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime
from enum import Enum

import structlog
import json
import re
from typing import Any

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType

# Import ClaudeCodeTool for LLM-based schema analysis
try:
    from src.tools.claude_code_tool import ClaudeCodeTool
    LLM_AVAILABLE = True
except ImportError:
    ClaudeCodeTool = None
    LLM_AVAILABLE = False

logger = structlog.get_logger(__name__)


class DatabaseTool(Enum):
    """Supported database/ORM tools."""
    PRISMA = "prisma"
    SQLALCHEMY = "sqlalchemy"
    DRIZZLE = "drizzle"
    TYPEORM = "typeorm"
    SEQUELIZE = "sequelize"
    MONGOOSE = "mongoose"
    UNKNOWN = "unknown"


class DatabaseSchemaAgent(AutonomousAgent):
    """
    Autonomous agent for managing database schema updates.

    Auto-detects database tool and runs appropriate commands:
    - Prisma: prisma generate, prisma db push
    - SQLAlchemy: alembic revision --autogenerate, alembic upgrade head
    - Drizzle: drizzle-kit generate, drizzle-kit push
    - TypeORM: typeorm migration:generate, typeorm migration:run
    - Sequelize: sequelize-cli db:migrate
    - Mongoose: (no migrations, schema is in code)
    """

    COOLDOWN_SECONDS = 10.0
    DEBOUNCE_SECONDS = 2.0

    # Schema file patterns for each tool
    SCHEMA_PATTERNS = {
        DatabaseTool.PRISMA: ["prisma/schema.prisma", "schema.prisma"],
        DatabaseTool.SQLALCHEMY: ["alembic.ini", "models/*.py", "src/models/*.py"],
        DatabaseTool.DRIZZLE: ["drizzle.config.ts", "drizzle/*.ts", "src/db/schema.ts"],
        DatabaseTool.TYPEORM: ["ormconfig.json", "ormconfig.ts", "src/entity/*.ts"],
        DatabaseTool.SEQUELIZE: [".sequelizerc", "models/*.js", "src/models/*.ts"],
        DatabaseTool.MONGOOSE: ["models/*.ts", "src/models/*.ts"],
    }

    def __init__(
        self,
        name: str = "DatabaseSchemaAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
        force_tool: Optional[DatabaseTool] = None,
        auto_migrate: bool = False,
        database_url: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.force_tool = force_tool
        self.auto_migrate = auto_migrate
        self.database_url = database_url
        self._last_update: Optional[datetime] = None
        self._pending_update: Optional[asyncio.Task] = None
        self._schema_hashes: dict[str, str] = {}
        self._detected_tool: Optional[DatabaseTool] = None
        self._code_tool: Optional[Any] = None  # Lazy-loaded ClaudeCodeTool
        self._llm_analysis_enabled = LLM_AVAILABLE
        self._previous_schema: Optional[str] = None  # For change tracking

        self.logger = logger.bind(agent=name, working_dir=working_dir)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Subscribe to file events and generation complete."""
        return [
            EventType.FILE_CREATED,
            EventType.FILE_MODIFIED,
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
        ]

    def _detect_database_tool(self) -> DatabaseTool:
        """Auto-detect which database tool is used in the project."""
        if self.force_tool:
            return self.force_tool

        working_path = Path(self.working_dir)

        # Check Prisma (most common in TS projects)
        if (working_path / "prisma" / "schema.prisma").exists():
            return DatabaseTool.PRISMA
        if (working_path / "schema.prisma").exists():
            return DatabaseTool.PRISMA

        # Check package.json for dependencies
        package_json = working_path / "package.json"
        if package_json.exists():
            try:
                import json
                pkg = json.loads(package_json.read_text())
                deps = {
                    **pkg.get("dependencies", {}),
                    **pkg.get("devDependencies", {}),
                }

                if "@prisma/client" in deps or "prisma" in deps:
                    return DatabaseTool.PRISMA
                if "drizzle-orm" in deps:
                    return DatabaseTool.DRIZZLE
                if "typeorm" in deps:
                    return DatabaseTool.TYPEORM
                if "sequelize" in deps:
                    return DatabaseTool.SEQUELIZE
                if "mongoose" in deps:
                    return DatabaseTool.MONGOOSE
            except Exception:
                pass

        # Check Python requirements
        requirements = working_path / "requirements.txt"
        if requirements.exists():
            try:
                content = requirements.read_text().lower()
                if "sqlalchemy" in content or "alembic" in content:
                    return DatabaseTool.SQLALCHEMY
            except Exception:
                pass

        # Check for alembic.ini
        if (working_path / "alembic.ini").exists():
            return DatabaseTool.SQLALCHEMY

        # Check drizzle config
        if (working_path / "drizzle.config.ts").exists():
            return DatabaseTool.DRIZZLE

        return DatabaseTool.UNKNOWN

    def _is_schema_file(self, file_path: str) -> bool:
        """Check if the file is a schema file for any supported tool."""
        file_path_lower = file_path.lower().replace("\\", "/")

        # Prisma
        if "schema.prisma" in file_path_lower:
            return True

        # SQLAlchemy/Python models
        if "/models/" in file_path_lower and file_path_lower.endswith(".py"):
            return True

        # Drizzle schema
        if "drizzle" in file_path_lower and file_path_lower.endswith(".ts"):
            return True
        if "schema.ts" in file_path_lower or "schema.js" in file_path_lower:
            return True

        # TypeORM entities
        if "/entity/" in file_path_lower or "/entities/" in file_path_lower:
            return True

        # Mongoose models
        if "/models/" in file_path_lower and file_path_lower.endswith((".ts", ".js")):
            return True

        return False

    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should act on any of these events."""
        for event in events:
            if event.type in (EventType.FILE_CREATED, EventType.FILE_MODIFIED):
                file_path = event.data.get("file_path", "") if event.data else ""

                if self._is_schema_file(file_path):
                    self._detected_tool = self._detect_database_tool()
                    self.logger.info(
                        "schema_file_change_detected",
                        file_path=file_path,
                        detected_tool=self._detected_tool.value,
                    )
                    if self._detected_tool != DatabaseTool.UNKNOWN:
                        return True

            elif event.type == EventType.GENERATION_COMPLETE:
                self._detected_tool = self._detect_database_tool()
                if self._detected_tool != DatabaseTool.UNKNOWN:
                    self.logger.info(
                        "generation_complete_checking_schema",
                        detected_tool=self._detected_tool.value,
                    )
                    return True

            elif event.type == EventType.BUILD_SUCCEEDED:
                self._detected_tool = self._detect_database_tool()
                if self._detected_tool == DatabaseTool.PRISMA:
                    client_path = Path(self.working_dir) / "node_modules" / ".prisma" / "client"
                    if not client_path.exists():
                        self.logger.info("build_succeeded_prisma_client_missing")
                        return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Handle the schema update with debouncing."""
        if self._last_update:
            elapsed = (datetime.now() - self._last_update).total_seconds()
            if elapsed < self.COOLDOWN_SECONDS:
                self.logger.debug("cooldown_active", remaining=self.COOLDOWN_SECONDS - elapsed)
                return

        if self._pending_update and not self._pending_update.done():
            self._pending_update.cancel()

        self._pending_update = asyncio.create_task(self._debounced_update(event))

    async def _debounced_update(self, event: Event) -> None:
        """Wait for writes to settle, then run schema commands."""
        try:
            await asyncio.sleep(self.DEBOUNCE_SECONDS)
            self._last_update = datetime.now()

            tool = self._detected_tool or self._detect_database_tool()
            if tool == DatabaseTool.UNKNOWN:
                self.logger.warning("no_database_tool_detected")
                return

            self.logger.info("starting_schema_update", tool=tool.value)

            # Run tool-specific commands
            if tool == DatabaseTool.PRISMA:
                await self._run_prisma_commands()
            elif tool == DatabaseTool.SQLALCHEMY:
                await self._run_sqlalchemy_commands()
            elif tool == DatabaseTool.DRIZZLE:
                await self._run_drizzle_commands()
            elif tool == DatabaseTool.TYPEORM:
                await self._run_typeorm_commands()
            elif tool == DatabaseTool.SEQUELIZE:
                await self._run_sequelize_commands()
            elif tool == DatabaseTool.MONGOOSE:
                self.logger.info("mongoose_no_migration_needed")

            await self._publish_success(tool)

        except asyncio.CancelledError:
            self.logger.debug("update_cancelled_newer_event")
        except Exception as e:
            self.logger.error("schema_update_error", error=str(e))
            await self._publish_error(str(e))

    # ==================== PRISMA ====================
    async def _run_prisma_commands(self) -> None:
        """Run Prisma CLI commands."""
        await self._run_command(
            ["npx", "prisma", "generate"],
            "prisma_generate",
        )

        if self._has_database_url():
            if self.auto_migrate:
                migration_name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                await self._run_command(
                    ["npx", "prisma", "migrate", "dev", "--name", migration_name],
                    "prisma_migrate",
                )
            else:
                await self._run_command(
                    ["npx", "prisma", "db", "push", "--accept-data-loss"],
                    "prisma_db_push",
                    allow_failure=True,
                )

    # ==================== SQLALCHEMY / ALEMBIC ====================
    async def _run_sqlalchemy_commands(self) -> None:
        """Run Alembic migration commands."""
        if not (Path(self.working_dir) / "alembic.ini").exists():
            self.logger.info("alembic_not_initialized_skipping")
            return

        if self.auto_migrate:
            # Generate migration
            await self._run_command(
                ["alembic", "revision", "--autogenerate", "-m", "auto_migration"],
                "alembic_autogenerate",
                use_python=True,
            )

            # Apply migration
            await self._run_command(
                ["alembic", "upgrade", "head"],
                "alembic_upgrade",
                use_python=True,
            )

    # ==================== DRIZZLE ====================
    async def _run_drizzle_commands(self) -> None:
        """Run Drizzle ORM commands."""
        await self._run_command(
            ["npx", "drizzle-kit", "generate"],
            "drizzle_generate",
        )

        if self._has_database_url():
            await self._run_command(
                ["npx", "drizzle-kit", "push"],
                "drizzle_push",
                allow_failure=True,
            )

    # ==================== TYPEORM ====================
    async def _run_typeorm_commands(self) -> None:
        """Run TypeORM migration commands."""
        if self.auto_migrate and self._has_database_url():
            await self._run_command(
                ["npx", "typeorm", "migration:generate", "-n", "AutoMigration"],
                "typeorm_generate",
            )
            await self._run_command(
                ["npx", "typeorm", "migration:run"],
                "typeorm_run",
            )

    # ==================== SEQUELIZE ====================
    async def _run_sequelize_commands(self) -> None:
        """Run Sequelize migration commands."""
        if self._has_database_url():
            await self._run_command(
                ["npx", "sequelize-cli", "db:migrate"],
                "sequelize_migrate",
                allow_failure=True,
            )

    # ==================== HELPERS ====================
    async def _run_command(
        self,
        cmd: list[str],
        label: str,
        use_python: bool = False,
        allow_failure: bool = False,
    ) -> bool:
        """Run a shell command via tool registry with logging."""
        self.logger.info(f"running_{label}", command=" ".join(cmd))

        try:
            # Use python -m for Python tools
            if use_python and cmd[0] in ("alembic",):
                cmd = ["python", "-m"] + cmd

            # Route through tool registry based on command type
            if cmd[0] == "npx" and len(cmd) > 1:
                # npx commands → npm.npx tool
                result = await self.call_tool(
                    "npm.npx",
                    command=cmd[1],
                    args=" ".join(cmd[2:]) if len(cmd) > 2 else "",
                    cwd=str(self.working_dir),
                )
            elif cmd[0] == "npm":
                result = await self.call_tool(
                    "npm.run_cmd",
                    cmd=" ".join(cmd[1:]),
                    cwd=str(self.working_dir),
                )
            else:
                # Fallback: use node.run_script for other commands
                result = await self.call_tool(
                    "npm.npx",
                    command=cmd[0],
                    args=" ".join(cmd[1:]) if len(cmd) > 1 else "",
                    cwd=str(self.working_dir),
                )

            if result.get("success"):
                self.logger.info(f"{label}_success")
                return True
            else:
                output = result.get("output", result.get("error", ""))
                if allow_failure:
                    self.logger.warning(
                        f"{label}_failed_allowed",
                        stderr=str(output)[:500],
                    )
                    return True
                else:
                    self.logger.error(
                        f"{label}_failed",
                        stderr=str(output)[:1000],
                    )
                    return False

        except Exception as e:
            self.logger.error(f"{label}_exception", error=str(e))
            return False

    def _has_database_url(self) -> bool:
        """Check if DATABASE_URL is available."""
        env = self._get_env()
        return bool(env.get("DATABASE_URL"))

    def _get_env(self) -> dict:
        """Get environment variables including .env file."""
        env = os.environ.copy()

        if self.database_url:
            env["DATABASE_URL"] = self.database_url

        # Load from .env
        env_file = Path(self.working_dir) / ".env"
        if env_file.exists():
            try:
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        if key.strip() not in env:
                            env[key.strip()] = value.strip().strip('"').strip("'")
            except Exception:
                pass

        return env

    # ==================== LLM SCHEMA ANALYSIS ====================
    async def _analyze_schema_change(
        self, old_schema: str, new_schema: str
    ) -> Optional[dict]:
        """
        Use Claude to analyze schema changes and detect breaking changes.

        This provides intelligent analysis of schema modifications to:
        1. Identify added/removed tables and columns
        2. Detect breaking changes (data loss risk)
        3. Explain type changes and their implications
        4. Provide migration recommendations

        Args:
            old_schema: Previous schema content
            new_schema: New schema content

        Returns:
            Analysis dict with changes, risk level, and recommendations
        """
        if not self._llm_analysis_enabled or ClaudeCodeTool is None:
            return None

        # Lazy-load code tool
        if self._code_tool is None:
            try:
                self._code_tool = ClaudeCodeTool(working_dir=self.working_dir)
            except Exception as e:
                self.logger.warning("code_tool_init_failed", error=str(e))
                self._llm_analysis_enabled = False
                return None

        prompt = f"""Analyze this database schema change:

OLD SCHEMA:
```
{old_schema[:5000]}
```

NEW SCHEMA:
```
{new_schema[:5000]}
```

Identify and return ONLY JSON (no markdown, no explanation):
{{
  "changes": {{
    "added_tables": ["list of new tables"],
    "removed_tables": ["list of removed tables - BREAKING!"],
    "added_columns": [{{"table": "...", "column": "...", "type": "..."}}],
    "removed_columns": [{{"table": "...", "column": "..." }}],
    "type_changes": [{{"table": "...", "column": "...", "from": "...", "to": "..."}}],
    "relation_changes": ["list of relation modifications"]
  }},
  "risk_level": "none|low|medium|high|critical",
  "breaking_changes": ["list of changes that may cause data loss"],
  "recommendations": ["list of migration recommendations"],
  "safe_to_auto_apply": true or false
}}
"""

        try:
            result = await asyncio.wait_for(
                self._code_tool.execute(prompt, "", "database"),
                timeout=30.0
            )

            output = result.output if hasattr(result, 'output') else str(result)

            # Extract JSON from output
            json_match = re.search(r'\{[\s\S]*"changes"[\s\S]*\}', output)
            if json_match:
                analysis = json.loads(json_match.group())

                self.logger.info(
                    "schema_change_analysis",
                    risk_level=analysis.get("risk_level"),
                    breaking_changes=len(analysis.get("breaking_changes", [])),
                    safe_to_auto_apply=analysis.get("safe_to_auto_apply"),
                )

                return analysis

        except asyncio.TimeoutError:
            self.logger.debug("schema_analysis_timeout")
        except Exception as e:
            self.logger.debug("schema_analysis_failed", error=str(e))

        return None

    def _read_current_schema(self) -> Optional[str]:
        """Read the current schema file content."""
        tool = self._detected_tool or self._detect_database_tool()

        schema_paths = {
            DatabaseTool.PRISMA: ["prisma/schema.prisma", "schema.prisma"],
            DatabaseTool.DRIZZLE: ["drizzle/schema.ts", "src/db/schema.ts"],
            DatabaseTool.SQLALCHEMY: ["models/*.py", "src/models/*.py"],
            DatabaseTool.TYPEORM: ["src/entity/*.ts"],
        }

        if tool not in schema_paths:
            return None

        working_path = Path(self.working_dir)
        for pattern in schema_paths[tool]:
            # Handle glob patterns
            if "*" in pattern:
                import glob
                matches = glob.glob(str(working_path / pattern))
                if matches:
                    try:
                        return Path(matches[0]).read_text(encoding="utf-8")
                    except Exception:
                        pass
            else:
                path = working_path / pattern
                if path.exists():
                    try:
                        return path.read_text(encoding="utf-8")
                    except Exception:
                        pass

        return None

    async def _check_and_analyze_changes(self) -> Optional[dict]:
        """Check for schema changes and analyze them with LLM."""
        current_schema = self._read_current_schema()
        if not current_schema:
            return None

        # Compare with previous
        if self._previous_schema and current_schema != self._previous_schema:
            analysis = await self._analyze_schema_change(
                self._previous_schema, current_schema
            )

            # Update stored schema
            self._previous_schema = current_schema
            return analysis

        # First run - just store the schema
        self._previous_schema = current_schema
        return None

    async def _publish_success(self, tool: DatabaseTool) -> None:
        """Publish schema update success event."""
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=EventType.FILE_MODIFIED,
                source=self.name,
                data={
                    "action": "database_schema_synced",
                    "tool": tool.value,
                    "working_dir": self.working_dir,
                    "timestamp": datetime.now().isoformat(),
                },
            ))

    async def _publish_error(self, error_message: str) -> None:
        """Publish schema update error event."""
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=EventType.VALIDATION_ERROR,
                source=self.name,
                data={
                    "error_type": "database_schema_error",
                    "message": error_message,
                    "working_dir": self.working_dir,
                },
            ))


async def create_database_schema_agent(
    event_bus,
    working_dir: str = ".",
    auto_migrate: bool = False,
    database_url: Optional[str] = None,
    auto_start: bool = True,
) -> DatabaseSchemaAgent:
    """Factory function to create and start a DatabaseSchemaAgent."""
    agent = DatabaseSchemaAgent(
        event_bus=event_bus,
        working_dir=working_dir,
        auto_migrate=auto_migrate,
        database_url=database_url,
    )

    if auto_start:
        asyncio.create_task(agent.start())

    return agent
