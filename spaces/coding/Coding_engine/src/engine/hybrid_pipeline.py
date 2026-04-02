"""
Hybrid Pipeline - Complete pipeline with pre-analysis and iterative execution.

This is the main entry point for the coding engine. It orchestrates:
1. Phase 1: Architect Agent analyzes requirements and creates contracts
2. Phase 2: Parallel code generation with contracts as context
3. Phase 3: Verification and merge
4. Phase 4: Iterative recovery loop
5. Phase 5: Memory update

Enhanced with:
- Parallel architecture analysis (domain-based chunking)
- Parallel batch execution for large projects
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING, Any
import structlog

from src.engine.dag_parser import DAGParser, RequirementsData
from src.engine.slicer import Slicer, SliceManifest
from src.engine.contracts import InterfaceContracts
from src.engine.spec_adapter import SpecAdapter, NormalizedSpec, ContextProvider, SpecFormat
from src.engine.merger import CodeMerger, MergeResult
from src.engine.project_analyzer import ProjectAnalyzer, ProjectProfile
from src.engine.planning_engine import PlanningEngine, ExecutionPlan
from src.engine.execution_plan import ExecutionPlan as ChunkExecutionPlan
from src.engine.runtime_report_manager import RuntimeReportManager, AggregatedReports
# Lazy imports to avoid circular dependency with agents package
if TYPE_CHECKING:
    from src.agents.architect_agent import ArchitectAgent, ChunkAnalysisResult
    from src.agents.coordinator_agent import CoordinatorAgent, CoordinatorResult
    from src.agents.validation_recovery_agent import ValidationRecoveryAgent
    from src.agents.agent_factory import AgentFactory
    from src.engine.tech_stack import TechStack
from src.tools.test_runner_tool import TestRunnerTool
from src.tools.memory_tool import MemoryTool
from src.tools.project_validator_tool import ProjectValidatorTool
from src.validators.base_validator import ValidationResult
from src.mind.event_bus import EventBus, Event, EventType

# Lazy import for DeployTestTeam to avoid circular dependency
def _get_deploy_test_team():
    """Lazy import DeployTestTeam."""
    try:
        from src.agents.deploy_test_team import DeployTestTeam, TeamResult
        return DeployTestTeam, TeamResult
    except ImportError:
        return None, None

# Keep RuntimeTestAgent as fallback
def _get_runtime_test_agent():
    """Lazy import RuntimeTestAgent (fallback)."""
    try:
        from src.agents.runtime_test_agent import RuntimeTestAgent, RuntimeResult
        return RuntimeTestAgent, RuntimeResult
    except ImportError:
        return None, None

logger = structlog.get_logger()


@dataclass
class PipelineProgress:
    """Progress tracking for the pipeline."""
    job_id: int
    phase: str  # architect, generating, testing, recovery, validating, complete
    phase_progress: float = 0.0  # 0-100
    total_phases: int = 6  # architect, generate, test/recovery, validate, fix, write
    current_phase: int = 0
    iteration: int = 0
    max_iterations: int = 3
    files_generated: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    validation_errors: int = 0
    validation_warnings: int = 0
    parallel_chunks: int = 0  # NEW: Track parallel chunk count
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "phase": self.phase,
            "phase_progress": self.phase_progress,
            "overall_progress": (self.current_phase / self.total_phases) * 100,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "files_generated": self.files_generated,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "parallel_chunks": self.parallel_chunks,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": self.error,
        }


@dataclass
class PipelineResult:
    """Final result from the hybrid pipeline."""
    success: bool
    job_id: int
    files_generated: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    validation_errors: int = 0
    validation_warnings: int = 0
    validation_fixes_applied: int = 0
    runtime_errors: int = 0
    runtime_warnings: int = 0
    runtime_failed_requests: int = 0
    runtime_fixes_applied: int = 0
    iterations: int = 0
    contracts: Optional[InterfaceContracts] = None
    merge_result: Optional[MergeResult] = None
    validation_result: Optional[ValidationResult] = None
    execution_time_ms: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "job_id": self.job_id,
            "files_generated": self.files_generated,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "validation_fixes_applied": self.validation_fixes_applied,
            "runtime_errors": self.runtime_errors,
            "runtime_warnings": self.runtime_warnings,
            "runtime_failed_requests": self.runtime_failed_requests,
            "runtime_fixes_applied": self.runtime_fixes_applied,
            "iterations": self.iterations,
            "execution_time_ms": self.execution_time_ms,
            "errors": self.errors,
        }


class HybridPipeline:
    """
    Complete hybrid pipeline for automated code generation.

    Pipeline Phases:
    1. ARCHITECT: Analyze requirements, generate contracts (supports parallel)
    2. GENERATE: Parallel code generation with contracts
    3. MERGE: Combine outputs, resolve conflicts
    4. VERIFY: Run tests, check for errors
    4.5 RUNTIME: Browser Console Tests after Build
    5. RECOVER: Fix failures (iterative)
    6. MEMORY: Store successful patterns
    """

    # Threshold for enabling parallel analysis
    PARALLEL_THRESHOLD = 15  # Use parallel analysis if > 15 requirements

    def __init__(
        self,
        output_dir: str,
        max_concurrent: int = 10,
        max_iterations: int = 3,
        slice_size: int = 10,
        progress_callback: Optional[Callable[[PipelineProgress], None]] = None,
        tech_stack: Optional[Any] = None,
        enable_parallel_analysis: bool = True,  # Enable/disable parallel arch analysis
        enable_intelligent_chunking: bool = False,  # LLM-based chunk planning
        llm_client: Optional[Any] = None,  # LLM client for chunk planning
        event_bus: Optional[EventBus] = None,  # EventBus for backend agent chain
        # Rate limit recovery options (Task 8)
        enable_checkpoints: bool = True,
        rate_limit_wait_hours: float = 4.0,
        rate_limit_interval_minutes: float = 30.0,
        rate_limit_max_retries: int = 10,
        # Fungus/Redis integration
        enable_fungus: bool = False,
        redis_url: str = "redis://localhost:6379/0",
        # Service Pipeline v2 (SpecParser + ServiceOrchestrator)
        use_service_pipeline: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.max_concurrent = max_concurrent
        self.max_iterations = max_iterations
        self.slice_size = slice_size
        self.progress_callback = progress_callback
        self.tech_stack = tech_stack
        self.enable_parallel_analysis = enable_parallel_analysis
        self.enable_intelligent_chunking = enable_intelligent_chunking
        self.llm_client = llm_client
        self.event_bus = event_bus

        # Rate limit recovery configuration
        self.enable_checkpoints = enable_checkpoints
        self.rate_limit_wait_hours = rate_limit_wait_hours
        self.rate_limit_interval_minutes = rate_limit_interval_minutes
        self.rate_limit_max_retries = rate_limit_max_retries

        # Fungus/Redis configuration
        self.enable_fungus = enable_fungus
        self.redis_url = redis_url
        self._fungus_worker = None

        # Service Pipeline v2 flag
        self.use_service_pipeline = use_service_pipeline

        # Universal spec support (set in execute_from_file)
        self.normalized_spec: Optional[NormalizedSpec] = None
        self.context_provider: Optional[ContextProvider] = None
        self.context_bridge = None  # AgentContextBridge for RAG integration

        # Phase 6: Runtime report manager for feedback loop
        self.report_manager = RuntimeReportManager(output_dir)
        self.runtime_reports: Optional[AggregatedReports] = None

        # Initialize components
        self.parser = DAGParser()
        self.slicer = Slicer(slice_size, tech_stack=tech_stack, working_dir=str(self.output_dir))
        self.merger = CodeMerger()
        self.memory = MemoryTool(enabled=True)

        self.logger = logger.bind(component="hybrid_pipeline")

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute_from_file(
        self,
        requirements_file: str,
        job_id: int = 1,
    ) -> PipelineResult:
        """Execute pipeline from a requirements JSON file.

        Supports multiple formats:
        - Simple: { requirements: [...] }
        - Rich billing spec: { project: {...}, llms: {...}, agents: {...} }
        - Legacy: { meta: {...}, requirements: [...], tech_stack: {...} }
        """
        # --- Service Pipeline v2 early-return branch ---
        # When use_service_pipeline=True and the path is a structured spec directory
        # (has architecture/ and api/ subdirs), delegate to ServiceOrchestrator.
        if self.use_service_pipeline:
            spec_path = Path(requirements_file)
            if spec_path.is_dir() and (spec_path / "architecture").is_dir() and (spec_path / "api").is_dir():
                from src.engine.spec_parser import SpecParser
                from src.engine.service_orchestrator import ServiceOrchestrator
                self.logger.info("service_pipeline_delegating", path=str(spec_path))
                parsed_spec = SpecParser(spec_path).parse()
                orchestrator = ServiceOrchestrator(parsed_spec, self.output_dir)
                await orchestrator.run_all()
                return PipelineResult(success=True, job_id=job_id)
        # --- End Service Pipeline v2 branch ---

        # Use SpecAdapter for universal format support
        spec_adapter = SpecAdapter()
        normalized_spec = spec_adapter.load(requirements_file)

        self.logger.info(
            "spec_normalized",
            format_detected=self._detect_format_type(normalized_spec),
            requirements_count=len(normalized_spec.requirements),
            has_api_specs=len(normalized_spec.context_layers.api_specs) > 0,
            has_llm_config=bool(normalized_spec.context_layers.llm_config),
            has_workflows=len(normalized_spec.context_layers.workflows) > 0,
        )

        # Store normalized spec and context provider for agent access
        self.normalized_spec = normalized_spec

        # Check if this is a documentation format project for rich context
        self.doc_spec = None
        if spec_adapter.last_format == SpecFormat.DOCUMENTATION:
            # Use RichContextProvider for documentation format (353 diagrams, 50 entities, etc.)
            from src.engine.documentation_loader import DocumentationLoader
            from src.engine.rich_context_provider import RichContextProvider

            loader = DocumentationLoader()
            self.doc_spec = loader.load(Path(requirements_file))
            self.context_provider = RichContextProvider(self.doc_spec)

            self.logger.info(
                "rich_context_provider_activated",
                diagrams_count=len(self.doc_spec.diagrams),
                entities_count=len(self.doc_spec.entities),
                epics_count=len(self.doc_spec.epics),
                has_design_tokens=bool(self.doc_spec.design_tokens.colors),
            )

            # ===== NEW: Create AgentContextBridge for RAG integration =====
            from src.engine.agent_context_bridge import AgentContextBridge

            # Try to load FungusContextAgent for RAG support (optional, enhances context)
            fungus_agent = None
            if self.enable_fungus and self.event_bus:
                try:
                    from src.agents.fungus_context_agent import FungusContextAgent
                    from src.mind.shared_state import SharedState
                    # Create temporary shared_state for fungus agent if needed
                    temp_shared_state = SharedState()
                    fungus_agent = FungusContextAgent(
                        name="FungusContext",
                        event_bus=self.event_bus,
                        shared_state=temp_shared_state,
                        working_dir=str(self.output_dir),
                    )
                    self.logger.info("fungus_agent_loaded_for_rag")
                except Exception as e:
                    self.logger.debug("fungus_agent_not_available", error=str(e))

            self.context_bridge = AgentContextBridge(
                context_provider=self.context_provider,
                fungus_agent=fungus_agent,
                enable_rag=self.enable_fungus,
            )
            self.logger.info(
                "agent_context_bridge_created",
                rag_enabled=self.enable_fungus,
                has_fungus=fungus_agent is not None,
            )
        else:
            # Use generic ContextProvider for other formats
            self.context_provider = ContextProvider(normalized_spec)
            self.context_bridge = None  # No bridge for simple formats

        # Convert to simple format for backward-compatible DAGParser
        simple_format = normalized_spec.to_simple_format()
        requirements_json = json.dumps(simple_format)

        return await self.execute(requirements_json, job_id)

    def _detect_format_type(self, spec: NormalizedSpec) -> str:
        """Detect format type from normalized spec."""
        if spec.context_layers.has_content():
            return "rich"
        return "simple"

    async def execute(
        self,
        requirements_json: str,
        job_id: int = 1,
    ) -> PipelineResult:
        """
        Execute the complete hybrid pipeline.

        Args:
            requirements_json: JSON string with requirements
            job_id: Job ID for tracking

        Returns:
            PipelineResult with execution summary
        """
        import time
        start_time = time.time()

        progress = PipelineProgress(
            job_id=job_id,
            phase="starting",
            start_time=datetime.now(),
            max_iterations=self.max_iterations,
        )
        self._report_progress(progress)

        try:
            # ===== PHASE -1: LOAD RUNTIME REPORTS (Feedback Loop) =====
            self.logger.info("loading_runtime_reports", job_id=job_id)
            self.runtime_reports = self.report_manager.load_all()
            if self.runtime_reports.report_files_processed:
                self.logger.info(
                    "runtime_reports_available",
                    files_loaded=len(self.runtime_reports.report_files_processed),
                    arch_score=self.runtime_reports.architecture.overall_score,
                    has_architecture_issues=self.runtime_reports.has_architecture_issues(),
                    high_risk_test_files=len(self.runtime_reports.tests.high_risk_files),
                )

            # Parse requirements
            self.logger.info("parsing_requirements", job_id=job_id)
            data = json.loads(requirements_json)
            req_data = self.parser.parse(data)

            # ===== PHASE 0: PROJECT ANALYSIS =====
            self.logger.info("=" * 60)
            self.logger.info(
                "[STAGE] Project Analysis",
                phase=0,
                requirements=len(req_data.requirements),
            )
            self.logger.info("=" * 60)
            progress.phase = "analyzing"
            self._report_progress(progress)
            analyzer = ProjectAnalyzer()
            profile = analyzer.analyze(req_data)

            self.logger.info(
                "project_analyzed",
                project_type=profile.project_type.value,
                technologies=[t.value for t in profile.technologies],
                domains=[d.value for d in profile.domains],
                agent_types=profile.get_agent_types(),
                validators=profile.get_validators(),
            )

            # Create slices - use domain strategy for potential parallel analysis
            self.logger.info("creating_slices", job_id=job_id)
            use_domain_slicing = (
                self.enable_parallel_analysis and
                len(req_data.requirements) > self.PARALLEL_THRESHOLD
            )
            # Use tech_stack strategy if tech_stack is available
            if self.tech_stack:
                slice_strategy = "tech_stack"
            elif use_domain_slicing:
                slice_strategy = "domain"
            else:
                slice_strategy = "hybrid"
            
            manifest = self.slicer.slice_requirements(
                req_data, job_id, strategy=slice_strategy, tech_stack=self.tech_stack
            )
            
            progress.parallel_chunks = len(manifest.slices)

            # ===== PHASE 1: ARCHITECT (parallel or sequential) =====
            # Check for cached contracts first (fast resume - skip Phase 1)
            from src.engine.checkpoint_manager import CheckpointManager
            checkpoint_manager = CheckpointManager(self.output_dir)
            cached_contracts = None

            # Create checkpoint early so contracts_cached flag can be set
            if self.enable_checkpoints and not checkpoint_manager.exists():
                checkpoint = checkpoint_manager.create(
                    job_id=f"gen_{job_id}_{len(manifest.slices)}",
                    total_batches=len(manifest.slices),
                    total_iterations=3,
                )
                await checkpoint_manager.save(checkpoint)
                self.logger.debug("early_checkpoint_created", job_id=checkpoint.job_id)

            if self.enable_checkpoints and checkpoint_manager.contracts_cache_exists():
                self.logger.info("checking_contracts_cache")
                cached_contracts = await checkpoint_manager.load_contracts()

            if cached_contracts:
                # Skip Phase 1 entirely - use cached contracts
                self.logger.info("=" * 60)
                self.logger.info(
                    "[STAGE] Architect - Using Cached Contracts (SKIPPED)",
                    phase=1,
                    types=len(cached_contracts.types),
                    endpoints=len(cached_contracts.endpoints),
                    components=len(cached_contracts.components),
                    services=len(cached_contracts.services),
                )
                self.logger.info("=" * 60)
                contracts = cached_contracts
                progress.phase = "architect_cached"
                progress.current_phase = 1
                self._report_progress(progress)
            else:
                # Generate contracts normally
                self.logger.info("=" * 60)
                self.logger.info(
                    "[STAGE] Architect - Contract Generation",
                    phase=1,
                    parallel=use_domain_slicing,
                    chunks=len(manifest.slices),
                )
                self.logger.info("=" * 60)
                progress.phase = "architect"
                progress.current_phase = 1
                self._report_progress(progress)

                # Runtime import to avoid circular dependency
                from src.agents.architect_agent import ArchitectAgent
                from src.agents.coordinator_agent import CoordinatorAgent

                # Phase 4: Log rich context availability
                if self.context_provider:
                    arch_ctx = self.context_provider.for_architect()
                    self.logger.info(
                        "rich_context_available",
                        api_endpoints=len(arch_ctx.get("api_endpoints", [])),
                        has_db_schema=bool(arch_ctx.get("db_schema")),
                        has_frontend_specs=bool(arch_ctx.get("frontend_specs")),
                    )

                architect = ArchitectAgent(
                    working_dir=str(self.output_dir),
                    max_parallel_chunks=self.max_concurrent,
                    context_provider=self.context_provider,  # Phase 4: Rich context
                )

                # Use parallel analysis for large projects
                if use_domain_slicing and len(manifest.slices) > 1:
                    contracts, chunk_results = await architect.analyze_parallel(
                        chunks=manifest.slices,
                        req_data=req_data,
                        project_name=f"Job-{job_id}",
                        tech_stack=self.tech_stack,
                    )

                    progress.phase_progress = 25.0  # Reset progress for next phase segment
                    progress.phase = "generating"
                    progress.current_phase = 2

                    successful_chunks = sum(1 for r in chunk_results if r.success)
                    self.logger.info(
                        "parallel_analysis_complete",
                        chunks_total=len(chunk_results),
                        chunks_successful=successful_chunks,
                    )
                else:
                    contracts = await architect.analyze(
                        req_data,
                        project_name=f"Job-{job_id}",
                        tech_stack=self.tech_stack,
                    )

                self.logger.info(
                    "[OK] STAGE COMPLETE: Contracts Generated",
                    types=len(contracts.types),
                    endpoints=len(contracts.endpoints),
                    components=len(contracts.components),
                    services=len(contracts.services),
                )

                # Cache contracts for fast resume (skip Phase 1 next time)
                if self.enable_checkpoints:
                    try:
                        await checkpoint_manager.save_contracts(contracts)
                        self.logger.info("contracts_saved_to_cache")
                    except Exception as e:
                        self.logger.warning("contracts_cache_save_failed", error=str(e))

            # ===== PUBLISH CONTRACTS_GENERATED EVENT =====
            # This triggers the backend agent chain: Database -> API -> Auth -> Infra
            if self.event_bus:
                # Extract entities from types (types with 'id' field are likely database entities)
                entities = [
                    t.to_dict() for t in contracts.types
                    if self._is_entity_type(t)
                ]

                # Extract relations between entities
                relations = self._extract_relations(contracts.types)

                await self.event_bus.publish(Event(
                    type=EventType.CONTRACTS_GENERATED,
                    source="hybrid_pipeline",
                    data={
                        "contracts_path": str(self.output_dir / f"job_{job_id}" / "contracts.json"),
                        "types": len(contracts.types),
                        "endpoints": len(contracts.endpoints),
                        "components": len(contracts.components),
                        "services": len(contracts.services),
                        "project_name": contracts.project_name,
                        "job_id": job_id,
                        # Include full contract data for DatabaseAgent
                        "entities": entities,
                        "interfaces": [t.to_dict() for t in contracts.types],
                        "relations": relations,
                        "api_endpoints": [e.to_dict() for e in contracts.endpoints],
                    }
                ))
                self.logger.info(
                    "contracts_generated_event_published",
                    job_id=job_id,
                    entities_count=len(entities),
                    relations_count=len(relations),
                )

            # ===== PHASE 1.1: STORE CONTRACTS IN SUPERMEMORY =====
            # Upload contracts to Supermemory for parallel batch context
            if self.memory.enabled:
                self.logger.info("storing_contracts_to_supermemory", job_id=job_id)
                try:
                    memory_result = await self.memory.store_contracts(
                        contracts_json=contracts.to_json(),
                        job_id=job_id,
                        project_name=contracts.project_name,
                    )
                    if memory_result.success:
                        self.logger.info(
                            "contracts_stored_in_supermemory",
                            memory_id=memory_result.memory_id,
                            status=memory_result.status,
                        )
                    else:
                        self.logger.warning(
                            "supermemory_store_failed",
                            error=memory_result.error,
                        )
                except Exception as e:
                    self.logger.warning("supermemory_store_exception", error=str(e))
            else:
                self.logger.debug("supermemory_not_available_skipping_upload")

            # ===== PHASE 1.5: PLANNING =====
            self.logger.info("=" * 60)
            self.logger.info(
                "[STAGE] Planning - Execution Strategy",
                phase="1.5",
                intelligent_chunking=self.enable_intelligent_chunking,
            )
            self.logger.info("=" * 60)
            progress.phase = "planning"
            self._report_progress(progress)

            # Use intelligent chunking if enabled
            chunk_execution_plan = None
            if self.enable_intelligent_chunking:
                self.logger.info(
                    "using_intelligent_chunking",
                    max_concurrent=self.max_concurrent,
                )
                from src.agents.chunk_planner_agent import ChunkPlannerAgent, ChunkPlannerConfig

                chunk_config = ChunkPlannerConfig(
                    max_concurrent=self.max_concurrent,
                    enable_llm_analysis=self.llm_client is not None,
                )
                chunk_planner = ChunkPlannerAgent(
                    config=chunk_config,
                    llm_client=self.llm_client,
                )

                # Get requirements list for chunk planning
                requirements_list = [
                    {
                        "id": req.get("id") or req.get("req_id", f"req_{i}"),
                        "name": req.get("name") or req.get("label", ""),
                        "description": req.get("description") or req.get("title", ""),
                        "priority": req.get("priority", "medium"),
                    }
                    for i, req in enumerate(req_data.requirements)
                ]

                chunk_execution_plan = await chunk_planner.create_execution_plan(
                    requirements=requirements_list,
                    tech_stack=self.tech_stack.to_dict() if self.tech_stack and hasattr(self.tech_stack, 'to_dict') else None,
                )

                self.logger.info(
                    "intelligent_chunking_complete",
                    total_chunks=chunk_execution_plan.total_chunks,
                    total_waves=chunk_execution_plan.total_waves,
                    total_estimated_minutes=chunk_execution_plan.total_estimated_minutes,
                    parallelization_factor=f"{chunk_execution_plan.parallelization_factor:.1f}x",
                    service_groups=[g.service_name for g in chunk_execution_plan.service_groups],
                )

                # Print execution plan summary (handle encoding for Windows console)
                try:
                    summary = chunk_execution_plan.print_summary()
                    print(summary.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
                except (UnicodeEncodeError, UnicodeDecodeError):
                    self.logger.info("execution_plan_summary_printed", chunks=chunk_execution_plan.total_chunks)

            # Publish execution plan to dashboard via EventBus
            if self.event_bus and chunk_execution_plan:
                await self.event_bus.publish(Event(
                    type=EventType.TASK_PROGRESS_UPDATE,
                    source="hybrid_pipeline",
                    data={
                        "type": "plan_created",
                        "plan": chunk_execution_plan.to_dict(),
                        "progress": chunk_execution_plan.get_progress(),
                    },
                ))

            # Standard planning (fallback or if intelligent chunking disabled)
            planner = PlanningEngine(batch_size=self.max_concurrent)
            execution_plan = planner.create_plan(
                manifest,
                force_sequential=False,  # Enable parallel execution within batches
                batch_size=self.max_concurrent,
            )

            self.logger.info(
                "execution_plan_created",
                total_batches=execution_plan.total_batches,
                sequential_only=execution_plan.sequential_only,
                parallel_within_batch=execution_plan.parallel_within_batch,
                estimated_time_ms=sum(b.estimated_time_ms for b in execution_plan.batches),
                intelligent_chunking=self.enable_intelligent_chunking,
            )

            # ===== PHASE 2-5: ITERATIVE GENERATION =====
            self.logger.info("=" * 60)
            self.logger.info(
                "[STAGE] Code Generation - Iterative Execution",
                phase="2-5",
                max_iterations=self.max_iterations,
                max_concurrent=self.max_concurrent,
            )
            self.logger.info("=" * 60)
            progress.phase = "generating"
            progress.current_phase = 2
            self._report_progress(progress)

            # Import coordinator (may have been imported in Phase 1, import again if cached)
            from src.agents.coordinator_agent import CoordinatorAgent

            coordinator = CoordinatorAgent(
                working_dir=str(self.output_dir),
                max_concurrent=self.max_concurrent,
                max_iterations=self.max_iterations,
                progress_callback=self._create_coordinator_callback(progress),
                tech_stack=self.tech_stack,
                # Rate limit recovery options (Task 8)
                enable_checkpoints=self.enable_checkpoints,
                rate_limit_wait_hours=self.rate_limit_wait_hours,
                rate_limit_interval_minutes=self.rate_limit_interval_minutes,
                rate_limit_max_retries=self.rate_limit_max_retries,
                # Fungus/Redis context integration - pass job_id for stream keys
                job_id=job_id,
                # Phase 4: Rich context from SpecAdapter
                context_provider=self.context_provider,
                # NEW: AgentContextBridge for RAG-enhanced context
                context_bridge=self.context_bridge,
                # Phase 6: Runtime reports for architecture feedback
                runtime_reports=self.runtime_reports,
                # Task visibility: pass event_bus for batch progress events
                event_bus=self.event_bus,
            )

            # Start FungusWorker for async parallel context discovery
            if self.enable_fungus:
                await self._start_fungus_worker(job_id, contracts)

            try:
                coord_result = await coordinator.execute(contracts, manifest, execution_plan)
            finally:
                # Stop FungusWorker after generation
                if self.enable_fungus and self._fungus_worker:
                    await self._stop_fungus_worker()

            progress.files_generated = coord_result.files_generated
            progress.tests_passed = coord_result.tests_passed
            progress.tests_failed = coord_result.tests_failed
            progress.iteration = coord_result.iterations

            # ===== PHASE 4: VALIDATION =====
            self.logger.info("=" * 60)
            self.logger.info(
                "[STAGE] Validation - Type Checking & Linting",
                phase=4,
                files_generated=coord_result.files_generated,
                tests_passed=coord_result.tests_passed,
            )
            self.logger.info("=" * 60)
            progress.phase = "validating"
            progress.current_phase = 4
            self._report_progress(progress)
            validation_result, validation_fixes = await self._run_validation_phase(
                str(self.output_dir),
                progress,
                profile=profile,
            )

            progress.validation_errors = validation_result.error_count
            progress.validation_warnings = validation_result.warning_count

            # ===== PHASE 4.5: RUNTIME TESTING =====
            runtime_result = None
            if validation_result.passed:
                self.logger.info("=" * 60)
                self.logger.info(
                    "[STAGE] Runtime Testing - Docker Sandbox",
                    phase="4.5",
                    validation_passed=True,
                )
                self.logger.info("=" * 60)
                progress.phase = "runtime_testing"
                self._report_progress(progress)
                runtime_result = await self._run_runtime_tests(
                    str(self.output_dir),
                    progress,
                )

                if runtime_result:
                    self.logger.info(
                        "runtime_tests_complete",
                        success=runtime_result.success,
                        errors=runtime_result.console_errors,
                        warnings=runtime_result.console_warnings,
                        failed_requests=runtime_result.network_errors,
                        fixes_applied=runtime_result.fixes_successful,
                    )
            else:
                self.logger.info("skipping_runtime_tests_validation_failed")

            # ===== PHASE 4.6: RECOVER DISABLED FILES =====
            self.logger.info("=" * 60)
            self.logger.info(
                "[STAGE] Recovering Disabled Files",
                phase="4.6",
            )
            self.logger.info("=" * 60)
            disabled_recovered = await self._recover_disabled_files()
            if disabled_recovered > 0:
                self.logger.info(
                    "disabled_files_recovered",
                    count=disabled_recovered,
                )

            # ===== PHASE 5: WRITE OUTPUT =====
            self.logger.info("=" * 60)
            self.logger.info(
                "[STAGE] Writing Output - Final Assembly",
                phase=5,
            )
            self.logger.info("=" * 60)
            progress.phase = "writing"
            progress.current_phase = 5
            self._report_progress(progress)
            await self._write_output(job_id, contracts, validation_result, profile, runtime_result)

            # ===== COMPLETE =====
            progress.phase = "complete"
            progress.end_time = datetime.now()
            self._report_progress(progress)

            execution_time = int((time.time() - start_time) * 1000)
            execution_time_s = execution_time / 1000

            self.logger.info("=" * 60)
            self.logger.info(
                "[OK] PIPELINE COMPLETE",
                job_id=job_id,
                success=coord_result.success,
                files_generated=coord_result.files_generated,
                tests_passed=coord_result.tests_passed,
                tests_failed=coord_result.tests_failed,
                validation_errors=validation_result.error_count,
                duration_seconds=f"{execution_time_s:.1f}s",
            )
            self.logger.info("=" * 60)

            # ===== PUBLISH GENERATION_COMPLETE EVENT =====
            # Triggers post-generation agents: InfrastructureAgent, SecurityScannerAgent, etc.
            if self.event_bus:
                await self.event_bus.publish(Event(
                    type=EventType.GENERATION_COMPLETE,
                    source="hybrid_pipeline",
                    data={
                        "job_id": job_id,
                        "files_generated": coord_result.files_generated,
                        "tests_passed": coord_result.tests_passed,
                        "success": coord_result.success,
                        "contracts_path": str(self.output_dir / f"job_{job_id}" / "contracts.json"),
                    },
                ))
                self.logger.info(
                    "generation_complete_event_published",
                    job_id=job_id,
                    files=coord_result.files_generated,
                )

            # Determine success
            overall_success = (
                coord_result.success and 
                validation_result.passed and
                (runtime_result is None or runtime_result.success)
            )

            # ===== CLEANUP: Delete processed runtime reports =====
            if self.runtime_reports and self.runtime_reports.report_files_processed:
                deleted = self.report_manager.cleanup(keep_consolidated=True)
                self.logger.info("runtime_reports_cleaned_up", files_deleted=deleted)

            return PipelineResult(
                success=overall_success,
                job_id=job_id,
                files_generated=coord_result.files_generated,
                tests_passed=coord_result.tests_passed,
                tests_failed=coord_result.tests_failed,
                validation_errors=validation_result.error_count,
                validation_warnings=validation_result.warning_count,
                validation_fixes_applied=len(validation_fixes),
                runtime_errors=runtime_result.console_errors if runtime_result else 0,
                runtime_warnings=runtime_result.console_warnings if runtime_result else 0,
                runtime_failed_requests=runtime_result.network_errors if runtime_result else 0,
                runtime_fixes_applied=runtime_result.fixes_successful if runtime_result else 0,
                iterations=coord_result.iterations,
                contracts=contracts,
                validation_result=validation_result,
                execution_time_ms=execution_time,
                errors=coord_result.errors,
            )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.logger.error("pipeline_failed", job_id=job_id, error=str(e))
            print(f"\n=== FULL TRACEBACK ===\n{tb}\n======================\n")
            progress.phase = "failed"
            progress.error = str(e)
            progress.end_time = datetime.now()
            self._report_progress(progress)

            # Cleanup runtime reports even on failure
            if self.runtime_reports and self.runtime_reports.report_files_processed:
                try:
                    self.report_manager.cleanup(keep_consolidated=True)
                except Exception:
                    pass  # Ignore cleanup errors on failure

            return PipelineResult(
                success=False,
                job_id=job_id,
                execution_time_ms=int((time.time() - start_time) * 1000),
                errors=[str(e)],
            )

    async def execute_parallel_batches(
        self,
        manifest: SliceManifest,
        contracts: InterfaceContracts,
        req_data: RequirementsData,
        progress: PipelineProgress,
    ) -> dict:
        """
        Execute parallel batches of slices.
        
        This method orchestrates parallel execution of slice batches,
        respecting dependencies between batches.
        
        Args:
            manifest: SliceManifest with all slices
            contracts: Interface contracts for context
            req_data: Requirements data
            progress: Progress tracker
            
        Returns:
            Dict with execution results per batch
        """
        from src.tools.claude_code_tool import ClaudeCodeTool
        
        # Get parallel batches from slicer
        batches = self.slicer.get_parallel_batches(manifest)
        
        self.logger.info(
            "executing_parallel_batches",
            total_batches=len(batches),
            total_slices=len(manifest.slices),
        )
        
        claude_tool = ClaudeCodeTool(
            working_dir=str(self.output_dir),
            max_concurrent=self.max_concurrent,
        )
        
        batch_results = {}
        
        for batch_idx, batch in enumerate(batches):
            self.logger.info(
                "executing_batch",
                batch_index=batch_idx,
                slices_in_batch=len(batch),
            )
            
            progress.phase = f"batch_{batch_idx + 1}_of_{len(batches)}"
            progress.phase_progress = (batch_idx / len(batches)) * 100
            self._report_progress(progress)
            
            # Build prompts for this batch
            prompts = []
            for slice_obj in batch:
                # Get requirements for this slice
                slice_reqs = [
                    req for req in req_data.requirements
                    if (req.get("id") or req.get("req_id")) in slice_obj.requirements
                ]
                
                prompt = self._build_slice_prompt(
                    slice_obj,
                    slice_reqs,
                    contracts,
                )
                
                prompts.append((
                    slice_obj.slice_id,
                    prompt,
                    contracts.to_json(),
                    slice_obj.agent_type,
                ))
            
            # Execute batch in parallel
            if len(prompts) > 1:
                results = await claude_tool.execute_batch(prompts)
            else:
                # Single slice - execute directly
                if prompts:
                    id_, prompt, ctx, agent_type = prompts[0]
                    result = await claude_tool.execute(prompt, ctx, agent_type)
                    results = {id_: result}
                else:
                    results = {}
            
            batch_results[f"batch_{batch_idx}"] = {
                "slice_count": len(batch),
                "results": {
                    id_: {
                        "success": r.success,
                        "files": len(r.files),
                        "time_ms": r.execution_time_ms,
                    }
                    for id_, r in results.items()
                }
            }
            
            self.logger.info(
                "batch_complete",
                batch_index=batch_idx,
                slices_processed=len(results),
            )
        
        return batch_results

    def _build_slice_prompt(
        self,
        slice_obj,
        slice_reqs: list[dict],
        contracts: InterfaceContracts,
    ) -> str:
        """Build a prompt for a single slice."""
        req_list = "\n".join([
            f"- [{req.get('id') or req.get('req_id', '')}] {req.get('label', req.get('title', req.get('description', '')))}"
            for req in slice_reqs[:20]
        ])
        
        return f"""Implement the following requirements for the {slice_obj.agent_type} domain:

