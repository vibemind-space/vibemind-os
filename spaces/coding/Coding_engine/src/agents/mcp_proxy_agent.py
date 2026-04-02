"""
MCP Proxy Agent - Routes tasks to MCP agents based on events.

This agent acts as a bridge between the Coding Engine's event system
and the MCP agent pool. When specific events occur, it spawns the
appropriate MCP agent to handle specialized tasks.

Example workflows:
- BUILD_FAILED → spawn npm agent to fix dependencies
- E2E_TEST_FAILED → spawn playwright agent for visual debugging
- DATABASE_SCHEMA_GENERATED → spawn prisma agent for migrations
"""

import asyncio
from typing import Optional
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    agent_event,
)
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent
from ..mcp.agent_pool import MCPAgentPool
from ..mcp.registry import MCPRegistry


logger = structlog.get_logger(__name__)


# Event to MCP Agent mapping
# Key: EventType that triggers MCP agent
# Value: List of (agent_name, task_template) tuples
MCP_EVENT_ROUTING = {
    # Build & Dependencies
    EventType.BUILD_FAILED: [
        ("npm", "Analyze build failure and fix package dependencies. Error: {error_message}"),
    ],

    # Database
    EventType.DATABASE_SCHEMA_GENERATED: [
        ("prisma", "Generate and apply database migration for schema changes"),
    ],

    # E2E Testing
    EventType.E2E_TEST_FAILED: [
        ("playwright", "Debug E2E test failure: {test_name}. Take screenshot and analyze UI state."),
    ],
    EventType.SANDBOX_TEST_FAILED: [
        ("playwright", "Investigate sandbox test failure in Docker container"),
    ],

    # Browser Errors
    EventType.BROWSER_ERROR: [
        ("playwright", "Investigate browser error: {error_message}"),
    ],
    EventType.BROWSER_CONSOLE_ERROR: [
        ("playwright", "Debug console error: {error_message}"),
    ],

    # Deployment Verification
    EventType.DEPLOY_SUCCEEDED: [
        ("playwright", "Verify deployment by testing critical user flows"),
    ],

    # Code Search & Context
    EventType.GENERATION_REQUESTED: [
        ("supermemory", "Search for relevant code patterns: {requirement_name}"),
    ],

    # Git Operations
    EventType.BUILD_SUCCEEDED: [
        # Only trigger git if configured
        # ("git", "Check git status and stage changes"),
    ],
}


