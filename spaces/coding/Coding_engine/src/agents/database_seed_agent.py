"""
DatabaseSeedAgent - Automatically seeds the database with initial data.

This agent runs after database schema is applied and auth is set up,
executing seed scripts to populate the database with demo data.
"""

from pathlib import Path
from typing import Any

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType


class DatabaseSeedAgent(AutonomousAgent):
    """Agent that seeds the database with initial/demo data."""

    subscribed_events = [
        EventType.AUTH_SETUP_COMPLETE,
        EventType.DATABASE_SCHEMA_GENERATED,
        EventType.BUILD_SUCCEEDED,
        EventType.DEPLOY_SUCCEEDED,
    ]

    def __init__(
        self,
        name: str = "DatabaseSeed",
        event_bus: Any = None,
        shared_state: Any = None,
        working_dir: str = ".",
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.working_dir = Path(working_dir)
        self._seeded = False
        self._seed_attempted = False

    async def should_act(self, events: list[Event]) -> bool:
        """Act when auth/db setup is complete and we haven't seeded yet."""
        if self._seeded:
            return False

        for event in events:
            # Seed after auth is set up (most complete state)
            if event.type == EventType.AUTH_SETUP_COMPLETE:
                return True
            # Or after successful deploy if auth wasn't triggered
            if event.type == EventType.DEPLOY_SUCCEEDED and not self._seed_attempted:
                return True
            # Or after first successful build if nothing else triggered
            if event.type == EventType.BUILD_SUCCEEDED and not self._seed_attempted:
                # Only on first build success
                return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Execute database seeding."""
        self._seed_attempted = True
        self.logger.info("database_seed_starting", working_dir=str(self.working_dir))

        try:
            # Detect project type and seed method
            seed_result = await self._run_seed()

            if seed_result["success"]:
                self._seeded = True
                self.logger.info(
                    "database_seed_complete",
                    method=seed_result["method"],
                    output=seed_result.get("output", "")[:500],
                )
                await self._publish_event(
                    EventType.GENERATION_COMPLETE,  # Using available event type
                    data={
                        "component": "database_seed",
                        "success": True,
                        "method": seed_result["method"],
                        "message": "Database seeded successfully",
                    },
                )
            else:
                self.logger.warning(
                    "database_seed_failed",
                    method=seed_result.get("method", "unknown"),
                    error=seed_result.get("error", "Unknown error"),
                )
                # Don't publish failure - seeding is optional

        except Exception as e:
            self.logger.error("database_seed_error", error=str(e))

    async def _run_seed(self) -> dict:
        """Detect and run the appropriate seed script."""
        # Check for Python seed script
        python_seed = self.working_dir / "scripts" / "seed_database.py"
        if python_seed.exists():
            return await self._run_python_seed(python_seed)

        # Check for TypeScript/Prisma seed
        prisma_seed = self.working_dir / "prisma" / "seed.ts"
        if prisma_seed.exists():
            return await self._run_prisma_seed()

        # Check for npm db:seed script in package.json
        package_json = self.working_dir / "package.json"
        if package_json.exists():
            import json
            try:
                pkg = json.loads(package_json.read_text())
                if "db:seed" in pkg.get("scripts", {}):
                    return await self._run_npm_seed()
            except json.JSONDecodeError:
                pass

        return {
            "success": False,
            "method": "none",
            "error": "No seed script found",
        }

    async def _run_python_seed(self, seed_path: Path) -> dict:
        """Run Python seed script."""
        self.logger.info("running_python_seed", path=str(seed_path))

        try:
            result = await self.call_tool(
                "python.run_script",
                script_path=str(seed_path),
                cwd=str(self.working_dir),
            )

            if result.get("success"):
                return {
                    "success": True,
                    "method": "python",
                    "output": result.get("output", ""),
                }
            else:
                return {
                    "success": False,
                    "method": "python",
                    "error": result.get("output") or result.get("error", "Unknown error"),
                }

        except Exception as e:
            return {
                "success": False,
                "method": "python",
                "error": str(e),
            }

    async def _run_prisma_seed(self) -> dict:
        """Run Prisma seed via npx."""
        self.logger.info("running_prisma_seed")

        try:
            result = await self.call_tool(
                "npm.npx",
                command="prisma",
                args="db seed",
                cwd=str(self.working_dir),
            )

            if result.get("success"):
                return {
                    "success": True,
                    "method": "prisma",
                    "output": result.get("output", ""),
                }
            else:
                return {
                    "success": False,
                    "method": "prisma",
                    "error": result.get("output") or result.get("error", "Unknown error"),
                }

        except Exception as e:
            return {
                "success": False,
                "method": "prisma",
                "error": str(e),
            }

    async def _run_npm_seed(self) -> dict:
        """Run npm run db:seed."""
        self.logger.info("running_npm_seed")

        try:
            result = await self.call_tool(
                "npm.run_cmd",
                cmd="run db:seed",
                cwd=str(self.working_dir),
            )

            if result.get("success"):
                return {
                    "success": True,
                    "method": "npm",
                    "output": result.get("output", ""),
                }
            else:
                return {
                    "success": False,
                    "method": "npm",
                    "error": result.get("output") or result.get("error", "Unknown error"),
                }

        except Exception as e:
            return {
                "success": False,
                "method": "npm",
                "error": str(e),
            }

    async def _publish_event(self, event_type: EventType, data: dict) -> None:
        """Publish an event to the event bus."""
        if self.event_bus:
            event = Event(
                type=event_type,
                source=self.name,
                data=data,
            )
            await self.event_bus.publish(event)