## Requirements
{req_list}

## Contracts Available
- Types: {len(contracts.types)}
- Endpoints: {len(contracts.endpoints)}
- Components: {len(contracts.components)}

Generate complete, production-ready code for these requirements.
"""

    def _create_coordinator_callback(
        self,
        progress: PipelineProgress,
    ) -> Callable[[str, int, int], None]:
        """Create a callback for the coordinator to report progress."""
        def callback(phase: str, iteration: int, max_iter: int):
            progress.phase = phase
            progress.iteration = iteration
            progress.phase_progress = (iteration / max_iter) * 100
            self._report_progress(progress)

        return callback

    async def _start_fungus_worker(
        self,
        job_id: int,
        contracts: InterfaceContracts,
    ) -> None:
        """
        Start FungusWorker for async parallel context discovery.

        The worker runs MCMP simulation in the background, publishing
        context updates to Redis streams for consumption by Claude CLI.
        """
        try:
            from src.services.fungus_worker import FungusWorker, JudgeMode

            # Create query from contracts summary
            type_names = [t.name for t in contracts.types[:10]]
            endpoint_paths = [e.path for e in contracts.endpoints[:5]]
            query = f"Code for types: {', '.join(type_names)}. APIs: {', '.join(endpoint_paths)}"

            self._fungus_worker = FungusWorker(
                redis_url=self.redis_url,
                job_id=str(job_id),
                working_dir=str(self.output_dir),
                max_rounds=3,
                min_confidence=0.6,
            )

            # Index project files
            indexed = await self._fungus_worker.index_project()
            self.logger.info("fungus_worker_indexed", documents=indexed)

            # Start background simulation
            await self._fungus_worker.start_background(query, mode=JudgeMode.STEERING)
            self.logger.info("fungus_worker_started", job_id=job_id)

        except ImportError as e:
            self.logger.warning("fungus_worker_import_failed", error=str(e))
            self._fungus_worker = None
        except Exception as e:
            self.logger.warning("fungus_worker_start_failed", error=str(e))
            self._fungus_worker = None

    async def _stop_fungus_worker(self) -> None:
        """Stop FungusWorker and clean up resources."""
        if not self._fungus_worker:
            return

        try:
            context = await self._fungus_worker.stop()
            self.logger.info(
                "fungus_worker_stopped",
                rounds=context.get("fungus_context", {}).get("simulation_steps", 0),
            )
            await self._fungus_worker.close()
        except Exception as e:
            self.logger.warning("fungus_worker_stop_failed", error=str(e))
        finally:
            self._fungus_worker = None

    async def _run_validation_phase(
        self,
        project_dir: str,
        progress: PipelineProgress,
        profile: Optional[ProjectProfile] = None,
    ) -> tuple[ValidationResult, list]:
        """
        Run project validation and attempt to fix failures.

        Args:
            project_dir: Path to the generated project
            progress: Progress tracker
            profile: Optional ProjectProfile for dynamic validator selection

        Returns:
            Tuple of (ValidationResult, list of fixes applied)
        """
        from src.validators.base_validator import ValidationSeverity

        fixes_applied = []

        # Run initial validation with profile-based validator selection
        self.logger.info(
            "running_validation",
            project_dir=project_dir,
            validators=profile.get_validators() if profile else "auto-discover",
        )
        validator_tool = ProjectValidatorTool(project_dir, profile=profile)
        validation_result = await validator_tool.validate()

        self.logger.info(
            "validation_initial_result",
            passed=validation_result.passed,
            errors=validation_result.error_count,
            warnings=validation_result.warning_count,
            checks_run=validation_result.checks_run,
        )

        # If validation passed, we're done
        if validation_result.passed:
            return validation_result, fixes_applied

        # Attempt to fix validation failures
        progress.phase = "fixing_validation"
        self._report_progress(progress)

        self.logger.info(
            "attempting_validation_fixes",
            failure_count=len(validation_result.failures),
        )

        # Runtime import to avoid circular dependency
        from src.agents.validation_recovery_agent import ValidationRecoveryAgent
        recovery_agent = ValidationRecoveryAgent(project_dir, memory_tool=self.memory)
        error_failures = [
            f for f in validation_result.failures
            if f.severity == ValidationSeverity.ERROR
        ]

        if error_failures:
            fixes = await recovery_agent.fix_multiple(error_failures)
            fixes_applied.extend(fixes)

            successful_fixes = [f for f in fixes if f.success]
            self.logger.info(
                "validation_fixes_applied",
                attempted=len(fixes),
                successful=len(successful_fixes),
            )

            # Re-run validation after fixes
            if successful_fixes:
                self.logger.info("rerunning_validation_after_fixes")
                validation_result = await validator_tool.validate()

                self.logger.info(
                    "validation_final_result",
                    passed=validation_result.passed,
                    errors=validation_result.error_count,
                    warnings=validation_result.warning_count,
                )

        return validation_result, fixes_applied

    async def _run_runtime_tests(
        self,
        project_dir: str,
        progress: PipelineProgress,
    ):
        """
        Run runtime tests (Dev Server + Browser Console Capture).

        Args:
            project_dir: Path to the generated project
            progress: Progress tracker

        Returns:
            RuntimeResult or None if runtime testing not available
        """
        DeployTestTeam, TeamResult = _get_deploy_test_team()

        if not DeployTestTeam:
            RuntimeTestAgent, RuntimeResult = _get_runtime_test_agent()

            if not RuntimeTestAgent:
                self.logger.warning("runtime_test_agent_not_available")
                return None

            try:
                agent = RuntimeTestAgent(
                    working_dir=project_dir,
                    port=3000,
                    max_fix_iterations=self.max_iterations,  # Use pipeline setting instead of hardcoded 3
                    server_timeout=60.0,
                    browser="chrome",
                )

                result = await agent.run_tests()
                return result

            except Exception as e:
                self.logger.error("runtime_tests_failed", error=str(e))
                return None

        agent = DeployTestTeam(
            working_dir=project_dir,
            browser="chrome",
        )
        return await agent.run()

    async def _write_output(
        self,
        job_id: int,
        contracts: InterfaceContracts,
        validation_result: Optional[ValidationResult] = None,
        profile: Optional[ProjectProfile] = None,
        runtime_result = None,
    ):
        """Write output files and metadata."""
        job_dir = self.output_dir / f"job_{job_id}"
        job_dir.mkdir(exist_ok=True)

        # Write contracts
        contracts_path = job_dir / "contracts.json"
        with open(contracts_path, "w", encoding="utf-8") as f:
            f.write(contracts.to_json())

        # Write manifest with validation info, project profile, and runtime results
        manifest_path = job_dir / "manifest.json"
        manifest_data = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "project_name": contracts.project_name,
            "project_profile": {
                "project_type": profile.project_type.value,
                "technologies": [t.value for t in profile.technologies],
                "platforms": profile.platforms,
                "domains": [d.value for d in profile.domains],
                "complexity": profile.complexity,
                "primary_language": profile.primary_language,
                "has_backend": profile.has_backend,
                "has_frontend": profile.has_frontend,
                "has_database": profile.has_database,
                "agent_types": profile.get_agent_types(),
                "validators": profile.get_validators(),
            } if profile else None,
            "contracts": {
                "types": len(contracts.types),
                "endpoints": len(contracts.endpoints),
                "components": len(contracts.components),
                "services": len(contracts.services),
            },
            "validation": {
                "passed": validation_result.passed if validation_result else None,
                "errors": validation_result.error_count if validation_result else 0,
                "warnings": validation_result.warning_count if validation_result else 0,
                "checks_run": validation_result.checks_run if validation_result else [],
                "checks_passed": validation_result.checks_passed if validation_result else [],
            } if validation_result else None,
            "runtime": runtime_result.to_dict() if runtime_result else None,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # Write validation report if there are failures
        if validation_result and validation_result.failures:
            validation_path = job_dir / "validation_report.json"
            with open(validation_path, "w", encoding="utf-8") as f:
                json.dump(validation_result.to_dict(), f, indent=2)

        # Write runtime report if there are errors
        if runtime_result and (runtime_result.console_errors > 0 or runtime_result.network_errors > 0):
            runtime_path = job_dir / "runtime_report.json"
            with open(runtime_path, "w", encoding="utf-8") as f:
                json.dump(runtime_result.to_dict(), f, indent=2)

        self.logger.debug("output_written", job_dir=str(job_dir))

    # =========================================================================
    # Phase 4.6: Recover Disabled Files
    # =========================================================================

    async def _recover_disabled_files(self) -> int:
        """
        Find and attempt to fix .disabled files.

        When Claude Code creates "simplified versions" of files due to TypeScript
        errors, the original full version is renamed to .disabled. This phase:
        1. Finds all .disabled files
        2. Attempts to restore and fix them
        3. Falls back to simplified version if fix fails

        Returns:
            Number of files successfully recovered
        """
        import subprocess
        import os

        disabled_files = list(self.output_dir.rglob("*.disabled"))

        if not disabled_files:
            self.logger.info("no_disabled_files_found")
            return 0

        self.logger.info(
            "disabled_files_found",
            count=len(disabled_files),
            files=[str(f.name) for f in disabled_files[:10]],
        )

        recovered_count = 0
        attempted_files = set()  # Track to avoid infinite loops

        for disabled_path in disabled_files:
            if str(disabled_path) in attempted_files:
                continue
            attempted_files.add(str(disabled_path))

            # Get original path (remove .disabled suffix)
            original_path = disabled_path.with_suffix("")
            if original_path.suffix == "":
                # Handle cases like file.ts.disabled -> file.ts
                original_path = Path(str(disabled_path).replace(".disabled", ""))

            self.logger.info(
                "attempting_disabled_recovery",
                disabled=str(disabled_path.name),
                original=str(original_path.name),
            )

            try:
                # Read disabled content
                disabled_content = disabled_path.read_text(encoding="utf-8")

                # Backup current simplified version if it exists
                simplified_backup = None
                if original_path.exists():
                    simplified_backup = original_path.read_text(encoding="utf-8")
                    original_path.rename(original_path.with_suffix(original_path.suffix + ".simplified"))

                # Restore disabled as original
                disabled_path.rename(original_path)

                # Run TypeScript check
                tsc_valid = await self._check_typescript_file(original_path)

                if tsc_valid:
                    self.logger.info("disabled_file_restored", file=str(original_path.name))
                    recovered_count += 1
                    # Remove simplified backup
                    simplified_path = original_path.with_suffix(original_path.suffix + ".simplified")
                    if simplified_path.exists():
                        simplified_path.unlink()
                else:
                    # Attempt fix with Claude
                    self.logger.info("attempting_fix_disabled", file=str(original_path.name))
                    fixed = await self._fix_disabled_file(original_path, disabled_content)

                    if fixed:
                        self.logger.info("disabled_file_fixed", file=str(original_path.name))
                        recovered_count += 1
                        # Remove simplified backup
                        simplified_path = original_path.with_suffix(original_path.suffix + ".simplified")
                        if simplified_path.exists():
                            simplified_path.unlink()
                    else:
                        # Restore simplified version
                        self.logger.warning(
                            "fix_failed_keeping_simplified",
                            file=str(original_path.name),
                        )
                        original_path.rename(disabled_path)  # Back to .disabled
                        simplified_path = original_path.with_suffix(original_path.suffix + ".simplified")
                        if simplified_path.exists():
                            simplified_path.rename(original_path)

            except Exception as e:
                self.logger.error(
                    "disabled_recovery_error",
                    file=str(disabled_path.name),
                    error=str(e),
                )

        self.logger.info(
            "disabled_recovery_complete",
            attempted=len(disabled_files),
            recovered=recovered_count,
        )
        return recovered_count

    async def _check_typescript_file(self, file_path: Path) -> bool:
        """
        Check if a TypeScript file compiles without errors.

        Args:
            file_path: Path to the TypeScript file

        Returns:
            True if file is valid, False if there are errors
        """
        import subprocess
        import os

        try:
            # Use tsc to check the file
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["npx", "tsc", "--noEmit", str(file_path)],
                    cwd=str(self.output_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    shell=(os.name == 'nt'),
                )
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.debug("tsc_check_failed", error=str(e))
            return False

    async def _fix_disabled_file(self, file_path: Path, content: str) -> bool:
        """
        Attempt to fix a disabled file using Claude.

        Args:
            file_path: Path to the file to fix
            content: Current content of the file

        Returns:
            True if fix succeeded, False otherwise
        """
        import subprocess
        import os

        try:
            # Get TypeScript errors
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["npx", "tsc", "--noEmit", str(file_path)],
                    cwd=str(self.output_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    shell=(os.name == 'nt'),
                )
            )
            error_output = result.stderr if result.stderr else result.stdout

            # Use Claude to fix
            from src.tools.claude_code_tool import ClaudeCodeTool

            tool = ClaudeCodeTool(
                working_dir=str(self.output_dir),
                timeout=180,
            )

            fix_prompt = f"""Fix the TypeScript errors in this file.

