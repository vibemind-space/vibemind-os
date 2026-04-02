# -*- coding: utf-8 -*-
"""
MCP Event Bridge - Bidirectional integration between MCP Orchestrator and EventBus.

This module provides:
1. Event subscriptions to trigger MCP tasks automatically
2. Event publishing from MCP task results back to EventBus
3. Task-to-Event mapping for coordinated automation

Usage:
    from src.mcp.event_bridge import MCPEventBridge, get_event_bridge

    # Initialize bridge (connects to global EventBus and MCPOrchestrator)
    bridge = get_event_bridge()

    # Start listening for events
    await bridge.start()

    # Or manually trigger a task
    result = await bridge.execute_task(
        task="Deploy PostgreSQL for development",
        context={"project": "my-app"}
    )
"""
import asyncio
import uuid
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
import structlog

from ..mind.event_bus import EventBus, Event, EventType, get_event_bus
from ..mind.event_payloads import (
    MCPTaskStartedPayload,
    MCPTaskPlannedPayload,
    MCPTaskCompletePayload,
    MCPTaskFailedPayload,
    MCPToolExecutionPayload,
    MCPDockerEventPayload,
    MCPGitEventPayload,
    MCPNpmEventPayload,
    MCPFileEventPayload,
)
from .mcp_orchestrator import MCPOrchestrator, TaskResult, get_mcp_orchestrator

logger = structlog.get_logger()


@dataclass
class EventTaskMapping:
    """Maps an event type to an MCP task template."""
    event_type: EventType
    task_template: str  # Task description with {placeholders}
    context_extractor: Optional[Callable[[Event], Dict]] = None
    enabled: bool = True


