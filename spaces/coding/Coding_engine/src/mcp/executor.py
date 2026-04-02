# -*- coding: utf-8 -*-
"""
MCP Executor - Executes tool plans with error handling and recovery.

This module takes Plans from the Planner and executes them step by step,
handling errors and optionally triggering recovery planning.
"""
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import structlog

from .planner import Plan, PlanStep

logger = structlog.get_logger()


@dataclass
class StepResult:
    """Result from executing a single plan step."""
    step: PlanStep
    success: bool
    output: Any
    error: Optional[str] = None
    duration: float = 0.0
    retried: bool = False


@dataclass
class ExecutionResult:
    """Complete result from executing a plan."""
    plan: Plan
    steps: List[StepResult]
    success: bool
    total_duration: float
    errors: List[str] = field(default_factory=list)

    @property
    def all_successful(self) -> bool:
        """Check if all steps succeeded."""
        return all(s.success for s in self.steps)

    def get_errors(self) -> List[Dict[str, str]]:
        """Get list of errors with step info."""
        return [
            {"step": s.step.tool, "error": s.error}
            for s in self.steps if s.error
        ]

    @property
    def final_output(self) -> Any:
        """Get output from last successful step."""
        for step in reversed(self.steps):
            if step.success and step.output:
                return step.output
        return None