## File: {file_path.name}

## TypeScript Errors:
```
{error_output[:3000]}
```

## Current Content:
```typescript
{content[:8000]}
```

## Instructions:
1. Fix ALL TypeScript errors listed above
2. Keep the FULL functionality - do NOT simplify or remove features
3. Ensure types match the Prisma schema
4. Make sure all imports are correct
5. Write the COMPLETE fixed file

IMPORTANT: Do NOT create a "simplified version". Fix the actual errors while preserving all functionality.
"""

            fix_result = await tool.execute(
                prompt=fix_prompt,
                context="Fixing disabled file TypeScript errors",
                agent_type="fixing",
            )

            if fix_result.success:
                # Recheck TypeScript
                recheck = await self._check_typescript_file(file_path)
                return recheck
            else:
                return False

        except Exception as e:
            self.logger.error("fix_disabled_error", error=str(e))
            return False

    # =========================================================================
    # Phase 3: Parallel Code + Test Generation Per Chunk
    # =========================================================================

    async def _generate_tests_for_chunk(
        self,
        chunk,  # RequirementChunk
        contracts: InterfaceContracts,
        project_dir: Path,
    ):
        """
        Generate tests for chunk requirements (parallel with code gen).

        This method generates tests FROM THE SAME REQUIREMENTS as code generation,
        not from the generated code. This enables parallel execution.

        Args:
            chunk: RequirementChunk with requirements to test
            contracts: Interface contracts for context
            project_dir: Path to project directory

        Returns:
            GenerationResult with test files
        """
        import time
        from src.tools.claude_code_tool import ClaudeCodeTool

        start_time = time.time()

        # Build test generation prompt
        req_list = "\n".join([
            f"- {req_id}" for req_id in chunk.requirements[:20]
        ])

        prompt = f"""Generate comprehensive tests for these requirements:

