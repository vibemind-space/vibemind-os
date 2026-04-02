"""
Coordinator Agent - Central orchestrator using Agent SDK patterns.

This agent coordinates all other agents and tools:
1. Receives requirements and contracts
2. Decides which tools to invoke
3. Handles errors and retries
4. Manages the verification loop
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Any, Callable
import structlog
from typing import TYPE_CHECKING

from src.engine.contracts import InterfaceContracts
from src.engine.slicer import SliceManifest, TaskSlice
from src.engine.planning_engine import ExecutionPlan
from src.tools.claude_code_tool import ClaudeCodeTool, CodeGenerationResult
from src.tools.test_runner_tool import TestRunnerTool, TestResult
from src.tools.supermemory_tools import SupermemoryTools
from src.mind.shared_state import SharedState
from src.mind.event_bus import EventBus, Event, EventType

# Checkpoint and rate limit handling
def _get_checkpoint_manager():
    """Lazy import CheckpointManager."""
    try:
        from src.engine.checkpoint_manager import CheckpointManager, GenerationCheckpoint
        return CheckpointManager, GenerationCheckpoint
    except ImportError:
        return None, None

def _get_rate_limit_handler():
    """Lazy import RateLimitHandler and RateLimitError."""
    try:
        from src.engine.rate_limit_handler import RateLimitHandler, RateLimitError
        return RateLimitHandler, RateLimitError
    except ImportError:
        return None, None

# FIX-30: AsyncGates für robuste Parallelisierung
def _get_async_gates():
    """Lazy import AsyncGates."""
    try:
        from src.engine.async_gates import AsyncGates, GateOutput, GateResult
        return AsyncGates, GateOutput, GateResult
    except ImportError:
        return None, None, None

if TYPE_CHECKING:
    from src.engine.tech_stack import TechStack

logger = structlog.get_logger()


@dataclass
class CoordinatorResult:
    """Result from the coordinator."""
    success: bool
    iterations: int = 0
    files_generated: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    errors: list[str] = field(default_factory=list)
    execution_time_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "iterations": self.iterations,
            "files_generated": self.files_generated,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "errors": self.errors,
            "execution_time_ms": self.execution_time_ms,
        }


COORDINATOR_SYSTEM_PROMPT = """You are a Coordinator Agent orchestrating code generation.

You have access to these tools:
1. generate_code - Generate code using Claude Code CLI
2. run_tests - Execute tests and get results
3. search_memory - Find similar patterns from past projects
4. store_memory - Save successful patterns for future use

Your goal is to:
1. Generate code for all requirements
2. Run tests to verify the code works
3. Fix any failures by regenerating or patching
4. Store successful patterns in memory