# Default event-to-task mappings
DEFAULT_MAPPINGS: List[EventTaskMapping] = [
    # Deploy events -> Docker tasks
    EventTaskMapping(
        event_type=EventType.DEPLOY_STARTED,
        task_template="Start Docker containers for {project}",
        context_extractor=lambda e: {
            "project": e.data.get("project", "app"),
            "output_dir": e.data.get("output_dir", "."),
        },
    ),

    # Database events -> Docker PostgreSQL/Redis
    EventTaskMapping(
        event_type=EventType.DATABASE_MIGRATION_NEEDED,
        task_template="Start PostgreSQL database container for development",
        context_extractor=lambda e: {
            "db_type": e.data.get("db_type", "postgres"),
        },
    ),

    # Build events -> NPM tasks
    EventTaskMapping(
        event_type=EventType.BUILD_STARTED,
        task_template="Run npm build in {output_dir}",
        context_extractor=lambda e: {
            "output_dir": e.data.get("output_dir", "."),
            "script": "build",
        },
    ),

    # Test events -> NPM test
    EventTaskMapping(
        event_type=EventType.TEST_STARTED,
        task_template="Run npm test in {output_dir}",
        context_extractor=lambda e: {
            "output_dir": e.data.get("output_dir", "."),
            "script": "test",
        },
    ),

    # Scaffolding -> NPM install
    EventTaskMapping(
        event_type=EventType.PROJECT_SCAFFOLDED,
        task_template="Run npm install in {output_dir}",
        context_extractor=lambda e: {
            "output_dir": e.data.get("output_dir", "."),
        },
    ),

    # ==========================================================================
    # Phase 16: Additional Mappings for Full Automation
    # ==========================================================================

    # Database Schema Generated -> Start PostgreSQL/Redis containers
    EventTaskMapping(
        event_type=EventType.DATABASE_SCHEMA_GENERATED,
        task_template="Start PostgreSQL and Redis containers for development",
        context_extractor=lambda e: {
            "db_type": e.data.get("db_type", "postgres"),
            "schema_path": e.data.get("schema_path", ""),
        },
    ),

    # Contracts Generated -> Prepare development environment
    EventTaskMapping(
        event_type=EventType.CONTRACTS_GENERATED,
        task_template="Start development environment with PostgreSQL for {project}",
        context_extractor=lambda e: {
            "project": e.data.get("project", "app"),
            "contracts_path": e.data.get("contracts_path", ""),
        },
    ),

    # Build Failed -> Collect Docker/build logs for diagnosis
    EventTaskMapping(
        event_type=EventType.BUILD_FAILED,
        task_template="Collect build logs and Docker container status for diagnosis",
        context_extractor=lambda e: {
            "error": e.data.get("error", ""),
            "output_dir": e.data.get("output_dir", "."),
            "build_command": e.data.get("command", "npm run build"),
        },
    ),

    # Sandbox Test Failed -> Collect container logs
    EventTaskMapping(
        event_type=EventType.SANDBOX_TEST_FAILED,
        task_template="Collect Docker container logs for failed sandbox test",
        context_extractor=lambda e: {
            "container_name": e.data.get("container_name", ""),
            "error": e.data.get("error", ""),
        },
    ),

    # Deploy Succeeded -> Run health check
    EventTaskMapping(
        event_type=EventType.DEPLOY_SUCCEEDED,
        task_template="Check Docker container health status and verify deployment",
        context_extractor=lambda e: {
            "container_name": e.data.get("container_name", ""),
            "ports": e.data.get("ports", {}),
        },
    ),

    # E2E Test Failed -> Collect logs and screenshots
    EventTaskMapping(
        event_type=EventType.E2E_TEST_FAILED,
        task_template="Collect Docker logs and browser console output for E2E failure analysis",
        context_extractor=lambda e: {
            "test_name": e.data.get("test_name", ""),
            "error": e.data.get("error", ""),
            "screenshot_path": e.data.get("screenshot_path", ""),
        },
    ),

    # Validation Error -> Check git status and recent changes
    EventTaskMapping(
        event_type=EventType.VALIDATION_ERROR,
        task_template="Check git status and recent file changes for validation error",
        context_extractor=lambda e: {
            "error": e.data.get("error", ""),
            "file_path": e.data.get("file_path", ""),
        },
    ),

    # Code Generated -> Git commit (disabled by default - user preference)
    EventTaskMapping(
        event_type=EventType.CODE_GENERATED,
        task_template="Git commit generated code with message: {message}",
        context_extractor=lambda e: {
            "message": e.data.get("message", "Auto-generated code"),
            "files": e.data.get("files", []),
        },
        enabled=False,  # Disabled by default - enable for auto-commit workflow
    ),

    # ==========================================================================
    # Phase 35: SoM Bridge Integration — Forward task lifecycle events to MCP
    # ==========================================================================

    # Epic task completed → run verification tools
    EventTaskMapping(
        event_type=EventType.EPIC_TASK_COMPLETED,
        task_template="Verify generated files from task {task_id}: check for empty files, broken imports, and TypeScript errors",
        context_extractor=lambda e: {
            "task_id": e.data.get("task_id", ""),
            "task_type": e.data.get("task_type", ""),
            "files_created": e.data.get("files_created", []),
        },
    ),

    # Epic task failed → collect debug context
    EventTaskMapping(
        event_type=EventType.EPIC_TASK_FAILED,
        task_template="Collect error context for failed task {task_id}: check Docker logs, build output, and recent file changes",
        context_extractor=lambda e: {
            "task_id": e.data.get("task_id", ""),
            "task_type": e.data.get("task_type", ""),
            "error": e.data.get("error", ""),
        },
    ),

    # API routes generated → start dev server for testing
    EventTaskMapping(
        event_type=EventType.API_ROUTES_GENERATED,
        task_template="Start development server and verify API endpoints are reachable",
        context_extractor=lambda e: {
            "task_type": e.data.get("task_type", ""),
            "epic_id": e.data.get("epic_id", ""),
        },
    ),

    # Auth setup complete → verify auth middleware is wired
    EventTaskMapping(
        event_type=EventType.AUTH_SETUP_COMPLETE,
        task_template="Verify JWT auth guards are registered and login endpoint returns tokens",
        context_extractor=lambda e: {
            "epic_id": e.data.get("epic_id", ""),
        },
    ),

    # Type error → run prisma generate + tsc for targeted fix info
    EventTaskMapping(
        event_type=EventType.TYPE_ERROR,
        task_template="Run npx prisma generate && npx tsc --noEmit to get full type error list for targeted fixing",
        context_extractor=lambda e: {
            "errors": e.data.get("errors", []),
            "file_path": e.data.get("file_path", ""),
        },
    ),

    # Test passed → run coverage report
    EventTaskMapping(
        event_type=EventType.TEST_PASSED,
        task_template="Generate test coverage report and check for uncovered critical paths",
        context_extractor=lambda e: {
            "test_count": e.data.get("test_count", 0),
        },
        enabled=False,  # Enable for coverage-aware workflows
    ),
]


