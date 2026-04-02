"""
Migration Agent - Autonomous agent for database migration management.

Manages database migrations including:
- Prisma migration generation and application
- SQLAlchemy/Alembic migration support
- Drizzle migration support
- Seed data management
- Rollback strategies

Publishes:
- DATABASE_MIGRATION_NEEDED: Migration required
- DATABASE_MIGRATION_COMPLETE: Migration successfully applied
- DATABASE_MIGRATION_FAILED: Migration failed
- DATABASE_SEED_COMPLETE: Seed data successfully inserted
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    database_migration_event,
    database_seed_complete_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin


logger = structlog.get_logger(__name__)


# Migration tool detection patterns
MIGRATION_TOOLS = {
    "prisma": {
        "config_file": "prisma/schema.prisma",
        "generate_cmd": ["npx", "prisma", "migrate", "dev", "--name"],
        "apply_cmd": ["npx", "prisma", "migrate", "deploy"],
        "reset_cmd": ["npx", "prisma", "migrate", "reset", "--force"],
        "seed_cmd": ["npx", "prisma", "db", "seed"],
        "status_cmd": ["npx", "prisma", "migrate", "status"],
    },
    "drizzle": {
        "config_file": "drizzle.config.ts",
        "generate_cmd": ["npx", "drizzle-kit", "generate:pg"],
        "apply_cmd": ["npx", "drizzle-kit", "push:pg"],
        "seed_cmd": None,
        "status_cmd": None,
    },
    "alembic": {
        "config_file": "alembic.ini",
        "generate_cmd": ["alembic", "revision", "--autogenerate", "-m"],
        "apply_cmd": ["alembic", "upgrade", "head"],
        "reset_cmd": ["alembic", "downgrade", "base"],
        "seed_cmd": None,
        "status_cmd": ["alembic", "current"],
    },
    "typeorm": {
        "config_file": "ormconfig.json",
        "generate_cmd": ["npx", "typeorm", "migration:generate", "-n"],
        "apply_cmd": ["npx", "typeorm", "migration:run"],
        "reset_cmd": ["npx", "typeorm", "migration:revert"],
        "seed_cmd": None,
        "status_cmd": ["npx", "typeorm", "migration:show"],
    },
}


class MigrationAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for database migration management.

    Triggers on:
    - DATABASE_SCHEMA_GENERATED: Generate migration after schema created
    - SCHEMA_UPDATE_NEEDED: Apply pending migrations

    Manages:
    - Migration generation
    - Migration application
    - Seed data
    - Rollback operations
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
        auto_generate_migrations: bool = True,
        auto_apply_migrations: bool = True,
        auto_run_seeds: bool = True,
        migration_tool: Optional[str] = None,
    ):
        """
        Initialize MigrationAgent.

        Args:
            event_bus: EventBus for pub/sub
            shared_state: SharedState for metrics
            working_dir: Project directory
            claude_tool: Optional Claude tool for AI assistance
            auto_generate_migrations: Automatically generate migrations
            auto_apply_migrations: Automatically apply migrations
            auto_run_seeds: Automatically run seed data
            migration_tool: Force specific tool (prisma, drizzle, alembic, typeorm)
        """
        super().__init__(
            name="MigrationAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.working_dir = Path(working_dir)
        self.claude_tool = claude_tool
        self.auto_generate_migrations = auto_generate_migrations
        self.auto_apply_migrations = auto_apply_migrations
        self.auto_run_seeds = auto_run_seeds
        self.forced_tool = migration_tool

        self._last_migration: Optional[datetime] = None
        self._detected_tool: Optional[str] = None
        self._migration_history: list[dict] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens for."""
        return [
            EventType.DATABASE_SCHEMA_GENERATED,
            EventType.SCHEMA_UPDATE_NEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Determine if agent should act on this event.

        Acts when:
        - Database schema was generated
        - Schema update is needed
        """
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Rate limit: Don't run migrations more than once per 30 seconds
            if self._last_migration:
                elapsed = (datetime.now() - self._last_migration).total_seconds()
                if elapsed < 30:
                    logger.debug(
                        "migration_skipped",
                        reason="rate_limited",
                        seconds_since_last=elapsed,
                    )
                    continue

            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Manage database migrations.

        Uses autogen team if available, falls back to direct tool execution.
        """
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> None:
        """Manage migrations using autogen MigrationOperator + MigrationValidator team."""
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_migration = datetime.now()

        try:
            tool = await self._detect_migration_tool()
            tool_name = tool or "prisma"

            task = self.build_task_prompt(events, extra_context=f"""
## Database Migration Task

Manage database migrations for the project at {self.working_dir}.

Detected migration tool: {tool_name}
Trigger: {event.type.value}
Auto-generate: {self.auto_generate_migrations}
Auto-apply: {self.auto_apply_migrations}
Auto-seed: {self.auto_run_seeds}

Steps:
1. Check migration status (pending migrations)
2. Generate migration if schema changed
3. Apply pending migrations
4. Run seed data if enabled
""")

            team = self.create_team(
                operator_name="MigrationOperator",
                operator_prompt=f"""You are a database migration expert for {tool_name}.

Your role is to manage database migrations:
- Detect the migration tool (prisma, drizzle, alembic, typeorm)
- Check for pending migrations
- Generate new migrations when schema changes
- Apply migrations safely
- Run seed data

Use the appropriate commands for {tool_name}.
When done, say TASK_COMPLETE.""",
                validator_name="MigrationValidator",
                validator_prompt=f"""You are a database migration validator for {tool_name}.

Review the migration operations and verify:
1. Migrations were generated correctly
2. Migrations applied without errors
3. Seed data was inserted (if applicable)
4. No data loss occurred

If all migrations are healthy, say TASK_COMPLETE.
If issues are found, describe them for the operator to fix.""",
                tool_categories=["prisma", "npm"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                self._detected_tool = tool_name
                await self.event_bus.publish(database_migration_event(
                    source="MigrationAgent",
                    success=True,
                    tool=tool_name,
                ))
                logger.info("migration_complete", tool=tool_name, mode="autogen")
            else:
                await self._publish_failure(f"Autogen migration failed: {result['result_text'][:200]}")

        except Exception as e:
            logger.error("migration_autogen_error", error=str(e))
            await self._publish_failure(f"Migration autogen error: {str(e)}")

    async def _act_legacy(self, events: list[Event]) -> None:
        """Manage migrations using direct tool calls (legacy)."""
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_migration = datetime.now()

        logger.info(
            "migration_started",
            working_dir=str(self.working_dir),
            trigger_event=event.type.value,
        )

        tool = await self._detect_migration_tool()
        if not tool:
            logger.warning("no_migration_tool_detected")
            return

        self._detected_tool = tool
        logger.info("migration_tool_detected", tool=tool)

        pending_migrations = await self._check_migration_status(tool)

        if event.type == EventType.DATABASE_SCHEMA_GENERATED and self.auto_generate_migrations:
            migration_name = event.data.get("migration_name", "schema_update")
            success = await self._generate_migration(tool, migration_name)
            if not success:
                await self._publish_failure("Migration generation failed")
                return

        if self.auto_apply_migrations:
            success = await self._apply_migrations(tool)
            if not success:
                await self._publish_failure("Migration application failed")
                return

        if self.auto_run_seeds:
            await self._run_seeds(tool)

        await self.event_bus.publish(database_migration_event(
            source="MigrationAgent",
            success=True,
            tool=tool,
        ))

        logger.info("migration_complete", tool=tool)

    async def _detect_migration_tool(self) -> Optional[str]:
        """Detect which migration tool is being used."""

        if self.forced_tool:
            return self.forced_tool

        for tool_name, tool_config in MIGRATION_TOOLS.items():
            config_file = self.working_dir / tool_config["config_file"]
            if config_file.exists():
                return tool_name

        # Check package.json for dependencies
        package_json = self.working_dir / "package.json"
        if package_json.exists():
            try:
                content = json.loads(package_json.read_text())
                deps = {
                    **content.get("dependencies", {}),
                    **content.get("devDependencies", {}),
                }

                if "prisma" in deps or "@prisma/client" in deps:
                    return "prisma"
                if "drizzle-orm" in deps:
                    return "drizzle"
                if "typeorm" in deps:
                    return "typeorm"
            except json.JSONDecodeError:
                pass

        # Check requirements.txt for Python tools
        requirements = self.working_dir / "requirements.txt"
        if requirements.exists():
            content = requirements.read_text().lower()
            if "alembic" in content:
                return "alembic"

        return None

    async def _run_migration_cmd(self, cmd: list[str]) -> dict:
        """Route a migration command through the tool registry."""
        if cmd[0] == "npx" and len(cmd) > 1:
            result = await self.call_tool(
                "npm.npx", command=cmd[1],
                args=" ".join(cmd[2:]) if len(cmd) > 2 else "",
                cwd=str(self.working_dir),
            )
        elif cmd[0] == "npm":
            result = await self.call_tool(
                "npm.run_cmd", cmd=" ".join(cmd[1:]),
                cwd=str(self.working_dir),
            )
        else:
            # Fallback for alembic etc. via npx wrapper
            result = await self.call_tool(
                "npm.npx", command=cmd[0],
                args=" ".join(cmd[1:]) if len(cmd) > 1 else "",
                cwd=str(self.working_dir),
            )
        return result

    async def _check_migration_status(self, tool: str) -> list[str]:
        """Check for pending migrations."""

        tool_config = MIGRATION_TOOLS.get(tool, {})
        status_cmd = tool_config.get("status_cmd")

        if not status_cmd:
            return []

        try:
            result = await self._run_migration_cmd(status_cmd)
            output = result.get("output", "")

            pending = []
            if "pending" in output.lower() or "not yet applied" in output.lower():
                lines = output.split("\n")
                for line in lines:
                    if "pending" in line.lower():
                        pending.append(line.strip())

            logger.info("migration_status_checked", pending_count=len(pending))
            return pending

        except Exception as e:
            logger.warning("migration_status_check_failed", error=str(e))
            return []

    async def _generate_migration(self, tool: str, name: str) -> bool:
        """Generate a new migration."""

        tool_config = MIGRATION_TOOLS.get(tool, {})
        generate_cmd = tool_config.get("generate_cmd")

        if not generate_cmd:
            logger.warning("migration_generation_not_supported", tool=tool)
            return True

        try:
            cmd = generate_cmd + [name]
            result = await self._run_migration_cmd(cmd)

            if not result.get("success"):
                logger.error(
                    "migration_generation_failed",
                    tool=tool,
                    stderr=result.get("output", "")[:500],
                )
                return False

            logger.info("migration_generated", tool=tool, name=name)

            self._migration_history.append({
                "action": "generate",
                "tool": tool,
                "name": name,
                "timestamp": datetime.now().isoformat(),
            })

            return True

        except Exception as e:
            logger.error("migration_generation_error", tool=tool, error=str(e))
            return False

    async def _apply_migrations(self, tool: str) -> bool:
        """Apply pending migrations."""

        tool_config = MIGRATION_TOOLS.get(tool, {})
        apply_cmd = tool_config.get("apply_cmd")

        if not apply_cmd:
            logger.warning("migration_apply_not_supported", tool=tool)
            return True

        try:
            result = await self._run_migration_cmd(apply_cmd)

            if not result.get("success"):
                logger.error(
                    "migration_apply_failed",
                    tool=tool,
                    stderr=result.get("output", "")[:500],
                )
                return False

            logger.info("migrations_applied", tool=tool)

            self._migration_history.append({
                "action": "apply",
                "tool": tool,
                "timestamp": datetime.now().isoformat(),
            })

            return True

        except Exception as e:
            logger.error("migration_apply_error", tool=tool, error=str(e))
            return False

    async def _run_seeds(self, tool: str) -> bool:
        """Run seed data."""

        tool_config = MIGRATION_TOOLS.get(tool, {})
        seed_cmd = tool_config.get("seed_cmd")

        if not seed_cmd:
            package_json = self.working_dir / "package.json"
            if package_json.exists():
                try:
                    content = json.loads(package_json.read_text())
                    scripts = content.get("scripts", {})
                    if "seed" in scripts or "db:seed" in scripts:
                        seed_cmd = ["npm", "run", "seed" if "seed" in scripts else "db:seed"]
                except json.JSONDecodeError:
                    pass

        if not seed_cmd:
            logger.debug("seed_command_not_available", tool=tool)
            return True

        try:
            result = await self._run_migration_cmd(seed_cmd)

            if not result.get("success"):
                logger.warning(
                    "seed_run_failed",
                    tool=tool,
                    stderr=result.get("output", "")[:500],
                )
                return False

            logger.info("seeds_applied", tool=tool)

            await self.event_bus.publish(database_seed_complete_event(
                source="MigrationAgent",
                tool=tool,
            ))

            return True

        except Exception as e:
            logger.warning("seed_run_error", tool=tool, error=str(e))
            return False

    async def _publish_failure(self, reason: str) -> None:
        """Publish migration failure event."""

        await self.event_bus.publish(database_migration_event(
            source="MigrationAgent",
            success=False,
            tool=self._detected_tool or "unknown",
            error=reason,
        ))

        logger.error("migration_failed", reason=reason)

    async def rollback(self, steps: int = 1) -> bool:
        """
        Rollback migrations.

        Args:
            steps: Number of migrations to rollback

        Returns:
            True if rollback successful
        """
        if not self._detected_tool:
            tool = await self._detect_migration_tool()
            if not tool:
                logger.error("rollback_failed", reason="no_tool_detected")
                return False
            self._detected_tool = tool

        tool_config = MIGRATION_TOOLS.get(self._detected_tool, {})
        reset_cmd = tool_config.get("reset_cmd")

        if not reset_cmd:
            logger.warning("rollback_not_supported", tool=self._detected_tool)
            return False

        try:
            result = await self._run_migration_cmd(reset_cmd)

            if not result.get("success"):
                logger.error(
                    "rollback_failed",
                    tool=self._detected_tool,
                    stderr=result.get("output", "")[:500],
                )
                return False

            logger.info("rollback_complete", tool=self._detected_tool)

            # Record in history
            self._migration_history.append({
                "action": "rollback",
                "tool": self._detected_tool,
                "steps": steps,
                "timestamp": datetime.now().isoformat(),
            })

            return True

        except Exception as e:
            logger.error("rollback_error", error=str(e))
            return False

    def get_migration_history(self) -> list[dict]:
        """Get migration operation history."""
        return self._migration_history.copy()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("migration_agent_cleanup_complete")