Be methodical. Generate code slice by slice. Verify each slice before moving on.
When tests fail, analyze the error and generate a targeted fix."""


class CoordinatorAgent:
    """
    Central coordinator that orchestrates code generation.

    This agent:
    - Takes contracts and slices as input
    - Invokes tools to generate code
    - Runs verification tests
    - Coordinates recovery on failures
    - Manages the iterative loop
    
    FIX-30: Now uses AsyncGates for parallel batch processing
    """

    # Retry configuration
    GENERATION_MAX_RETRIES = 3
    GENERATION_RETRY_DELAY_BASE = 2.0  # seconds, exponential backoff

    def __init__(
        self,
        working_dir: Optional[str] = None,
        max_iterations: int = 3,
        max_concurrent: int = 5,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        tech_stack: Optional[Any] = None,
        parallel_strategy: str = "majority",  # FIX-30: Default Parallel-Strategie
        # Rate limit recovery options
        enable_checkpoints: bool = True,
        rate_limit_wait_hours: float = 4.0,
        rate_limit_interval_minutes: float = 30.0,
        rate_limit_max_retries: int = 10,
        # Review Gate support
        shared_state: Optional[SharedState] = None,
        event_bus: Optional[EventBus] = None,
        # Fungus/Redis context integration
        job_id: Optional[int] = None,
        # Phase 4: Rich context from SpecAdapter
        context_provider: Optional[Any] = None,
        # NEW: AgentContextBridge for RAG-enhanced context
        context_bridge: Optional[Any] = None,
        # Phase 6: Runtime reports for architecture feedback
        runtime_reports: Optional[Any] = None,
    ):
        self.working_dir = working_dir
        self.max_iterations = max_iterations
        self.shared_state = shared_state
        self.event_bus = event_bus
        self.max_concurrent = max_concurrent
        self.progress_callback = progress_callback
        self.tech_stack = tech_stack  # TechStack instance for code generation context
        self.parallel_strategy = parallel_strategy  # FIX-30: "and", "or", "majority"
        self.enable_checkpoints = enable_checkpoints
        self.job_id = job_id  # For Fungus/Redis context streaming
        self.context_provider = context_provider  # Phase 4: Rich context from SpecAdapter
        self.context_bridge = context_bridge  # AgentContextBridge for RAG integration
        self.runtime_reports = runtime_reports  # Phase 6: Architecture health feedback

        # Initialize tools
        self.code_tool = ClaudeCodeTool(
            working_dir=working_dir,
            max_concurrent=max_concurrent,
            job_id=job_id,  # Pass job_id for Redis stream context
        )
        self.test_tool = TestRunnerTool(working_dir=working_dir)
        self.memory_tool = SupermemoryTools()

        # FIX-30: AsyncGates für parallele Verarbeitung
        AsyncGates, _, _ = _get_async_gates()
        self._async_gates = AsyncGates(max_concurrent=max_concurrent) if AsyncGates else None

        # Initialize checkpoint manager
        CheckpointManager, GenerationCheckpoint = _get_checkpoint_manager()
        self._checkpoint_manager = None
        self._checkpoint: Optional[Any] = None  # GenerationCheckpoint
        if enable_checkpoints and working_dir and CheckpointManager:
            self._checkpoint_manager = CheckpointManager(working_dir)

        # Initialize rate limit handler
        RateLimitHandler, _ = _get_rate_limit_handler()
        self._rate_limit_handler = None
        if RateLimitHandler:
            self._rate_limit_handler = RateLimitHandler(
                initial_wait_hours=rate_limit_wait_hours,
                retry_interval_minutes=rate_limit_interval_minutes,
                max_retries=rate_limit_max_retries,
            )

        self.logger = logger.bind(agent="coordinator")

    async def _init_checkpoint(
        self,
        job_id: str,
        total_batches: int,
        requirements_file: Optional[str] = None,
    ) -> None:
        """Initialize or load existing checkpoint."""
        if not self._checkpoint_manager:
            self.logger.debug(
                "checkpoint_init_skipped",
                reason="no_checkpoint_manager",
                enable_checkpoints=self.enable_checkpoints,
            )
            return

        self.logger.debug(
            "checkpoint_init_starting",
            job_id=job_id,
            total_batches=total_batches,
            requirements_file=requirements_file,
        )

        # Try to load existing checkpoint
        existing = await self._checkpoint_manager.load()
        if existing:
            self.logger.debug(
                "checkpoint_existing_found",
                existing_job_id=existing.job_id,
                existing_batch=existing.current_batch,
            )
            # Validate it's for the same job
            is_valid = await self._checkpoint_manager.validate(
                existing, requirements_file
            )
            if is_valid:
                self._checkpoint = existing
                self.logger.info(
                    "checkpoint_resumed",
                    job_id=existing.job_id,
                    batch=existing.current_batch,
                    slices_completed=len(existing.completed_slices),
                )
                return
            else:
                self.logger.warning(
                    "checkpoint_validation_failed",
                    existing_job_id=existing.job_id,
                    new_job_id=job_id,
                )

        # Create new checkpoint
        _, GenerationCheckpoint = _get_checkpoint_manager()
        if GenerationCheckpoint:
            self._checkpoint = self._checkpoint_manager.create(
                job_id=job_id,
                requirements_file=requirements_file,
                total_batches=total_batches,
                total_iterations=self.max_iterations,
            )
            await self._checkpoint_manager.save(self._checkpoint)
            self.logger.info(
                "checkpoint_created_new",
                job_id=job_id,
                total_batches=total_batches,
            )
        else:
            self.logger.warning(
                "checkpoint_init_failed",
                reason="GenerationCheckpoint_class_not_available",
            )

    async def _save_checkpoint(
        self,
        batch_id: int,
        iteration: int,
        completed_slices: list[str],
        completed_files: list[str],
        metrics: Optional[dict] = None,
    ) -> None:
        """Save checkpoint after batch completion."""
        if not self._checkpoint_manager:
            self.logger.warning(
                "checkpoint_save_skipped",
                reason="no_checkpoint_manager",
                batch_id=batch_id,
            )
            return
        if not self._checkpoint:
            self.logger.warning(
                "checkpoint_save_skipped",
                reason="checkpoint_not_initialized",
                batch_id=batch_id,
                has_manager=bool(self._checkpoint_manager),
            )
            return

        self._checkpoint.current_batch = batch_id
        self._checkpoint.current_iteration = iteration

        for slice_id in completed_slices:
            self._checkpoint.mark_slice_completed(slice_id)

        for file_path in completed_files:
            self._checkpoint.mark_file_completed(file_path)

        if metrics:
            self._checkpoint.metrics.update(metrics)

        await self._checkpoint_manager.save(self._checkpoint)
        self.logger.info(
            "checkpoint_saved",
            batch_id=batch_id,
            iteration=iteration,
            slices_completed=len(self._checkpoint.completed_slices),
            files_completed=len(self._checkpoint.completed_files),
        )

    async def _handle_rate_limit(self, error_msg: str) -> bool:
        """
        Handle rate limit error with checkpoint save and retry.

        Returns True if recovered and ready to resume, False if should exit.
        """
        if not self._rate_limit_handler:
            self.logger.error("rate_limit_no_handler", error=error_msg)
            return False

        # Save checkpoint before waiting
        if self._checkpoint_manager and self._checkpoint:
            self._checkpoint.set_rate_limit_hit(error_msg)
            await self._checkpoint_manager.save(self._checkpoint)
            self.logger.info(
                "checkpoint_saved_before_wait",
                batch=self._checkpoint.current_batch,
                slices=len(self._checkpoint.completed_slices),
            )

        # Wait and retry
        recovered = await self._rate_limit_handler.handle_rate_limit()

        if recovered and self._checkpoint:
            self._checkpoint.clear_rate_limit()
            await self._checkpoint_manager.save(self._checkpoint)

        return recovered

    def _is_slice_completed(self, slice_id: str) -> bool:
        """Check if a slice was already completed (from checkpoint)."""
        if not self._checkpoint:
            return False
        return self._checkpoint.is_slice_completed(slice_id)

    async def execute(
        self,
        contracts: InterfaceContracts,
        manifest: SliceManifest,
        execution_plan: Optional[ExecutionPlan] = None,
    ) -> CoordinatorResult:
        """
        Execute the full code generation workflow.

        Args:
            contracts: Interface contracts from architect
            manifest: Slice manifest from slicer
            execution_plan: Optional execution plan for sequential batching

        Returns:
            CoordinatorResult with execution summary
        """
        import time
        start_time = time.time()

        self.logger.info(
            "starting_coordination",
            slices=manifest.total_slices,
            max_iterations=self.max_iterations,
        )

        total_files = 0
        all_errors = []
        iteration = 0

        # Iterative loop
        while iteration < self.max_iterations:
            iteration += 1
            self.logger.info("iteration_start", iteration=iteration)

            # Report progress
            if self.progress_callback:
                self.progress_callback("generating", iteration, self.max_iterations)

            # Phase 1: Generate code for all slices
            gen_results = await self._generate_code_for_slices(
                contracts, manifest, iteration, execution_plan
            )

            total_files = sum(len(r.files) for r in gen_results.values())
            self.logger.info("generation_complete", files=total_files)

            # Phase 2: Run tests
            if self.progress_callback:
                self.progress_callback("testing", iteration, self.max_iterations)

            test_result = await self.test_tool.execute(test_type="auto")

            self.logger.info(
                "tests_complete",
                passed=test_result.passed,
                failed=test_result.failed,
            )

            # Check if all tests pass
            if test_result.success:
                self.logger.info("all_tests_passed")

                # Store successful patterns in memory
                await self._store_successful_patterns(gen_results, contracts)

                return CoordinatorResult(
                    success=True,
                    iterations=iteration,
                    files_generated=total_files,
                    tests_passed=test_result.passed,
                    tests_failed=0,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            # Tests failed - attempt recovery
            if self.progress_callback:
                self.progress_callback("recovering", iteration, self.max_iterations)

            # Collect errors
            for failure in test_result.failures:
                all_errors.append(f"{failure.test_name}: {failure.error_message}")

            # If this isn't the last iteration, try to fix
            if iteration < self.max_iterations:
                await self._attempt_recovery(test_result, contracts)

        # Max iterations reached
        self.logger.warning(
            "max_iterations_reached",
            iterations=iteration,
            remaining_failures=len(all_errors),
        )

        return CoordinatorResult(
            success=False,
            iterations=iteration,
            files_generated=total_files,
            tests_passed=test_result.passed if test_result else 0,
            tests_failed=test_result.failed if test_result else 0,
            errors=all_errors,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    async def _generate_with_retry(
        self,
        slice_id: str,
        prompt: str,
        context: str,
        agent_type: str,
    ) -> CodeGenerationResult:
        """
        Generate code with retry logic for transient failures.
        
        Args:
            slice_id: ID of the slice being generated
            prompt: Generation prompt
            context: Contract context
            agent_type: Type of agent for generation
            
        Returns:
            CodeGenerationResult from code_tool
        """
        last_error: Optional[str] = None
        
        for attempt in range(self.GENERATION_MAX_RETRIES):
            try:
                result = await self.code_tool.execute(prompt, context, agent_type)
                
                # Check if generation actually succeeded (has files)
                if result.success and result.files:
                    if attempt > 0:
                        self.logger.info(
                            "generation_retry_succeeded",
                            slice_id=slice_id,
                            attempt=attempt + 1,
                        )
                    return result
                
                # Generation returned but no files - this is a soft failure
                if not result.files:
                    last_error = result.error or "No files generated"
                    self.logger.warning(
                        "generation_no_files",
                        slice_id=slice_id,
                        attempt=attempt + 1,
                        error=last_error,
                    )
                else:
                    # Result indicates failure
                    last_error = result.error or "Generation failed"
                    self.logger.warning(
                        "generation_failed",
                        slice_id=slice_id,
                        attempt=attempt + 1,
                        error=last_error,
                    )
                
            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    "generation_exception",
                    slice_id=slice_id,
                    attempt=attempt + 1,
                    error=last_error,
                )
            
            # Don't retry on last attempt
            if attempt < self.GENERATION_MAX_RETRIES - 1:
                delay = self.GENERATION_RETRY_DELAY_BASE * (2 ** attempt)
                self.logger.info(
                    "generation_retry_scheduled",
                    slice_id=slice_id,
                    attempt=attempt + 1,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)
        
        # All retries exhausted
        self.logger.error(
            "generation_all_retries_failed",
            slice_id=slice_id,
            total_attempts=self.GENERATION_MAX_RETRIES,
            last_error=last_error,
        )
        
        # Return a failure result
        return CodeGenerationResult(
            success=False,
            output="",
            files=[],
            error=f"Generation failed after {self.GENERATION_MAX_RETRIES} attempts: {last_error}",
            execution_time_ms=0,
        )

    async def _generate_code_for_slices(
        self,
        contracts: InterfaceContracts,
        manifest: SliceManifest,
        iteration: int,
        execution_plan: Optional[ExecutionPlan] = None,
    ) -> dict[str, CodeGenerationResult]:
        """
        Generate code for all slices using execution plan.

        FIX-30: Uses AsyncGates for parallel batch processing instead of sequential.
        Task 8: Includes checkpoint save/resume and rate limit recovery.
        """
        all_results: dict[str, CodeGenerationResult] = {}

        # Get RateLimitError for catching
        _, RateLimitError = _get_rate_limit_handler()

        # Use execution plan if provided (sequential execution)
        if execution_plan:
            self.logger.info(
                "using_execution_plan",
                total_batches=execution_plan.total_batches,
                sequential_only=execution_plan.sequential_only,
                parallel_strategy=self.parallel_strategy,
            )

            # Initialize checkpoint if needed
            if self._checkpoint_manager and not self._checkpoint:
                job_id = f"gen_{iteration}_{execution_plan.total_batches}"
                await self._init_checkpoint(job_id, execution_plan.total_batches)

            # FIX: Don't skip batches by batch number - batch_size may have changed
            # between runs, causing batch numbering mismatch. Instead, rely on
            # per-slice _is_slice_completed() check which uses completed_slices.
            if self._checkpoint and len(self._checkpoint.completed_slices) > 0:
                self.logger.info(
                    "resuming_from_checkpoint",
                    completed_slices=len(self._checkpoint.completed_slices),
                    total_slices=sum(len(b.slices) for b in execution_plan.batches),
                )

            for batch in execution_plan.batches:
                # Individual slices will be skipped via _is_slice_completed() below

                self.logger.info(
                    "processing_batch",
                    batch_id=batch.batch_id + 1,
                    total=execution_plan.total_batches,
                    slices=len(batch.slices),
                    complexity=batch.complexity,
                    estimated_time_ms=batch.estimated_time_ms,
                )

                # Publish batch_started event for dashboard task visibility
                if self.event_bus:
                    await self.event_bus.publish(Event(
                        type=EventType.TASK_PROGRESS_UPDATE,
                        source="coordinator",
                        data={
                            "type": "batch_started",
                            "batch_id": batch.batch_id,
                            "slice_ids": [s.slice_id for s in batch.slices],
                            "total_batches": execution_plan.total_batches,
                            "batch_size": len(batch.slices),
                        },
                    ))

                # Build prompts with contracts for this batch
                # Skip slices that were already completed (from checkpoint)
                prompts = []
                for slice_obj in batch.slices:
                    if self._is_slice_completed(slice_obj.slice_id):
                        self.logger.debug(
                            "skipping_completed_slice",
                            slice_id=slice_obj.slice_id,
                        )
                        continue
                    context = contracts.to_prompt_context(slice_obj.agent_type)
                    prompt = self._build_slice_prompt(slice_obj)
                    prompts.append((slice_obj.slice_id, prompt, context, slice_obj.agent_type))

                # Skip empty batches (all slices completed)
                if not prompts:
                    self.logger.info(
                        "batch_already_complete",
                        batch_id=batch.batch_id,
                    )
                    # Still update checkpoint to reflect batch progress
                    await self._save_checkpoint(
                        batch_id=batch.batch_id + 1,
                        iteration=iteration,
                        completed_slices=[],  # No new slices
                        completed_files=[],
                    )
                    continue

                try:
                    # FIX-30: Parallele Batch-Verarbeitung mit AsyncGates
                    if self._async_gates and len(prompts) > 1:
                        batch_results = await self._execute_batch_parallel(prompts)
                        all_results.update(batch_results)
                    else:
                        # Fallback: Sequential mit Retry
                        for slice_id, prompt, context, agent_type in prompts:
                            result = await self._generate_with_retry(slice_id, prompt, context, agent_type)
                            all_results[slice_id] = result

                    # Save checkpoint after successful batch
                    # Only mark slices as completed if they actually generated files
                    completed_slices = [
                        p[0] for p in prompts
                        if p[0] in all_results and all_results[p[0]].files
                    ]
                    completed_files = []
                    for slice_id in completed_slices:
                        if slice_id in all_results and all_results[slice_id].files:
                            completed_files.extend([f.path for f in all_results[slice_id].files])

                    await self._save_checkpoint(
                        batch_id=batch.batch_id + 1,
                        iteration=iteration,
                        completed_slices=completed_slices,
                        completed_files=completed_files,
                        metrics={"files_generated": len(completed_files)},
                    )

                    # Publish batch_completed event for dashboard task visibility
                    if self.event_bus:
                        failed_slices = [
                            p[0] for p in prompts
                            if p[0] not in completed_slices
                        ]
                        await self.event_bus.publish(Event(
                            type=EventType.TASK_PROGRESS_UPDATE,
                            source="coordinator",
                            data={
                                "type": "batch_completed",
                                "batch_id": batch.batch_id,
                                "completed_slices": completed_slices,
                                "failed_slices": failed_slices,
                                "total_batches": execution_plan.total_batches,
                            },
                        ))

                    # Review Gate: Check if user requested pause after batch
                    if await self._check_review_pause():
                        await self._wait_for_review_resume()

                except Exception as e:
                    # Check if it's a rate limit error
                    if RateLimitError and isinstance(e, RateLimitError):
                        self.logger.warning(
                            "rate_limit_hit_during_batch",
                            batch_id=batch.batch_id,
                            error=str(e),
                        )

                        # Handle rate limit with wait and retry
                        recovered = await self._handle_rate_limit(str(e))
                        if recovered:
                            # Retry this batch
                            self.logger.info(
                                "retrying_batch_after_rate_limit",
                                batch_id=batch.batch_id,
                            )
                            # Re-run the same batch
                            if self._async_gates and len(prompts) > 1:
                                batch_results = await self._execute_batch_parallel(prompts)
                                all_results.update(batch_results)
                            else:
                                for slice_id, prompt, context, agent_type in prompts:
                                    result = await self._generate_with_retry(slice_id, prompt, context, agent_type)
                                    all_results[slice_id] = result

                            # Save checkpoint after retry success
                            # Only mark slices as completed if they actually generated files
                            completed_slices = [
                                p[0] for p in prompts
                                if p[0] in all_results and all_results[p[0]].files
                            ]
                            completed_files = []
                            for slice_id in completed_slices:
                                if slice_id in all_results and all_results[slice_id].files:
                                    completed_files.extend([f.path for f in all_results[slice_id].files])

                            await self._save_checkpoint(
                                batch_id=batch.batch_id + 1,
                                iteration=iteration,
                                completed_slices=completed_slices,
                                completed_files=completed_files,
                            )

                            # Review Gate: Check if user requested pause after batch
                            if await self._check_review_pause():
                                await self._wait_for_review_resume()
                        else:
                            # Max retries exceeded - save and exit
                            self.logger.error(
                                "rate_limit_max_retries_exceeded",
                                batch_id=batch.batch_id,
                            )
                            raise
                    else:
                        # Re-raise non-rate-limit errors
                        raise

        else:
            # Fallback to parallel batches (legacy behavior)
            from src.engine.slicer import Slicer

            slicer = Slicer(working_dir=self.working_dir)
            batches = slicer.get_parallel_batches(manifest)

            # Initialize checkpoint if needed
            if self._checkpoint_manager and not self._checkpoint:
                job_id = f"gen_{iteration}_{len(batches)}"
                await self._init_checkpoint(job_id, len(batches))

            # FIX: Don't skip batches by batch number - batch_size may have changed
            # between runs, causing batch numbering mismatch. Instead, rely on
            # per-slice _is_slice_completed() check which uses completed_slices.
            if self._checkpoint and len(self._checkpoint.completed_slices) > 0:
                self.logger.info(
                    "resuming_from_checkpoint_legacy",
                    completed_slices=len(self._checkpoint.completed_slices),
                    total_slices=sum(len(b) for b in batches),
                )

            for batch_idx, batch in enumerate(batches):
                # Individual slices will be skipped via _is_slice_completed() below

                self.logger.info(
                    "processing_batch",
                    batch=batch_idx + 1,
                    total=len(batches),
                    slices=len(batch),
                )

                # Build prompts with contracts, skip completed slices
                prompts = []
                for slice_obj in batch:
                    if self._is_slice_completed(slice_obj.slice_id):
                        self.logger.debug(
                            "skipping_completed_slice_legacy",
                            slice_id=slice_obj.slice_id,
                        )
                        continue
                    context = contracts.to_prompt_context(slice_obj.agent_type)
                    prompt = self._build_slice_prompt(slice_obj)
                    prompts.append((slice_obj.slice_id, prompt, context, slice_obj.agent_type))

                # Skip empty batches (all slices completed)
                if not prompts:
                    # Still update checkpoint to reflect batch progress
                    await self._save_checkpoint(
                        batch_id=batch_idx + 1,
                        iteration=iteration,
                        completed_slices=[],  # No new slices
                        completed_files=[],
                    )
                    continue

                try:
                    # FIX-30: Parallele Batch-Verarbeitung mit AsyncGates
                    if self._async_gates and len(prompts) > 1:
                        batch_results = await self._execute_batch_parallel(prompts)
                        all_results.update(batch_results)
                    else:
                        # Fallback: Sequential mit Retry
                        for slice_id, prompt, context, agent_type in prompts:
                            result = await self._generate_with_retry(slice_id, prompt, context, agent_type)
                            all_results[slice_id] = result

                    # Save checkpoint after successful batch
                    # Only mark slices as completed if they actually generated files
                    completed_slices = [
                        p[0] for p in prompts
                        if p[0] in all_results and all_results[p[0]].files
                    ]
                    completed_files = []
                    for slice_id in completed_slices:
                        if slice_id in all_results and all_results[slice_id].files:
                            completed_files.extend([f.path for f in all_results[slice_id].files])

                    await self._save_checkpoint(
                        batch_id=batch_idx + 1,
                        iteration=iteration,
                        completed_slices=completed_slices,
                        completed_files=completed_files,
                    )

                except Exception as e:
                    # Check if it's a rate limit error
                    if RateLimitError and isinstance(e, RateLimitError):
                        self.logger.warning(
                            "rate_limit_hit_legacy",
                            batch_idx=batch_idx,
                            error=str(e),
                        )

                        recovered = await self._handle_rate_limit(str(e))
                        if recovered:
                            # Retry this batch
                            if self._async_gates and len(prompts) > 1:
                                batch_results = await self._execute_batch_parallel(prompts)
                                all_results.update(batch_results)
                            else:
                                for slice_id, prompt, context, agent_type in prompts:
                                    result = await self._generate_with_retry(slice_id, prompt, context, agent_type)
                                    all_results[slice_id] = result

                            # Save checkpoint
                            # Only mark slices as completed if they actually generated files
                            completed_slices = [
                                p[0] for p in prompts
                                if p[0] in all_results and all_results[p[0]].files
                            ]
                            completed_files = []
                            for slice_id in completed_slices:
                                if slice_id in all_results and all_results[slice_id].files:
                                    completed_files.extend([f.path for f in all_results[slice_id].files])

                            await self._save_checkpoint(
                                batch_id=batch_idx + 1,
                                iteration=iteration,
                                completed_slices=completed_slices,
                                completed_files=completed_files,
                            )
                        else:
                            raise
                    else:
                        raise

        return all_results

    async def _execute_batch_parallel(
        self,
        prompts: list[tuple[str, str, str, str]],
    ) -> dict[str, CodeGenerationResult]:
        """
        FIX-30: Execute batch of prompts in parallel using AsyncGates.
        
        Uses the configured parallel_strategy:
        - "and": All must succeed (fail-fast on error)
        - "or": At least one must succeed (first success wins)
        - "majority": Majority must succeed (robust against single failures)
        
        Args:
            prompts: List of (slice_id, prompt, context, agent_type) tuples
            
        Returns:
            Dict mapping slice_id to CodeGenerationResult
        """
        if not self._async_gates:
            # Fallback to sequential
            results = {}
            for slice_id, prompt, context, agent_type in prompts:
                results[slice_id] = await self._generate_with_retry(
                    slice_id, prompt, context, agent_type
                )
            return results
        
        self.logger.info(
            "parallel_batch_start",
            task_count=len(prompts),
            strategy=self.parallel_strategy,
        )
        
        # Create async task factories
        async def create_generation_task(
            sid: str, p: str, c: str, at: str
        ) -> CodeGenerationResult:
            """Task factory for a single generation."""
            return await self.code_tool.execute(p, c, at)
        
        # Build tasks list for AsyncGates
        tasks = [
            (slice_id, lambda sid=slice_id, p=prompt, c=context, at=agent_type: 
             create_generation_task(sid, p, c, at))
            for slice_id, prompt, context, agent_type in prompts
        ]
        
        # Execute with selected strategy
        _, GateOutput, GateResult = _get_async_gates()
        
        if self.parallel_strategy == "or":
            gate_result = await self._async_gates.OR(tasks, min_success=1)
        elif self.parallel_strategy == "and":
            gate_result = await self._async_gates.AND(tasks, fail_fast=False)
        else:  # default: MAJORITY
            gate_result = await self._async_gates.MAJORITY(tasks, threshold=0.5)
        
        # Convert to results dict
        results: dict[str, CodeGenerationResult] = {}
        
        for task_result in gate_result.results:
            if task_result.success and task_result.result:
                results[task_result.task_id] = task_result.result
            else:
                # Create failure result
                results[task_result.task_id] = CodeGenerationResult(
                    success=False,
                    error=task_result.error or "Generation failed",
                    files=[],
                    output="",
                    execution_time_ms=task_result.execution_time_ms,
                )
        
        self.logger.info(
            "parallel_batch_complete",
            strategy=self.parallel_strategy,
            status=gate_result.status.value,
            successful=gate_result.successful_count,
            failed=gate_result.failed_count,
            time_ms=gate_result.total_time_ms,
        )
        
        return results

    def _build_slice_prompt(self, slice: TaskSlice) -> str:
        """Build generation prompt for a slice."""
        req_list = "\n".join([
            f"- [{r.get('id', '')}] {r.get('label', '')}: {r.get('description', '')}"
            for r in slice.requirement_details
        ])

        # Build tech stack context if available
        tech_stack_section = ""
        if self.tech_stack:
            tech_stack_section = f"""
