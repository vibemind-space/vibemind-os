"""
Base Subagent - Abstract base class for all subagent implementations.

Provides:
- Common interface for all subagents
- Context management
- LLM client access
- Logging and metrics
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SubagentState(Enum):
    """States a subagent can be in."""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentContext:
    """
    Context passed to subagent for task execution.

    Contains all information the subagent needs to process a task,
    isolated from other concurrent tasks.
    """
    task_id: str
    goal: str
    params: Dict[str, Any]

    # Screenshot data
    screenshot_bytes: Optional[bytes] = None
    screenshot_ref: Optional[str] = None  # Redis key for shared screenshot

    # UI context
    active_app: Optional[str] = None
    screen_elements: List[Dict[str, Any]] = field(default_factory=list)
    cursor_position: Optional[Dict[str, int]] = None

    # Parent context (from orchestrator)
    parent_context: Dict[str, Any] = field(default_factory=dict)

    # Local state (for this subagent's use)
    local_state: Dict[str, Any] = field(default_factory=dict)

    # Timing
    created_at: float = field(default_factory=time.time)
    timeout: float = 30.0


@dataclass
class SubagentOutput:
    """
    Output from a subagent task execution.

    Standardized output format that all subagents return.
    """
    success: bool
    result: Any
    confidence: float = 1.0
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis publishing."""
        return {
            "success": self.success,
            "result": self.result,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms
        }


class BaseSubagent(ABC):
    """
    Abstract base class for all subagents.

    Subagents are specialized workers that handle specific types of tasks:
    - Planning: Generate action sequences
    - Vision: Analyze screen regions
    - Specialist: Provide domain knowledge
    - Background: Monitor for conditions

    Subclasses must implement:
    - execute(): Process a task and return output
    - get_capabilities(): Return what this subagent can do
    """

    def __init__(
        self,
        subagent_id: str,
        openrouter_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the subagent.

        Args:
            subagent_id: Unique identifier for this subagent instance
            openrouter_client: Client for LLM API calls (optional)
            config: Additional configuration
        """
        self.subagent_id = subagent_id
        self.client = openrouter_client
        self.config = config or {}

        self.state = SubagentState.IDLE
        self._context: Optional[SubagentContext] = None

        # Statistics
        self._stats = {
            "tasks_executed": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "total_execution_time_ms": 0
        }

    @abstractmethod
    async def execute(self, context: SubagentContext) -> SubagentOutput:
        """
        Execute a task with the given context.

        This is the main method that subclasses must implement.

        Args:
            context: SubagentContext with all task information

        Returns:
            SubagentOutput with results
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Return the capabilities of this subagent.

        Used by the SubagentManager to route tasks appropriately.

        Returns:
            Dict describing what this subagent can do
        """
        pass

    async def process(self, context: SubagentContext) -> SubagentOutput:
        """
        Process a task with state management and error handling.

        This wraps execute() with:
        - State tracking
        - Timing
        - Error handling
        - Statistics

        Args:
            context: SubagentContext with task information

        Returns:
            SubagentOutput with results
        """
        self.state = SubagentState.PROCESSING
        self._context = context
        start_time = time.time()

        try:
            output = await self.execute(context)

            execution_time = (time.time() - start_time) * 1000
            output.execution_time_ms = execution_time

            # Update stats
            self._stats["tasks_executed"] += 1
            self._stats["total_execution_time_ms"] += execution_time
            if output.success:
                self._stats["tasks_succeeded"] += 1
            else:
                self._stats["tasks_failed"] += 1

            self.state = SubagentState.COMPLETED
            return output

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Subagent {self.subagent_id} failed: {e}", exc_info=True)

            self._stats["tasks_executed"] += 1
            self._stats["tasks_failed"] += 1
            self._stats["total_execution_time_ms"] += execution_time

            self.state = SubagentState.FAILED
            return SubagentOutput(
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=execution_time
            )

        finally:
            self._context = None

    def is_available(self) -> bool:
        """Check if subagent is available for new tasks."""
        return self.state in [
            SubagentState.IDLE,
            SubagentState.COMPLETED,
            SubagentState.FAILED
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        avg_time = 0
        if self._stats["tasks_executed"] > 0:
            avg_time = (
                self._stats["total_execution_time_ms"] /
                self._stats["tasks_executed"]
            )

        return {
            **self._stats,
            "subagent_id": self.subagent_id,
            "state": self.state.value,
            "average_execution_time_ms": avg_time
        }

    async def cancel(self):
        """Cancel current task if running."""
        if self.state == SubagentState.PROCESSING:
            logger.info(f"Cancelling subagent {self.subagent_id}")
            self.state = SubagentState.CANCELLED

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.subagent_id}, state={self.state.value})"
