# -*- coding: utf-8 -*-
"""
Differential Fix Agent - Phase 21b

Routes CODE_FIX_NEEDED events from differential analysis to individual
MCP agents (filesystem, prisma, npm, etc.) via MCPAgentPool. Each MCP
agent has its own SocietyOfMind team (Operator + QA Validator) with
specialized tools.

Only handles CODE_FIX_NEEDED events where source_analysis starts with
"differential" — all other CODE_FIX_NEEDED events continue to be handled
by GeneratorAgent.

Event lifecycle:
    CODE_FIX_NEEDED (source_analysis="differential*")
        -> Determine gap type (schema, dependency, api, etc.)
        -> Spawn individual MCP agents via MCPAgentPool
        -> Publish DIFFERENTIAL_FIX_COMPLETE + CODE_FIXED on success
"""

import asyncio
from typing import Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Gap-type routing: keywords -> agent(s)
# ---------------------------------------------------------------------------

GAP_TYPE_KEYWORDS = {
    # Order matters: more specific types first
    "migration": [
        "migration", "migrate", "alembic", "seed", "db push",
    ],
    "dependency": [
        "package", "dependency", "npm", "install", "module not found",
        "cannot find module", "pnpm", "node_modules",
    ],
    "schema": [
        "schema", "prisma", "model", "table", "column", "entity",
        "database model", "db model", "data model",
    ],
}

GAP_AGENT_ROUTING = {
    "schema": ["claude-code", "prisma"],
    "migration": ["prisma"],
    "dependency": ["npm"],
    "api": ["claude-code"],
    "ui": ["claude-code"],
    "auth": ["claude-code"],
    "default": ["claude-code", "filesystem"],
}


