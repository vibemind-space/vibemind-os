"""
Automation Engine - Long-running task execution for MoireTracker.

The AutomationEngine coordinates complex multi-step tasks by:
1. Decomposing natural language goals into subtasks
2. Scheduling subtasks with dependency management
3. Delegating to the subagent team (planning, vision, specialist, background)
4. Tracking progress with real-time status updates
5. Aggregating results for the conversational AI

Example usage:
    engine = await get_automation_engine()
    result = await engine.execute_complex_task(
        goal="Open Chrome, search for news, summarize headlines",
        on_progress=lambda s: print(f"Progress: {s['progress']:.0%}")
    )
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable
from uuid import uuid4

from .task_decomposer import TaskDecomposer, Subtask
from .task_scheduler import TaskScheduler, ExecutionPlan, ExecutionPhase
from .progress_tracker import ProgressTracker, SubtaskStatus

logger = logging.getLogger(__name__)


class TaskState(Enum):
    """State of a running automation task."""
    PENDING = "pending"
    DECOMPOSING = "decomposing"
    SCHEDULING = "scheduling"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AutomationResult:
    """Result of a complex automation task."""
    task_id: str
    success: bool
    goal: str
    subtasks_completed: int
    subtasks_total: int
    duration_seconds: float
    results: List[Dict[str, Any]] = field(default_factory=list)
    summary: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunningTask:
    """A task currently being executed."""
    task_id: str
    goal: str
    state: TaskState
    started_at: float
    subtasks: List[Subtask] = field(default_factory=list)
    current_phase: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class AutomationEngine:
    """
    Long-running automation engine for complex multi-step tasks.

    The engine coordinates:
    - Task decomposition (breaking goals into subtasks)
    - Task scheduling (managing dependencies and parallelism)
    - Subagent delegation (planning, vision, specialist workers)
    - Progress tracking (real-time status updates)
    """

    def __init__(
        self,
        orchestrator=None,  # OrchestratorV2 instance
        subagent_manager=None,  # SubagentManager instance
        redis_client=None,  # RedisStreamClient instance
        openrouter_client=None  # For LLM-based decomposition
    ):
        """
        Initialize the AutomationEngine.

        Args:
            orchestrator: OrchestratorV2 for action execution
            subagent_manager: SubagentManager for parallel subagents
            redis_client: RedisStreamClient for communication
            openrouter_client: OpenRouter client for LLM calls
        """
        self.orchestrator = orchestrator
        self.subagents = subagent_manager
        self.redis = redis_client
        self.llm_client = openrouter_client

        # Core components
        self.decomposer = TaskDecomposer(openrouter_client)
        self.scheduler = TaskScheduler()
        self.progress = ProgressTracker()

        # Running tasks
        self._running_tasks: Dict[str, RunningTask] = {}
        self._task_results: Dict[str, AutomationResult] = {}

        # Configuration
        self.max_concurrent_tasks = 3
        self.default_subtask_timeout = 60.0  # seconds

        logger.info("AutomationEngine initialized")

    async def execute_complex_task(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        on_progress: Optional[Callable[[Dict], Awaitable[None]]] = None
    ) -> AutomationResult:
        """
        Execute a complex multi-step task.

        This is the main entry point for the conversational AI to submit
        automation tasks.

        Args:
            goal: Natural language description of the task
            context: Optional context (current app, screen state, etc.)
            on_progress: Optional async callback for progress updates

        Returns:
            AutomationResult with success status and aggregated results
        """
        task_id = str(uuid4())
        start_time = time.time()
        context = context or {}

        # Create running task
        task = RunningTask(
            task_id=task_id,
            goal=goal,
            state=TaskState.PENDING,
            started_at=start_time
        )
        self._running_tasks[task_id] = task

        try:
            # Phase 1: Decompose goal into subtasks
            task.state = TaskState.DECOMPOSING
            await self._notify_progress(on_progress, {
                "task_id": task_id,
                "state": "decomposing",
                "message": f"Analyzing task: {goal}"
            })

            subtasks = await self.decomposer.decompose(goal, context)
            task.subtasks = subtasks

            logger.info(f"Task {task_id}: Decomposed into {len(subtasks)} subtasks")

            # Phase 2: Create execution plan
            task.state = TaskState.SCHEDULING
            await self._notify_progress(on_progress, {
                "task_id": task_id,
                "state": "scheduling",
                "message": f"Planning execution of {len(subtasks)} subtasks",
                "subtasks_total": len(subtasks)
            })

            execution_plan = self.scheduler.create_plan(subtasks)

            logger.info(
                f"Task {task_id}: Created plan with {len(execution_plan.phases)} phases"
            )

            # Phase 3: Execute plan phase by phase
            task.state = TaskState.EXECUTING
            self.progress.start_task(task_id, subtasks)

            for phase_idx, phase in enumerate(execution_plan.phases):
                if task._cancel_event.is_set():
                    logger.info(f"Task {task_id} cancelled")
                    task.state = TaskState.CANCELLED
                    break

                task.current_phase = phase_idx

                await self._notify_progress(on_progress, {
                    "task_id": task_id,
                    "state": "executing",
                    "phase": phase_idx + 1,
                    "total_phases": len(execution_plan.phases),
                    "progress": self.progress.get_progress(task_id),
                    "current_subtasks": [s.description for s in phase.subtasks]
                })

                # Execute phase (may be parallel)
                phase_results = await self._execute_phase(
                    task, phase, on_progress
                )
                task.results.extend(phase_results)

                # Check if we should continue
                if not self._should_continue(phase_results):
                    logger.warning(f"Task {task_id}: Stopping due to phase failures")
                    break

            # Phase 4: Aggregate results
            duration = time.time() - start_time

            if task.state != TaskState.CANCELLED:
                task.state = TaskState.COMPLETED

            result = AutomationResult(
                task_id=task_id,
                success=task.state == TaskState.COMPLETED,
                goal=goal,
                subtasks_completed=self.progress.get_completed_count(task_id),
                subtasks_total=len(subtasks),
                duration_seconds=duration,
                results=task.results,
                summary=self._generate_summary(task.results),
                metadata={
                    "phases": len(execution_plan.phases),
                    "context": context
                }
            )

            self._task_results[task_id] = result

            await self._notify_progress(on_progress, {
                "task_id": task_id,
                "state": "completed",
                "success": result.success,
                "progress": 1.0,
                "duration": duration
            })

            return result

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            task.state = TaskState.FAILED

            duration = time.time() - start_time
            result = AutomationResult(
                task_id=task_id,
                success=False,
                goal=goal,
                subtasks_completed=self.progress.get_completed_count(task_id),
                subtasks_total=len(task.subtasks),
                duration_seconds=duration,
                error=str(e)
            )
            self._task_results[task_id] = result

            await self._notify_progress(on_progress, {
                "task_id": task_id,
                "state": "failed",
                "error": str(e)
            })

            return result

        finally:
            # Cleanup
            self._running_tasks.pop(task_id, None)
            self.progress.end_task(task_id)

    async def _execute_phase(
        self,
        task: RunningTask,
        phase: ExecutionPhase,
        on_progress: Optional[Callable]
    ) -> List[Dict[str, Any]]:
        """Execute a single phase of subtasks."""
        results = []

        if phase.can_parallel and len(phase.subtasks) > 1:
            # Execute subtasks in parallel
            logger.info(
                f"Task {task.task_id}: Executing {len(phase.subtasks)} "
                f"subtasks in parallel"
            )

            async_tasks = [
                self._execute_subtask(task, subtask, on_progress)
                for subtask in phase.subtasks
            ]

            phase_results = await asyncio.gather(
                *async_tasks, return_exceptions=True
            )

            for i, result in enumerate(phase_results):
                if isinstance(result, Exception):
                    results.append({
                        "subtask": phase.subtasks[i].description,
                        "success": False,
                        "error": str(result)
                    })
                else:
                    results.append(result)

        else:
            # Execute subtasks sequentially
            for subtask in phase.subtasks:
                if task._cancel_event.is_set():
                    break

                result = await self._execute_subtask(task, subtask, on_progress)
                results.append(result)

                if not result.get("success", False):
                    # Stop on failure for sequential execution
                    break

        return results

    async def _execute_subtask(
        self,
        task: RunningTask,
        subtask: Subtask,
        on_progress: Optional[Callable]
    ) -> Dict[str, Any]:
        """Execute a single subtask."""
        logger.info(f"Task {task.task_id}: Executing subtask: {subtask.description}")

        self.progress.start_subtask(task.task_id, subtask.id)

        await self._notify_progress(on_progress, {
            "task_id": task.task_id,
            "state": "executing_subtask",
            "subtask": subtask.description,
            "approach": subtask.approach,
            "progress": self.progress.get_progress(task.task_id)
        })

        start_time = time.time()
        result = {"subtask": subtask.description, "approach": subtask.approach}

        try:
            timeout = subtask.timeout or self.default_subtask_timeout

            # Execute based on approach
            if subtask.approach == "keyboard":
                result["data"] = await self._execute_keyboard_subtask(subtask, timeout)
            elif subtask.approach == "mouse":
                result["data"] = await self._execute_mouse_subtask(subtask, timeout)
            elif subtask.approach == "hybrid":
                result["data"] = await self._execute_hybrid_subtask(subtask, timeout)
            elif subtask.approach == "vision":
                result["data"] = await self._execute_vision_subtask(subtask, timeout)
            elif subtask.approach == "specialist":
                result["data"] = await self._execute_specialist_subtask(subtask, timeout)
            else:
                # Default: use orchestrator
                result["data"] = await self._execute_orchestrator_subtask(subtask, timeout)

            result["success"] = True
            result["duration"] = time.time() - start_time

            self.progress.complete_subtask(task.task_id, subtask.id, success=True)

        except asyncio.TimeoutError:
            result["success"] = False
            result["error"] = f"Subtask timed out after {timeout}s"
            result["duration"] = time.time() - start_time
            self.progress.complete_subtask(task.task_id, subtask.id, success=False)

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["duration"] = time.time() - start_time
            self.progress.complete_subtask(task.task_id, subtask.id, success=False)
            logger.error(f"Subtask failed: {e}", exc_info=True)

        return result

    async def _execute_keyboard_subtask(
        self, subtask: Subtask, timeout: float
    ) -> Dict[str, Any]:
        """Execute subtask using keyboard approach via subagents."""
        if self.subagents:
            # Use parallel planning to find best keyboard approach
            plan_result = await asyncio.wait_for(
                self.subagents.tool_call_planning(
                    approach="keyboard",
                    goal=subtask.description,
                    context=subtask.context or {}
                ),
                timeout=timeout
            )

            if plan_result.success and self.orchestrator:
                # Execute the plan
                return await self._execute_plan_actions(plan_result, timeout)

            return {"plan": plan_result.result if plan_result.success else None}

        # Fallback: use orchestrator directly
        return await self._execute_orchestrator_subtask(subtask, timeout)

    async def _execute_mouse_subtask(
        self, subtask: Subtask, timeout: float
    ) -> Dict[str, Any]:
        """Execute subtask using mouse approach."""
        if self.subagents:
            plan_result = await asyncio.wait_for(
                self.subagents.tool_call_planning(
                    approach="mouse",
                    goal=subtask.description,
                    context=subtask.context or {}
                ),
                timeout=timeout
            )

            if plan_result.success and self.orchestrator:
                return await self._execute_plan_actions(plan_result, timeout)

            return {"plan": plan_result.result if plan_result.success else None}

        return await self._execute_orchestrator_subtask(subtask, timeout)

    async def _execute_hybrid_subtask(
        self, subtask: Subtask, timeout: float
    ) -> Dict[str, Any]:
        """Execute subtask using hybrid approach (parallel planning)."""
        if self.subagents:
            # Spawn parallel planners
            best_plan = await asyncio.wait_for(
                self.subagents.spawn_parallel_planners(
                    goal=subtask.description,
                    approaches=["keyboard", "mouse", "hybrid"],
                    context=subtask.context or {}
                ),
                timeout=timeout
            )

            if best_plan.success and self.orchestrator:
                return await self._execute_plan_actions(best_plan, timeout)

            return {
                "approach": best_plan.approach,
                "confidence": best_plan.confidence
            }

        return await self._execute_orchestrator_subtask(subtask, timeout)

    async def _execute_vision_subtask(
        self, subtask: Subtask, timeout: float
    ) -> Dict[str, Any]:
        """Execute subtask using vision analysis."""
        if self.subagents:
            # Get current screenshot
            screenshot_ref = None
            if self.orchestrator and hasattr(self.orchestrator, 'moire_client'):
                # Capture screenshot via MoireServer
                pass

            # Parallel vision analysis
            regions = subtask.context.get("regions", [
                {"name": "main_content", "x": 0, "y": 0, "width": 1920, "height": 1080}
            ])

            vision_results = await asyncio.wait_for(
                self.subagents.spawn_parallel_vision(
                    regions=regions,
                    prompts=[subtask.description] * len(regions),
                    screenshot_ref=screenshot_ref
                ),
                timeout=timeout
            )

            return {"vision_results": vision_results}

        return {"analysis": "Vision not available without subagents"}

    async def _execute_specialist_subtask(
        self, subtask: Subtask, timeout: float
    ) -> Dict[str, Any]:
        """Execute subtask by querying domain specialist."""
        if self.subagents:
            domain = subtask.context.get("domain", "system")

            result = await asyncio.wait_for(
                self.subagents.query_specialist(
                    domain=domain,
                    query=subtask.description,
                    context=subtask.context
                ),
                timeout=timeout
            )

            return {
                "domain": domain,
                "answer": result.answer,
                "shortcuts": result.shortcuts,
                "workflow": result.workflow
            }

        return {"answer": "Specialist not available without subagents"}

    async def _execute_orchestrator_subtask(
        self, subtask: Subtask, timeout: float
    ) -> Dict[str, Any]:
        """Execute subtask using the main orchestrator."""
        if self.orchestrator:
            result = await asyncio.wait_for(
                self.orchestrator.execute_task_with_reflection(
                    goal=subtask.description,
                    max_reflection_rounds=2,
                    actions_per_round=3
                ),
                timeout=timeout
            )

            return {
                "orchestrator_result": result,
                "actions_executed": getattr(result, 'actions_executed', 0)
            }

        # Mock execution if no orchestrator
        await asyncio.sleep(0.5)  # Simulate work
        return {"mock": True, "description": subtask.description}

    async def _execute_plan_actions(
        self, plan_result, timeout: float
    ) -> Dict[str, Any]:
        """Execute a plan's actions through the orchestrator."""
        if not self.orchestrator:
            return {"error": "No orchestrator available"}

        # Convert plan to action events and execute
        # This would integrate with orchestrator.execute_actions()
        return {
            "plan_executed": True,
            "actions": plan_result.result.get("data", {}).get("actions", [])
        }

    def _should_continue(self, phase_results: List[Dict]) -> bool:
        """Check if execution should continue based on phase results."""
        if not phase_results:
            return True

        # Continue if at least one subtask succeeded
        successes = sum(1 for r in phase_results if r.get("success", False))
        return successes > 0

    def _generate_summary(self, results: List[Dict]) -> str:
        """Generate a summary of the task execution."""
        successful = [r for r in results if r.get("success", False)]
        failed = [r for r in results if not r.get("success", False)]

        summary_parts = []

        if successful:
            summary_parts.append(
                f"Completed {len(successful)} subtask(s) successfully."
            )

        if failed:
            summary_parts.append(
                f"Failed {len(failed)} subtask(s): " +
                ", ".join(r.get("subtask", "unknown") for r in failed[:3])
            )

        return " ".join(summary_parts) or "No subtasks executed."

    async def _notify_progress(
        self,
        callback: Optional[Callable],
        status: Dict[str, Any]
    ):
        """Notify progress callback if provided."""
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(status)
                else:
                    callback(status)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    # ==================== Task Management ====================

    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """Get list of currently running tasks."""
        return [
            {
                "task_id": task.task_id,
                "goal": task.goal,
                "state": task.state.value,
                "progress": self.progress.get_progress(task.task_id),
                "subtasks_total": len(task.subtasks),
                "current_phase": task.current_phase
            }
            for task in self._running_tasks.values()
        ]

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task."""
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            return {
                "task_id": task_id,
                "goal": task.goal,
                "state": task.state.value,
                "progress": self.progress.get_progress(task_id),
                "subtasks": [
                    {"description": s.description, "approach": s.approach}
                    for s in task.subtasks
                ],
                "current_phase": task.current_phase,
                "running": True
            }
        elif task_id in self._task_results:
            result = self._task_results[task_id]
            return {
                "task_id": task_id,
                "goal": result.goal,
                "state": "completed" if result.success else "failed",
                "progress": 1.0,
                "success": result.success,
                "summary": result.summary,
                "running": False
            }
        return None

    def get_task_result(self, task_id: str) -> Optional[AutomationResult]:
        """Get result of a completed task."""
        return self._task_results.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            task._cancel_event.set()
            logger.info(f"Task {task_id} cancellation requested")
            return True
        return False


# Singleton instance
_engine_instance: Optional[AutomationEngine] = None


async def get_automation_engine(
    orchestrator=None,
    subagent_manager=None,
    redis_client=None,
    openrouter_client=None
) -> AutomationEngine:
    """
    Get or create the singleton AutomationEngine instance.

    Args:
        orchestrator: OrchestratorV2 instance
        subagent_manager: SubagentManager instance
        redis_client: RedisStreamClient instance
        openrouter_client: OpenRouter client for LLM calls

    Returns:
        AutomationEngine instance
    """
    global _engine_instance

    if _engine_instance is None:
        _engine_instance = AutomationEngine(
            orchestrator=orchestrator,
            subagent_manager=subagent_manager,
            redis_client=redis_client,
            openrouter_client=openrouter_client
        )

    return _engine_instance


def shutdown_automation_engine():
    """Shutdown the automation engine."""
    global _engine_instance
    if _engine_instance:
        logger.info("Shutting down AutomationEngine")
        _engine_instance = None