class MCPExecutor:
    """
    Executes MCP tool plans with error handling.

    Takes a Plan from the Planner and executes each step sequentially,
    handling errors and optionally triggering recovery.

    Usage:
        executor = MCPExecutor(tool_registry, planner)
        result = await executor.execute_plan(plan)

        if not result.success:
            print(f"Failed: {result.get_errors()}")
    """

    def __init__(self, tool_registry, planner=None,
                 recovery_enabled: bool = True,
                 max_retries: int = 2):
        """
        Initialize the executor.

        Args:
            tool_registry: MCPToolRegistry instance
            planner: MCPPlanner for recovery planning (optional)
            recovery_enabled: Enable automatic recovery on failures
            max_retries: Maximum retry attempts per step
        """
        self.tool_registry = tool_registry
        self.planner = planner
        self.recovery_enabled = recovery_enabled
        self.max_retries = max_retries

    async def execute_plan(self, plan: Plan) -> ExecutionResult:
        """
        Execute a complete plan.

        Args:
            plan: Plan to execute

        Returns:
            ExecutionResult with all step results
        """
        start_time = time.time()
        results: List[StepResult] = []
        all_success = True

        logger.info("executor_starting",
                   task=plan.task[:50],
                   steps=len(plan.steps))

        for i, step in enumerate(plan.steps):
            logger.debug("executor_step",
                        step=i+1,
                        total=len(plan.steps),
                        tool=step.tool)

            # Execute with retry logic
            step_result = await self._execute_step_with_retry(step, plan.context)
            results.append(step_result)

            if not step_result.success:
                all_success = False

                # Try recovery if enabled
                if self.recovery_enabled and self.planner:
                    recovery_result = await self._attempt_recovery(
                        step, step_result.error or "Unknown error", plan.context
                    )

                    if recovery_result:
                        results.extend(recovery_result)

                        # Retry original step after recovery
                        retry_result = await self._execute_step(step)
                        retry_result.retried = True
                        results.append(retry_result)

                        if retry_result.success:
                            all_success = True
                            continue

                # Stop on unrecoverable failure
                logger.warning("executor_step_failed",
                              step=step.tool,
                              error=step_result.error)
                break

        total_duration = time.time() - start_time

        logger.info("executor_completed",
                   success=all_success,
                   steps_executed=len(results),
                   duration=round(total_duration, 2))

        return ExecutionResult(
            plan=plan,
            steps=results,
            success=all_success,
            total_duration=total_duration
        )

    async def _execute_step_with_retry(self, step: PlanStep,
                                        context: Dict = None) -> StepResult:
        """Execute a step with retry logic."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            result = await self._execute_step(step)

            if result.success:
                return result

            last_error = result.error
            if attempt < self.max_retries:
                logger.debug("executor_retry",
                            step=step.tool,
                            attempt=attempt + 1,
                            max=self.max_retries)

        return StepResult(
            step=step,
            success=False,
            output=None,
            error=last_error,
            retried=True
        )

    async def _execute_step(self, step: PlanStep) -> StepResult:
        """Execute a single plan step."""
        start_time = time.time()

        try:
            # Get tool from registry
            tool = self.tool_registry.get_tool(step.tool)

            if not tool:
                return StepResult(
                    step=step,
                    success=False,
                    output=None,
                    error=f"Tool '{step.tool}' not found in registry",
                    duration=0
                )

            # Execute tool with args
            result = tool(**step.args)
            duration = time.time() - start_time

            # Parse result if JSON
            parsed_result = result
            if isinstance(result, str):
                try:
                    parsed_result = json.loads(result)
                except json.JSONDecodeError:
                    pass

            # Check for error in result
            if isinstance(parsed_result, dict) and "error" in parsed_result:
                return StepResult(
                    step=step,
                    success=False,
                    output=parsed_result,
                    error=parsed_result["error"],
                    duration=duration
                )

            logger.debug("executor_step_success",
                        tool=step.tool,
                        duration=round(duration, 2))

            return StepResult(
                step=step,
                success=True,
                output=parsed_result,
                duration=duration
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error("executor_step_exception",
                        tool=step.tool,
                        error=str(e))

            return StepResult(
                step=step,
                success=False,
                output=None,
                error=str(e),
                duration=duration
            )

    async def _attempt_recovery(self, failed_step: PlanStep,
                                 error: str,
                                 context: Dict) -> Optional[List[StepResult]]:
        """
        Attempt to recover from a failed step.

        Args:
            failed_step: The step that failed
            error: Error message
            context: Execution context

        Returns:
            List of recovery step results, or None if recovery not possible
        """
        if not self.planner:
            return None

        logger.info("executor_attempting_recovery", tool=failed_step.tool)

        try:
            recovery_plan = await self.planner.plan_recovery(
                failed_step, error, context
            )

            if not recovery_plan.steps:
                logger.debug("executor_no_recovery_plan")
                return None

            # Execute recovery steps
            recovery_results = []
            for step in recovery_plan.steps:
                result = await self._execute_step(step)
                recovery_results.append(result)

                if not result.success:
                    logger.warning("executor_recovery_failed", step=step.tool)
                    break

            return recovery_results

        except Exception as e:
            logger.error("executor_recovery_error", error=str(e))
            return None

    async def execute_single(self, tool: str, **kwargs) -> StepResult:
        """
        Execute a single tool call directly.

        Args:
            tool: Tool name (e.g., "docker.list_containers")
            **kwargs: Tool arguments

        Returns:
            StepResult
        """
        step = PlanStep(tool=tool, args=kwargs, reason="Direct execution")
        return await self._execute_step(step)


if __name__ == "__main__":
    import asyncio
    from tool_registry import MCPToolRegistry
    from planner import MCPPlanner

    async def test_executor():
        print("Testing MCPExecutor...")

        registry = MCPToolRegistry()
        planner = MCPPlanner(registry)
        executor = MCPExecutor(registry, planner)

        # Test single tool execution
        print("\n1. Single tool execution:")
        result = await executor.execute_single("git.status")
        print(f"   Success: {result.success}")
        print(f"   Output: {result.output}")

        # Test plan execution
        print("\n2. Plan execution:")
        plan = await planner.create_plan(
            task="Check system status",
            context={}
        )

        exec_result = await executor.execute_plan(plan)
        print(f"   Success: {exec_result.success}")
        print(f"   Steps: {len(exec_result.steps)}")
        print(f"   Duration: {exec_result.total_duration:.2f}s")

        for sr in exec_result.steps:
            status = "✓" if sr.success else "✗"
            print(f"   {status} {sr.step.tool}: {sr.duration:.2f}s")

    asyncio.run(test_executor())
