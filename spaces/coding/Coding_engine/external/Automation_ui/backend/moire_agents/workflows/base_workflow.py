"""
Base Workflow - Abstract base class for reusable automation workflows.

Provides common functionality for:
- Step definition and execution
- Progress tracking integration
- Error handling and recovery
- Timeout management
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event_queue import ActionEvent, ActionStatus

# Optional imports
try:
    from agents.progress_agent import ProgressAgent, TaskProgress
    HAS_PROGRESS_AGENT = True
except ImportError:
    HAS_PROGRESS_AGENT = False
    ProgressAgent = None
    TaskProgress = None

try:
    from core.localization import L
    HAS_LOCALIZATION = True
except ImportError:
    HAS_LOCALIZATION = False
    L = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StepStatus(Enum):
    """Status of a workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """Definition of a single workflow step."""
    id: str
    action_type: str
    params: Dict[str, Any]
    description: str
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 2
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_action_event(self, task_id: str) -> ActionEvent:
        """Convert to ActionEvent for execution."""
        return ActionEvent(
            id=self.id,
            task_id=task_id,
            action_type=self.action_type,
            params=self.params,
            description=self.description,
            status=ActionStatus.PENDING
        )


@dataclass
class WorkflowResult:
    """Result of workflow execution."""
    success: bool
    workflow_name: str
    steps_completed: int
    steps_total: int
    duration: float
    progress: Optional[TaskProgress] = None
    error: Optional[str] = None
    output: Optional[Any] = None
    step_results: List[Dict[str, Any]] = field(default_factory=list)