class DifferentialFixAgent(AutonomousAgent):
    """
    Bridge agent that routes differential analysis gaps to individual MCP agents.

    Subscribes to CODE_FIX_NEEDED but only acts on events with
    source_analysis="differential" or "differential_epic". Uses MCPAgentPool
    to spawn the right MCP agent(s) based on gap type:
      - filesystem agent for code file creation/modification
      - prisma agent for schema and migrations
      - npm agent for package/dependency fixes
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self._pool = None
        self._fix_count = 0

    # ------------------------------------------------------------------
    # AutonomousAgent interface
    # ------------------------------------------------------------------

    @property
    def subscribed_events(self) -> list:
        return [EventType.CODE_FIX_NEEDED]

    async def should_act(self, events: list) -> bool:
        """Only act on CODE_FIX_NEEDED from differential analysis."""
        return any(self._is_differential_fix(e) for e in events)

    async def act(self, events: list) -> Optional[Event]:
        """Route differential gaps to individual MCP agents."""
        for event in events:
            if event.source == self.name:
                continue
            if not self._is_differential_fix(event):
                continue

            try:
                await self._handle_fix(event)
            except Exception as e:
                self.logger.error(
                    "differential_fix_error",
                    error=str(e),
                    requirement_id=event.data.get("requirement_id"),
                )

        return None

    # ------------------------------------------------------------------
    # Core Fix Routing
    # ------------------------------------------------------------------

    async def _handle_fix(self, event: Event) -> None:
        """Route a single differential gap to individual MCP agent(s)."""
        requirement_id = event.data.get("requirement_id", "unknown")
        epic_id = event.data.get("epic_id", "")
        reason = event.data.get("reason", "")
        gap_description = event.data.get("gap_description", "")
        suggested_tasks = event.data.get("suggested_tasks", [])

        # Determine which MCP agents to spawn
        gap_type = self._determine_gap_type(event)
        agent_names = GAP_AGENT_ROUTING.get(gap_type, GAP_AGENT_ROUTING["default"])

        self.logger.info(
            "routing_differential_fix",
            requirement_id=requirement_id,
            epic_id=epic_id,
            gap_type=gap_type,
            agents=agent_names,
        )

        pool = self._get_pool()
        if pool is None:
            self.logger.warning(
                "pool_unavailable",
                msg="MCPAgentPool not available, skipping fix",
            )
            return

        # Filter to available agents only
        available = pool.list_available()
        agent_names = [a for a in agent_names if a in available]
        if not agent_names:
            # Fallback: try filesystem
            if "filesystem" in available:
                agent_names = ["filesystem"]
            else:
                self.logger.warning("no_agents_available")
                return

        # Build tasks for each agent
        spawn_tasks = []
        for agent_name in agent_names:
            task_desc = self._build_agent_task(
                agent_name, requirement_id, gap_description or reason,
                suggested_tasks,
            )
            spawn_tasks.append({"agent": agent_name, "task": task_desc})

        try:
            # Spawn agent(s)
            if len(spawn_tasks) == 1:
                result = await pool.spawn(
                    spawn_tasks[0]["agent"],
                    spawn_tasks[0]["task"],
                )
                results = [result]
            else:
                results = await pool.spawn_parallel(spawn_tasks)

            success = any(r.success for r in results)
            self._fix_count += 1

            # Collect outputs
            outputs = []
            errors = []
            for r in results:
                if r.success and r.output:
                    outputs.append(f"[{r.agent}] {r.output[:500]}")
                if r.error:
                    errors.append(f"[{r.agent}] {r.error[:200]}")

            # Publish DIFFERENTIAL_FIX_COMPLETE
            await self.event_bus.publish(Event(
                type=EventType.DIFFERENTIAL_FIX_COMPLETE,
                source=self.name,
                data={
                    "requirement_id": requirement_id,
                    "epic_id": epic_id,
                    "success": success,
                    "fix_result": "\n".join(outputs) if outputs else "",
                    "error": "\n".join(errors) if errors and not success else None,
                    "fix_count": self._fix_count,
                    "gap_type": gap_type,
                    "agents_used": [r.agent for r in results],
                },
            ))

            # Also publish CODE_FIXED so downstream agents react
            if success:
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIXED,
                    source=self.name,
                    data={
                        "reason": f"Differential fix: {requirement_id}",
                        "requirement_id": requirement_id,
                        "epic_id": epic_id,
                        "source_analysis": "differential_fix",
                    },
                ))

            self.logger.info(
                "differential_fix_complete",
                requirement_id=requirement_id,
                success=success,
                gap_type=gap_type,
                agents=[r.agent for r in results],
            )

        except Exception as e:
            self.logger.error(
                "agent_execution_error",
                requirement_id=requirement_id,
                error=str(e),
            )

            await self.event_bus.publish(Event(
                type=EventType.DIFFERENTIAL_FIX_COMPLETE,
                source=self.name,
                data={
                    "requirement_id": requirement_id,
                    "epic_id": epic_id,
                    "success": False,
                    "error": str(e),
                },
            ))

    # ------------------------------------------------------------------
    # Gap Type Detection
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_gap_type(event: Event) -> str:
        """Determine gap type from event data using keyword matching."""
        gap_desc = event.data.get("gap_description", "").lower()
        reason = event.data.get("reason", "").lower()
        tasks = event.data.get("suggested_tasks", [])
        tasks_text = " ".join(str(t).lower() for t in tasks)

        search_text = f"{gap_desc} {reason} {tasks_text}"

        for gap_type, keywords in GAP_TYPE_KEYWORDS.items():
            if any(kw in search_text for kw in keywords):
                return gap_type

        return "default"

    # ------------------------------------------------------------------
    # Task Building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_agent_task(
        agent_name: str,
        requirement_id: str,
        description: str,
        suggested_tasks: list,
    ) -> str:
        """Build a task description tailored for the specific MCP agent."""
        tasks_text = ""
        if suggested_tasks:
            tasks_text = "\nSuggested implementation tasks:\n"
            for i, task in enumerate(suggested_tasks, 1):
                tasks_text += f"  {i}. {task}\n"

        if agent_name == "claude-code":
            return (
                f"Implement the missing requirement {requirement_id} for this NestJS project.\n\n"
                f"Gap description: {description}\n"
                f"{tasks_text}\n"
                f"Instructions:\n"
                f"1. First read the existing project structure (package.json, prisma/schema.prisma, src/ directory)\n"
                f"2. Check what already exists before creating new files\n"
                f"3. Create the missing NestJS service, controller, DTOs, and module files\n"
                f"4. Follow NestJS conventions: @Injectable() services, @Controller() controllers, class-validator DTOs\n"
                f"5. Import and register new modules in the parent module\n"
                f"6. Use the existing Prisma schema models — do NOT modify schema.prisma\n"
                f"7. Write production-ready TypeScript code with proper error handling\n"
            )
        elif agent_name == "prisma":
            return (
                f"Implement missing database requirement {requirement_id}.\n"
                f"Description: {description}\n"
                f"{tasks_text}\n"
                f"Use Prisma tools to create/update the schema and run migrations."
            )
        elif agent_name == "npm":
            return (
                f"Fix missing dependency for requirement {requirement_id}.\n"
                f"Description: {description}\n"
                f"{tasks_text}\n"
                f"Install required packages and verify they work."
            )
        else:
            # filesystem (default) — general code writing
            return (
                f"Task: Implement missing requirement {requirement_id}\n"
                f"Description: {description}\n"
                f"Type: fix_code\n"
                f"{tasks_text}\n"
                f"Create or modify the necessary source files to implement "
                f"the missing functionality."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_differential_fix(event: Event) -> bool:
        """Check if event is a CODE_FIX_NEEDED from differential analysis."""
        if event.type != EventType.CODE_FIX_NEEDED:
            return False
        source = event.data.get("source_analysis", "")
        return source.startswith("differential")

    def _get_pool(self):
        """Lazy-initialize the MCPAgentPool."""
        if self._pool is not None:
            return self._pool

        try:
            from ..mcp.agent_pool import MCPAgentPool

            self._pool = MCPAgentPool(working_dir=str(self.working_dir))
            self.logger.info(
                "mcp_agent_pool_initialized",
                available=self._pool.list_available(),
            )
            return self._pool

        except Exception as e:
            self.logger.warning("pool_init_failed", error=str(e))
            return None
