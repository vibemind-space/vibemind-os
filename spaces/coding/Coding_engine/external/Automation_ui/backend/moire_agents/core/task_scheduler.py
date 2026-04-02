"""
Task Scheduler - Manages subtask dependencies and execution order.

Creates execution plans that:
- Group subtasks into phases based on dependencies
- Identify parallelization opportunities within phases
- Manage timeouts for each phase
- Handle dynamic replanning on failures

Example:
    scheduler = TaskScheduler()
    plan = scheduler.create_plan(subtasks)
    for phase in plan.phases:
        if phase.can_parallel:
            await asyncio.gather(*[execute(s) for s in phase.subtasks])
        else:
            for subtask in phase.subtasks:
                await execute(subtask)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional

from .task_decomposer import Subtask

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPhase:
    """A phase of subtasks that can be executed together."""
    phase_id: int
    subtasks: List[Subtask]
    can_parallel: bool = False
    timeout: float = 60.0
    dependencies_met: bool = True

    @property
    def subtask_ids(self) -> Set[str]:
        """Get IDs of all subtasks in this phase."""
        return {s.id for s in self.subtasks}

    def __repr__(self):
        parallel_str = "parallel" if self.can_parallel else "sequential"
        return (
            f"Phase {self.phase_id} ({parallel_str}): "
            f"{len(self.subtasks)} subtask(s)"
        )


@dataclass
class ExecutionPlan:
    """Complete execution plan with ordered phases."""
    phases: List[ExecutionPhase]
    total_subtasks: int
    estimated_duration: float = 0.0
    metadata: Dict = field(default_factory=dict)

    @property
    def total_phases(self) -> int:
        return len(self.phases)

    def get_phase(self, phase_id: int) -> Optional[ExecutionPhase]:
        """Get phase by ID."""
        for phase in self.phases:
            if phase.phase_id == phase_id:
                return phase
        return None

    def __repr__(self):
        return (
            f"ExecutionPlan: {self.total_phases} phases, "
            f"{self.total_subtasks} subtasks"
        )


class TaskScheduler:
    """
    Schedules subtasks into execution phases.

    The scheduler:
    1. Analyzes subtask dependencies
    2. Groups subtasks into phases (dependency levels)
    3. Identifies parallel execution opportunities
    4. Sets timeouts for each phase
    """

    def __init__(
        self,
        default_timeout: float = 60.0,
        max_parallel_per_phase: int = 5
    ):
        """
        Initialize the scheduler.

        Args:
            default_timeout: Default timeout per subtask (seconds)
            max_parallel_per_phase: Maximum subtasks to run in parallel
        """
        self.default_timeout = default_timeout
        self.max_parallel_per_phase = max_parallel_per_phase

    def create_plan(self, subtasks: List[Subtask]) -> ExecutionPlan:
        """
        Create an execution plan from subtasks.

        Args:
            subtasks: List of subtasks with dependencies

        Returns:
            ExecutionPlan with ordered phases
        """
        if not subtasks:
            return ExecutionPlan(phases=[], total_subtasks=0)

        # Build dependency graph
        dep_graph = self._build_dependency_graph(subtasks)

        # Topological sort into levels
        levels = self._topological_levels(subtasks, dep_graph)

        # Create phases from levels
        phases = self._create_phases(levels)

        # Calculate total duration estimate
        estimated_duration = sum(p.timeout for p in phases)

        plan = ExecutionPlan(
            phases=phases,
            total_subtasks=len(subtasks),
            estimated_duration=estimated_duration,
            metadata={
                "dependency_graph": {
                    s.id: list(s.dependencies) for s in subtasks
                }
            }
        )

        logger.info(f"Created execution plan: {plan}")
        return plan

    def _build_dependency_graph(
        self,
        subtasks: List[Subtask]
    ) -> Dict[str, Set[str]]:
        """Build a dependency graph from subtasks."""
        graph = {}
        subtask_ids = {s.id for s in subtasks}

        for subtask in subtasks:
            # Filter to only include valid dependencies
            valid_deps = set(subtask.dependencies) & subtask_ids
            graph[subtask.id] = valid_deps

        return graph

    def _topological_levels(
        self,
        subtasks: List[Subtask],
        dep_graph: Dict[str, Set[str]]
    ) -> List[List[Subtask]]:
        """
        Group subtasks into dependency levels using topological sorting.

        Level 0: Subtasks with no dependencies
        Level 1: Subtasks depending only on Level 0
        Level N: Subtasks depending only on Levels 0 to N-1
        """
        # Map ID to subtask
        id_to_subtask = {s.id: s for s in subtasks}

        # Calculate in-degrees
        in_degree = {s.id: len(dep_graph[s.id]) for s in subtasks}

        # Track completed subtasks
        completed = set()
        levels = []

        while len(completed) < len(subtasks):
            # Find subtasks with all dependencies satisfied
            current_level = []

            for subtask_id, degree in in_degree.items():
                if subtask_id in completed:
                    continue

                # Check if all dependencies are completed
                deps = dep_graph[subtask_id]
                if deps <= completed:
                    current_level.append(id_to_subtask[subtask_id])

            if not current_level:
                # Cycle detected or orphan dependencies
                logger.warning("Dependency cycle detected, breaking remaining tasks")
                # Add remaining tasks to final level
                remaining = [
                    id_to_subtask[sid]
                    for sid in id_to_subtask
                    if sid not in completed
                ]
                if remaining:
                    levels.append(remaining)
                break

            # Sort by order within level
            current_level.sort(key=lambda s: s.order)
            levels.append(current_level)

            # Mark as completed
            for subtask in current_level:
                completed.add(subtask.id)

        return levels

    def _create_phases(
        self,
        levels: List[List[Subtask]]
    ) -> List[ExecutionPhase]:
        """Create execution phases from dependency levels."""
        phases = []

        for level_idx, level_subtasks in enumerate(levels):
            if not level_subtasks:
                continue

            # Determine if phase can run in parallel
            can_parallel = self._can_parallelize(level_subtasks)

            # If too many for parallel, split into chunks
            if can_parallel and len(level_subtasks) > self.max_parallel_per_phase:
                # Split into multiple parallel phases
                for chunk_start in range(
                    0, len(level_subtasks), self.max_parallel_per_phase
                ):
                    chunk = level_subtasks[
                        chunk_start:chunk_start + self.max_parallel_per_phase
                    ]
                    timeout = self._calculate_phase_timeout(chunk, can_parallel)

                    phases.append(ExecutionPhase(
                        phase_id=len(phases) + 1,
                        subtasks=chunk,
                        can_parallel=True,
                        timeout=timeout
                    ))
            else:
                timeout = self._calculate_phase_timeout(level_subtasks, can_parallel)

                phases.append(ExecutionPhase(
                    phase_id=len(phases) + 1,
                    subtasks=level_subtasks,
                    can_parallel=can_parallel,
                    timeout=timeout
                ))

        return phases

    def _can_parallelize(self, subtasks: List[Subtask]) -> bool:
        """
        Determine if subtasks in a level can run in parallel.

        Subtasks can run in parallel if:
        - More than one subtask in the level
        - At least one subtask has can_parallel=True
        - Subtasks don't have conflicting approaches (e.g., both need keyboard)
        """
        if len(subtasks) <= 1:
            return False

        # Check if any subtask explicitly allows parallel
        any_parallel = any(s.can_parallel for s in subtasks)

        # Check for conflicting approaches
        approaches = [s.approach for s in subtasks]

        # These approaches conflict (need exclusive access)
        exclusive_approaches = {"keyboard", "mouse", "hybrid"}
        exclusive_count = sum(1 for a in approaches if a in exclusive_approaches)

        # Can parallelize if approaches don't conflict
        # Vision and specialist can always run in parallel with others
        if exclusive_count > 1:
            return False

        return any_parallel or exclusive_count == 0

    def _calculate_phase_timeout(
        self,
        subtasks: List[Subtask],
        can_parallel: bool
    ) -> float:
        """Calculate timeout for a phase."""
        timeouts = [s.timeout or self.default_timeout for s in subtasks]

        if can_parallel:
            # Parallel: use max timeout
            return max(timeouts) * 1.5  # Add buffer
        else:
            # Sequential: sum timeouts
            return sum(timeouts)

    def replan(
        self,
        original_plan: ExecutionPlan,
        completed_subtasks: Set[str],
        failed_subtasks: Set[str]
    ) -> ExecutionPlan:
        """
        Create a new plan based on execution results.

        Used when a subtask fails and we need to replan.

        Args:
            original_plan: The original execution plan
            completed_subtasks: IDs of successfully completed subtasks
            failed_subtasks: IDs of failed subtasks

        Returns:
            New ExecutionPlan for remaining subtasks
        """
        # Collect remaining subtasks
        remaining = []
        for phase in original_plan.phases:
            for subtask in phase.subtasks:
                if subtask.id not in completed_subtasks:
                    # Update dependencies to remove completed ones
                    subtask.dependencies = [
                        d for d in subtask.dependencies
                        if d not in completed_subtasks
                    ]
                    remaining.append(subtask)

        if not remaining:
            return ExecutionPlan(phases=[], total_subtasks=0)

        # Create new plan for remaining subtasks
        return self.create_plan(remaining)
