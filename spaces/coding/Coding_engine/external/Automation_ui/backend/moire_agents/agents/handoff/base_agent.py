"""
Base Handoff Agent

Abstract base class for agents that participate in the handoff pattern.
Each agent can:
- Process UserTask messages
- Execute tools (regular and delegate)
- Hand off to other agents via delegate tools
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .messages import UserTask, AgentResponse, HandoffRequest, ProgressUpdate

if TYPE_CHECKING:
    from .runtime import AgentRuntime

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """A tool that an agent can use."""
    name: str
    description: str
    handler: Callable
    is_delegate: bool = False  # True if this tool hands off to another agent
    target_agent: Optional[str] = None  # For delegate tools


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    description: str = ""
    topic_type: str = ""  # Topic this agent subscribes to
    max_retries: int = 2
    timeout: float = 30.0


class BaseHandoffAgent(ABC):
    """
    Base class for handoff-capable agents.

    Implements the core handoff pattern:
    1. Receive UserTask message
    2. Process with tools (regular or delegate)
    3. If delegate tool called -> hand off to target agent
    4. If regular tool called -> execute and continue
    5. Return AgentResponse with results
    """

    def __init__(self, config: AgentConfig, runtime: Optional['AgentRuntime'] = None):
        self.config = config
        self.runtime = runtime
        self.tools: Dict[str, Tool] = {}
        self._running = False

        # Statistics
        self.tasks_processed = 0
        self.handoffs_made = 0
        self.errors_encountered = 0

        # Register default tools
        self._register_default_tools()

    @property
    def name(self) -> str:
        return self.config.name

    def set_runtime(self, runtime: 'AgentRuntime'):
        """Set the agent runtime (for message passing)."""
        self.runtime = runtime

    # ==================== Tool Management ====================

    def register_tool(self, tool: Tool):
        """Register a tool for this agent."""
        self.tools[tool.name] = tool
        logger.debug(f"Agent {self.name}: Registered tool '{tool.name}'")

    def register_delegate_tool(
        self,
        name: str,
        target_agent: str,
        description: str
    ):
        """Register a delegate tool that hands off to another agent."""
        async def delegate_handler(task: UserTask, **kwargs) -> HandoffRequest:
            return HandoffRequest(
                target_agent=target_agent,
                reason=f"Delegated via {name}",
                task=task,
                source_agent=self.name
            )

        tool = Tool(
            name=name,
            description=description,
            handler=delegate_handler,
            is_delegate=True,
            target_agent=target_agent
        )
        self.register_tool(tool)

    def _register_default_tools(self):
        """Register default tools. Override in subclasses."""
        pass

    # ==================== Message Handling ====================

    async def handle_task(self, task: UserTask) -> AgentResponse:
        """
        Main entry point for processing a task.

        This implements the handoff loop:
        1. Analyze task and decide on action
        2. Execute tool (regular or delegate)
        3. If delegate -> return with handoff info
        4. If regular -> continue processing
        """
        start_time = time.time()
        self.tasks_processed += 1

        logger.info(f"Agent {self.name}: Processing task - {task.goal[:50]}...")

        try:
            # Process the task
            result = await self._process_task(task)

            # Check if we need to hand off
            if isinstance(result, HandoffRequest):
                self.handoffs_made += 1
                logger.info(f"Agent {self.name}: Handing off to {result.target_agent}")

                return AgentResponse(
                    success=True,
                    next_agent=result.target_agent,
                    result=result,
                    source_agent=self.name,
                    session_id=task.session_id,
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            # Return regular response
            return AgentResponse(
                success=True,
                result=result,
                source_agent=self.name,
                session_id=task.session_id,
                execution_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            self.errors_encountered += 1
            logger.error(f"Agent {self.name}: Error processing task - {e}")

            return AgentResponse(
                success=False,
                error=str(e),
                source_agent=self.name,
                session_id=task.session_id,
                execution_time_ms=(time.time() - start_time) * 1000
            )

    @abstractmethod
    async def _process_task(self, task: UserTask) -> Any:
        """
        Process the task. Override in subclasses.

        Returns:
            - HandoffRequest if handing off to another agent
            - Any other value as the result
        """
        pass

    # ==================== Handoff Helpers ====================

    async def hand_off_to(self, target_agent: str, task: UserTask, reason: str = "") -> HandoffRequest:
        """Create a handoff request to another agent."""
        task.add_to_history(self.name, "handoff", {
            "target": target_agent,
            "reason": reason
        })

        return HandoffRequest(
            target_agent=target_agent,
            reason=reason,
            task=task,
            source_agent=self.name,
            handoff_count=task.context.get("handoff_count", 0) + 1
        )

    async def execute_tool(self, tool_name: str, task: UserTask, **kwargs) -> Any:
        """Execute a registered tool."""
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")

        logger.debug(f"Agent {self.name}: Executing tool '{tool_name}'")

        result = await tool.handler(task, **kwargs)

        # Log to history
        task.add_to_history(self.name, f"tool:{tool_name}", {
            "kwargs": kwargs,
            "is_delegate": tool.is_delegate
        })

        return result

    # ==================== Progress Reporting ====================

    async def report_progress(
        self,
        task: UserTask,
        percentage: float,
        current_action: str,
        blockers: List[str] = None
    ):
        """Report progress to the runtime."""
        if self.runtime:
            update = ProgressUpdate(
                agent_name=self.name,
                session_id=task.session_id,
                progress_percentage=percentage,
                current_action=current_action,
                blockers=blockers or []
            )
            await self.runtime.publish_progress(update)

    # ==================== Lifecycle ====================

    async def start(self):
        """Start the agent."""
        self._running = True
        logger.info(f"Agent {self.name}: Started")

    async def stop(self):
        """Stop the agent."""
        self._running = False
        logger.info(f"Agent {self.name}: Stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "name": self.name,
            "tasks_processed": self.tasks_processed,
            "handoffs_made": self.handoffs_made,
            "errors_encountered": self.errors_encountered,
            "tools_count": len(self.tools)
        }