## Technology Stack

{self.tech_stack.to_prompt_context()}

CRITICAL: You MUST use the technologies specified above. Do NOT use different frameworks or libraries.
"""

        # Phase 4 Fix 4: Add pre-defined API endpoints from rich context
        rich_context_section = ""
        if self.context_provider:
            try:
                # Get requirement IDs for this slice
                req_ids = [r.get("id", r.get("req_id")) for r in slice.requirement_details]

                # Get context for this slice
                gen_context = self.context_provider.for_generator(
                    requirement_id=req_ids[0] if req_ids else None
                )

                # Add related API endpoints if available
                related_endpoints = gen_context.get("related_endpoints", [])
                if related_endpoints:
                    endpoints_text = "\n".join([
                        f"- {ep.get('method', 'GET')} {ep.get('path', '')}: {ep.get('description', '')}"
                        for ep in related_endpoints[:10]  # Limit to 10 endpoints
                    ])
                    rich_context_section = f"""
## Pre-defined API Endpoints

The following API endpoints are already designed for this feature:

{endpoints_text}

Use these endpoint definitions when implementing API routes.
"""
            except Exception:
                pass  # Silently ignore context errors

        # Phase 6: Add architecture insights from runtime reports
        architecture_section = ""
        if self.runtime_reports and self.runtime_reports.has_architecture_issues():
            try:
                arch_context = self.runtime_reports.to_prompt_context()
                if arch_context:
                    architecture_section = f"""
