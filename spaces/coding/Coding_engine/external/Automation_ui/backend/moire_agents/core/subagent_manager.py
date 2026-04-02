"""
Subagent Manager - Orchestrates tool calls to subagent workers.

The SubagentManager is the main interface for the Orchestrator to communicate
with subagents. It provides methods to:
- Call individual subagents (planning, vision, specialist, background)
- Spawn parallel subagents and aggregate results
- Manage background monitoring tasks

Example usage:
    manager = SubagentManager(redis_client)

    # Parallel planning
    best_plan = await manager.spawn_parallel_planners(
        goal="Open Word",
        approaches=["keyboard", "mouse", "hybrid"]
    )

    # Parallel vision
    analysis = await manager.spawn_parallel_vision(
        screenshot=screenshot_bytes,
        regions=[taskbar, main_content, system_tray]
    )

    # Query specialist
    advice = await manager.query_specialist("office", "How to save in Word?")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from uuid import uuid4

from .redis_streams import RedisStreamClient, ToolCallResult
from .result_aggregator import ResultAggregator, AggregationStrategy

logger = logging.getLogger(__name__)


@dataclass
class SubagentConfig:
    """Configuration for the SubagentManager."""
    # Concurrency limits
    max_planning_subagents: int = 3
    max_vision_subagents: int = 5
    max_specialist_subagents: int = 4
    max_background_subagents: int = 3

    # Timeouts
    planning_timeout: float = 30.0
    vision_timeout: float = 15.0
    specialist_timeout: float = 20.0
    background_check_interval: float = 5.0

    # Aggregation
    aggregation_strategy: AggregationStrategy = AggregationStrategy.BEST_CONFIDENCE


@dataclass
class PlanningResult:
    """Result from a planning subagent."""
    approach: str
    actions: List[Dict[str, Any]]
    confidence: float
    reasoning: str
    execution_time_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class VisionResult:
    """Result from a vision subagent."""
    region_name: str
    elements: List[Dict[str, Any]]
    analysis: str
    confidence: float
    execution_time_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class SpecialistResult:
    """Result from a specialist subagent."""
    domain: str
    answer: Any
    shortcuts: Optional[Dict[str, str]] = None
    workflow: Optional[List[str]] = None
    confidence: float = 1.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class BackgroundMonitor:
    """A running background monitor."""
    monitor_id: str
    condition_type: str
    target: str
    callback: Callable[[bool, Dict], Awaitable[None]]
    check_interval: float
    timeout: Optional[float]
    started_at: float = field(default_factory=time.time)
    _task: Optional[asyncio.Task] = None


class SubagentManager:
    """
    Central manager for subagent tool calls.

    Provides a high-level interface for the Orchestrator to:
    - Make tool calls to individual subagents
    - Spawn parallel subagents and aggregate results
    - Manage background monitoring tasks
    """

    def __init__(
        self,
        redis_client: RedisStreamClient,
        config: Optional[SubagentConfig] = None
    ):
        """
        Initialize the SubagentManager.

        Args:
            redis_client: Connected RedisStreamClient
            config: Optional configuration
        """
        self.redis = redis_client
        self.config = config or SubagentConfig()
        self.aggregator = ResultAggregator(self.config.aggregation_strategy)

        # Background monitors
        self._background_monitors: Dict[str, BackgroundMonitor] = {}

        # Stats
        self._stats = {
            "planning_calls": 0,
            "vision_calls": 0,
            "specialist_calls": 0,
            "background_monitors": 0
        }

    # ==================== Planning Subagents ====================

    async def tool_call_planning(
        self,
        approach: str,
        goal: str,
        context: Dict[str, Any],
        screenshot_ref: Optional[str] = None
    ) -> PlanningResult:
        """
        Call a planning subagent with a specific approach.

        Args:
            approach: Planning approach (keyboard, mouse, hybrid)
            goal: The goal to plan for
            context: Additional context (active app, UI elements, etc.)
            screenshot_ref: Reference to screenshot in Redis (optional)

        Returns:
            PlanningResult with actions and confidence
        """
        self._stats["planning_calls"] += 1

        result = await self.redis.call_tool(
            tool_name="planning",
            params={
                "approach": approach,
                "goal": goal,
                "context": context,
                "screenshot_ref": screenshot_ref
            },
            timeout=self.config.planning_timeout
        )

        if result.success:
            data = result.result.get("data", {})
            return PlanningResult(
                approach=approach,
                actions=data.get("actions", []),
                confidence=data.get("confidence", 0.0),
                reasoning=data.get("reasoning", ""),
                execution_time_ms=result.execution_time_ms,
                success=True
            )
        else:
            return PlanningResult(
                approach=approach,
                actions=[],
                confidence=0.0,
                reasoning="",
                execution_time_ms=result.execution_time_ms,
                success=False,
                error=result.error
            )

    async def spawn_parallel_planners(
        self,
        goal: str,
        approaches: List[str] = None,
        context: Dict[str, Any] = None,
        screenshot_ref: Optional[str] = None
    ) -> PlanningResult:
        """
        Spawn multiple planning subagents in parallel and select best result.

        Args:
            goal: The goal to plan for
            approaches: List of approaches to try (default: keyboard, mouse, hybrid)
            context: Additional context
            screenshot_ref: Reference to screenshot in Redis

        Returns:
            Best PlanningResult based on aggregation strategy
        """
        approaches = approaches or ["keyboard", "mouse", "hybrid"]
        context = context or {}

        logger.info(f"Spawning {len(approaches)} parallel planners for: {goal}")

        # Create tasks for parallel execution
        tasks = [
            self.tool_call_planning(approach, goal, context, screenshot_ref)
            for approach in approaches[:self.config.max_planning_subagents]
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        valid_results = []
        for r in results:
            if isinstance(r, PlanningResult) and r.success:
                valid_results.append(r)
            elif isinstance(r, Exception):
                logger.error(f"Planning task failed: {r}")

        if not valid_results:
            logger.warning("All planning approaches failed")
            return PlanningResult(
                approach="none",
                actions=[],
                confidence=0.0,
                reasoning="All planning approaches failed",
                execution_time_ms=0,
                success=False,
                error="All approaches failed"
            )

        # Aggregate results
        best = self.aggregator.aggregate_planning_results(valid_results)
        logger.info(
            f"Selected {best.approach} approach with confidence {best.confidence:.2f}"
        )
        return best

    # ==================== Vision Subagents ====================

    async def tool_call_vision(
        self,
        region: Dict[str, int],
        prompt: str,
        screenshot_ref: Optional[str] = None,
        screenshot_bytes: Optional[bytes] = None
    ) -> VisionResult:
        """
        Call a vision subagent to analyze a screen region.

        Args:
            region: Screen region {name, x, y, width, height}
            prompt: Analysis prompt
            screenshot_ref: Reference to screenshot in Redis
            screenshot_bytes: Raw screenshot bytes (if not using ref)

        Returns:
            VisionResult with detected elements and analysis
        """
        self._stats["vision_calls"] += 1

        result = await self.redis.call_tool(
            tool_name="vision",
            params={
                "region": region,
                "prompt": prompt,
                "screenshot_ref": screenshot_ref,
                # Note: screenshot_bytes would need base64 encoding for Redis
            },
            timeout=self.config.vision_timeout
        )

        region_name = region.get("name", "unknown")

        if result.success:
            data = result.result.get("data", {})
            return VisionResult(
                region_name=region_name,
                elements=data.get("elements", []),
                analysis=data.get("analysis", ""),
                confidence=data.get("confidence", 0.0),
                execution_time_ms=result.execution_time_ms,
                success=True
            )
        else:
            return VisionResult(
                region_name=region_name,
                elements=[],
                analysis="",
                confidence=0.0,
                execution_time_ms=result.execution_time_ms,
                success=False,
                error=result.error
            )

    async def spawn_parallel_vision(
        self,
        regions: List[Dict[str, Any]],
        prompts: Optional[List[str]] = None,
        screenshot_ref: Optional[str] = None
    ) -> Dict[str, VisionResult]:
        """
        Spawn multiple vision subagents to analyze different regions in parallel.

        Args:
            regions: List of regions [{name, x, y, width, height}, ...]
            prompts: List of prompts for each region (optional)
            screenshot_ref: Reference to shared screenshot in Redis

        Returns:
            Dict mapping region name to VisionResult
        """
        prompts = prompts or ["Analyze UI elements in this region"] * len(regions)

        logger.info(f"Spawning {len(regions)} parallel vision analyzers")

        # Create tasks for parallel execution
        tasks = []
        for region, prompt in zip(
            regions[:self.config.max_vision_subagents],
            prompts[:self.config.max_vision_subagents]
        ):
            tasks.append(self.tool_call_vision(region, prompt, screenshot_ref))

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results by region name
        merged = {}
        for i, r in enumerate(results):
            if isinstance(r, VisionResult):
                merged[r.region_name] = r
            elif isinstance(r, Exception):
                region_name = regions[i].get("name", f"region_{i}")
                logger.error(f"Vision task for {region_name} failed: {r}")
                merged[region_name] = VisionResult(
                    region_name=region_name,
                    elements=[],
                    analysis="",
                    confidence=0.0,
                    execution_time_ms=0,
                    success=False,
                    error=str(r)
                )

        return merged

    # ==================== Specialist Subagents ====================

    async def query_specialist(
        self,
        domain: str,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        """
        Query a domain specialist subagent.

        Args:
            domain: Domain (office, browser, gaming, system, creative, development)
            query: The question or request
            context: Additional context (current app, state, etc.)

        Returns:
            SpecialistResult with answer, shortcuts, workflow
        """
        self._stats["specialist_calls"] += 1
        context = context or {}

        result = await self.redis.call_tool(
            tool_name="specialist",
            params={
                "domain": domain,
                "query": query,
                "context": context
            },
            timeout=self.config.specialist_timeout
        )

        if result.success:
            data = result.result.get("data", {})
            return SpecialistResult(
                domain=domain,
                answer=data.get("answer"),
                shortcuts=data.get("shortcuts"),
                workflow=data.get("workflow"),
                confidence=data.get("confidence", 1.0),
                success=True
            )
        else:
            return SpecialistResult(
                domain=domain,
                answer=None,
                success=False,
                error=result.error
            )

    async def get_shortcut(
        self,
        domain: str,
        action: str
    ) -> Optional[str]:
        """
        Get a keyboard shortcut from a specialist.

        Args:
            domain: Domain (office, browser, etc.)
            action: Action name (save, bold, copy, etc.)

        Returns:
            Shortcut string or None
        """
        result = await self.query_specialist(
            domain=domain,
            query=f"What is the keyboard shortcut for '{action}'?"
        )

        if result.success and result.shortcuts:
            return result.shortcuts.get(action)
        return None

    async def get_workflow(
        self,
        domain: str,
        task: str
    ) -> Optional[List[str]]:
        """
        Get a workflow for a task from a specialist.

        Args:
            domain: Domain (office, browser, etc.)
            task: Task description

        Returns:
            List of workflow steps or None
        """
        result = await self.query_specialist(
            domain=domain,
            query=f"What are the steps to '{task}'?"
        )

        if result.success:
            return result.workflow
        return None

    # ==================== Background Subagents ====================

    async def start_background_monitor(
        self,
        condition_type: str,
        target: str,
        callback: Callable[[bool, Dict], Awaitable[None]],
        check_interval: float = None,
        timeout: Optional[float] = None
    ) -> str:
        """
        Start a background monitor that watches for a condition.

        Args:
            condition_type: Type of condition (element_appears, text_contains, state_change)
            target: What to look for
            callback: Async function called when condition is met
            check_interval: How often to check (seconds)
            timeout: Maximum time to monitor (seconds, None for indefinite)

        Returns:
            Monitor ID for later management
        """
        monitor_id = str(uuid4())
        check_interval = check_interval or self.config.background_check_interval

        monitor = BackgroundMonitor(
            monitor_id=monitor_id,
            condition_type=condition_type,
            target=target,
            callback=callback,
            check_interval=check_interval,
            timeout=timeout
        )

        # Start the monitoring task
        monitor._task = asyncio.create_task(
            self._run_background_monitor(monitor)
        )

        self._background_monitors[monitor_id] = monitor
        self._stats["background_monitors"] += 1

        logger.info(
            f"Started background monitor {monitor_id}: "
            f"{condition_type} - '{target}'"
        )

        return monitor_id

    async def _run_background_monitor(self, monitor: BackgroundMonitor):
        """Internal loop for a background monitor."""
        start_time = time.time()

        while True:
            try:
                # Check for timeout
                if monitor.timeout:
                    elapsed = time.time() - start_time
                    if elapsed >= monitor.timeout:
                        logger.info(f"Monitor {monitor.monitor_id} timed out")
                        await monitor.callback(False, {
                            "reason": "timeout",
                            "elapsed": elapsed
                        })
                        break

                # Call background subagent to check condition
                result = await self.redis.call_tool(
                    tool_name="background",
                    params={
                        "check_type": monitor.condition_type,
                        "target": monitor.target,
                        "monitor_id": monitor.monitor_id
                    },
                    timeout=monitor.check_interval + 5.0
                )

                if result.success:
                    data = result.result.get("data", {})
                    condition_met = data.get("condition_met", False)

                    if condition_met:
                        logger.info(
                            f"Monitor {monitor.monitor_id}: condition met!"
                        )
                        await monitor.callback(True, data)
                        break

                # Wait before next check
                await asyncio.sleep(monitor.check_interval)

            except asyncio.CancelledError:
                logger.info(f"Monitor {monitor.monitor_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitor {monitor.monitor_id}: {e}")
                await asyncio.sleep(monitor.check_interval)

        # Clean up
        self._background_monitors.pop(monitor.monitor_id, None)

    async def stop_background_monitor(self, monitor_id: str) -> bool:
        """
        Stop a background monitor.

        Args:
            monitor_id: The monitor to stop

        Returns:
            True if stopped, False if not found
        """
        monitor = self._background_monitors.get(monitor_id)
        if monitor and monitor._task:
            monitor._task.cancel()
            try:
                await monitor._task
            except asyncio.CancelledError:
                pass
            self._background_monitors.pop(monitor_id, None)
            logger.info(f"Stopped monitor {monitor_id}")
            return True
        return False

    async def stop_all_monitors(self):
        """Stop all background monitors."""
        for monitor_id in list(self._background_monitors.keys()):
            await self.stop_background_monitor(monitor_id)

    # ==================== Utility Methods ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            **self._stats,
            "active_monitors": len(self._background_monitors)
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check manager and Redis health."""
        redis_health = await self.redis.health_check()

        return {
            "healthy": redis_health.get("healthy", False),
            "stats": self.get_stats(),
            "config": {
                "max_planning": self.config.max_planning_subagents,
                "max_vision": self.config.max_vision_subagents,
                "max_specialist": self.config.max_specialist_subagents,
                "aggregation_strategy": self.config.aggregation_strategy.value
            },
            "redis": redis_health
        }


# Convenience function to create a manager with defaults
async def create_subagent_manager(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    config: Optional[SubagentConfig] = None
) -> SubagentManager:
    """
    Create and initialize a SubagentManager.

    Args:
        redis_host: Redis server host
        redis_port: Redis server port
        config: Optional configuration

    Returns:
        Initialized SubagentManager
    """
    from .redis_streams import get_redis_client

    redis_client = await get_redis_client(redis_host, redis_port)
    return SubagentManager(redis_client, config)