class MCPEventBridge:
    """
    Bidirectional bridge between MCP Orchestrator and EventBus.

    - Subscribes to EventBus events and triggers MCP tasks
    - Publishes MCP results back to EventBus
    - Maintains task-to-event correlation

    Usage:
        bridge = MCPEventBridge()
        await bridge.start()  # Start listening

        # Events will automatically trigger MCP tasks
        # MCP results will publish events back to EventBus
    """

    def __init__(
        self,
        event_bus: EventBus = None,
        orchestrator: MCPOrchestrator = None,
        mappings: List[EventTaskMapping] = None,
        auto_publish: bool = True,
    ):
        """
        Initialize the event bridge.

        Args:
            event_bus: EventBus instance (uses global if None)
            orchestrator: MCPOrchestrator instance (uses global if None)
            mappings: Event-to-task mappings (uses defaults if None)
            auto_publish: Automatically publish results to EventBus
        """
        self.event_bus = event_bus or get_event_bus()
        self.orchestrator = orchestrator or get_mcp_orchestrator()
        self.mappings = mappings or DEFAULT_MAPPINGS
        self.auto_publish = auto_publish

        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._active_task_ids: Dict[str, str] = {}  # event_id -> task_id

        logger.info(
            "mcp_event_bridge_initialized",
            mappings=len(self.mappings),
            auto_publish=auto_publish,
        )

    async def start(self) -> None:
        """Start listening for events."""
        if self._running:
            logger.warning("mcp_event_bridge_already_running")
            return

        self._running = True

        # Subscribe to mapped events
        for mapping in self.mappings:
            if mapping.enabled:
                self.event_bus.subscribe(
                    mapping.event_type,
                    self._create_handler(mapping),
                )
                logger.debug(
                    "mcp_event_bridge_subscribed",
                    event_type=mapping.event_type.value,
                )

        logger.info(
            "mcp_event_bridge_started",
            subscriptions=len([m for m in self.mappings if m.enabled]),
        )

    async def stop(self) -> None:
        """Stop the event bridge."""
        self._running = False

        # Cancel pending tasks
        for task_id, task in self._tasks.items():
            if not task.done():
                task.cancel()

        self._tasks.clear()
        self._active_task_ids.clear()

        logger.info("mcp_event_bridge_stopped")

    def _create_handler(self, mapping: EventTaskMapping) -> Callable:
        """Create an event handler for a mapping."""

        async def handler(event: Event) -> None:
            if not self._running:
                return

            # Extract context from event
            context = {}
            if mapping.context_extractor:
                try:
                    context = mapping.context_extractor(event)
                except Exception as e:
                    logger.warning(
                        "mcp_event_bridge_context_error",
                        event_type=event.type.value,
                        error=str(e),
                    )

            # Format task template
            task = mapping.task_template.format(**context) if context else mapping.task_template

            # Execute as background task
            task_id = str(uuid.uuid4())[:8]
            event_key = f"{event.type.value}_{task_id}"  # Unique key for tracking
            self._active_task_ids[event_key] = task_id

            asyncio.create_task(
                self._execute_and_publish(task_id, task, context, event, event_key)
            )

        return handler

    async def _execute_and_publish(
        self,
        task_id: str,
        task: str,
        context: Dict[str, Any],
        source_event: Event,
        event_key: str = None,
    ) -> None:
        """Execute an MCP task and publish results."""
        try:
            # Publish task started event
            if self.auto_publish:
                await self._publish_task_started(task_id, task, context, source_event)

            # Execute via orchestrator
            result = await self.orchestrator.execute_task(task, context)

            # Publish results
            if self.auto_publish:
                await self._publish_task_result(task_id, result, source_event)

        except Exception as e:
            logger.error(
                "mcp_event_bridge_execution_error",
                task_id=task_id,
                task=task[:50],
                error=str(e),
            )

            if self.auto_publish:
                await self._publish_task_failed(task_id, task, str(e), source_event)

        finally:
            # Cleanup tracking
            if event_key and event_key in self._active_task_ids:
                del self._active_task_ids[event_key]

    async def _publish_task_started(
        self,
        task_id: str,
        task: str,
        context: Dict[str, Any],
        source_event: Event,
    ) -> None:
        """Publish MCP_TASK_STARTED event."""
        payload = MCPTaskStartedPayload(
            task_id=task_id,
            task=task,
            context=context,
            triggered_by=source_event.type.value if source_event else "direct",
            working_dir=context.get("working_dir") or context.get("output_dir"),
        )

        await self.event_bus.publish(
            Event(
                type=EventType.MCP_TASK_STARTED,
                data=payload.to_dict(),
                source="MCPEventBridge",
            )
        )

    async def _publish_task_result(
        self,
        task_id: str,
        result: TaskResult,
        source_event: Event,
    ) -> None:
        """Publish task completion event (success or failure)."""
        if result.success:
            # Publish MCP_TASK_COMPLETE
            payload = MCPTaskCompletePayload(
                task_id=task_id,
                task=result.task,
                success=True,
                steps_executed=result.steps_executed,
                total_duration=result.total_duration,
                output=result.output,
                tools_called=[s.tool for s in result.plan.steps] if result.plan else [],
            )

            await self.event_bus.publish(
                Event(
                    type=EventType.MCP_TASK_COMPLETE,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

            # Publish tool-specific events
            await self._publish_tool_specific_events(task_id, result)

        else:
            # Publish MCP_TASK_FAILED
            errors = result.errors or []
            error_msg = errors[0].get("error", "Unknown error") if errors else "Unknown error"
            failed_tool = errors[0].get("step") if errors else None

            payload = MCPTaskFailedPayload(
                task_id=task_id,
                task=result.task,
                steps_executed=result.steps_executed,
                total_duration=result.total_duration,
                error=error_msg,
                failed_tool=failed_tool,
                partial_output=result.output,
            )

            await self.event_bus.publish(
                Event(
                    type=EventType.MCP_TASK_FAILED,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

    async def _publish_tool_specific_events(
        self,
        task_id: str,
        result: TaskResult,
    ) -> None:
        """Publish tool-specific events based on task output."""
        if not result.plan:
            return

        for step in result.plan.steps:
            tool_name = step.tool.lower()

            # Docker events
            if "docker" in tool_name:
                await self._publish_docker_event(task_id, tool_name, step.args)

            # Git events
            elif "git" in tool_name:
                await self._publish_git_event(task_id, tool_name, step.args)

            # NPM events
            elif "npm" in tool_name:
                await self._publish_npm_event(task_id, tool_name, step.args)

            # File events
            elif "filesystem" in tool_name or "file" in tool_name:
                await self._publish_file_event(task_id, tool_name, step.args)

    async def _publish_docker_event(
        self,
        task_id: str,
        tool_name: str,
        args: Dict[str, Any],
    ) -> None:
        """Publish Docker-specific events."""
        event_type = None
        operation = ""

        if "run_container" in tool_name or "start" in tool_name:
            event_type = EventType.MCP_DOCKER_CONTAINER_STARTED
            operation = "container_start"
        elif "stop" in tool_name:
            event_type = EventType.MCP_DOCKER_CONTAINER_STOPPED
            operation = "container_stop"
        elif "compose_up" in tool_name:
            event_type = EventType.MCP_DOCKER_COMPOSE_UP
            operation = "compose_up"
        elif "compose_down" in tool_name:
            event_type = EventType.MCP_DOCKER_COMPOSE_DOWN
            operation = "compose_down"
        elif "pull" in tool_name:
            event_type = EventType.MCP_DOCKER_IMAGE_PULLED
            operation = "image_pull"

        if event_type:
            payload = MCPDockerEventPayload(
                task_id=task_id,
                operation=operation,
                container_name=args.get("name"),
                image=args.get("image"),
                ports=self._parse_ports(args.get("ports", "")),
            )

            await self.event_bus.publish(
                Event(
                    type=event_type,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

    async def _publish_git_event(
        self,
        task_id: str,
        tool_name: str,
        args: Dict[str, Any],
    ) -> None:
        """Publish Git-specific events."""
        event_type = None
        operation = ""

        if "commit" in tool_name:
            event_type = EventType.MCP_GIT_COMMIT_CREATED
            operation = "commit"
        elif "branch" in tool_name:
            event_type = EventType.MCP_GIT_BRANCH_CREATED
            operation = "branch"
        elif "push" in tool_name:
            event_type = EventType.MCP_GIT_PUSH_COMPLETE
            operation = "push"

        if event_type:
            payload = MCPGitEventPayload(
                task_id=task_id,
                operation=operation,
                commit_message=args.get("message"),
                branch=args.get("branch"),
            )

            await self.event_bus.publish(
                Event(
                    type=event_type,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

    async def _publish_npm_event(
        self,
        task_id: str,
        tool_name: str,
        args: Dict[str, Any],
    ) -> None:
        """Publish NPM-specific events."""
        event_type = None
        operation = ""

        if "install" in tool_name:
            event_type = EventType.MCP_NPM_INSTALL_COMPLETE
            operation = "install"
        elif "build" in args.get("script", "").lower() or "build" in tool_name:
            event_type = EventType.MCP_NPM_BUILD_COMPLETE
            operation = "build"
        elif "test" in args.get("script", "").lower() or "test" in tool_name:
            event_type = EventType.MCP_NPM_TEST_COMPLETE
            operation = "test"

        if event_type:
            payload = MCPNpmEventPayload(
                task_id=task_id,
                operation=operation,
                script=args.get("script"),
            )

            await self.event_bus.publish(
                Event(
                    type=event_type,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

    async def _publish_file_event(
        self,
        task_id: str,
        tool_name: str,
        args: Dict[str, Any],
    ) -> None:
        """Publish Filesystem-specific events."""
        event_type = None
        operation = ""

        if "write" in tool_name or "create" in tool_name:
            event_type = EventType.MCP_FILE_CREATED
            operation = "create"
        elif "edit" in tool_name or "modify" in tool_name:
            event_type = EventType.MCP_FILE_MODIFIED
            operation = "modify"
        elif "mkdir" in tool_name or "directory" in tool_name:
            event_type = EventType.MCP_DIRECTORY_CREATED
            operation = "mkdir"

        if event_type:
            payload = MCPFileEventPayload(
                task_id=task_id,
                operation=operation,
                file_path=args.get("path", ""),
                is_directory="mkdir" in operation or "directory" in tool_name,
            )

            await self.event_bus.publish(
                Event(
                    type=event_type,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

    async def _publish_task_failed(
        self,
        task_id: str,
        task: str,
        error: str,
        source_event: Event,
    ) -> None:
        """Publish MCP_TASK_FAILED event for exceptions."""
        payload = MCPTaskFailedPayload(
            task_id=task_id,
            task=task,
            error=error,
        )

        await self.event_bus.publish(
            Event(
                type=EventType.MCP_TASK_FAILED,
                data=payload.to_dict(),
                source="MCPEventBridge",
            )
        )

    def _parse_ports(self, ports_str: str) -> Dict[str, str]:
        """Parse port mapping string like '5432:5432' into dict."""
        if not ports_str:
            return {}

        result = {}
        for mapping in ports_str.split(","):
            mapping = mapping.strip()
            if ":" in mapping:
                host, container = mapping.split(":", 1)
                result[container] = host
            else:
                result[mapping] = mapping
        return result

    # =========================================================================
    # Manual Task Execution
    # =========================================================================

    async def execute_task(
        self,
        task: str,
        context: Dict[str, Any] = None,
        publish_events: bool = True,
    ) -> TaskResult:
        """
        Manually execute an MCP task with optional event publishing.

        Args:
            task: Natural language task description
            context: Task context
            publish_events: Whether to publish events

        Returns:
            TaskResult from orchestrator
        """
        task_id = str(uuid.uuid4())[:8]
        context = context or {}

        if publish_events:
            payload = MCPTaskStartedPayload(
                task_id=task_id,
                task=task,
                context=context,
                triggered_by="direct",
            )
            await self.event_bus.publish(
                Event(
                    type=EventType.MCP_TASK_STARTED,
                    data=payload.to_dict(),
                    source="MCPEventBridge",
                )
            )

        result = await self.orchestrator.execute_task(task, context)

        if publish_events:
            await self._publish_task_result(task_id, result, None)

        return result

    # =========================================================================
    # Mapping Management
    # =========================================================================

    def add_mapping(self, mapping: EventTaskMapping) -> None:
        """Add a new event-to-task mapping."""
        self.mappings.append(mapping)

        if self._running and mapping.enabled:
            self.event_bus.subscribe(
                mapping.event_type,
                self._create_handler(mapping),
            )

        logger.debug(
            "mcp_event_bridge_mapping_added",
            event_type=mapping.event_type.value,
        )

    def remove_mapping(self, event_type: EventType) -> None:
        """Remove mapping for an event type."""
        self.mappings = [m for m in self.mappings if m.event_type != event_type]
        logger.debug(
            "mcp_event_bridge_mapping_removed",
            event_type=event_type.value,
        )

    def list_mappings(self) -> List[Dict[str, Any]]:
        """List all current mappings."""
        return [
            {
                "event_type": m.event_type.value,
                "task_template": m.task_template,
                "enabled": m.enabled,
            }
            for m in self.mappings
        ]


# =============================================================================
# Module-level singleton
# =============================================================================

_bridge_instance: Optional[MCPEventBridge] = None


def get_event_bridge() -> MCPEventBridge:
    """Get or create the global MCPEventBridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = MCPEventBridge()
    return _bridge_instance


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    async def main():
        print("=" * 60)
        print("MCP Event Bridge Test")
        print("=" * 60)

        bridge = get_event_bridge()

        # Show mappings
        print("\nConfigured Mappings:")
        for mapping in bridge.list_mappings():
            status = "✓" if mapping["enabled"] else "✗"
            print(f"  {status} {mapping['event_type']} -> {mapping['task_template'][:50]}...")

        # Manual task execution
        print("\n" + "-" * 40)
        print("Manual Task Execution")
        print("-" * 40)

        result = await bridge.execute_task(
            task="List Docker containers",
            context={},
            publish_events=False,  # Don't publish to avoid EventBus dependency
        )

        print(f"Task: {result.task}")
        print(f"Success: {result.success}")
        print(f"Steps: {result.steps_executed}")
        print(f"Duration: {result.total_duration:.2f}s")

        print("\n" + "=" * 60)
        print("Test completed")
        print("=" * 60)

    asyncio.run(main())