## Requirements
{req_list}

## Contracts Context
- Types: {len(contracts.types)}
- Endpoints: {len(contracts.endpoints)}
- Services: {len(contracts.services)}

## Available Type Definitions
{json.dumps([t.to_dict() for t in contracts.types[:10]], indent=2)}

## Available Endpoints
{json.dumps([e.to_dict() for e in contracts.endpoints[:10]], indent=2)}

## CRITICAL RULES - NO MOCKS POLICY

1. **NO MOCKING ALLOWED** - All tests must be real integration tests
2. Test actual endpoints/functions, not mocked implementations
3. Use real database connections (SQLite for testing is acceptable)
4. Use real HTTP calls to actual endpoints
5. Each requirement must have at least one test
6. Tests must verify actual behavior, not implementation details

## FORBIDDEN PATTERNS (will cause validation failure)
- unittest.mock, Mock(), MagicMock(), AsyncMock()
- @patch, with patch()
- jest.mock(), vi.mock()
- sinon.stub(), sinon.mock()
- Any mocking of HTTP clients, databases, or services

## REQUIRED APPROACH
- Use real test database (SQLite in-memory or test containers)
- Make actual HTTP requests to test API endpoints
- Test real file I/O operations
- Use fixtures that create real data, not mock data

Generate pytest tests for Python or vitest tests for TypeScript.
"""

        claude_tool = ClaudeCodeTool(
            working_dir=str(project_dir),
            max_concurrent=1,  # Single chunk
        )

        result = await claude_tool.execute(
            prompt=prompt,
            context=contracts.to_json(),
            agent_type="testing",
        )

        result.execution_time_ms = int((time.time() - start_time) * 1000)
        return result

    async def execute_chunk_with_tests(
        self,
        chunk,  # RequirementChunk
        contracts: InterfaceContracts,
        project_dir: Path,
    ):
        """
        Execute chunk with parallel code + test generation.

        Both code and tests are generated from the SAME requirements
        simultaneously, then tests are run to validate.

        Args:
            chunk: RequirementChunk to execute
            contracts: Interface contracts for context
            project_dir: Path to project directory

        Returns:
            ChunkResult with code and test generation results
        """
        import time
        from src.engine.execution_plan import ChunkResult
        from src.validators.no_mock_validator import NoMockValidator
        from src.tools.claude_code_tool import ClaudeCodeTool

        start_time = time.time()

        self.logger.info(
            "executing_chunk_with_tests",
            chunk_id=chunk.chunk_id,
            requirements=chunk.requirements,
            service_group=chunk.service_group,
        )

        # Build code generation prompt
        req_list = "\n".join([
            f"- {req_id}" for req_id in chunk.requirements[:20]
        ])

        code_prompt = f"""Implement the following requirements:

