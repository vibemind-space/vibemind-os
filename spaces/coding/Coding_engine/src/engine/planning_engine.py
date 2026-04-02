"""
Planning Engine - Creates execution plan for code generation.

This module:
1. Analyzes slices for dependencies and complexity
2. Creates execution batches for parallel or sequential execution
3. Provides optimal order for code generation

Enhanced: Now supports parallel batch execution with configurable batch_size
"""
from dataclasses import dataclass, field
from typing import Optional
import structlog

from src.engine.slicer import TaskSlice, SliceManifest

logger = structlog.get_logger()


@dataclass
class ExecutionBatch:
    """A batch of slices to execute (potentially in parallel)."""
    batch_id: int
    slices: list[TaskSlice] = field(default_factory=list)
    estimated_time_ms: int = 0
    complexity: str = "medium"  # low, medium, high
    parallel: bool = False  # Whether slices in this batch can run in parallel

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "slice_count": len(self.slices),
            "estimated_time_ms": self.estimated_time_ms,
            "complexity": self.complexity,
            "parallel": self.parallel,
        }


@dataclass
class ExecutionPlan:
    """Complete execution plan for code generation."""
    job_id: int
    total_batches: int
    batches: list[ExecutionBatch] = field(default_factory=list)
    sequential_only: bool = True  # Force sequential execution between batches
    parallel_within_batch: bool = False  # Allow parallel execution within batches

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "total_batches": self.total_batches,
            "sequential_only": self.sequential_only,
            "parallel_within_batch": self.parallel_within_batch,
            "batches": [b.to_dict() for b in self.batches],
        }


class PlanningEngine:
    """
    Creates execution plan for code generation.

    The planning engine:
    - Analyzes slice dependencies
    - Estimates complexity per slice
    - Creates batches for efficient execution
    - Supports both sequential and parallel modes
    
    NEW: batch_size parameter controls how many slices per batch
    """

    # Estimated time per slice (in ms) based on complexity
    TIME_ESTIMATES = {
        "low": 30000,      # 30 seconds
        "medium": 60000,   # 1 minute
        "high": 120000,    # 2 minutes
    }

    def __init__(self, batch_size: int = 5):
        """
        Initialize PlanningEngine.
        
        Args:
            batch_size: Number of slices per batch (default: 5 for parallel execution)
        """
        self.batch_size = batch_size
        self.logger = logger.bind(component="planning_engine")

    def create_plan(
        self,
        manifest: SliceManifest,
        force_sequential: bool = False,  # Changed default to False for parallel
        batch_size: Optional[int] = None,
    ) -> ExecutionPlan:
        """
        Create execution plan from slice manifest.

        Args:
            manifest: Slice manifest from Slicer
            force_sequential: Force 1 slice per batch (old behavior)
            batch_size: Override batch size (uses instance default if None)

        Returns:
            ExecutionPlan with batches
        """
        effective_batch_size = batch_size or self.batch_size
        
        # Force sequential means 1 slice per batch (old behavior)
        if force_sequential:
            effective_batch_size = 1
        
        self.logger.info(
            "creating_execution_plan",
            job_id=manifest.job_id,
            total_slices=manifest.total_slices,
            batch_size=effective_batch_size,
            force_sequential=force_sequential,
        )

        batches = []
        current_batch_slices = []
        batch_id = 0
        
        for slice_obj in manifest.slices:
            current_batch_slices.append(slice_obj)
            
            # Create batch when we reach batch_size
            if len(current_batch_slices) >= effective_batch_size:
                batch = self._create_batch(batch_id, current_batch_slices, not force_sequential)
                batches.append(batch)
                current_batch_slices = []
                batch_id += 1
        
        # Handle remaining slices
        if current_batch_slices:
            batch = self._create_batch(batch_id, current_batch_slices, not force_sequential)
            batches.append(batch)

        plan = ExecutionPlan(
            job_id=manifest.job_id,
            total_batches=len(batches),
            batches=batches,
            sequential_only=force_sequential,
            parallel_within_batch=not force_sequential,
        )

        total_time = sum(b.estimated_time_ms for b in batches)
        # Parallel execution reduces time by batch_size factor
        effective_time = total_time if force_sequential else total_time // max(1, effective_batch_size)
        
        self.logger.info(
            "execution_plan_created",
            job_id=manifest.job_id,
            total_batches=len(batches),
            total_slices=manifest.total_slices,
            batch_size=effective_batch_size,
            estimated_total_time_ms=total_time,
            estimated_parallel_time_ms=effective_time,
            parallel_speedup=f"{effective_batch_size}x" if not force_sequential else "1x",
        )

        return plan

    def _create_batch(
        self, 
        batch_id: int, 
        slices: list[TaskSlice], 
        parallel: bool
    ) -> ExecutionBatch:
        """Create a batch from a list of slices."""
        # Highest complexity in batch determines batch complexity
        complexities = [self._estimate_complexity(s) for s in slices]
        batch_complexity = max(complexities, key=lambda c: ["low", "medium", "high"].index(c))
        
        # Time is max of individual times if parallel, sum if sequential
        times = [self.TIME_ESTIMATES.get(c, 60000) for c in complexities]
        estimated_time = max(times) if parallel else sum(times)
        
        return ExecutionBatch(
            batch_id=batch_id,
            slices=list(slices),  # Copy the list
            estimated_time_ms=estimated_time,
            complexity=batch_complexity,
            parallel=parallel,
        )

    def _estimate_complexity(self, slice_obj: TaskSlice) -> str:
        """
        Estimate complexity of a slice.

        Args:
            slice_obj: Slice to estimate

        Returns:
            Complexity level: "low", "medium", "high"
        """
        req_count = len(slice_obj.requirements)
        token_count = slice_obj.estimated_tokens

        # Simple heuristic based on requirements and tokens
        if req_count <= 3 and token_count < 1000:
            return "low"
        elif req_count <= 7 and token_count < 3000:
            return "medium"
        else:
            return "high"

    def get_next_batch(
        self,
        plan: ExecutionPlan,
        completed_batch_ids: set[int],
    ) -> Optional[ExecutionBatch]:
        """
        Get next batch to execute.

        Args:
            plan: Execution plan
            completed_batch_ids: Set of completed batch IDs

        Returns:
            Next batch to execute, or None if all complete
        """
        for batch in plan.batches:
            if batch.batch_id not in completed_batch_ids:
                return batch
        return None
