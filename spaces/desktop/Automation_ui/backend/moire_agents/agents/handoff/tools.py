"""
Delegate Tools for Handoff Pattern

Tool abstractions that trigger handoffs to other agents.
Based on AutoGen's delegate tool pattern.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import logging

from .messages import UserTask, HandoffRequest

logger = logging.getLogger(__name__)


@dataclass
class DelegateTool:
    """
    A tool that triggers a handoff to another agent.

    When executed, creates a HandoffRequest instead of
    performing an action directly.
    """
    name: str
    description: str
    target_agent: str
    priority: int = 0  # Higher = more urgent handoffs

    def __post_init__(self):
        """Validate tool configuration."""
        if not self.name:
            raise ValueError("DelegateTool requires a name")
        if not self.target_agent:
            raise ValueError("DelegateTool requires a target_agent")

    async def execute(
        self,
        task: UserTask,
        source_agent: str = "",
        **kwargs
    ) -> HandoffRequest:
        """
        Execute the delegate tool (creates handoff request).

        Args:
            task: Current task context
            source_agent: Agent executing this tool
            **kwargs: Additional context to pass

        Returns:
            HandoffRequest for the target agent
        """
        # Add execution context to task
        task.context["delegate_tool"] = self.name
        task.context["delegate_kwargs"] = kwargs

        return HandoffRequest(
            target_agent=self.target_agent,
            reason=f"Delegated via '{self.name}': {self.description}",
            task=task,
            source_agent=source_agent,
            priority=self.priority,
            handoff_count=task.context.get("handoff_count", 0)
        )


@dataclass
class ActionTool:
    """
    A regular tool that performs an action directly.

    Unlike DelegateTool, this executes a handler function
    and returns the result.
    """
    name: str
    description: str
    handler: Callable
    timeout: float = 30.0

    async def execute(self, task: UserTask, **kwargs) -> Any:
        """Execute the tool handler."""
        logger.debug(f"Executing tool '{self.name}' with kwargs: {kwargs}")

        if callable(self.handler):
            # Check if handler is async
            import asyncio
            if asyncio.iscoroutinefunction(self.handler):
                return await self.handler(task, **kwargs)
            else:
                return self.handler(task, **kwargs)
        else:
            raise ValueError(f"Tool '{self.name}' has invalid handler")


def create_delegate_tool(
    name: str,
    target_agent: str,
    description: str,
    priority: int = 0
) -> DelegateTool:
    """
    Factory function to create a delegate tool.

    Args:
        name: Tool name (should be descriptive action like "transfer_to_vision")
        target_agent: Name of agent to hand off to
        description: What this delegation is for
        priority: Handoff priority (higher = more urgent)

    Returns:
        Configured DelegateTool
    """
    return DelegateTool(
        name=name,
        description=description,
        target_agent=target_agent,
        priority=priority
    )


def create_action_tool(
    name: str,
    description: str,
    handler: Callable,
    timeout: float = 30.0
) -> ActionTool:
    """
    Factory function to create an action tool.

    Args:
        name: Tool name
        description: What this tool does
        handler: Function to execute
        timeout: Execution timeout

    Returns:
        Configured ActionTool
    """
    return ActionTool(
        name=name,
        description=description,
        handler=handler,
        timeout=timeout
    )


# ==================== Pre-built Delegate Tools ====================

# Execution agent - for keyboard/mouse actions
transfer_to_execution = create_delegate_tool(
    name="transfer_to_execution",
    target_agent="execution",
    description="Use for executing keyboard actions (hotkey, type, press) or mouse actions (click, scroll)"
)

# Vision agent - for finding UI elements
transfer_to_vision = create_delegate_tool(
    name="transfer_to_vision",
    target_agent="vision",
    description="Use for finding UI elements on screen via OCR or vision analysis"
)

# Recovery agent - for handling failures
transfer_to_recovery = create_delegate_tool(
    name="transfer_to_recovery",
    target_agent="recovery",
    description="Use when an action fails and recovery is needed",
    priority=1  # Higher priority for recovery
)

# Orchestrator - return control to orchestrator
transfer_to_orchestrator = create_delegate_tool(
    name="transfer_to_orchestrator",
    target_agent="orchestrator",
    description="Return control to orchestrator for next step or completion"
)


# ==================== Tool Registry ====================

class ToolRegistry:
    """
    Registry for managing tools across agents.

    Provides centralized tool discovery and management.
    """

    def __init__(self):
        self._delegate_tools: Dict[str, DelegateTool] = {}
        self._action_tools: Dict[str, ActionTool] = {}

        # Register default delegate tools
        self.register_delegate_tool(transfer_to_execution)
        self.register_delegate_tool(transfer_to_vision)
        self.register_delegate_tool(transfer_to_recovery)
        self.register_delegate_tool(transfer_to_orchestrator)

    def register_delegate_tool(self, tool: DelegateTool):
        """Register a delegate tool."""
        self._delegate_tools[tool.name] = tool
        logger.debug(f"Registry: Registered delegate tool '{tool.name}'")

    def register_action_tool(self, tool: ActionTool):
        """Register an action tool."""
        self._action_tools[tool.name] = tool
        logger.debug(f"Registry: Registered action tool '{tool.name}'")

    def get_delegate_tool(self, name: str) -> Optional[DelegateTool]:
        """Get a delegate tool by name."""
        return self._delegate_tools.get(name)

    def get_action_tool(self, name: str) -> Optional[ActionTool]:
        """Get an action tool by name."""
        return self._action_tools.get(name)

    def list_delegate_tools(self) -> List[str]:
        """List all delegate tool names."""
        return list(self._delegate_tools.keys())

    def list_action_tools(self) -> List[str]:
        """List all action tool names."""
        return list(self._action_tools.keys())

    def get_tools_for_agent(self, agent_name: str) -> List[DelegateTool]:
        """Get delegate tools that target a specific agent."""
        return [
            tool for tool in self._delegate_tools.values()
            if tool.target_agent == agent_name
        ]

    def describe_tools(self) -> str:
        """Get a description of all available tools."""
        lines = ["Available Delegate Tools:"]
        for name, tool in self._delegate_tools.items():
            lines.append(f"  - {name}: {tool.description} -> {tool.target_agent}")

        lines.append("\nAvailable Action Tools:")
        for name, tool in self._action_tools.items():
            lines.append(f"  - {name}: {tool.description}")

        return "\n".join(lines)


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