## Architecture Feedback (from previous runs)

{arch_context}

When implementing, please address these architecture issues where applicable.
"""
            except Exception:
                pass  # Silently ignore errors

        return f"""Implement the following requirements:

{req_list}
{tech_stack_section}{rich_context_section}{architecture_section}
IMPORTANT: You MUST write all code files to disk using your Write tool.
Do NOT just output code blocks - actually create the files in the current directory.

Create complete, production-ready code with proper file structure.
Follow the interface contracts provided in the context.
Use appropriate file paths for your agent type ({slice.agent_type}).

Write each file using the Write tool with the correct path and content.
"""

    async def _attempt_recovery(
        self,
        test_result: TestResult,
        contracts: InterfaceContracts,
    ):
        """Attempt to fix failing tests."""
        from src.agents.recovery_agent import RecoveryAgent

        recovery_agent = RecoveryAgent(working_dir=self.working_dir)

        for failure in test_result.failures[:5]:  # Limit to first 5 failures
            self.logger.info(
                "attempting_recovery",
                test=failure.test_name,
                file=failure.file_path,
            )

            # Search memory for similar fixes
            similar = await self.memory_tool.search(
                query=f"{failure.error_type} {failure.error_message}",
                category="error_fix",
                limit=3,
            )

            # Attempt fix
            fix_result = await recovery_agent.fix_failure(
                failure=failure,
                contracts=contracts,
                similar_fixes=similar.results if similar.found else None,
            )

            if fix_result.success:
                self.logger.info(
                    "recovery_successful",
                    test=failure.test_name,
                )
            else:
                self.logger.warning(
                    "recovery_failed",
                    test=failure.test_name,
                    error=fix_result.error,
                )

    async def _store_successful_patterns(
        self,
        results: dict[str, CodeGenerationResult],
        contracts: InterfaceContracts,
    ):
        """
        Store successful code patterns in Supermemory for future context.
        
        Uses containerTags for project/domain scoping:
        - project_{job_id}: Project-level grouping
        - domain_{type}: Domain filtering (frontend/backend/etc.)
        - generated_pattern: Category tag
        """
        # Get job_id from contracts project_name (e.g., "Job-123" -> 123)
        job_id = 1
        try:
            if contracts.project_name and contracts.project_name.startswith("Job-"):
                job_id = int(contracts.project_name.split("-")[1])
        except (ValueError, IndexError):
            pass
        
        stored_count = 0
        
        for slice_id, result in results.items():
            if result.success and result.files:
                # Extract domain from slice_id (e.g., "frontend-slice-1" -> "frontend")
                domain = slice_id.split("-")[0] if "-" in slice_id else "general"
                
                # Store each file as a pattern with proper container tags
                for file in result.files[:3]:  # Limit to 3 files per slice
                    try:
                        # Use new store_generated_pattern with container tags
                        store_result = await self.memory_tool.store_generated_pattern(
                            code=file.content[:3000],  # Truncate large files
                            slice_id=slice_id,
                            domain=domain,
                            feature=file.language,  # Use language as feature category
                            job_id=job_id,
                            success=True,
                        )
                        
                        if store_result.success:
                            stored_count += 1
                            self.logger.debug(
                                "pattern_stored",
                                slice_id=slice_id,
                                file=file.path,
                                memory_id=store_result.memory_id,
                            )
                        else:
                            self.logger.debug(
                                "pattern_store_failed",
                                slice_id=slice_id,
                                error=store_result.error,
                            )
                            
                    except Exception as e:
                        self.logger.debug(
                            "pattern_store_exception",
                            slice_id=slice_id,
                            error=str(e),
                        )
        
        if stored_count > 0:
            self.logger.info(
                "patterns_stored_to_memory",
                total_stored=stored_count,
                job_id=job_id,
            )

    # =========================================================================
    # Review Gate Methods (Pause/Resume for User Review)
    # =========================================================================

    async def _check_review_pause(self) -> bool:
        """Check if user requested pause for review."""
        if self.shared_state:
            return self.shared_state.review_paused
        return False

    async def _wait_for_review_resume(self) -> None:
        """Block until user resumes generation."""
        if not self.shared_state:
            return

        self.logger.info("review_gate_waiting", message="Generation paused, waiting for user review")

        # Publish pause event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=EventType.REVIEW_PAUSED,
                source="coordinator",
                data={
                    "checkpoint": self._checkpoint.to_dict() if self._checkpoint else None,
                    "working_dir": self.working_dir,
                }
            ))

        # Block until resumed
        await self.shared_state.review_pause_event.wait()

        self.logger.info("review_gate_resumed", message="User resumed generation")

        # Publish resume event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=EventType.REVIEW_RESUMED,
                source="coordinator",
                data={"has_feedback": bool(self.shared_state.review_feedback)}
            ))

    def _get_review_feedback_context(self) -> Optional[str]:
        """Get user feedback to inject into next generation."""
        if self.shared_state:
            feedback = self.shared_state.get_review_feedback()
            if feedback:
                self.logger.info(
                    "review_feedback_injecting",
                    feedback_length=len(feedback),
                )
                return f"""
## User Review Feedback

The user has reviewed the application and provided the following feedback:

{feedback}

Please address these concerns in your next code generation. Prioritize fixing the issues mentioned above.
"""
        return None


async def coordinate_generation(
    contracts: InterfaceContracts,
    manifest: SliceManifest,
    working_dir: Optional[str] = None,
    max_iterations: int = 3,
) -> CoordinatorResult:
    """
    Convenience function to coordinate code generation.

    Args:
        contracts: Interface contracts
        manifest: Slice manifest
        working_dir: Working directory
        max_iterations: Max retry iterations

    Returns:
        CoordinatorResult
    """
    coordinator = CoordinatorAgent(
        working_dir=working_dir,
        max_iterations=max_iterations,
    )
    return await coordinator.execute(contracts, manifest)