class BaseWorkflow(ABC):
    """
    Abstract base class for automation workflows.

    Subclasses define specific workflows by implementing:
    - define_steps(): Return list of WorkflowStep objects
    - Optional: on_step_completed(), on_step_failed()
    """

    def __init__(
        self,
        steering_agent=None,
        progress_agent: Optional[ProgressAgent] = None,
        name: str = "BaseWorkflow"
    ):
        self.steering_agent = steering_agent
        self.progress_agent = progress_agent
        self.name = name

        self.steps: List[WorkflowStep] = []
        self.current_step_index: int = 0
        self._running: bool = False
        self._cancelled: bool = False

        # Callbacks
        self.on_step_start: Optional[Callable[[WorkflowStep], None]] = None
        self.on_step_complete: Optional[Callable[[WorkflowStep], None]] = None
        self.on_step_failed: Optional[Callable[[WorkflowStep, str], None]] = None
        self.on_progress: Optional[Callable[[float], None]] = None

    @abstractmethod
    def define_steps(self, **kwargs) -> List[WorkflowStep]:
        """
        Define the steps for this workflow.

        Override in subclasses to define specific workflow steps.

        Args:
            **kwargs: Workflow-specific parameters

        Returns:
            List of WorkflowStep objects
        """
        pass

    async def execute(self, **kwargs) -> WorkflowResult:
        """
        Execute the workflow.

        Args:
            **kwargs: Parameters passed to define_steps()

        Returns:
            WorkflowResult with execution details
        """
        start_time = time.time()
        self._running = True
        self._cancelled = False

        # Define steps
        self.steps = self.define_steps(**kwargs)
        self.current_step_index = 0

        logger.info(f"Starting workflow '{self.name}' with {len(self.steps)} steps")

        # Start progress monitoring if available
        task_id = f"workflow_{self.name}_{int(start_time)}"
        if self.progress_agent and HAS_PROGRESS_AGENT:
            actions = [step.to_action_event(task_id) for step in self.steps]
            await self.progress_agent.start_monitoring(
                task_id=task_id,
                goal=f"Execute workflow: {self.name}",
                actions=actions
            )

        step_results = []
        error = None

        try:
            for i, step in enumerate(self.steps):
                if self._cancelled:
                    logger.info(f"Workflow cancelled at step {i}")
                    break

                self.current_step_index = i

                # Execute step
                step_result = await self._execute_step(step)
                step_results.append(step_result)

                if not step_result.get("success", False):
                    error = step_result.get("error", "Step failed")
                    if step.retry_count >= step.max_retries:
                        logger.error(f"Step {step.id} failed after {step.retry_count} retries")
                        break
                    else:
                        # Retry
                        step.retry_count += 1
                        step.status = StepStatus.PENDING
                        step_result = await self._execute_step(step)
                        step_results[-1] = step_result

                        if not step_result.get("success", False):
                            error = step_result.get("error", "Step failed after retry")
                            break

                # Update progress
                progress_pct = (i + 1) / len(self.steps) * 100
                if self.on_progress:
                    self.on_progress(progress_pct)

                # Check if goal achieved early
                if self.progress_agent and self.progress_agent.goal_achieved:
                    logger.info("Goal achieved early, stopping workflow")
                    break

        except Exception as e:
            error = str(e)
            logger.error(f"Workflow error: {e}")

        finally:
            self._running = False

            # Stop progress monitoring
            progress = None
            if self.progress_agent and HAS_PROGRESS_AGENT:
                progress = await self.progress_agent.stop_monitoring()

        # Calculate results
        completed_steps = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        duration = time.time() - start_time

        success = error is None and completed_steps == len(self.steps)

        result = WorkflowResult(
            success=success,
            workflow_name=self.name,
            steps_completed=completed_steps,
            steps_total=len(self.steps),
            duration=duration,
            progress=progress,
            error=error,
            step_results=step_results
        )

        logger.info(f"Workflow '{self.name}' completed: success={success}, "
                   f"steps={completed_steps}/{len(self.steps)}, duration={duration:.1f}s")

        return result

    async def _execute_step(self, step: WorkflowStep) -> Dict[str, Any]:
        """Execute a single workflow step."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()

        if self.on_step_start:
            self.on_step_start(step)

        logger.info(f"Executing step: {step.description}")

        try:
            # Execute via steering agent if available
            if self.steering_agent:
                result = await self._execute_via_steering(step)
            else:
                result = await self._execute_directly(step)

            step.status = StepStatus.COMPLETED
            step.result = result
            step.finished_at = time.time()

            if self.on_step_complete:
                self.on_step_complete(step)

            # Notify progress agent
            if self.progress_agent:
                await self.progress_agent.action_completed(
                    self.current_step_index,
                    result
                )

            return {"success": True, "result": result}

        except asyncio.TimeoutError:
            step.status = StepStatus.FAILED
            step.error = "Timeout"
            step.finished_at = time.time()

            if self.on_step_failed:
                self.on_step_failed(step, "Timeout")

            return {"success": False, "error": "Timeout"}

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.finished_at = time.time()

            if self.on_step_failed:
                self.on_step_failed(step, str(e))

            return {"success": False, "error": str(e)}

    async def _execute_via_steering(self, step: WorkflowStep) -> Dict[str, Any]:
        """Execute step via SteeringAgent."""
        from core.task_decomposer import Subtask

        # Create subtask compatible with SteeringAgent
        subtask = Subtask.create(
            description=step.description,
            approach="keyboard" if step.action_type in ["hotkey", "press_key", "type"] else "mouse",
            context={
                "pyautogui_action": {"type": step.action_type, **step.params},
                "wait_after": 0.2
            }
        )

        # Execute with timeout - SteeringAgent expects a list of subtasks
        async with asyncio.timeout(step.timeout):
            result = await self.steering_agent.execute_with_steering(
                subtasks=[subtask],
                goal=step.description
            )

        return {
            "success": result.success if hasattr(result, 'success') else True,
            "goal_achieved": result.goal_achieved if hasattr(result, 'goal_achieved') else False,
            "steering_result": result
        }

    async def _execute_directly(self, step: WorkflowStep) -> Dict[str, Any]:
        """Execute step directly using pyautogui."""
        import pyautogui

        action_type = step.action_type
        params = step.params

        async with asyncio.timeout(step.timeout):
            if action_type == "hotkey":
                keys = params.get("keys", [])
                pyautogui.hotkey(*keys)
                return {"action": "hotkey", "keys": keys}

            elif action_type in ("press", "press_key"):
                key = params.get("key", "")
                pyautogui.press(key)
                return {"action": "press", "key": key}

            elif action_type in ("write", "type"):
                text = params.get("text", "")
                interval = params.get("interval", 0.02)
                pyautogui.write(text, interval=interval)
                return {"action": "write", "text": text}

            elif action_type == "click":
                x = params.get("x")
                y = params.get("y")
                if x is not None and y is not None:
                    pyautogui.click(x, y)
                else:
                    pyautogui.click()
                return {"action": "click", "x": x, "y": y}

            elif action_type in ("sleep", "wait"):
                duration = params.get("seconds", params.get("duration", 1.0))
                await asyncio.sleep(duration)
                return {"action": "sleep", "seconds": duration}

            elif action_type == "find_and_click":
                target = params.get("target", "")
                # This would need vision agent integration
                return {"action": "find_and_click", "target": target, "found": False}

            else:
                logger.warning(f"Unknown action type: {action_type}")
                return {"action": action_type, "status": "unknown"}

    def cancel(self) -> None:
        """Cancel the running workflow."""
        self._cancelled = True
        logger.info(f"Workflow '{self.name}' cancellation requested")

    @property
    def is_running(self) -> bool:
        """Check if workflow is currently running."""
        return self._running

    @property
    def progress_percentage(self) -> float:
        """Get current progress percentage."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return completed / len(self.steps) * 100

    def get_status(self) -> Dict[str, Any]:
        """Get current workflow status."""
        return {
            "name": self.name,
            "running": self._running,
            "cancelled": self._cancelled,
            "current_step": self.current_step_index,
            "total_steps": len(self.steps),
            "progress": self.progress_percentage,
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "status": s.status.value,
                    "error": s.error
                }
                for s in self.steps
            ]
        }