class MCPProxyAgent(AutonomousAgent):
    """
    Proxy agent that delegates tasks to MCP agents based on events.

    This agent listens for specific event types and automatically
    spawns the appropriate MCP agent to handle specialized tasks.

    Subscribes to:
    - BUILD_FAILED, DATABASE_SCHEMA_GENERATED, E2E_TEST_FAILED,
    - BROWSER_ERROR, DEPLOY_SUCCEEDED, etc.

    Publishes:
    - AGENT_COMPLETED: After MCP agent finishes (success or failure)
    """

    # Cooldown to prevent rapid spawning
    COOLDOWN_SECONDS = 5.0

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        registry: MCPRegistry = None,
        enabled_agents: list[str] = None,
        **kwargs
    ):
        """
        Initialize the MCP Proxy Agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project working directory
            registry: MCP Registry (uses global if None)
            enabled_agents: List of enabled MCP agents (None = all available)
        """
        super().__init__(name, event_bus, shared_state, working_dir, **kwargs)

        self.pool = MCPAgentPool(working_dir, registry)
        self.enabled_agents = enabled_agents or self.pool.list_available()
        self._last_spawn_time: dict[str, float] = {}
        self._spawn_count: dict[str, int] = {}

        self.logger.info("mcp_proxy_agent_initialized",
                        enabled_agents=self.enabled_agents,
                        event_routing=list(MCP_EVENT_ROUTING.keys()))

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return list(MCP_EVENT_ROUTING.keys())

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if we should spawn an MCP agent.

        Acts when:
        - Event type is in MCP_EVENT_ROUTING
        - Target MCP agent is enabled and available
        - Not in cooldown period for that agent
        """
        import time

        for event in events:
            if event.type not in MCP_EVENT_ROUTING:
                continue

            routing = MCP_EVENT_ROUTING[event.type]
            for agent_name, _ in routing:
                # Skip if agent not enabled
                if agent_name not in self.enabled_agents:
                    continue

                # Skip if agent not available (missing requirements)
                if agent_name not in self.pool.list_available():
                    continue

                # Check cooldown
                last_spawn = self._last_spawn_time.get(agent_name, 0)
                if time.time() - last_spawn < self.COOLDOWN_SECONDS:
                    self.logger.debug("mcp_agent_in_cooldown",
                                     agent=agent_name,
                                     event=event.type.value)
                    continue

                return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Spawn MCP agents for matching events.

        For each event, finds the appropriate MCP agent and spawns it
        with a task derived from the event data.
        """
        import time

        for event in events:
            if event.type not in MCP_EVENT_ROUTING:
                continue

            routing = MCP_EVENT_ROUTING[event.type]
            event_data = event.data or {}

            for agent_name, task_template in routing:
                # Skip if not available
                if agent_name not in self.pool.list_available():
                    self.logger.debug("mcp_agent_unavailable",
                                     agent=agent_name)
                    continue

                # Skip if in cooldown
                last_spawn = self._last_spawn_time.get(agent_name, 0)
                if time.time() - last_spawn < self.COOLDOWN_SECONDS:
                    continue

                # Build task from template
                task = self._build_task(task_template, event, event_data)

                self.logger.info("mcp_proxy_spawning",
                               agent=agent_name,
                               event=event.type.value,
                               task=task[:80])

                # Update tracking
                self._last_spawn_time[agent_name] = time.time()
                self._spawn_count[agent_name] = self._spawn_count.get(agent_name, 0) + 1

                # Spawn agent
                result = await self.pool.spawn(
                    agent_name=agent_name,
                    task=task,
                )

                # Log result
                if result.success:
                    self.logger.info("mcp_proxy_success",
                                   agent=agent_name,
                                   duration=round(result.duration, 1))

                    # Publish completion event
                    await self._publish_agent_event(
                        f"MCP agent {agent_name} completed successfully"
                    )
                else:
                    self.logger.warning("mcp_proxy_failed",
                                       agent=agent_name,
                                       error=result.error[:100] if result.error else None)

                    # Publish error event (but don't fail the whole system)
                    await self._publish_agent_event(
                        f"MCP agent {agent_name} failed: {result.error[:50] if result.error else 'Unknown'}"
                    )

    def _build_task(self, template: str, event: Event, data: dict) -> str:
        """Build task string from template and event data."""
        # Common fields
        replacements = {
            "error_message": data.get("error_message") or data.get("message") or "",
            "test_name": data.get("test_name") or data.get("test") or "",
            "file_path": event.file_path or data.get("file") or "",
            "requirement_name": data.get("requirement_name") or data.get("name") or "",
            "requirement_id": event.requirement_id or data.get("requirement_id") or "",
        }

        # Format template with available data
        task = template
        for key, value in replacements.items():
            task = task.replace(f"{{{key}}}", str(value))

        return task

    async def _publish_agent_event(self, message: str):
        """Publish agent event for logging/tracking."""
        try:
            await self.event_bus.publish(Event(
                type=EventType.AGENT_COMPLETED,
                data={
                    "agent": self.name,
                    "message": message,
                    "component": "mcp_proxy",
                },
            ))
        except Exception as e:
            self.logger.debug("event_publish_failed", error=str(e))

    def get_stats(self) -> dict:
        """Get spawn statistics."""
        return {
            "enabled_agents": self.enabled_agents,
            "available_agents": self.pool.list_available(),
            "spawn_counts": self._spawn_count.copy(),
            "running": self.pool.list_running(),
        }


if __name__ == "__main__":
    # Test the agent
    print("MCPProxyAgent - Event to MCP Agent Routing:\n")

    for event_type, routing in MCP_EVENT_ROUTING.items():
        if routing:
            print(f"{event_type.value}:")
            for agent_name, task in routing:
                print(f"  → {agent_name}: {task[:60]}...")
            print()