## Requirements
{req_list}

## Service Group: {chunk.service_group}

## Contracts Context
{json.dumps({
    "types": [t.to_dict() for t in contracts.types[:15]],
    "endpoints": [e.to_dict() for e in contracts.endpoints[:15]],
    "services": [s.to_dict() for s in contracts.services[:10]],
}, indent=2)}

Generate complete, production-ready code for these requirements.
"""

        claude_tool = ClaudeCodeTool(
            working_dir=str(project_dir),
            max_concurrent=1,
        )

        # 1. Generate code AND tests in parallel (same input!)
        code_task = claude_tool.execute(
            prompt=code_prompt,
            context=contracts.to_json(),
            agent_type=chunk.service_group or "backend",
        )
        test_task = self._generate_tests_for_chunk(chunk, contracts, project_dir)

        code_result, test_result = await asyncio.gather(code_task, test_task)

        code_gen_time = code_result.execution_time_ms
        test_gen_time = test_result.execution_time_ms

        # 2. Validate tests for mock usage (NO MOCKS policy)
        mock_violations = []
        test_files = [Path(f) for f in test_result.files if f]

        if test_files:
            validator = NoMockValidator(str(project_dir), strict_mode=True)
            mock_passed, mock_violations = await validator.validate_test_files_quick(test_files)

            if not mock_passed:
                self.logger.warning(
                    "mock_violations_found",
                    chunk_id=chunk.chunk_id,
                    violations=mock_violations,
                )

        # 3. Run tests against generated code
        validation_start = time.time()
        tests_passed = 0
        tests_failed = 0
        validation_errors = []

        if test_files and not mock_violations:
            try:
                test_runner = TestRunnerTool(str(project_dir))
                test_result_run = await test_runner.run_tests(
                    test_files=[str(f) for f in test_files],
                    timeout=120,
                )
                tests_passed = test_result_run.get("passed", 0)
                tests_failed = test_result_run.get("failed", 0)
                validation_errors = test_result_run.get("errors", [])
            except Exception as e:
                self.logger.error(
                    "test_run_failed",
                    chunk_id=chunk.chunk_id,
                    error=str(e),
                )
                validation_errors.append(str(e))
                tests_failed = len(test_files)

        validation_time = int((time.time() - validation_start) * 1000)
        total_time = int((time.time() - start_time) * 1000)

        # Build result
        result = ChunkResult(
            chunk_id=chunk.chunk_id,
            requirements=chunk.requirements,
            code_files=[f for f in code_result.files if f],
            code_success=code_result.success,
            test_files=[str(f) for f in test_files],
            test_success=test_result.success and not mock_violations,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            validation_errors=validation_errors,
            mock_violations=mock_violations,
            ready_for_merge=(
                code_result.success
                and test_result.success
                and tests_failed == 0
                and len(mock_violations) == 0
            ),
            code_gen_time_ms=code_gen_time,
            test_gen_time_ms=test_gen_time,
            validation_time_ms=validation_time,
            total_time_ms=total_time,
        )

        self.logger.info(
            "chunk_execution_complete",
            chunk_id=chunk.chunk_id,
            code_success=result.code_success,
            test_success=result.test_success,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            mock_violations=len(mock_violations),
            ready_for_merge=result.ready_for_merge,
            total_time_ms=total_time,
        )

        return result

    async def _execute_wave_with_tests(
        self,
        wave,  # Wave
        chunks: list,  # list[RequirementChunk]
        contracts: InterfaceContracts,
        project_dir: Path,
    ) -> list:
        """
        Execute all chunks in wave with parallel code+test generation.

        All chunks in the wave execute concurrently. Each chunk
        generates code and tests in parallel internally.

        Args:
            wave: Wave object with chunk IDs
            chunks: List of all chunks
            contracts: Interface contracts
            project_dir: Project directory

        Returns:
            List of ChunkResult for each chunk in wave
        """
        from src.engine.execution_plan import ChunkResult

        wave_chunks = [c for c in chunks if c.chunk_id in wave.chunks]

        self.logger.info(
            "executing_wave_with_tests",
            wave_id=wave.wave_id,
            chunk_count=len(wave_chunks),
            chunk_ids=[c.chunk_id for c in wave_chunks],
        )

        # All chunks in wave execute in parallel
        # Each chunk generates code+tests in parallel internally
        tasks = [
            self.execute_chunk_with_tests(chunk, contracts, project_dir)
            for chunk in wave_chunks
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(
                    "chunk_execution_error",
                    chunk_id=wave_chunks[i].chunk_id,
                    error=str(result),
                )
                # Create failed result
                final_results.append(ChunkResult(
                    chunk_id=wave_chunks[i].chunk_id,
                    requirements=wave_chunks[i].requirements,
                    code_success=False,
                    test_success=False,
                    validation_errors=[str(result)],
                    ready_for_merge=False,
                ))
            else:
                final_results.append(result)

        # Log wave summary
        passed = sum(1 for r in final_results if r.ready_for_merge)
        failed = len(final_results) - passed

        self.logger.info(
            "wave_execution_complete",
            wave_id=wave.wave_id,
            chunks_passed=passed,
            chunks_failed=failed,
            total_tests_passed=sum(r.tests_passed for r in final_results),
            total_tests_failed=sum(r.tests_failed for r in final_results),
            total_mock_violations=sum(len(r.mock_violations) for r in final_results),
        )

        return final_results

    def _report_progress(self, progress: PipelineProgress):
        """Report progress via callback if available."""
        if self.progress_callback:
            self.progress_callback(progress)

    def _is_entity_type(self, type_def) -> bool:
        """
        Detect if a TypeDefinition should be a database entity.

        Heuristics:
        1. Has an 'id' field (primary key indicator)
        2. Name ends with common entity suffixes
        3. Has timestamp fields (createdAt, updatedAt)
        """
        # Check for id field
        fields = type_def.fields if isinstance(type_def.fields, dict) else {}
        field_names = [f.lower() for f in fields.keys()]

        if "id" in field_names:
            return True

        # Check for timestamp fields (common in database entities)
        timestamp_indicators = ["createdat", "updatedat", "timestamp", "created_at", "updated_at"]
        if any(ts in field_names for ts in timestamp_indicators):
            return True

        # Check name patterns (common entity suffixes)
        entity_patterns = [
            "Transport", "Route", "Position", "User", "Order", "Item",
            "Product", "Customer", "Invoice", "Payment", "Document",
            "Event", "Log", "Record", "Entry", "Entity"
        ]
        name = type_def.name if hasattr(type_def, 'name') else ""
        if any(name.endswith(p) or name == p for p in entity_patterns):
            return True

        return False

    def _extract_relations(self, types: list) -> list:
        """
        Extract relationships between entity types.

        Detects foreign key patterns like userId, orderId, etc.
        Returns a list of relation dicts: {from, to, type, field}
        """
        relations = []
        type_names = {t.name for t in types if hasattr(t, 'name')}

        for t in types:
            if not hasattr(t, 'fields'):
                continue

            fields = t.fields if isinstance(t.fields, dict) else {}
            for field_name, field_type in fields.items():
                # Detect foreign key patterns: userId, orderId, transportId, etc.
                if field_name.endswith("Id") and len(field_name) > 2:
                    # Extract the related entity name
                    related = field_name[:-2]  # Remove "Id"
                    related_capitalized = related[0].upper() + related[1:] if related else ""

                    # Check if the related type exists
                    if related_capitalized in type_names:
                        relations.append({
                            "from": t.name,
                            "to": related_capitalized,
                            "type": "many-to-one",
                            "field": field_name,
                        })

                # Also check for array fields that might indicate one-to-many
                if isinstance(field_type, str):
                    # Pattern: type[] or Array<type>
                    if field_type.endswith("[]"):
                        related_type = field_type[:-2]
                        if related_type in type_names:
                            relations.append({
                                "from": t.name,
                                "to": related_type,
                                "type": "one-to-many",
                                "field": field_name,
                            })

        return relations


async def run_hybrid_pipeline(
    requirements_file: str,
    output_dir: str = "./output",
    job_id: int = 1,
    max_concurrent: int = 10,
    max_iterations: int = 3,
) -> PipelineResult:
    """
    Convenience function to run the hybrid pipeline.

    Args:
        requirements_file: Path to requirements JSON
        output_dir: Output directory
        job_id: Job ID
        max_concurrent: Max parallel executions
        max_iterations: Max recovery iterations

    Returns:
        PipelineResult
    """
    pipeline = HybridPipeline(
        output_dir=output_dir,
        max_concurrent=max_concurrent,
        max_iterations=max_iterations,
    )

    return await pipeline.execute_from_file(requirements_file, job_id)


# CLI entry point
async def main():
    """CLI entry point for the hybrid pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the hybrid coding engine pipeline"
    )
    parser.add_argument(
        "requirements_file",
        help="Path to requirements JSON file",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        default=1,
        help="Job ID for tracking",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent CLI calls",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum recovery iterations",
    )
    parser.add_argument(
        "--slice-size",
        type=int,
        default=10,
        help="Requirements per slice",
    )
    parser.add_argument(
        "--intelligent-chunking",
        action="store_true",
        help="Enable LLM-based intelligent chunk planning for optimal parallelization",
    )

    args = parser.parse_args()

    def print_progress(progress: PipelineProgress):
        print(
            f"[{progress.phase}] "
            f"Phase {progress.current_phase}/{progress.total_phases} | "
            f"Iteration {progress.iteration}/{progress.max_iterations} | "
            f"Files: {progress.files_generated}"
        )

    pipeline = HybridPipeline(
        output_dir=args.output_dir,
        max_concurrent=args.max_concurrent,
        max_iterations=args.max_iterations,
        slice_size=args.slice_size,
        progress_callback=print_progress,
        enable_intelligent_chunking=args.intelligent_chunking,
    )

    result = await pipeline.execute_from_file(
        args.requirements_file,
        args.job_id,
    )

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Success: {result.success}")
    print(f"  Files Generated: {result.files_generated}")
    print(f"  Tests Passed: {result.tests_passed}")
    print(f"  Tests Failed: {result.tests_failed}")
    print(f"  Validation Errors: {result.validation_errors}")
    print(f"  Validation Warnings: {result.validation_warnings}")
    print(f"  Validation Fixes Applied: {result.validation_fixes_applied}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Time: {result.execution_time_ms}ms")

    if result.errors:
        print("\n  Errors:")
        for error in result.errors[:5]:
            print(f"    - {error}")

    if result.validation_result and result.validation_result.failures:
        print("\n  Validation Failures:")
        for failure in result.validation_result.failures[:5]:
            print(f"    - [{failure.check_type}] {failure.error_message[:80]}")

    return result


if __name__ == "__main__":
    asyncio.run(main())
