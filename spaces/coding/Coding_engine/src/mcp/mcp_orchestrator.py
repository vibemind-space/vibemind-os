# -*- coding: utf-8 -*-
"""
MCP Orchestrator - Main coordinator for LLM-planned tool execution.

This module provides the main entry point for executing natural language
tasks using MCP tools with LLM-based planning.
"""
import asyncio
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import structlog

from .tool_registry import MCPToolRegistry, get_tool_registry
from .planner import MCPPlanner, Plan
from .executor import MCPExecutor, ExecutionResult

logger = structlog.get_logger()


@dataclass
class TaskResult:
    """Result from executing a task via the orchestrator."""
    task: str
    success: bool
    steps_executed: int
    total_duration: float
    output: Any
    errors: List[Dict[str, str]]
    plan: Optional[Plan] = None


class MCPOrchestrator:
    """
    Main orchestrator for MCP tool execution.

    Coordinates the Planner, Executor, and Tool Registry to execute
    natural language tasks using available MCP tools.

    Usage:
        mcp = MCPOrchestrator()

        # Execute a task
        result = await mcp.execute_task(
            task="Deploy PostgreSQL and Redis for development",
            context={"project": "my-app", "output_dir": "./output"}
        )

        if result.success:
            print(f"Completed in {result.total_duration:.1f}s")
        else:
            print(f"Errors: {result.errors}")

        # Execute multiple tasks
        results = await mcp.execute_tasks([
            "Start database containers",
            "Run npm install",
            "Run tests"
        ])

        # With EventBus integration
        mcp = MCPOrchestrator(publish_events=True)
        # Events will be published to EventBus during execution
    """

    def __init__(self, working_dir: str = ".",
                 recovery_enabled: bool = True,
                 model: str = None,
                 publish_events: bool = False,
                 event_bus=None):
        """
        Initialize the orchestrator.

        Args:
            working_dir: Working directory for operations
            recovery_enabled: Enable automatic error recovery
            model: LLM model for planning (defaults to Haiku 4.5)
            publish_events: Enable publishing events to EventBus
            event_bus: EventBus instance (uses global if None)
        """
        self.working_dir = working_dir
        self.recovery_enabled = recovery_enabled
        self.publish_events = publish_events
        self._event_bus = event_bus
        self._task_counter = 0

        # Initialize components
        self.registry = get_tool_registry()
        self.planner = MCPPlanner(self.registry, model=model)
        self.executor = MCPExecutor(
            self.registry,
            self.planner if recovery_enabled else None,
            recovery_enabled=recovery_enabled
        )

        logger.info("mcp_orchestrator_initialized",
                   tools=len(self.registry.list_tools()),
                   categories=self.registry.list_categories(),
                   recovery=recovery_enabled,
                   publish_events=publish_events)

    def _get_event_bus(self):
        """Get EventBus instance (lazy load to avoid circular imports)."""
        if self._event_bus is None and self.publish_events:
            try:
                from ..mind.event_bus import get_event_bus
                self._event_bus = get_event_bus()
            except ImportError:
                logger.warning("mcp_orchestrator_eventbus_not_available")
                self.publish_events = False
        return self._event_bus

    async def _publish_event(self, event_type, data: dict, source: str = "MCPOrchestrator"):
        """Publish an event to the EventBus if enabled."""
        if not self.publish_events:
            return

        event_bus = self._get_event_bus()
        if event_bus:
            try:
                from ..mind.event_bus import Event
                await event_bus.publish(Event(
                    type=event_type,  # Event uses 'type' not 'event_type'
                    data=data,
                    source=source,
                ))
            except Exception as e:
                logger.debug("mcp_orchestrator_publish_error", error=str(e))

    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        self._task_counter += 1
        return f"mcp-{self._task_counter:04d}"

    async def execute_task(self, task: str,
                           context: Dict[str, Any] = None) -> TaskResult:
        """
        Execute a natural language task.

        Args:
            task: Task description in natural language
            context: Additional context (output_dir, project info, etc.)

        Returns:
            TaskResult with execution details
        """
        context = context or {}
        context["working_dir"] = self.working_dir
        task_id = self._generate_task_id()

        logger.info("mcp_orchestrator_task_start", task=task[:80], task_id=task_id)

        # Publish task started event
        if self.publish_events:
            try:
                from ..mind.event_bus import EventType
                await self._publish_event(
                    EventType.MCP_TASK_STARTED,
                    {
                        "task_id": task_id,
                        "task": task,
                        "context": context,
                        "triggered_by": "direct",
                    }
                )
            except ImportError:
                pass

        try:
            # Phase 1: Planning
            plan = await self.planner.create_plan(task, context)

            if not plan.steps:
                logger.warning("mcp_orchestrator_no_plan", task=task[:50])
                result = TaskResult(
                    task=task,
                    success=False,
                    steps_executed=0,
                    total_duration=0,
                    output=None,
                    errors=[{"step": "planning", "error": "Could not create plan"}],
                    plan=plan
                )

                # Publish failure event
                if self.publish_events:
                    try:
                        from ..mind.event_bus import EventType
                        await self._publish_event(
                            EventType.MCP_TASK_FAILED,
                            {
                                "task_id": task_id,
                                "task": task,
                                "error": "Could not create plan",
                            }
                        )
                    except ImportError:
                        pass

                return result

            # Publish plan created event
            if self.publish_events:
                try:
                    from ..mind.event_bus import EventType
                    await self._publish_event(
                        EventType.MCP_TASK_PLANNED,
                        {
                            "task_id": task_id,
                            "task": task,
                            "steps_count": len(plan.steps),
                            "expected_outcome": plan.expected_outcome,
                            "tools_to_use": [s.tool for s in plan.steps],
                            "plan_method": "llm" if plan.steps else "fallback",
                        }
                    )
                except ImportError:
                    pass

            # Phase 2: Execution
            result = await self.executor.execute_plan(plan)

            # Phase 3: Result packaging
            task_result = TaskResult(
                task=task,
                success=result.success,
                steps_executed=len(result.steps),
                total_duration=result.total_duration,
                output=result.final_output,
                errors=result.get_errors(),
                plan=plan
            )

            # Publish completion event
            if self.publish_events:
                try:
                    from ..mind.event_bus import EventType
                    if task_result.success:
                        await self._publish_event(
                            EventType.MCP_TASK_COMPLETE,
                            {
                                "task_id": task_id,
                                "task": task,
                                "success": True,
                                "steps_executed": task_result.steps_executed,
                                "total_duration": task_result.total_duration,
                                "tools_called": [s.tool for s in plan.steps],
                            }
                        )
                    else:
                        errors = task_result.errors or []
                        error_msg = errors[0].get("error", "Unknown") if errors else "Unknown"
                        await self._publish_event(
                            EventType.MCP_TASK_FAILED,
                            {
                                "task_id": task_id,
                                "task": task,
                                "error": error_msg,
                                "steps_executed": task_result.steps_executed,
                            }
                        )
                except ImportError:
                    pass

            return task_result

        except Exception as e:
            logger.error("mcp_orchestrator_error", task=task[:50], error=str(e))

            # Publish failure event
            if self.publish_events:
                try:
                    from ..mind.event_bus import EventType
                    await self._publish_event(
                        EventType.MCP_TASK_FAILED,
                        {
                            "task_id": task_id,
                            "task": task,
                            "error": str(e),
                        }
                    )
                except ImportError:
                    pass

            return TaskResult(
                task=task,
                success=False,
                steps_executed=0,
                total_duration=0,
                output=None,
                errors=[{"step": "orchestrator", "error": str(e)}]
            )

    async def execute_tasks(self, tasks: List[str],
                            context: Dict[str, Any] = None,
                            stop_on_error: bool = True) -> List[TaskResult]:
        """
        Execute multiple tasks sequentially.

        Args:
            tasks: List of task descriptions
            context: Shared context for all tasks
            stop_on_error: Stop execution on first error

        Returns:
            List of TaskResults
        """
        results = []
        context = context or {}

        for task in tasks:
            result = await self.execute_task(task, context)
            results.append(result)

            if not result.success and stop_on_error:
                logger.warning("mcp_orchestrator_stopping",
                              task=task[:50],
                              completed=len(results))
                break

            # Update context with previous results for chaining
            if result.success and result.output:
                context["previous_result"] = result.output

        return results

    async def execute_tool(self, tool: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a single tool directly (bypass planning).

        Args:
            tool: Tool name (e.g., "docker.list_containers")
            **kwargs: Tool arguments

        Returns:
            Tool result as dict
        """
        result = await self.executor.execute_single(tool, **kwargs)

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "duration": result.duration
        }

    def list_tools(self) -> List[Dict[str, str]]:
        """List all available tools."""
        return self.registry.list_tools()

    def list_categories(self) -> List[str]:
        """List tool categories."""
        return self.registry.list_categories()

    def get_tools_summary(self) -> str:
        """Get formatted summary of available tools."""
        lines = ["Available MCP Tools:"]
        for cat in self.registry.list_categories():
            tools = self.registry.get_tools_by_category(cat)
            lines.append(f"\n[{cat.upper()}] ({len(tools)} tools)")
            for t in tools:
                info = self.registry.get_tool_info(t)
                lines.append(f"  - {t}: {info.description[:60]}...")
        return "\n".join(lines)


# Module-level singleton
_orchestrator_instance: Optional[MCPOrchestrator] = None


def get_mcp_orchestrator(working_dir: str = ".") -> MCPOrchestrator:
    """Get or create the global MCPOrchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = MCPOrchestrator(working_dir)
    return _orchestrator_instance


# Convenience function for quick task execution
async def execute_mcp_task(task: str, context: Dict[str, Any] = None) -> TaskResult:
    """
    Execute an MCP task using the global orchestrator.

    Args:
        task: Natural language task description
        context: Optional context

    Returns:
        TaskResult
    """
    orchestrator = get_mcp_orchestrator()
    return await orchestrator.execute_task(task, context)


if __name__ == "__main__":
    async def main():
        print("=" * 60)
        print("MCP Orchestrator Test")
        print("=" * 60)

        mcp = MCPOrchestrator()

        # Show available tools
        print("\n" + mcp.get_tools_summary())

        # Test 1: Direct tool execution
        print("\n" + "-" * 40)
        print("Test 1: Direct tool execution")
        print("-" * 40)

        result = await mcp.execute_tool("git.status")
        print(f"git.status: success={result['success']}")
        if result['output']:
            print(f"  Output: {result['output']}")

        # Test 2: Natural language task
        print("\n" + "-" * 40)
        print("Test 2: Natural language task")
        print("-" * 40)

        task_result = await mcp.execute_task(
            task="Check system status (git and docker)",
            context={"project": "test"}
        )

        print(f"Task: {task_result.task}")
        print(f"Success: {task_result.success}")
        print(f"Steps: {task_result.steps_executed}")
        print(f"Duration: {task_result.total_duration:.2f}s")

        if task_result.plan:
            print(f"Plan steps:")
            for i, step in enumerate(task_result.plan.steps):
                print(f"  {i+1}. {step.tool}: {step.reason}")

        if task_result.errors:
            print(f"Errors: {task_result.errors}")

        # Test 3: Docker task (if available)
        print("\n" + "-" * 40)
        print("Test 3: Docker task")
        print("-" * 40)

        docker_result = await mcp.execute_task(
            task="List all Docker containers",
            context={}
        )

        print(f"Success: {docker_result.success}")
        if docker_result.output:
            print(f"Output: {json.dumps(docker_result.output, indent=2)[:500]}")

        print("\n" + "=" * 60)
        print("Tests completed")
        print("=" * 60)

    asyncio.run(main())
