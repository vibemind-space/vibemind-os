"""
Integration Bridge - Connects HybridPipeline with Society of Mind.

Provides utilities to:
1. Run initial code generation via HybridPipeline
2. Hand off to Society of Mind for continuous iteration
3. Convert pipeline results to Society events
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any
import structlog
from .convergence import ConvergenceCriteria, DEFAULT_CRITERIA
from .shared_state import SharedState, ConvergenceMetrics
from .orchestrator import Orchestrator
from .event_bus import EventBus
from .live_preview import LivePreviewSystem
from src.llm_config import get_model
# Note: GeneratorAgent imported lazily to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.engine.tech_stack import TechStack

logger = structlog.get_logger(__name__)


@dataclass
class HybridSocietyConfig:
    """Configuration for the hybrid Society of Mind runner."""
    # Input
    requirements_path: str
    output_dir: str

    # Pipeline settings
    max_concurrent: int = 5  # Increased for large projects (was 2)
    slice_size: int = 30
    initial_iterations: int = 3  # Multiple passes for iterative fixes (was 1)

    # Convergence settings
    criteria: ConvergenceCriteria = None  # Uses DEFAULT_CRITERIA if None

    # Society settings
    enable_live_preview: bool = True
    preview_port: int = 5173
    open_browser: bool = True  # Auto-open browser when preview is ready
    enable_websocket: bool = True
    session_id: Optional[str] = None

    # Dashboard settings
    enable_dashboard: bool = False  # Enable real-time dashboard
    dashboard_port: int = 8080  # HTTP port for dashboard
    dashboard_ws_port: int = 8765  # WebSocket port for dashboard

    # Callbacks
    progress_callback: Optional[Callable[[ConvergenceMetrics, float], None]] = None

    # Async Services: E2E Testing and UX Review (run continuously parallel to Phase 3)
    enable_async_e2e: bool = False  # Continuous async E2E testing
    enable_async_ux: bool = False  # Continuous async UX review
    async_e2e_interval: int = 60  # Seconds between async E2E test cycles
    async_ux_interval: int = 120  # Seconds between async UX review cycles
    requirements_list: Optional[list[str]] = None  # For E2E/UX agents

    # LLM-based Verification (Multi-Agent Debate for Phase 4)
    enable_llm_verification: bool = False  # Enable Multi-Agent Debate verification
    verification_debate_rounds: int = 3  # Number of debate rounds

    # Documentation generation
    enable_auto_docs: bool = True  # Auto-generate CLAUDE.md

    # Deployment Team: Sandbox and Cloud Testing
    enable_sandbox_testing: bool = False  # Enable Docker sandbox testing
    enable_cloud_tests: bool = False  # Enable GitHub Actions testing

    # VNC Screen Streaming
    enable_vnc_streaming: bool = False  # Enable VNC for Electron apps in sandbox
    vnc_port: int = 6080  # noVNC web port (access at http://localhost:6080/vnc.html)

    # Preview Health Monitor
    enable_preview_monitor: bool = True  # Monitor preview health every 30s
    preview_monitor_interval: float = 30.0  # Seconds between health checks

    # Continuous Sandbox Testing
    enable_continuous_sandbox: bool = False  # Enable continuous 30-second test cycle
    sandbox_cycle_interval: int = 30  # Seconds between sandbox test cycles
    start_sandbox_immediately: bool = True  # Start sandbox loop immediately (before code ready)

    # Continuous Debug (NEW) - Real-time debugging during generation
    # Auto-enabled when enable_continuous_sandbox=True (sandbox errors need debug agent)
    enable_continuous_debug: bool = True  # Enable real-time debug with Claude Code
    debug_cycle_interval: int = 5  # Seconds between debug cycles
    max_debug_iterations: int = 10  # Max fix attempts per error group

    # Tech Stack Configuration
    tech_stack: Optional[Any] = None  # TechStack instance
    tech_stack_path: Optional[str] = None  # Path to tech_stack.json file

    # ValidationTeam Configuration (NEW)
    enable_validation_team: bool = False  # Enable test generation + debug engine
    validation_test_framework: str = "vitest"  # "vitest", "jest", "pytest"
    validation_use_docker: bool = True  # Use Docker for port isolation
    validation_docker_network: str = "validation-net"
    validation_frontend_port: int = 3100
    validation_backend_port: int = 8100
    validation_max_debug_iterations: int = 3
    validation_timeout_seconds: int = 300
    enable_shell_stream: bool = True  # Enable visible shell for user feedback
    on_shell_output: Optional[Callable] = None  # Shell output callback

    # Persistent Deployment Configuration
    enable_persistent_deploy: bool = False  # Deploy to VNC container on convergence
    persistent_vnc_port: int = 6080  # VNC port for persistent deployment
    inject_collected_secrets: bool = True  # Inject secrets from os.environ

    # Claude Monitor Configuration (NEW)
    enable_claude_monitor: bool = False  # Enable AI-powered error analysis
    monitor_api_key: Optional[str] = None  # Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
    monitor_suggestions_file: str = "improvement_suggestions.md"  # Output file for suggestions

    # Intelligent Chunking Configuration (Phase 2)
    enable_intelligent_chunking: bool = False  # LLM-based service grouping and load balancing

    # Task 24: Backend Agent Feature Flags
    enable_database_generation: bool = True  # DatabaseAgent - auto database schema generation
    enable_api_generation: bool = True  # APIAgent - auto API route generation
    enable_auth_setup: bool = True  # AuthAgent - auto authentication setup
    enable_infrastructure_setup: bool = True  # InfrastructureAgent - auto env/docker/CI config

    # Fungus Context System (la_fungus_search integration)
    enable_fungus: bool = False  # Enable semantic code context via la_fungus_search
    fungus_num_agents: int = 200  # Number of MCMP agents for simulation
    fungus_max_iterations: int = 50  # Max iterations for MCMP simulation
    fungus_judge_provider: str = "openrouter"  # LLM provider for judge (openrouter, ollama, etc.)
    fungus_judge_model: str = field(default_factory=lambda: get_model("judge"))  # Model for Judge LLM
    # Phase 11: Advanced Fungus parameters for completeness checking
    fungus_top_k: int = 20  # Number of top results per query
    fungus_steering_every: int = 3  # LLM steering frequency (every N rounds)
    fungus_exploration_bonus: float = 0.15  # Exploration bonus for less visited paths
    fungus_restart_every: int = 10  # Restart simulation every N steps
    fungus_judge_every: int = 3  # Judge evaluation frequency (every N rounds)
    fungus_min_confidence: float = 0.6  # Minimum confidence threshold for results

    # Design Pipeline Configuration
    execution_plan: Optional[dict] = None  # ExecutionPlan from Design Pipeline

    # Rate Limit Recovery (Task 8) - Auto-resume after rate limit
    enable_checkpoints: bool = True  # Enable checkpoint saving for rate limit recovery
    rate_limit_wait_hours: float = 4.0  # Hours to wait after rate limit hit
    rate_limit_interval_minutes: float = 30.0  # Minutes between retries after initial wait
    rate_limit_max_retries: int = 10  # Maximum retry attempts before giving up

    # Phase 10: VotingAI Configuration
    voting_enabled: bool = True  # Enable voting for fix selection
    voting_method: str = "qualified_majority"  # majority|qualified_majority|ranked_choice|unanimous|weighted_majority
    voting_qualified_threshold: float = 0.67  # 2/3 for qualified majority

    # Phase 10: A/B Generation Configuration
    ab_generation_enabled: bool = False  # Enable parallel A/B solution generation
    ab_num_solutions: int = 2  # Number of solutions to generate (2-5)
    ab_require_build_pass: bool = True  # Only consider solutions that build

    # Phase 10: Verification Debate Configuration
    enable_llm_verification: bool = False  # Enable VerificationDebateAgent
    verification_debate_rounds: int = 3  # Number of debate rounds

    def __post_init__(self):
        if self.criteria is None:
            self.criteria = DEFAULT_CRITERIA


@dataclass
class HybridSocietyResult:
    """Result from running the hybrid Society of Mind."""
    success: bool
    converged: bool

    # Pipeline phase
    initial_generation_success: bool = False
    files_generated: int = 0

    # Society phase
    iterations: int = 0
    final_metrics: Optional[ConvergenceMetrics] = None
    preview_url: Optional[str] = None

    # Sandbox testing results
    sandbox_cycles_completed: int = 0
    sandbox_last_success: bool = False
    vnc_url: Optional[str] = None

    # ValidationTeam results (NEW)
    validation_tests_passed: int = 0
    validation_tests_failed: int = 0
    validation_pass_rate: float = 0.0
    validation_fixes_applied: int = 0

    # Timing
    pipeline_duration_seconds: float = 0
    society_duration_seconds: float = 0
    total_duration_seconds: float = 0

    # Errors
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "converged": self.converged,
            "initial_generation_success": self.initial_generation_success,
            "files_generated": self.files_generated,
            "iterations": self.iterations,
            "preview_url": self.preview_url,
            "vnc_url": self.vnc_url,
            "sandbox_cycles_completed": self.sandbox_cycles_completed,
            "sandbox_last_success": self.sandbox_last_success,
            # Validation results
            "validation_tests_passed": self.validation_tests_passed,
            "validation_tests_failed": self.validation_tests_failed,
            "validation_pass_rate": self.validation_pass_rate,
            "validation_fixes_applied": self.validation_fixes_applied,
            # Timing
            "pipeline_duration_seconds": self.pipeline_duration_seconds,
            "society_duration_seconds": self.society_duration_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "errors": self.errors,
            "metrics": self.final_metrics.to_dict() if self.final_metrics else None,
        }


class HybridSocietyRunner:
    """
    Unified runner that combines HybridPipeline and Society of Mind.

    Flow:
    1. Run HybridPipeline for initial code generation (minimal iterations)
    2. Start Society of Mind agents for continuous iteration
    3. Monitor convergence and provide live preview
    """

    def __init__(self, config: HybridSocietyConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)

        # Initialize memory tool
        from ..tools.memory_tool import MemoryTool
        self.memory_tool = MemoryTool(enabled=True)

        # Core components (initialized on run)
        self.event_bus: Optional[EventBus] = None
        self.shared_state: Optional[SharedState] = None
        self.orchestrator: Optional[Orchestrator] = None
        self.live_preview: Optional[LivePreviewSystem] = None
        self.dashboard: Optional[Any] = None  # DashboardServer, lazy imported
        self.generator_agent: Optional[Any] = None  # GeneratorAgent, lazy imported
        self.claude_monitor: Optional[Any] = None  # ClaudeMonitor, lazy imported
        self.preview_monitor: Optional[Any] = None  # PreviewHealthMonitor, lazy imported
        self.browser_error_detector: Optional[Any] = None  # BrowserErrorDetector, lazy imported

        self.logger = logger.bind(component="hybrid_society_runner")

    async def run(self) -> HybridSocietyResult:
        """
        Execute the hybrid Society of Mind pipeline.

        Returns:
            HybridSocietyResult with final state
        """
        import time
        from datetime import datetime

        start_time = datetime.now()
        errors = []

        self.logger.info(
            "starting_hybrid_society",
            requirements=self.config.requirements_path,
            output_dir=str(self.output_dir),
            continuous_sandbox=self.config.enable_continuous_sandbox,
        )

        result = HybridSocietyResult(
            success=False,
            converged=False,
        )

        try:
            # Task 23: Create EventBus BEFORE initial generation so CONTRACTS_GENERATED
            # event can be published and trigger the backend agent chain
            self.event_bus = EventBus()
            self.logger.debug("event_bus_created_for_pipeline")

            # Start live preview early (during code generation, not after)
            # This allows user to watch code appear in real-time
            early_preview_url = None
            if self.config.enable_live_preview:
                early_preview_url = await self._start_early_preview()
                if early_preview_url:
                    result.preview_url = early_preview_url

            # Start preview health monitor early
            if self.config.enable_preview_monitor and self.live_preview:
                try:
                    from ..monitoring.preview_monitor import PreviewHealthMonitor
                    self.preview_monitor = PreviewHealthMonitor(
                        event_bus=self.event_bus,
                        port=self.config.preview_port,
                        check_interval=self.config.preview_monitor_interval,
                        working_dir=str(self.output_dir),
                    )
                    await self.preview_monitor.start()
                    self.logger.info(
                        "early_preview_monitor_started",
                        port=self.config.preview_port,
                        interval=self.config.preview_monitor_interval,
                    )
                except ImportError as e:
                    self.logger.warning("preview_monitor_import_failed", error=str(e))
                except Exception as e:
                    self.logger.warning("early_preview_monitor_failed", error=str(e))

            # Start dependency manager early (handles missing deps during code gen)
            # This allows auto-install of missing modules when dev server crashes
            self.early_dependency_agent = None
            if self.config.enable_live_preview:
                try:
                    from ..agents.dependency_manager_agent import DependencyManagerAgent
                    self.early_dependency_agent = DependencyManagerAgent(
                        name="EarlyDependencyManager",
                        event_bus=self.event_bus,
                        shared_state=None,  # Not needed for basic dep checks
                        working_dir=str(self.output_dir),
                        auto_update_patch=True,
                        auto_update_minor=False,
                        check_licenses=False,  # Skip license checks during gen
                    )
                    # Start listening for events
                    asyncio.create_task(self.early_dependency_agent.start())
                    self.logger.info("early_dependency_agent_started")
                except ImportError as e:
                    self.logger.warning("dependency_agent_import_failed", error=str(e))
                except Exception as e:
                    self.logger.warning("early_dependency_agent_failed", error=str(e))

            # Start bug fixer agent early (handles code-level errors during code gen)
            # This allows auto-fix of missing exports, import paths, etc.
            # ALWAYS start this agent, regardless of preview setting, to catch errors immediately
            self.early_bug_fixer_agent = None
            try:
                from ..agents.bug_fixer_agent import BugFixerAgent
                self.early_bug_fixer_agent = BugFixerAgent(
                    name="EarlyBugFixer",
                    event_bus=self.event_bus,
                    shared_state=None,  # Not needed for early startup
                    working_dir=str(self.output_dir),
                )
                # Start listening for events
                asyncio.create_task(self.early_bug_fixer_agent.start())
                self.logger.info("early_bug_fixer_agent_started")
            except ImportError as e:
                self.logger.warning("bug_fixer_agent_import_failed", error=str(e))
            except Exception as e:
                self.logger.warning("early_bug_fixer_agent_failed", error=str(e))

            # Start database schema agent (auto-runs prisma generate, alembic, drizzle, etc.)
            # Detects database tool from project files and runs appropriate commands
            self.database_schema_agent = None
            if self.config.enable_live_preview:
                try:
                    from ..agents.database_schema_agent import DatabaseSchemaAgent
                    self.database_schema_agent = DatabaseSchemaAgent(
                        name="DatabaseSchemaAgent",
                        event_bus=self.event_bus,
                        working_dir=str(self.output_dir),
                        auto_migrate=False,  # Safe mode: generate only, no db push
                    )
                    asyncio.create_task(self.database_schema_agent.start())
                    self.logger.info("database_schema_agent_started")
                except ImportError as e:
                    self.logger.warning("database_schema_agent_import_failed", error=str(e))
                except Exception as e:
                    self.logger.warning("database_schema_agent_failed", error=str(e))

            # Start database docker agent (auto-starts PostgreSQL container on database errors)
            # This agent listens for database connection errors and creates/starts Docker containers
            self.database_docker_agent = None
            try:
                from ..agents.database_docker_agent import DatabaseDockerAgent
                self.database_docker_agent = DatabaseDockerAgent(
                    name="DatabaseDocker",
                    event_bus=self.event_bus,
                    shared_state=None,
                    working_dir=str(self.output_dir),
                )
                asyncio.create_task(self.database_docker_agent.start())
                self.logger.info("database_docker_agent_started")
            except ImportError as e:
                self.logger.warning("database_docker_agent_import_failed", error=str(e))
            except Exception as e:
                self.logger.warning("database_docker_agent_failed", error=str(e))

            # Emit PROJECT_SCAFFOLDED to trigger proactive database startup
            # This allows DatabaseDockerAgent to start PostgreSQL before first build error
            from .event_bus import Event, EventType
            await self.event_bus.publish(Event(
                type=EventType.PROJECT_SCAFFOLDED,
                source="HybridSocietyRunner",
                data={
                    "output_dir": str(self.output_dir),
                    "requirements_path": self.config.requirements_path,
                },
            ))
            self.logger.info("project_scaffolded_event_emitted")

            # Start browser error detector (monitors browser console for JS errors)
            # This catches client-side errors that the dev server can't see
            self.browser_error_detector = None
            if self.config.enable_live_preview:
                try:
                    from ..monitoring.browser_error_detector import BrowserErrorDetector
                    self.browser_error_detector = BrowserErrorDetector(
                        event_bus=self.event_bus,
                        port=self.config.preview_port,
                        check_interval=2.0,  # Check every 2 seconds for faster error detection
                        working_dir=str(self.output_dir),
                    )
                    asyncio.create_task(self.browser_error_detector.start())
                    self.logger.info("browser_error_detector_started")
                except ImportError as e:
                    self.logger.warning("browser_error_detector_import_failed", error=str(e))
                except Exception as e:
                    self.logger.warning("browser_error_detector_failed", error=str(e))

            # Phase 1: Initial code generation via HybridPipeline
            pipeline_start = time.time()
            initial_success, files_generated = await self._run_initial_generation()
            result.pipeline_duration_seconds = time.time() - pipeline_start
            result.initial_generation_success = initial_success
            result.files_generated = files_generated

            if not initial_success:
                errors.append("Initial code generation failed")
                self.logger.error("initial_generation_failed")
                # Continue anyway - Society might be able to fix it

            # Phase 2: Society of Mind continuous iteration
            society_start = time.time()
            society_result = await self._run_society()
            result.society_duration_seconds = time.time() - society_start

            result.converged = society_result.get("converged", False)
            result.iterations = society_result.get("iterations", 0)
            result.final_metrics = society_result.get("metrics")
            result.preview_url = society_result.get("preview_url")
            
            # Sandbox testing results
            result.sandbox_cycles_completed = society_result.get("sandbox_cycles", 0)
            result.sandbox_last_success = society_result.get("sandbox_last_success", False)
            result.vnc_url = society_result.get("vnc_url")

            # ValidationTeam results (NEW)
            result.validation_tests_passed = society_result.get("validation_tests_passed", 0)
            result.validation_tests_failed = society_result.get("validation_tests_failed", 0)
            result.validation_pass_rate = society_result.get("validation_pass_rate", 0.0)
            result.validation_fixes_applied = society_result.get("validation_fixes_applied", 0)

            if society_result.get("errors"):
                errors.extend(society_result["errors"])

            result.success = result.converged and not errors

        except Exception as e:
            errors.append(str(e))
            self.logger.error("hybrid_society_error", error=str(e))

        finally:
            await self._cleanup()

        result.total_duration_seconds = (datetime.now() - start_time).total_seconds()
        result.errors = errors

        self.logger.info(
            "hybrid_society_complete",
            success=result.success,
            converged=result.converged,
            iterations=result.iterations,
            sandbox_cycles=result.sandbox_cycles_completed,
            duration=result.total_duration_seconds,
        )

        return result

    async def _start_early_preview(self) -> Optional[str]:
        """
        Start live preview early (before/during code generation).

        This allows users to watch code appear in real-time as batches
        complete. The preview may show errors until scaffolding completes
        and npm dependencies are installed - this is expected behavior.

        Returns:
            Preview URL or None if failed
        """
        self.logger.info("starting_early_preview")

        # Don't open browser popup when VNC streaming is enabled - user accesses via VNC instead
        should_open_browser = (
            self.config.open_browser
            and not self.config.enable_dashboard
            and not self.config.enable_vnc_streaming
            and not self.config.enable_continuous_sandbox
        )
        self.live_preview = LivePreviewSystem(
            working_dir=str(self.output_dir),
            event_bus=self.event_bus,
            port=self.config.preview_port,
            open_browser=should_open_browser,
        )

        try:
            # Don't wait for ready - scaffolding may not be complete yet
            # Vite will automatically reload once files appear
            await self.live_preview.start(wait_for_ready=False, timeout=10)
            url = f"http://localhost:{self.config.preview_port}"
            self.logger.info("early_preview_started", url=url)
            return url
        except Exception as e:
            self.logger.warning("early_preview_failed", error=str(e))
            return None

    async def _run_initial_generation(self) -> tuple[bool, int]:
        """
        Run initial code generation via HybridPipeline.

        Returns:
            Tuple of (success, files_generated)
        """
        from ..engine.hybrid_pipeline import HybridPipeline

        self.logger.info("starting_initial_generation")

        try:
            pipeline = HybridPipeline(
                output_dir=str(self.output_dir),
                max_concurrent=self.config.max_concurrent,
                max_iterations=self.config.initial_iterations,
                slice_size=self.config.slice_size,
                tech_stack=self.config.tech_stack,
                enable_intelligent_chunking=self.config.enable_intelligent_chunking,
                event_bus=self.event_bus,  # Triggers backend agent chain
                # Rate limit recovery (Task 8)
                enable_checkpoints=self.config.enable_checkpoints,
                rate_limit_wait_hours=self.config.rate_limit_wait_hours,
                rate_limit_interval_minutes=self.config.rate_limit_interval_minutes,
                rate_limit_max_retries=self.config.rate_limit_max_retries,
            )

            result = await pipeline.execute_from_file(self.config.requirements_path)

            # Store pipeline context for agent access (RichContextProvider, doc_spec, tech_stack)
            self._pipeline_context_provider = pipeline.context_provider
            self._pipeline_doc_spec = pipeline.doc_spec
            self._pipeline_tech_stack = pipeline.tech_stack

            files_generated = 0
            if result.success and self.output_dir.exists():
                # Count generated files
                for f in self.output_dir.rglob("*"):
                    if f.is_file() and not str(f).endswith(('.pyc', '.git')):
                        files_generated += 1

            self.logger.info(
                "initial_generation_complete",
                success=result.success,
                files=files_generated,
            )

            return result.success, files_generated

        except Exception as e:
            self.logger.error("initial_generation_error", error=str(e))
            return False, 0

    async def _run_society(self) -> dict:
        """
        Run Society of Mind for continuous iteration.

        Returns:
            Dict with results
        """
        self.logger.info("starting_society_phase")

        # Initialize components
        # Task 23: Reuse existing EventBus if already created (preserves CONTRACTS_GENERATED event)
        if self.event_bus is None:
            self.event_bus = EventBus()
        self.shared_state = SharedState()
        await self.shared_state.start()

        # Transfer rich context from pipeline to shared_state for agent access
        # This enables agents to access diagrams, entities, design tokens via shared_state.context_provider
        if hasattr(self, '_pipeline_context_provider') and self._pipeline_context_provider:
            self.shared_state.context_provider = self._pipeline_context_provider
            self.logger.info("rich_context_transferred_to_shared_state")
        if hasattr(self, '_pipeline_doc_spec') and self._pipeline_doc_spec:
            self.shared_state.doc_spec = self._pipeline_doc_spec
        if hasattr(self, '_pipeline_tech_stack') and self._pipeline_tech_stack:
            self.shared_state.tech_stack = self._pipeline_tech_stack

        # Create orchestrator
        self.orchestrator = Orchestrator(
            working_dir=str(self.output_dir),
            criteria=self.config.criteria,
            progress_callback=self.config.progress_callback,
            enable_auto_docs=self.config.enable_auto_docs,
            enable_sandbox_testing=self.config.enable_sandbox_testing,
            enable_cloud_tests=self.config.enable_cloud_tests,
            enable_vnc_streaming=self.config.enable_vnc_streaming,
            vnc_port=self.config.vnc_port,
            # Continuous sandbox testing parameters
            enable_continuous_sandbox=self.config.enable_continuous_sandbox,
            sandbox_cycle_interval=self.config.sandbox_cycle_interval,
            start_sandbox_immediately=self.config.start_sandbox_immediately,
            # Continuous debug parameters (NEW)
            enable_continuous_debug=self.config.enable_continuous_debug,
            debug_cycle_interval=self.config.debug_cycle_interval,
            max_debug_iterations=self.config.max_debug_iterations,
            memory_tool=self.memory_tool,
            # FIX-5: Inject event_bus and shared_state to prevent mismatch
            event_bus=self.event_bus,
            shared_state=self.shared_state,
            # FIX-26: Pass tech_stack to Orchestrator for technology-aware agents
            tech_stack=self.config.tech_stack,
            # Persistent deployment parameters
            enable_persistent_deploy=self.config.enable_persistent_deploy,
            persistent_vnc_port=self.config.persistent_vnc_port,
            inject_collected_secrets=self.config.inject_collected_secrets,
            # Task 24: Backend agent feature flags
            enable_database_generation=self.config.enable_database_generation,
            enable_api_generation=self.config.enable_api_generation,
            enable_auth_setup=self.config.enable_auth_setup,
            enable_infrastructure_setup=self.config.enable_infrastructure_setup,
            # Fungus Context System (la_fungus_search integration)
            enable_fungus=self.config.enable_fungus,
            fungus_num_agents=self.config.fungus_num_agents,
            fungus_max_iterations=self.config.fungus_max_iterations,
            fungus_judge_provider=self.config.fungus_judge_provider,
            fungus_judge_model=self.config.fungus_judge_model,
            # Phase 10: VotingAI & Verification Debate
            enable_llm_verification=self.config.enable_llm_verification,
            voting_method=self.config.voting_method,
            verification_debate_rounds=self.config.verification_debate_rounds,
        )

        # Add generator agent (lazy import to avoid circular imports)
        from ..agents.generator_agent import GeneratorAgent
        self.generator_agent = GeneratorAgent(
            name="Generator",
            event_bus=self.event_bus,
            shared_state=self.shared_state,
            working_dir=str(self.output_dir),
            memory_tool=self.memory_tool,
            document_registry=self.orchestrator.document_registry,
            tech_stack=self.config.tech_stack,
        )
        self.orchestrator.add_agent(self.generator_agent)

        # Add ValidationTeamAgent if enabled (NEW)
        validation_agent = None
        if self.config.enable_validation_team:
            try:
                from ..agents.validation_team_agent import ValidationTeamAgent
                import json
                
                # Load requirements for validation
                requirements = []
                if self.config.requirements_path:
                    try:
                        with open(self.config.requirements_path, 'r') as f:
                            data = json.load(f)
                        if isinstance(data, dict) and "requirements" in data:
                            requirements = data["requirements"]
                        elif isinstance(data, list):
                            requirements = data
                    except Exception as e:
                        self.logger.warning("requirements_load_error", error=str(e))
                
                validation_agent = ValidationTeamAgent(
                    name="ValidationTeam",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=str(self.output_dir),
                    memory_tool=self.memory_tool,
                    requirements_path=self.config.requirements_path,
                    test_framework=self.config.validation_test_framework,
                    use_docker=self.config.validation_use_docker,
                    docker_network=self.config.validation_docker_network,
                    frontend_port=self.config.validation_frontend_port,
                    backend_port=self.config.validation_backend_port,
                    max_debug_iterations=self.config.validation_max_debug_iterations,
                    timeout_seconds=self.config.validation_timeout_seconds,
                    enable_shell_stream=self.config.enable_shell_stream,
                    on_shell_output=self.config.on_shell_output,
                )
                
                # Set requirements
                if requirements:
                    validation_agent.set_requirements(requirements)
                
                self.orchestrator.add_agent(validation_agent)
                self.logger.info(
                    "validation_team_agent_added",
                    test_framework=self.config.validation_test_framework,
                    use_docker=self.config.validation_use_docker,
                )
            except ImportError as e:
                self.logger.warning("validation_team_import_failed", error=str(e))
            except Exception as e:
                self.logger.warning("validation_team_setup_failed", error=str(e))

        # Start live preview if enabled (or reuse existing early preview)
        preview_url = None
        if self.config.enable_live_preview:
            # Check if preview was already started early in run()
            if self.live_preview and hasattr(self.live_preview, 'dev_server') and self.live_preview.dev_server:
                # Reuse existing early preview
                preview_url = self.live_preview.dev_server.state.url
                self.logger.info("reusing_early_preview", url=preview_url)
            else:
                # Start fresh preview (fallback if early preview failed)
                # Don't open browser popup when VNC streaming is enabled
                should_open_browser = (
                    self.config.open_browser
                    and not self.config.enable_dashboard
                    and not self.config.enable_vnc_streaming
                    and not self.config.enable_continuous_sandbox
                )
                self.live_preview = LivePreviewSystem(
                    working_dir=str(self.output_dir),
                    event_bus=self.event_bus,
                    port=self.config.preview_port,
                    open_browser=should_open_browser,
                )
                try:
                    await self.live_preview.start(wait_for_ready=True, timeout=60)
                    preview_url = self.live_preview.dev_server.state.url
                    self.logger.info("live_preview_ready", url=preview_url)
                except Exception as e:
                    self.logger.warning("live_preview_failed", error=str(e))

        # Start preview health monitor if enabled (or reuse existing early monitor)
        if self.config.enable_preview_monitor and self.config.enable_live_preview:
            # Check if monitor was already started early in run()
            if self.preview_monitor and self.preview_monitor.is_running:
                self.logger.info("reusing_early_preview_monitor")
            else:
                # Start fresh monitor (fallback if early monitor failed)
                try:
                    from ..monitoring.preview_monitor import PreviewHealthMonitor
                    self.preview_monitor = PreviewHealthMonitor(
                        event_bus=self.event_bus,
                        port=self.config.preview_port,
                        check_interval=self.config.preview_monitor_interval,
                        working_dir=str(self.output_dir),
                    )
                    await self.preview_monitor.start()
                    self.logger.info(
                        "preview_monitor_started",
                        port=self.config.preview_port,
                        interval=self.config.preview_monitor_interval,
                    )
                except ImportError as e:
                    self.logger.warning("preview_monitor_import_failed", error=str(e))
                except Exception as e:
                    self.logger.warning("preview_monitor_start_failed", error=str(e))

        # Start dashboard if enabled
        if self.config.enable_dashboard:
            try:
                from ..dashboard import DashboardServer
                self.dashboard = DashboardServer(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    http_port=self.config.dashboard_port,
                    ws_port=self.config.dashboard_ws_port,
                    preview_port=self.config.preview_port,
                    criteria=self.config.criteria,
                )
                await self.dashboard.start(open_browser=self.config.open_browser)
                self.logger.info("dashboard_started", port=self.config.dashboard_port)
            except ImportError as e:
                self.logger.warning("dashboard_import_failed", error=str(e))
            except Exception as e:
                self.logger.warning("dashboard_start_failed", error=str(e))

        # Start Claude Monitor if enabled (NEW)
        if self.config.enable_claude_monitor:
            try:
                from ..monitoring.claude_monitor import ClaudeMonitor, create_monitor
                
                suggestions_path = str(self.output_dir / self.config.monitor_suggestions_file)
                self.claude_monitor = create_monitor(
                    output_dir=str(self.output_dir),
                    suggestions_file=suggestions_path,
                    api_key=self.config.monitor_api_key,
                )
                
                if self.claude_monitor:
                    # Register error event listeners
                    await self.claude_monitor.start(self.event_bus)
                    self.logger.info(
                        "claude_monitor_started",
                        suggestions_file=suggestions_path,
                    )
                else:
                    self.logger.warning("claude_monitor_no_api_key")
            except ImportError as e:
                self.logger.warning("claude_monitor_import_failed", error=str(e))
            except Exception as e:
                self.logger.warning("claude_monitor_start_failed", error=str(e))

        # Run orchestrator
        try:
            orch_result = await self.orchestrator.run()

            # Get sandbox stats from DeploymentTeamAgent if it exists
            sandbox_cycles = 0
            sandbox_last_success = False
            vnc_url = None
            
            # Get validation stats from ValidationTeamAgent (NEW)
            validation_tests_passed = 0
            validation_tests_failed = 0
            validation_pass_rate = 0.0
            validation_fixes_applied = 0
            
            for agent in self.orchestrator.agents:
                # Sandbox stats
                if hasattr(agent, 'get_continuous_status'):
                    status = agent.get_continuous_status()
                    sandbox_cycles = status.get('cycle_count', 0)
                    last_cycle = status.get('last_cycle')
                    if last_cycle:
                        sandbox_last_success = last_cycle.get('success', False)
                    vnc_url = status.get('vnc_url')
                
                # Validation stats (NEW)
                if hasattr(agent, 'get_last_result'):
                    result = agent.get_last_result()
                    if result and hasattr(result, 'report') and result.report:
                        validation_tests_passed = result.report.tests_passed
                        validation_tests_failed = result.report.tests_failed
                        validation_pass_rate = result.final_pass_rate
                        validation_fixes_applied = result.total_fixes_applied

            return {
                "converged": orch_result.converged,
                "iterations": orch_result.iterations,
                "metrics": orch_result.final_metrics,
                "preview_url": preview_url,
                "vnc_url": vnc_url,
                "sandbox_cycles": sandbox_cycles,
                "sandbox_last_success": sandbox_last_success,
                # Validation results (NEW)
                "validation_tests_passed": validation_tests_passed,
                "validation_tests_failed": validation_tests_failed,
                "validation_pass_rate": validation_pass_rate,
                "validation_fixes_applied": validation_fixes_applied,
                "errors": orch_result.errors,
            }

        except Exception as e:
            self.logger.error("society_run_error", error=str(e))
            return {
                "converged": False,
                "iterations": 0,
                "preview_url": preview_url,
                "errors": [str(e)],
            }

    async def _cleanup(self) -> None:
        """Clean up resources."""
        # Stop Claude Monitor first (NEW)
        if self.claude_monitor:
            try:
                await self.claude_monitor.stop()
            except Exception as e:
                self.logger.warning("claude_monitor_cleanup_error", error=str(e))

        if self.dashboard:
            try:
                await self.dashboard.stop()
            except Exception as e:
                self.logger.warning("dashboard_cleanup_error", error=str(e))

        # Stop preview monitor before live preview
        if self.preview_monitor:
            try:
                await self.preview_monitor.stop()
            except Exception as e:
                self.logger.warning("preview_monitor_cleanup_error", error=str(e))

        # Stop early dependency agent
        if hasattr(self, 'early_dependency_agent') and self.early_dependency_agent:
            try:
                await self.early_dependency_agent.stop()
            except Exception as e:
                self.logger.warning("early_dependency_agent_cleanup_error", error=str(e))

        # Stop early bug fixer agent
        if hasattr(self, 'early_bug_fixer_agent') and self.early_bug_fixer_agent:
            try:
                await self.early_bug_fixer_agent.stop()
            except Exception as e:
                self.logger.warning("early_bug_fixer_agent_cleanup_error", error=str(e))

        # Stop database schema agent
        if hasattr(self, 'database_schema_agent') and self.database_schema_agent:
            try:
                await self.database_schema_agent.stop()
            except Exception as e:
                self.logger.warning("database_schema_agent_cleanup_error", error=str(e))

        # Stop database docker agent
        if hasattr(self, 'database_docker_agent') and self.database_docker_agent:
            try:
                await self.database_docker_agent.stop()
            except Exception as e:
                self.logger.warning("database_docker_agent_cleanup_error", error=str(e))

        # Stop browser error detector
        if hasattr(self, 'browser_error_detector') and self.browser_error_detector:
            try:
                await self.browser_error_detector.stop()
            except Exception as e:
                self.logger.warning("browser_error_detector_cleanup_error", error=str(e))

        if self.live_preview:
            try:
                await self.live_preview.stop()
            except Exception as e:
                self.logger.warning("preview_cleanup_error", error=str(e))

        if self.orchestrator:
            try:
                await self.orchestrator.stop()
            except Exception as e:
                self.logger.warning("orchestrator_cleanup_error", error=str(e))

        if self.memory_tool:
            try:
                await self.memory_tool.close()
            except Exception as e:
                self.logger.warning("memory_tool_cleanup_error", error=str(e))


async def run_hybrid_society(
    requirements_path: str,
    output_dir: str,
    criteria: Optional[ConvergenceCriteria] = None,
    enable_live_preview: bool = True,
    preview_port: int = 5173,
    progress_callback: Optional[Callable] = None,
) -> HybridSocietyResult:
    """
    Convenience function to run the hybrid Society of Mind pipeline.

    Args:
        requirements_path: Path to requirements JSON file
        output_dir: Output directory for generated code
        criteria: Convergence criteria
        enable_live_preview: Enable live preview
        preview_port: Port for dev server
        progress_callback: Progress callback

    Returns:
        HybridSocietyResult

    Example:
        result = await run_hybrid_society(
            requirements_path="requirements.json",
            output_dir="./output",
            enable_live_preview=True,
        )

        if result.success:
            print(f"Converged in {result.iterations} iterations")
            print(f"Preview: {result.preview_url}")
    """
    config = HybridSocietyConfig(
        requirements_path=requirements_path,
        output_dir=output_dir,
        criteria=criteria,
        enable_live_preview=enable_live_preview,
        preview_port=preview_port,
        progress_callback=progress_callback,
    )

    runner = HybridSocietyRunner(config)
    return await runner.run()
