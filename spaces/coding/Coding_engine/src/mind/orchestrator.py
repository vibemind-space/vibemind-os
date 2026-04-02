"""
Orchestrator - The Mind that coordinates the Society of Agents.

The Orchestrator:
1. Starts all specialized agents
2. Monitors convergence metrics
3. Broadcasts state updates
4. Determines when the system is "done"
5. Handles graceful shutdown
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, TYPE_CHECKING, Any
import os
from pathlib import Path
import structlog

from .event_bus import EventBus, Event, EventType
from .shared_state import SharedState, ConvergenceMetrics
from .convergence import (
    ConvergenceCriteria,
    is_converged,
    get_progress_percentage,
    DEFAULT_CRITERIA,
)
from .agent_monitor import AgentMonitor, create_monitor
from .message_protocols import TopicType, EventTask, AgentResponse
from ..registry.document_registry import DocumentRegistry
from src.llm_config import get_model

# Lazy import SkillRegistry to avoid circular dependencies
def _get_skill_registry():
    """Lazy import SkillRegistry."""
    try:
        from ..skills.registry import SkillRegistry
        return SkillRegistry
    except ImportError:
        return None

# Lazy import to avoid circular dependency
if TYPE_CHECKING:
    from ..agents.autonomous_base import AutonomousAgent
    from ..agents.event_interpreter_agent import EventInterpreterAgent
    from ..engine.tech_stack import TechStack
    from ..skills.registry import SkillRegistry

logger = structlog.get_logger(__name__)

# Code file extensions for bootstrap scanning
CODE_EXTENSIONS = {'.ts', '.tsx', '.js', '.jsx', '.py', '.css', '.html', '.json', '.vue', '.svelte'}
IGNORE_DIRS = {'node_modules', '.git', '__pycache__', 'dist', 'build', '.next', '.venv', 'venv'}

# Task 22: Engine root for skills directory - skills are in Coding_engine/.claude/skills/
# not in the output directory (working_dir)
ENGINE_ROOT = Path(__file__).parent.parent.parent


# =============================================================================
# AGENT DEPENDENCY GRAPH - Defines execution order for push-based architecture
# =============================================================================
AGENT_DEPENDENCIES = {
    # Agent name: list of agents that must complete before this one
    "Builder": [],  # Builder runs first, no dependencies
    "Validator": ["Builder"],  # Validator waits for build
    "Tester": ["Builder"],  # Tester waits for build
    "Fixer": ["Builder", "Validator", "Tester"],  # Fixer waits for all checks
    "Generator": ["Fixer"],  # Generator can respond to fixes
    "Documentation": ["Builder", "Tester"],  # Docs after build & tests
    "TesterTeam": ["Builder"],  # E2E team after build
    "UXDesigner": ["Builder"],  # UX after build
    "DeploymentTeam": ["Builder", "Tester"],  # Deploy after build & tests
    "RuntimeDebugger": ["Builder"],  # Debug after build
    "PlaywrightE2E": ["Builder"],  # Playwright after build
    "CodeQuality": ["Builder", "Tester", "Validator"],  # Quality after all checks
    "ContinuousDebug": ["Builder"],  # Continuous debug after build
    "E2EIntegrationTeam": ["Builder", "DeploymentTeam"],  # E2E CRUD tests after deploy
    # Task 12: Backend Agent Dependencies (Database → API → Auth → Infrastructure)
    "DatabaseAgent": ["Builder"],  # Database schema after contracts/build
    "APIAgent": ["DatabaseAgent"],  # API routes need schema first
    "AuthAgent": ["APIAgent"],  # Auth middleware after API routes
    "InfrastructureAgent": ["AuthAgent"],  # Infrastructure after auth is setup
    # Task 24: Browser Console & Validation Recovery Agents
    "BrowserConsole": ["Builder"],  # Browser console monitoring after build
    "ValidationRecovery": ["Validator"],  # Validation recovery after validation
    # Continuous Feedback Loop: Fullstack Verification + Contract Refinement
    "FullstackVerifier": ["Builder", "DeploymentTeam"],  # Verifies all fullstack components
    "ContinuousArchitect": [],  # Refines contracts based on verification feedback (no deps - event-driven)
    # Database Seeding Agents
    "DatabaseSeed": ["AuthAgent"],  # Seed database after auth is set up
    "PermissionsSeed": ["AuthAgent"],  # Seed permissions after auth setup
    # Emergent System: TreeQuest Verification + ShinkaEvolve
    "TreeQuestVerification": ["Builder"],  # Verify code after build
    "ShinkaEvolve": ["Fixer"],  # Evolve code when fixers exhaust
}


# Event types that should trigger specific agents
AGENT_TRIGGERS = {
    "Builder": [EventType.FILE_CREATED, EventType.FILE_MODIFIED, EventType.CODE_FIXED],
    "Validator": [EventType.BUILD_SUCCEEDED],
    "Tester": [EventType.BUILD_SUCCEEDED],
    "Fixer": [EventType.TYPE_ERROR, EventType.TEST_FAILED, EventType.BUILD_FAILED, EventType.VALIDATION_ERROR],
    "Generator": [EventType.GENERATION_REQUESTED, EventType.CODE_FIX_NEEDED],
    "Documentation": [EventType.BUILD_SUCCEEDED, EventType.TEST_SUITE_COMPLETE],
    "RuntimeDebugger": [EventType.BUILD_SUCCEEDED, EventType.RUNTIME_TEST_FAILED],
    "DeploymentTeam": [EventType.BUILD_SUCCEEDED],
    "PlaywrightE2E": [EventType.DEPLOY_SUCCEEDED],
    "RequirementsPlaywright": [EventType.BUILD_SUCCEEDED, EventType.DEPLOY_SUCCEEDED, EventType.PREVIEW_READY],
    "CodeQuality": [EventType.BUILD_SUCCEEDED, EventType.TEST_SUITE_COMPLETE],
    # Task 16: Backend Agent Triggers (chain: Database → API → Auth → Infrastructure)
    "DatabaseAgent": [EventType.CONTRACTS_GENERATED],
    "APIAgent": [EventType.DATABASE_SCHEMA_GENERATED],
    "AuthAgent": [EventType.API_ROUTES_GENERATED],
    "InfrastructureAgent": [EventType.AUTH_SETUP_COMPLETE, EventType.GENERATION_COMPLETE, EventType.DATABASE_SCHEMA_GENERATED],
    # Phase 10: Security & Dependency Management Agents
    "SecurityScannerAgent": [EventType.BUILD_SUCCEEDED, EventType.CODE_GENERATED, EventType.GENERATION_COMPLETE],
    "DependencyManagerAgent": [EventType.PROJECT_SCAFFOLDED, EventType.DEPENDENCY_VULNERABILITY],
    "BugFixerAgent": [EventType.VALIDATION_ERROR, EventType.BROWSER_ERROR],  # Handles code-level & browser console errors
    "DatabaseDockerAgent": [EventType.VALIDATION_ERROR],  # Auto-starts PostgreSQL Docker container on database errors
    "DatabaseSchemaAgent": [EventType.FILE_CREATED, EventType.FILE_MODIFIED, EventType.GENERATION_COMPLETE, EventType.BUILD_SUCCEEDED],
    "UIIntegrationAgent": [EventType.FILE_CREATED, EventType.FILE_MODIFIED, EventType.CODE_GENERATED, EventType.CODE_FIXED, EventType.BUILD_SUCCEEDED, EventType.GENERATION_COMPLETE],
    "ContinuousE2EAgent": [EventType.PREVIEW_READY, EventType.BUILD_SUCCEEDED],
    # E2E Integration Team - CRUD Verification
    "E2EIntegrationTeam": [EventType.BUILD_SUCCEEDED, EventType.DEPLOY_SUCCEEDED, EventType.DEPENDENCY_UPDATED],
    # Phase 10.2: Performance, Accessibility, Documentation, Migration, Localization
    "PerformanceAgent": [EventType.BUILD_SUCCEEDED, EventType.E2E_TEST_PASSED, EventType.DEPLOY_SUCCEEDED],
    "AccessibilityAgent": [EventType.E2E_TEST_PASSED, EventType.SCREEN_STREAM_READY, EventType.UX_REVIEW_PASSED],
    "APIDocumentationAgent": [EventType.API_ROUTES_GENERATED, EventType.API_ENDPOINT_CREATED],
    "MigrationAgent": [EventType.DATABASE_SCHEMA_GENERATED, EventType.SCHEMA_UPDATE_NEEDED],
    "LocalizationAgent": [EventType.CONTRACTS_GENERATED, EventType.GENERATION_COMPLETE],
    # Task 24: Browser Console & Validation Recovery Agents
    "BrowserConsole": [EventType.BUILD_SUCCEEDED, EventType.PREVIEW_READY],
    "ValidationRecovery": [EventType.VALIDATION_ERROR],
    # Continuous Feedback Loop: Fullstack Verification + Contract Refinement
    "FullstackVerifier": [
        EventType.BUILD_SUCCEEDED,
        EventType.API_ROUTES_GENERATED,
        EventType.AUTH_SETUP_COMPLETE,
        EventType.DATABASE_SCHEMA_GENERATED,
        EventType.E2E_TEST_PASSED,
        EventType.E2E_TEST_FAILED,
        EventType.DEPLOY_SUCCEEDED,
        EventType.TESTS_PASSED,
        EventType.VERIFICATION_PASSED,
        EventType.CRUD_TEST_PASSED,
    ],
    "ContinuousArchitect": [
        EventType.VERIFICATION_FAILED,
        EventType.FULLSTACK_INCOMPLETE,
        EventType.E2E_TEST_FAILED,
        EventType.CONTRACTS_REFINEMENT_NEEDED,
    ],
    # Database Seeding Agents
    "DatabaseSeed": [
        EventType.AUTH_SETUP_COMPLETE,
        EventType.DATABASE_SCHEMA_GENERATED,
        EventType.BUILD_SUCCEEDED,
        EventType.DEPLOY_SUCCEEDED,
    ],
    "PermissionsSeed": [
        EventType.AUTH_SETUP_COMPLETE,
        EventType.DATABASE_SCHEMA_GENERATED,
    ],
    # Emergent System: TreeQuest Verification + ShinkaEvolve
    "TreeQuestVerification": [
        EventType.CODE_GENERATED,
        EventType.BUILD_SUCCEEDED,
        EventType.CODE_FIXED,
        EventType.VALIDATION_PASSED,
    ],
    "ShinkaEvolve": [
        EventType.ESCALATION_EXHAUSTED,
        EventType.CODE_FIX_NEEDED,
    ],
}


@dataclass
class OrchestratorResult:
    """Result from running the orchestrator."""
    success: bool
    converged: bool
    convergence_reasons: list[str] = field(default_factory=list)
    final_metrics: Optional[ConvergenceMetrics] = None
    iterations: int = 0
    duration_seconds: float = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "converged": self.converged,
            "convergence_reasons": self.convergence_reasons,
            "iterations": self.iterations,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "metrics": self.final_metrics.to_dict() if self.final_metrics else None,
        }


class Orchestrator:
    """
    The Mind - orchestrates the Society of Agents.

    Runs all agents in parallel and monitors for convergence.
    Provides real-time updates via callbacks and WebSocket.
    
    ARCHITECTURE v2.0: Push-based with Dependency Graph
    - Agents are triggered based on events, not polling
    - Dependency graph ensures correct execution order
    - Convergence check only when system is idle
    """

    def __init__(
        self,
        working_dir: str,
        criteria: Optional[ConvergenceCriteria] = None,
        progress_callback: Optional[Callable[[ConvergenceMetrics, float], None]] = None,
        enable_e2e_testing: bool = False,
        enable_ux_review: bool = False,
        enable_auto_docs: bool = True,
        enable_frontend_validation: bool = False,
        enable_runtime_debug: bool = True,
        enable_monitoring: bool = True,
        enable_sandbox_testing: bool = False,
        enable_cloud_tests: bool = False,
        enable_vnc_streaming: bool = False,
        vnc_port: int = 6080,
        # Continuous sandbox testing parameters (NEW)
        enable_continuous_sandbox: bool = False,
        sandbox_cycle_interval: int = 30,
        start_sandbox_immediately: bool = True,
        # Continuous debug parameters (NEW)
        enable_continuous_debug: bool = False,
        debug_cycle_interval: int = 5,
        max_debug_iterations: int = 10,
        requirements: Optional[list[str]] = None,
        memory_tool: Optional[Any] = None,
        # FIX-5: Allow external event_bus and shared_state injection
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        # FIX-26: TechStack parameter for technology-aware agent behavior
        tech_stack: Optional["TechStack"] = None,
        # Push architecture settings
        use_push_architecture: bool = True,
        # Persistent deployment parameters
        enable_persistent_deploy: bool = False,
        persistent_vnc_port: int = 6080,
        inject_collected_secrets: bool = True,
        # Async Services: E2E Testing and UX Review (run continuously parallel to Phase 3)
        enable_async_e2e: bool = False,
        enable_async_ux: bool = False,
        async_e2e_interval: int = 60,
        async_ux_interval: int = 120,
        # Event Interpreter (Handoffs Pattern) for intelligent event routing
        enable_event_interpreter: bool = False,
        use_llm_routing: bool = True,  # Use LLM for routing decisions (vs rule-based)
        # Task 13: Backend agent feature flags
        enable_database_generation: bool = True,
        enable_api_generation: bool = True,
        enable_auth_setup: bool = True,
        enable_infrastructure_setup: bool = True,
        # WebSocket and Redis Pub/Sub agents for real-time features
        enable_websocket_generation: bool = True,
        enable_redis_pubsub: bool = True,
        # Messaging Platform agents (Group, Presence, Encryption)
        enable_group_management: bool = True,
        enable_presence_tracking: bool = True,
        enable_encryption: bool = True,
        # Phase 10: Security & Dependency Management flags
        enable_security_scanning: bool = True,
        enable_dependency_management: bool = True,
        # Phase 10.2: Performance, Accessibility, Documentation, Migration, Localization flags
        enable_performance_analysis: bool = True,
        enable_accessibility_testing: bool = True,
        enable_api_documentation: bool = True,
        enable_migrations: bool = True,
        enable_localization: bool = True,
        # Task 24: Browser Console & Validation Recovery flags
        enable_browser_console: bool = True,
        enable_validation_recovery: bool = True,
        # Fungus Context System (la_fungus_search integration)
        enable_fungus: bool = False,
        fungus_num_agents: int = 200,
        fungus_max_iterations: int = 50,
        fungus_judge_provider: str = "openrouter",
        fungus_judge_model: str = None,
        # Phase 17: Fungus Validation (autonomous MCMP validation)
        enable_fungus_validation: bool = False,
        fungus_validation_interval: int = 10,
        # Phase 18: Fungus Memory (memory-augmented MCMP search)
        enable_fungus_memory: bool = False,
        fungus_memory_interval: int = 10,
        # Phase 20: Differential Analysis (docs vs code gap detection)
        enable_differential_analysis: bool = False,
        differential_data_dir: str = "",
        # Phase 23: Cross-Layer Validation (frontend ↔ backend consistency)
        enable_cross_layer_validation: bool = False,
        # Phase 10: VotingAI & Verification Debate
        enable_llm_verification: bool = False,
        voting_method: str = "qualified_majority",
        verification_debate_rounds: int = 3,
        # Phase 16: MCP Orchestrator with EventBus Integration
        enable_mcp_event_bridge: bool = True,
        # Container Log Seeding (automatic log capture on container events)
        enable_container_log_seeding: bool = True,
    ):
        """
        Initialize the orchestrator.

        Args:
            working_dir: Working directory for the project
            criteria: Convergence criteria (defaults to DEFAULT_CRITERIA)
            progress_callback: Called with (metrics, progress_percentage) on updates
            enable_e2e_testing: Enable E2E testing with Playwright (Phase 5)
            enable_ux_review: Enable UX design review agent (Phase 5)
            enable_auto_docs: Enable auto-generation of CLAUDE.md (default: True)
            enable_frontend_validation: Enable UI validation against requirements
            enable_runtime_debug: Enable runtime debugging agent (default: True)
            enable_monitoring: Enable real-time agent monitoring dashboard (default: True)
            enable_sandbox_testing: Enable Docker sandbox deployment testing
            enable_cloud_tests: Enable GitHub Actions cloud testing
            enable_vnc_streaming: Enable VNC streaming for Electron apps in sandbox
            vnc_port: noVNC web port (default 6080, access at http://localhost:6080/vnc.html)
            enable_continuous_sandbox: Enable continuous 30-second sandbox test cycle (NEW)
            sandbox_cycle_interval: Seconds between sandbox test cycles (default 30) (NEW)
            start_sandbox_immediately: Start sandbox loop immediately without waiting for BUILD_SUCCEEDED (NEW)
            enable_continuous_debug: Enable continuous real-time debugging (NEW)
            debug_cycle_interval: Seconds between debug cycles (NEW)
            max_debug_iterations: Maximum number of debug cycles (NEW)
            requirements: List of requirements for E2E/UX agents
            memory_tool: Optional memory tool for agents to search/store patterns
            event_bus: Optional external EventBus instance (FIX-5: prevents event bus mismatch)
            shared_state: Optional external SharedState instance (FIX-5: prevents state mismatch)
            tech_stack: Optional TechStack instance for technology-aware generation (FIX-26)
            use_push_architecture: Use push-based agent triggering (default: True)
            enable_async_e2e: Enable continuous async E2E testing (runs parallel to Phase 3)
            enable_async_ux: Enable continuous async UX review (runs parallel to Phase 3)
            async_e2e_interval: Seconds between async E2E test cycles (default: 60)
            async_ux_interval: Seconds between async UX review cycles (default: 120)
            enable_event_interpreter: Enable Event Interpreter (Handoffs Pattern) for intelligent routing
            use_llm_routing: Use LLM for routing decisions (default: True), False = rule-based only
        """
        self.working_dir = working_dir
        self.criteria = criteria or DEFAULT_CRITERIA
        self.progress_callback = progress_callback
        self.memory_tool = memory_tool
        self.enable_monitoring = enable_monitoring
        self.use_push_architecture = use_push_architecture
        # FIX-26: Store tech_stack for agent access
        self.tech_stack = tech_stack

        # Persistent deployment config
        self.enable_persistent_deploy = enable_persistent_deploy
        self.persistent_vnc_port = persistent_vnc_port
        self.inject_collected_secrets = inject_collected_secrets

        # Async Services config (E2E and UX run continuously parallel to Phase 3)
        self.enable_async_e2e = enable_async_e2e
        self.enable_async_ux = enable_async_ux
        self.async_e2e_interval = async_e2e_interval
        self.async_ux_interval = async_ux_interval
        self._async_service_tasks: list[asyncio.Task] = []  # Track async service tasks

        # Event Interpreter (Handoffs Pattern) config
        self.enable_event_interpreter = enable_event_interpreter
        self.use_llm_routing = use_llm_routing
        self.event_interpreter: Optional["EventInterpreterAgent"] = None

        # Phase 16: MCP Event Bridge config (bidirectional EventBus <-> MCP Orchestrator)
        self.enable_mcp_event_bridge = enable_mcp_event_bridge
        self.mcp_event_bridge: Optional[Any] = None  # MCPEventBridge instance

        # Task 13: Backend agent feature flags
        self.enable_database_generation = enable_database_generation
        self.enable_api_generation = enable_api_generation
        self.enable_auth_setup = enable_auth_setup
        self.enable_infrastructure_setup = enable_infrastructure_setup

        # WebSocket and Redis Pub/Sub agent feature flags
        self.enable_websocket_generation = enable_websocket_generation
        self.enable_redis_pubsub = enable_redis_pubsub

        # Messaging Platform agent feature flags (Group, Presence, Encryption)
        self.enable_group_management = enable_group_management
        self.enable_presence_tracking = enable_presence_tracking
        self.enable_encryption = enable_encryption

        # Phase 10: Security & Dependency Management flags
        self.enable_security_scanning = enable_security_scanning
        self.enable_dependency_management = enable_dependency_management

        # Phase 10.2: Performance, Accessibility, Documentation, Migration, Localization flags
        self.enable_performance_analysis = enable_performance_analysis
        self.enable_accessibility_testing = enable_accessibility_testing
        self.enable_api_documentation = enable_api_documentation
        self.enable_migrations = enable_migrations
        self.enable_localization = enable_localization

        # Task 24: Browser Console & Validation Recovery flags
        self.enable_browser_console = enable_browser_console
        self.enable_validation_recovery = enable_validation_recovery

        # Fungus Context System flags
        self.enable_fungus = enable_fungus
        self.fungus_num_agents = fungus_num_agents
        self.fungus_max_iterations = fungus_max_iterations
        self.fungus_judge_provider = fungus_judge_provider
        self.fungus_judge_model = fungus_judge_model or get_model("judge")

        # Phase 17: Fungus Validation
        self.enable_fungus_validation = enable_fungus_validation
        self.fungus_validation_interval = fungus_validation_interval

        # Phase 18: Fungus Memory
        self.enable_fungus_memory = enable_fungus_memory
        self.fungus_memory_interval = fungus_memory_interval

        # Phase 20: Differential Analysis
        self.enable_differential_analysis = enable_differential_analysis
        self.differential_data_dir = differential_data_dir

        # Phase 23: Cross-Layer Validation
        self.enable_cross_layer_validation = enable_cross_layer_validation

        # Logger first (needed by _setup_agents)
        self.logger = logger.bind(component="orchestrator")

        # Log tech_stack if present
        if tech_stack:
            self.logger.info(
                "tech_stack_configured",
                frontend=getattr(tech_stack, 'frontend_framework', None),
                backend=getattr(tech_stack, 'backend_framework', None),
                platform=getattr(tech_stack, 'platform', None),
            )

        # Core components - use injected or create new (FIX-5)
        self.event_bus = event_bus if event_bus is not None else EventBus()
        self.shared_state = shared_state if shared_state is not None else SharedState()

        # Agent Monitor for real-time tracking
        self.monitor: Optional[AgentMonitor] = None
        if enable_monitoring:
            self.monitor = create_monitor(
                event_bus=self.event_bus,
                shared_state=self.shared_state,
            )

        # Discord Notifier for live status updates
        try:
            from src.services.discord_notifier import init_discord_notifier
            self.discord_notifier = init_discord_notifier(event_bus=self.event_bus)
            self.logger.info("discord_notifier_initialized")
        except Exception as e:
            self.discord_notifier = None
            self.logger.debug("discord_notifier_skipped", reason=str(e))

        # Document Registry for inter-agent communication
        self.document_registry = DocumentRegistry(working_dir)

        # Container Log Seeder for automatic log capture on container events
        self.enable_container_log_seeding = enable_container_log_seeding
        self.container_log_seeder = None
        if enable_container_log_seeding:
            try:
                from ..services.container_log_seeder import ContainerLogSeeder
                self.container_log_seeder = ContainerLogSeeder(
                    output_dir=working_dir,
                    event_bus=self.event_bus,
                    max_logs_per_container=10,
                    default_tail_lines=500,
                )
                self.logger.info("container_log_seeder_initialized", logs_dir=str(self.container_log_seeder.logs_dir))
            except Exception as e:
                self.logger.warning("container_log_seeder_init_failed", error=str(e))

        # Error Receiver Server for client-side JavaScript error reporting
        self.enable_error_receiver = enable_browser_console  # Reuse browser console flag
        self.error_receiver_server = None

        # Skill Registry for agent skill loading and injection
        self.skill_registry: Optional["SkillRegistry"] = None
        SkillRegistry = _get_skill_registry()
        if SkillRegistry:
            try:
                self.skill_registry = SkillRegistry(ENGINE_ROOT)  # Task 22: Use engine root, not output dir
                num_skills = self.skill_registry.initialize()
                if num_skills > 0:
                    self.logger.info(
                        "skills_registry_initialized",
                        skills_loaded=num_skills,
                        metadata_tokens=self.skill_registry.total_metadata_tokens,
                    )
            except Exception as e:
                self.logger.debug("skill_registry_init_failed", error=str(e))

        # Coordination semaphore for deployment vs coding
        self.coding_semaphore = asyncio.Semaphore(1)

        # PUSH ARCHITECTURE: Track idle state for convergence checks
        self._active_agents: set[str] = set()
        self._last_activity_time: datetime = datetime.now()
        self._idle_check_interval = 1.0  # Check idle state every 1s

        # Agents
        self.agents: list["AutonomousAgent"] = []
        self._agent_map: dict[str, "AutonomousAgent"] = {}  # Name -> Agent lookup
        # Phase 10: Store voting/verification parameters
        self.enable_llm_verification = enable_llm_verification
        self.voting_method = voting_method
        self.verification_debate_rounds = verification_debate_rounds

        self._setup_agents(
            enable_e2e_testing=enable_e2e_testing,
            enable_ux_review=enable_ux_review,
            enable_auto_docs=enable_auto_docs,
            enable_frontend_validation=enable_frontend_validation,
            enable_runtime_debug=enable_runtime_debug,
            enable_sandbox_testing=enable_sandbox_testing,
            enable_cloud_tests=enable_cloud_tests,
            enable_vnc_streaming=enable_vnc_streaming,
            vnc_port=vnc_port,
            enable_continuous_sandbox=enable_continuous_sandbox,
            sandbox_cycle_interval=sandbox_cycle_interval,
            start_sandbox_immediately=start_sandbox_immediately,
            enable_continuous_debug=enable_continuous_debug,
            debug_cycle_interval=debug_cycle_interval,
            max_debug_iterations=max_debug_iterations,
            requirements=requirements,
            enable_llm_verification=enable_llm_verification,
            voting_method=voting_method,
            verification_debate_rounds=verification_debate_rounds,
        )

        # Build agent lookup map
        for agent in self.agents:
            self._agent_map[agent.name] = agent
            self.logger.debug("agent_configured", agent=agent.name)

        # Inject skills into agents if registry is available
        if self.skill_registry:
            self._inject_skills_to_agents()

        # Initialize Event Interpreter (Handoffs Pattern) if enabled
        if self.enable_event_interpreter:
            self._setup_event_interpreter()

        # Initialize MCP Event Bridge (Phase 16: bidirectional EventBus <-> MCP Orchestrator)
        if self.enable_mcp_event_bridge:
            self._setup_mcp_event_bridge()

        # State
        self._start_time: Optional[datetime] = None
        self._should_stop = False

        # Subscribe to state changes
        self.shared_state.on_change(self._on_state_change)

        # Subscribe to all events for logging
        self.event_bus.subscribe_all(self._on_event)

        # Subscribe to agent lifecycle events for idle tracking
        self.event_bus.subscribe(EventType.AGENT_ACTING, self._on_agent_acting)
        self.event_bus.subscribe(EventType.AGENT_COMPLETED, self._on_agent_idle)
        self.event_bus.subscribe(EventType.AGENT_ERROR, self._on_agent_idle)

    def _setup_agents(
        self,
        enable_e2e_testing: bool = False,
        enable_ux_review: bool = False,
        enable_auto_docs: bool = True,
        enable_frontend_validation: bool = False,
        enable_runtime_debug: bool = True,
        enable_sandbox_testing: bool = False,
        enable_cloud_tests: bool = False,
        enable_vnc_streaming: bool = False,
        vnc_port: int = 6080,
        enable_continuous_sandbox: bool = False,
        sandbox_cycle_interval: int = 30,
        start_sandbox_immediately: bool = True,
        enable_continuous_debug: bool = False,
        debug_cycle_interval: int = 5,
        max_debug_iterations: int = 10,
        requirements: list[str] = None,
        # Phase 10: VotingAI & Verification Debate
        enable_llm_verification: bool = False,
        voting_method: str = "qualified_majority",
        verification_debate_rounds: int = 3,
        # Phase 14: Post-epic task validation
        enable_task_validation: bool = True,
    ) -> None:
        """Create and configure all agents."""
        # Lazy import to avoid circular dependency
        from ..agents.autonomous_base import (
            TesterAgent,
            BuilderAgent,
            ValidatorAgent,
            FixerAgent,
        )

        agent_classes = [
            ("Tester", TesterAgent),
            ("Builder", BuilderAgent),
            ("Validator", ValidatorAgent),
            ("Fixer", FixerAgent),
        ]

        for name, agent_class in agent_classes:
            # FIX-28: Pass tech_stack to FixerAgent for technology-aware fixing
            if name == "Fixer":
                agent = agent_class(
                    name=name,
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_tool=self.memory_tool,
                    tech_stack=self.tech_stack,
                )
            else:
                agent = agent_class(
                    name=name,
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_tool=self.memory_tool,
                )
            self.agents.append(agent)
            self.logger.debug("agent_configured", agent=name)

        # Add E2E Tester Team if enabled
        if enable_e2e_testing:
            try:
                from ..agents.tester_team_agent import TesterTeamAgent
                e2e_agent = TesterTeamAgent(
                    name="TesterTeam",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    requirements=requirements or [],
                    memory_tool=self.memory_tool,
                    document_registry=self.document_registry,
                )
                self.agents.append(e2e_agent)
                self.logger.debug("agent_configured", agent="TesterTeam")
            except ImportError as e:
                self.logger.warning("e2e_agent_import_failed", error=str(e))

        # Add UX Design Agent if enabled
        if enable_ux_review:
            try:
                from ..agents.ux_design_agent import UXDesignAgent
                ux_agent = UXDesignAgent(
                    name="UXDesigner",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    requirements=requirements or [],
                )
                self.agents.append(ux_agent)
                self.logger.debug("agent_configured", agent="UXDesigner")
            except ImportError as e:
                self.logger.warning("ux_agent_import_failed", error=str(e))

        # Add Documentation Agent for auto-generating CLAUDE.md
        if enable_auto_docs:
            try:
                from ..agents.documentation_agent import DocumentationAgent
                docs_agent = DocumentationAgent(
                    name="Documentation",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    requirements=requirements or [],
                )
                self.agents.append(docs_agent)
                self.logger.debug("agent_configured", agent="Documentation")
            except ImportError as e:
                self.logger.warning("docs_agent_import_failed", error=str(e))

        # Add Frontend Validator Agent for UI validation via Playwright
        if enable_frontend_validation:
            try:
                from ..agents.frontend_validator_agent import FrontendValidatorAgent
                frontend_agent = FrontendValidatorAgent(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    requirements_path=None,  # Will auto-detect
                )
                self.agents.append(frontend_agent)
                self.logger.debug("agent_configured", agent="FrontendValidator")
            except ImportError as e:
                self.logger.warning("frontend_validator_import_failed", error=str(e))

        # Add Runtime Debug Agent for automatic runtime debugging
        if enable_runtime_debug:
            try:
                from ..agents.runtime_debug_agent import RuntimeDebugAgent
                runtime_agent = RuntimeDebugAgent(
                    name="RuntimeDebugger",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_tool=self.memory_tool,
                )
                self.agents.append(runtime_agent)
                self.logger.debug("agent_configured", agent="RuntimeDebugger")
            except ImportError as e:
                self.logger.warning("runtime_debug_agent_import_failed", error=str(e))

        # Add Deploy Agent for automated deployment and log collection
        try:
            from ..agents.deploy_agent import DeployAgent
            deploy_agent = DeployAgent(
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                coding_semaphore=self.coding_semaphore,
                memory_tool=self.memory_tool,
            )
            self.agents.append(deploy_agent)
            self.logger.debug("agent_configured", agent="DeployAgent")
        except ImportError as e:
            self.logger.warning("deploy_agent_import_failed", error=str(e))

        # Add Task Validator Agent for post-epic fix loop
        if enable_task_validation:
            try:
                from ..agents.task_validator_agent import TaskValidatorAgent
                tv_agent = TaskValidatorAgent(
                    name="TaskValidator",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                )
                self.agents.append(tv_agent)
                self.logger.debug("agent_configured", agent="TaskValidator")
            except ImportError as e:
                self.logger.warning("task_validator_agent_import_failed", error=str(e))

        # Add Playwright E2E Agent for post-deployment visual testing
        try:
            from ..agents.playwright_e2e_agent import PlaywrightE2EAgent
            playwright_agent = PlaywrightE2EAgent(
                name="PlaywrightE2E",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                memory_tool=self.memory_tool,
                document_registry=self.document_registry,
            )
            self.agents.append(playwright_agent)
            self.logger.debug("agent_configured", agent="PlaywrightE2E")
        except ImportError as e:
            self.logger.warning("playwright_e2e_agent_import_failed", error=str(e))

        # Add Requirements Playwright Agent for LLM-guided E2E testing against requirements
        try:
            from ..agents.requirements_playwright_agent import RequirementsPlaywrightAgent
            requirements_agent = RequirementsPlaywrightAgent(
                name="RequirementsPlaywright",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                requirements_path=getattr(self, 'requirements_path', None),
                app_url=f"http://localhost:{getattr(self, 'preview_port', 5173)}",
            )
            self.agents.append(requirements_agent)
            self.logger.debug("agent_configured", agent="RequirementsPlaywright")
        except ImportError as e:
            self.logger.warning("requirements_playwright_agent_import_failed", error=str(e))

        # Add Code Quality Agent for cleanup, refactoring, and documentation
        try:
            from ..agents.code_quality_agent import CodeQualityAgent
            quality_agent = CodeQualityAgent(
                name="CodeQuality",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                document_registry=self.document_registry,
            )
            self.agents.append(quality_agent)
            self.logger.debug("agent_configured", agent="CodeQuality")
        except ImportError as e:
            self.logger.warning("code_quality_agent_import_failed", error=str(e))

        # Add Generator Agent with document registry for inter-agent communication
        try:
            from ..agents.generator_agent import GeneratorAgent
            generator_agent = GeneratorAgent(
                name="Generator",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                memory_tool=self.memory_tool,
                document_registry=self.document_registry,
                tech_stack=self.tech_stack,  # FIX-27: Pass tech_stack
            )
            self.agents.append(generator_agent)
            self.logger.debug("agent_configured", agent="Generator")
        except ImportError as e:
            self.logger.warning("generator_agent_import_failed", error=str(e))

        # Add Database Agent for schema generation from contracts (Task 13: feature flag)
        if self.enable_database_generation:
            try:
                from ..agents.database_agent import DatabaseAgent
                # Determine db_type from tech_stack or default to prisma
                db_type = "prisma"
                if self.tech_stack:
                    # Map database names to ORM types
                    db_name = (self.tech_stack.database_name or "").lower()
                    if "postgres" in db_name or "mysql" in db_name or "sqlite" in db_name:
                        db_type = "prisma"  # Prisma supports these SQL databases
                    elif "mongo" in db_name:
                        db_type = "prisma"  # Prisma supports MongoDB
                    elif self.tech_stack.backend_language == "Python":
                        db_type = "sqlalchemy"  # Python projects use SQLAlchemy
                db_agent = DatabaseAgent(
                    name="DatabaseAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_registry=self.skill_registry,
                    db_type=db_type,
                )
                self.agents.append(db_agent)
                self.logger.debug("agent_configured", agent="DatabaseAgent", db_type=db_type)
            except ImportError as e:
                self.logger.warning("database_agent_import_failed", error=str(e))

        # Add API Agent for REST endpoint generation (Task 13: feature flag)
        if self.enable_api_generation:
            try:
                from ..agents.api_agent import APIAgent
                # Determine api_framework from tech_stack or default to nextjs
                api_framework = "nextjs"
                if self.tech_stack:
                    backend = (self.tech_stack.backend_framework or "").lower()
                    if "fastapi" in backend:
                        api_framework = "fastapi"
                    elif "express" in backend:
                        api_framework = "express"
                    elif "next" in backend:
                        api_framework = "nextjs"
                    elif "flask" in backend:
                        api_framework = "flask"
                    elif "django" in backend:
                        api_framework = "django"
                api_agent = APIAgent(
                    name="APIAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_registry=self.skill_registry,
                    api_framework=api_framework,
                )
                self.agents.append(api_agent)
                self.logger.debug("agent_configured", agent="APIAgent", api_framework=api_framework)
            except ImportError as e:
                self.logger.warning("api_agent_import_failed", error=str(e))

        # Add Auth Agent for authentication/authorization setup (Task 13: feature flag)
        if self.enable_auth_setup:
            try:
                from ..agents.auth_agent import AuthAgent
                # Determine auth_type from tech_stack or default to jwt
                auth_type = "jwt"
                enable_rbac = True
                if self.tech_stack:
                    # Check raw_data for auth configuration
                    raw = self.tech_stack.raw_data or {}
                    tech_data = raw.get("tech_stack", raw)
                    auth_config = tech_data.get("auth", {})
                    if isinstance(auth_config, dict):
                        auth_type = auth_config.get("type", "jwt").lower()
                        enable_rbac = auth_config.get("rbac", True)
                    elif isinstance(auth_config, str):
                        auth_type = auth_config.lower()
                    # Also check additional_tools for OAuth hints
                    tools = " ".join(self.tech_stack.additional_tools).lower()
                    if "oauth" in tools or "google" in tools or "github" in tools:
                        auth_type = "oauth2"
                auth_agent = AuthAgent(
                    name="AuthAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_registry=self.skill_registry,
                    auth_type=auth_type,
                    enable_rbac=enable_rbac,
                )
                self.agents.append(auth_agent)
                self.logger.debug("agent_configured", agent="AuthAgent", auth_type=auth_type)
            except ImportError as e:
                self.logger.warning("auth_agent_import_failed", error=str(e))

        # Add Infrastructure Agent for .env, Docker, CI/CD setup (Task 13: feature flag)
        if self.enable_infrastructure_setup:
            try:
                from ..agents.infrastructure_agent import InfrastructureAgent
                infra_agent = InfrastructureAgent(
                    name="InfrastructureAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_registry=self.skill_registry,
                    enable_docker=True,  # Task 21: Fixed parameter name
                    enable_ci=True,  # Task 21: Fixed parameter name
                )
                self.agents.append(infra_agent)
                self.logger.debug("agent_configured", agent="InfrastructureAgent")
            except ImportError as e:
                self.logger.warning("infrastructure_agent_import_failed", error=str(e))

        # Add WebSocket Agent for real-time messaging features
        if self.enable_websocket_generation:
            try:
                from ..agents.websocket_agent import WebSocketAgent
                # Determine websocket_framework from tech_stack
                websocket_framework = "nestjs"
                if self.tech_stack:
                    backend = (self.tech_stack.backend_framework or "").lower()
                    if "express" in backend:
                        websocket_framework = "express-ws"
                    elif "fastapi" in backend:
                        websocket_framework = "fastapi-websockets"
                ws_agent = WebSocketAgent(
                    name="WebSocketAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_registry=self.skill_registry,
                    websocket_framework=websocket_framework,
                )
                self.agents.append(ws_agent)
                self.logger.debug("agent_configured", agent="WebSocketAgent", framework=websocket_framework)
            except ImportError as e:
                self.logger.warning("websocket_agent_import_failed", error=str(e))

        # Add Redis Pub/Sub Agent for WebSocket scaling and caching
        if self.enable_redis_pubsub:
            try:
                from ..agents.redis_pubsub_agent import RedisPubSubAgent
                redis_agent = RedisPubSubAgent(
                    name="RedisPubSubAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_registry=self.skill_registry,
                    enable_caching=True,
                    enable_session_store=True,
                    enable_queue=True,
                )
                self.agents.append(redis_agent)
                self.logger.debug("agent_configured", agent="RedisPubSubAgent")
            except ImportError as e:
                self.logger.warning("redis_pubsub_agent_import_failed", error=str(e))

        # Add Group Management Agent for messaging platform groups
        if self.enable_group_management:
            try:
                from ..agents.group_management_agent import GroupManagementAgent
                group_agent = GroupManagementAgent(
                    name="GroupManagementAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_loader=self.skill_registry,
                )
                self.agents.append(group_agent)
                self.logger.debug("agent_configured", agent="GroupManagementAgent")
            except ImportError as e:
                self.logger.warning("group_management_agent_import_failed", error=str(e))

        # Add Presence Agent for online/offline status, typing, read receipts
        if self.enable_presence_tracking:
            try:
                from ..agents.presence_agent import PresenceAgent
                presence_agent = PresenceAgent(
                    name="PresenceAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_loader=self.skill_registry,
                )
                self.agents.append(presence_agent)
                self.logger.debug("agent_configured", agent="PresenceAgent")
            except ImportError as e:
                self.logger.warning("presence_agent_import_failed", error=str(e))

        # Add Encryption Agent for end-to-end encryption (E2EE)
        if self.enable_encryption:
            try:
                from ..agents.encryption_agent import EncryptionAgent
                encryption_agent = EncryptionAgent(
                    name="EncryptionAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    skill_loader=self.skill_registry,
                )
                self.agents.append(encryption_agent)
                self.logger.debug("agent_configured", agent="EncryptionAgent")
            except ImportError as e:
                self.logger.warning("encryption_agent_import_failed", error=str(e))

        # Phase 10: Add Security Scanner Agent for vulnerability detection
        if self.enable_security_scanning:
            try:
                from ..agents.security_scanner_agent import SecurityScannerAgent
                security_agent = SecurityScannerAgent(
                    name="SecurityScannerAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    run_npm_audit=True,
                    run_pip_audit=True,
                    scan_for_secrets=True,
                    scan_patterns=True,
                    fail_on_critical=True,
                )
                self.agents.append(security_agent)
                self.logger.debug("agent_configured", agent="SecurityScannerAgent")
            except ImportError as e:
                self.logger.warning("security_scanner_agent_import_failed", error=str(e))

        # Phase 10: Add Dependency Manager Agent for package management
        if self.enable_dependency_management:
            try:
                from ..agents.dependency_manager_agent import DependencyManagerAgent
                dependency_agent = DependencyManagerAgent(
                    name="DependencyManagerAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    auto_update_patch=True,
                    auto_update_minor=False,
                    check_licenses=True,
                )
                self.agents.append(dependency_agent)
                self.logger.debug("agent_configured", agent="DependencyManagerAgent")
            except ImportError as e:
                self.logger.warning("dependency_manager_agent_import_failed", error=str(e))

        # Phase 10.1: Add Bug Fixer Agent for code-level error fixes
        if self.enable_dependency_management:  # Uses same flag as dependency management
            try:
                from ..agents.bug_fixer_agent import BugFixerAgent
                bug_fixer_agent = BugFixerAgent(
                    name="BugFixerAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                )
                self.agents.append(bug_fixer_agent)
                self.logger.debug("agent_configured", agent="BugFixerAgent")
            except ImportError as e:
                self.logger.warning("bug_fixer_agent_import_failed", error=str(e))

        # Phase 10.1b: Add Database Schema Agent for auto-migrations
        if self.enable_dependency_management:
            try:
                from ..agents.database_schema_agent import DatabaseSchemaAgent
                database_schema_agent = DatabaseSchemaAgent(
                    name="DatabaseSchemaAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    auto_migrate=False,  # Safe mode: generate only
                )
                self.agents.append(database_schema_agent)
                self.logger.debug("agent_configured", agent="DatabaseSchemaAgent")
            except ImportError as e:
                self.logger.warning("database_schema_agent_import_failed", error=str(e))

        # UIIntegrationAgent - Auto-integrates new components into App.tsx
        try:
            from ..agents.ui_integration_agent import UIIntegrationAgent
            ui_integration_agent = UIIntegrationAgent(
                name="UIIntegrationAgent",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(ui_integration_agent)
            self.logger.debug("agent_configured", agent="UIIntegrationAgent")
        except ImportError as e:
            self.logger.warning("ui_integration_agent_import_failed", error=str(e))

        # ContinuousE2EAgent - Periodic E2E testing during generation
        if enable_e2e_testing:
            try:
                from ..agents.continuous_e2e_agent import ContinuousE2EAgent
                continuous_e2e_agent = ContinuousE2EAgent(
                    name="ContinuousE2EAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    app_url=f"http://localhost:{getattr(self, 'preview_port', 5173)}",
                )
                self.agents.append(continuous_e2e_agent)
                self.logger.debug("agent_configured", agent="ContinuousE2EAgent")
            except ImportError as e:
                self.logger.warning("continuous_e2e_agent_import_failed", error=str(e))

        # E2EIntegrationTeamAgent - CRUD verification with VNC always-on mode
        if enable_e2e_testing or enable_sandbox_testing:
            try:
                from ..agents.e2e_integration_team_agent import E2EIntegrationTeamAgent
                e2e_integration_agent = E2EIntegrationTeamAgent(
                    event_bus=self.event_bus,
                    output_dir=self.working_dir,
                    shared_state=self.shared_state,
                    app_url=f"http://localhost:{getattr(self, 'preview_port', 5173)}",
                    vnc_url=f"http://localhost:{vnc_port}/vnc.html" if enable_vnc_streaming else None,
                )
                self.agents.append(e2e_integration_agent)
                self.logger.debug("agent_configured", agent="E2EIntegrationTeam")
            except ImportError as e:
                self.logger.warning("e2e_integration_team_agent_import_failed", error=str(e))

        # Phase 10.2: Add Performance Agent for bundle analysis and optimization
        if self.enable_performance_analysis:
            try:
                from ..agents.performance_agent import PerformanceAgent
                performance_agent = PerformanceAgent(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    enable_lighthouse=True,
                    enable_pattern_scan=True,
                )
                self.agents.append(performance_agent)
                self.logger.debug("agent_configured", agent="PerformanceAgent")
            except ImportError as e:
                self.logger.warning("performance_agent_import_failed", error=str(e))

        # Phase 10.2: Add Accessibility Agent for WCAG compliance testing
        if self.enable_accessibility_testing:
            try:
                from ..agents.accessibility_agent import AccessibilityAgent
                accessibility_agent = AccessibilityAgent(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    wcag_level="AA",
                    enable_axe_core=True,
                )
                self.agents.append(accessibility_agent)
                self.logger.debug("agent_configured", agent="AccessibilityAgent")
            except ImportError as e:
                self.logger.warning("accessibility_agent_import_failed", error=str(e))

        # Phase 10.2: Add API Documentation Agent for OpenAPI/Swagger generation
        if self.enable_api_documentation:
            try:
                from ..agents.api_documentation_agent import APIDocumentationAgent
                api_docs_agent = APIDocumentationAgent(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    generate_openapi=True,
                    generate_swagger_ui=True,
                )
                self.agents.append(api_docs_agent)
                self.logger.debug("agent_configured", agent="APIDocumentationAgent")
            except ImportError as e:
                self.logger.warning("api_documentation_agent_import_failed", error=str(e))

        # Phase 10.2: Add Migration Agent for database migrations
        if self.enable_migrations:
            try:
                from ..agents.migration_agent import MigrationAgent
                migration_agent = MigrationAgent(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    auto_generate_migrations=True,
                    auto_run_seeds=True,
                )
                self.agents.append(migration_agent)
                self.logger.debug("agent_configured", agent="MigrationAgent")
            except ImportError as e:
                self.logger.warning("migration_agent_import_failed", error=str(e))

        # Phase 10.2: Add Localization Agent for i18n setup
        if self.enable_localization:
            try:
                from ..agents.localization_agent import LocalizationAgent
                localization_agent = LocalizationAgent(
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    default_locale="en",
                    extract_strings=True,
                )
                self.agents.append(localization_agent)
                self.logger.debug("agent_configured", agent="LocalizationAgent")
            except ImportError as e:
                self.logger.warning("localization_agent_import_failed", error=str(e))

        # Task 24: Add BrowserConsoleAgent for real-time browser error detection
        # NOTE: BrowserConsoleAgent is a utility class, NOT an AutonomousAgent
        # It only accepts 'browser' parameter and is used directly when needed
        if self.enable_browser_console:
            try:
                from ..agents.browser_console_agent import BrowserConsoleAgent
                # Store as utility for direct use - not added to agents list
                self._browser_console = BrowserConsoleAgent(browser="chrome")
                self.logger.debug("browser_console_utility_configured")
            except ImportError as e:
                self.logger.warning("browser_console_agent_import_failed", error=str(e))

        # Task 24: Add ValidationRecoveryAgent for automatic validation failure fixes
        # NOTE: ValidationRecoveryAgent is a utility class, NOT an AutonomousAgent
        # It only accepts project_dir, claude_tool, max_retries, memory_tool
        if self.enable_validation_recovery:
            try:
                from ..agents.validation_recovery_agent import ValidationRecoveryAgent
                # Store as utility for direct use - not added to agents list
                self._validation_recovery = ValidationRecoveryAgent(
                    project_dir=str(self.working_dir),
                    memory_tool=self.memory_tool,
                )
                self.logger.debug("validation_recovery_utility_configured")
            except ImportError as e:
                self.logger.warning("validation_recovery_agent_import_failed", error=str(e))

        # Add Deployment Team Agent for Docker sandbox testing or persistent deployment
        if enable_sandbox_testing or enable_continuous_sandbox or self.enable_persistent_deploy:
            try:
                from ..agents.deployment_team_agent import DeploymentTeamAgent
                deployment_agent = DeploymentTeamAgent(
                    name="DeploymentTeam",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_tool=self.memory_tool,
                    enable_sandbox=True,
                    enable_cloud_tests=enable_cloud_tests,
                    enable_vnc=enable_vnc_streaming,
                    vnc_port=vnc_port,
                    # Continuous testing mode
                    enable_continuous=enable_continuous_sandbox,
                    cycle_interval=sandbox_cycle_interval,
                    start_continuous_immediately=start_sandbox_immediately,
                    # Persistent deployment mode
                    enable_persistent_final_deploy=self.enable_persistent_deploy,
                    persistent_vnc_port=self.persistent_vnc_port,
                    inject_collected_secrets=self.inject_collected_secrets,
                )
                self.agents.append(deployment_agent)
                self.logger.debug(
                    "agent_configured",
                    agent="DeploymentTeam",
                    continuous_mode=enable_continuous_sandbox,
                    cycle_interval=sandbox_cycle_interval,
                )
            except ImportError as e:
                self.logger.warning("deployment_team_agent_import_failed", error=str(e))

        # Add Continuous Debug Agent for real-time debugging during generation
        self.logger.info(
            "continuous_debug_check",
            enable_continuous_debug=enable_continuous_debug,
            debug_cycle_interval=debug_cycle_interval,
            max_debug_iterations=max_debug_iterations,
        )
        if enable_continuous_debug:
            try:
                from ..agents.continuous_debug_agent import ContinuousDebugAgent
                debug_agent = ContinuousDebugAgent(
                    name="ContinuousDebug",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_tool=self.memory_tool,
                    poll_interval=debug_cycle_interval,
                    max_debug_iterations=max_debug_iterations,
                    enable_file_sync=enable_continuous_sandbox,  # Sync if container running
                    enable_hot_reload=enable_continuous_sandbox,
                )
                # Inject container log seeder for historical log access
                if self.container_log_seeder:
                    debug_agent.set_container_log_seeder(self.container_log_seeder)
                self.agents.append(debug_agent)
                self.logger.debug(
                    "agent_configured",
                    agent="ContinuousDebug",
                    cycle_interval=debug_cycle_interval,
                    max_iterations=max_debug_iterations,
                    has_log_seeder=self.container_log_seeder is not None,
                )
            except ImportError as e:
                self.logger.warning("continuous_debug_agent_import_failed", error=str(e))
        else:
            self.logger.warning(
                "continuous_debug_agent_SKIPPED",
                reason="enable_continuous_debug flag is False",
                hint="Pass --enable-continuous-debug to enable",
            )

        # Add LLM-enhanced diagnosis agents (Phase 6)
        # DatabaseDiagnosticAgent - LLM schema error analysis
        try:
            from ..agents.database_diagnostic_agent import DatabaseDiagnosticAgent
            db_diagnostic_agent = DatabaseDiagnosticAgent(
                name="DatabaseDiagnostic",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(db_diagnostic_agent)
            self.logger.info("agent_configured", agent="DatabaseDiagnosticAgent")
        except ImportError as e:
            self.logger.warning("database_diagnostic_agent_import_failed", error=str(e))

        # ErrorContextAgent - Cross-file error tracing
        try:
            from ..agents.error_context_agent import ErrorContextAgent
            error_context_agent = ErrorContextAgent(
                name="ErrorContext",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(error_context_agent)
            self.logger.info("agent_configured", agent="ErrorContextAgent")
        except ImportError as e:
            self.logger.warning("error_context_agent_import_failed", error=str(e))

        # SmartTestGeneratorAgent - Intelligent test generation
        try:
            from ..agents.smart_test_generator_agent import SmartTestGeneratorAgent
            smart_test_agent = SmartTestGeneratorAgent(
                name="SmartTestGenerator",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(smart_test_agent)
            self.logger.info("agent_configured", agent="SmartTestGeneratorAgent")
        except ImportError as e:
            self.logger.warning("smart_test_generator_agent_import_failed", error=str(e))

        # Add Phase 7 LLM-enhanced agents
        # DockerDiagnosticAgent - LLM Docker/infrastructure error diagnosis
        try:
            from ..agents.docker_diagnostic_agent import DockerDiagnosticAgent
            docker_diagnostic_agent = DockerDiagnosticAgent(
                name="DockerDiagnostic",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(docker_diagnostic_agent)
            self.logger.info("agent_configured", agent="DockerDiagnosticAgent")
        except ImportError as e:
            self.logger.warning("docker_diagnostic_agent_import_failed", error=str(e))

        # TraceabilityAgent - LLM requirement-to-code tracing (Phase 8)
        try:
            from ..agents.traceability_agent import TraceabilityAgent
            traceability_agent = TraceabilityAgent(
                name="Traceability",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(traceability_agent)
            self.logger.info("agent_configured", agent="TraceabilityAgent")
        except ImportError as e:
            self.logger.warning("traceability_agent_import_failed", error=str(e))

        # ArchitectureHealthAgent - LLM architecture quality assessment (Phase 8)
        try:
            from ..agents.architecture_health_agent import ArchitectureHealthAgent
            architecture_agent = ArchitectureHealthAgent(
                name="ArchitectureHealth",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(architecture_agent)
            self.logger.info("agent_configured", agent="ArchitectureHealthAgent")
        except ImportError as e:
            self.logger.warning("architecture_health_agent_import_failed", error=str(e))

        # Phase 10: VerificationDebateAgent - Event-driven verification with voting
        if enable_llm_verification:
            try:
                from ..agents.verification_debate_agent import (
                    VerificationDebateAgent, VotingConfig, VotingMethod
                )
                # Build VotingConfig from voting_method string
                voting_cfg = VotingConfig(
                    method=VotingMethod(voting_method),
                    require_reasoning=True,
                )
                verification_debate = VerificationDebateAgent(
                    name="VerificationDebate",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    requirements=requirements or [],
                    num_debate_rounds=verification_debate_rounds,
                    voting_config=voting_cfg,
                )
                self.agents.append(verification_debate)
                self.logger.info(
                    "agent_configured",
                    agent="VerificationDebateAgent",
                    voting_method=voting_method,
                    debate_rounds=verification_debate_rounds,
                )
            except ImportError as e:
                self.logger.warning("verification_debate_agent_import_failed", error=str(e))
            except Exception as e:
                self.logger.warning("verification_debate_agent_init_failed", error=str(e))

        # Add FungusContextAgent for semantic code context via la_fungus_search
        if self.enable_fungus:
            try:
                from ..agents.fungus_context_agent import FungusContextAgent
                from ..services.mcmp_background import SimulationConfig

                fungus_config = SimulationConfig(
                    num_agents=self.fungus_num_agents,
                    max_iterations=self.fungus_max_iterations,
                    judge_provider=self.fungus_judge_provider,
                    judge_model=self.fungus_judge_model,
                )
                fungus_agent = FungusContextAgent(
                    name="FungusContext",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_tool=self.memory_tool,
                    mcmp_config=fungus_config,
                )
                self.agents.append(fungus_agent)
                self.logger.info(
                    "agent_configured",
                    agent="FungusContextAgent",
                    num_agents=self.fungus_num_agents,
                    judge_provider=self.fungus_judge_provider,
                )
            except ImportError as e:
                self.logger.warning("fungus_context_agent_import_failed", error=str(e))

        # Phase 17: Add FungusValidationAgent for autonomous MCMP validation
        if self.enable_fungus_validation:
            try:
                from ..agents.fungus_validation_agent import FungusValidationAgent
                fungus_validation_agent = FungusValidationAgent(
                    name="FungusValidation",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    validation_interval=self.fungus_validation_interval,
                )
                self.agents.append(fungus_validation_agent)
                self.logger.info("agent_configured", agent="FungusValidationAgent")
            except ImportError as e:
                self.logger.warning("fungus_validation_agent_import_failed", error=str(e))

        # Phase 18: Add FungusMemoryAgent for memory-augmented MCMP search
        if self.enable_fungus_memory:
            try:
                from ..agents.fungus_memory_agent import FungusMemoryAgent
                fungus_memory_agent = FungusMemoryAgent(
                    name="FungusMemory",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    memory_interval=self.fungus_memory_interval,
                )
                self.agents.append(fungus_memory_agent)
                self.logger.info("agent_configured", agent="FungusMemoryAgent")
            except ImportError as e:
                self.logger.warning("fungus_memory_agent_import_failed", error=str(e))

        # Phase 20: Add DifferentialAnalysisAgent for docs vs code gap detection
        if self.enable_differential_analysis:
            try:
                from ..agents.differential_analysis_agent import DifferentialAnalysisAgent
                diff_agent = DifferentialAnalysisAgent(
                    name="DifferentialAnalysis",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    data_dir=self.differential_data_dir or None,
                )
                self.agents.append(diff_agent)
                self.logger.info("agent_configured", agent="DifferentialAnalysisAgent")
            except ImportError as e:
                self.logger.warning("differential_analysis_agent_import_failed", error=str(e))

            # Phase 21: DifferentialFixAgent routes gaps to MCP Orchestrator
            try:
                from ..agents.differential_fix_agent import DifferentialFixAgent
                diff_fix_agent = DifferentialFixAgent(
                    name="DifferentialFix",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                )
                self.agents.append(diff_fix_agent)
                self.logger.info("agent_configured", agent="DifferentialFixAgent")
            except ImportError as e:
                self.logger.warning("differential_fix_agent_import_failed", error=str(e))

        # Phase 23: Add CrossLayerValidationAgent for frontend ↔ backend consistency
        if self.enable_cross_layer_validation:
            try:
                from ..agents.cross_layer_validation_agent import CrossLayerValidationAgent
                cross_layer_agent = CrossLayerValidationAgent(
                    name="CrossLayerValidation",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                )
                self.agents.append(cross_layer_agent)
                self.logger.info("agent_configured", agent="CrossLayerValidationAgent")
            except ImportError as e:
                self.logger.warning("cross_layer_validation_agent_import_failed", error=str(e))

        # Add FullstackVerifierAgent for continuous fullstack verification (termination condition)
        try:
            from ..agents.fullstack_verifier_agent import FullstackVerifierAgent
            fullstack_verifier = FullstackVerifierAgent(
                name="FullstackVerifier",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                check_interval=30.0,  # Check every 30 seconds
            )
            self.agents.append(fullstack_verifier)
            self.logger.info("agent_configured", agent="FullstackVerifierAgent")
        except ImportError as e:
            self.logger.warning("fullstack_verifier_agent_import_failed", error=str(e))

        # Add ContinuousArchitectAgent for contract refinement based on verification feedback
        try:
            from ..agents.continuous_architect_agent import ContinuousArchitectAgent
            continuous_architect = ContinuousArchitectAgent(
                name="ContinuousArchitect",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                max_refinements=5,  # Prevent infinite refinement loops
            )
            self.agents.append(continuous_architect)
            self.logger.info("agent_configured", agent="ContinuousArchitectAgent")
        except ImportError as e:
            self.logger.warning("continuous_architect_agent_import_failed", error=str(e))

        # Add DatabaseSeedAgent for seeding database with demo data
        try:
            from ..agents.database_seed_agent import DatabaseSeedAgent
            database_seed = DatabaseSeedAgent(
                name="DatabaseSeed",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(database_seed)
            self.logger.info("agent_configured", agent="DatabaseSeedAgent")
        except ImportError as e:
            self.logger.warning("database_seed_agent_import_failed", error=str(e))

        # Add PermissionsSeedAgent for seeding roles, permissions, and admin user
        try:
            from ..agents.permissions_seed_agent import PermissionsSeedAgent
            permissions_seed = PermissionsSeedAgent(
                name="PermissionsSeed",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(permissions_seed)
            self.logger.info("agent_configured", agent="PermissionsSeedAgent")
        except ImportError as e:
            self.logger.warning("permissions_seed_agent_import_failed", error=str(e))

        # MCP Proxy Agent for event-triggered MCP tool spawning
        try:
            from ..agents.mcp_proxy_agent import MCPProxyAgent
            mcp_proxy = MCPProxyAgent(
                name="MCPProxy",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(mcp_proxy)
            self.logger.info(
                "agent_configured",
                agent="MCPProxyAgent",
                available_mcp_agents=len(mcp_proxy.pool.list_available()),
            )
        except ImportError as e:
            self.logger.warning("mcp_proxy_agent_import_failed", error=str(e))

        # GitPushAgent for autonomous git commit/push after generation
        try:
            from ..agents.git_push_agent import GitPushAgent

            # Read auto_push config from environment
            auto_push = os.environ.get("GIT_AUTO_PUSH", "false").lower() == "true"
            create_feature_branch = os.environ.get("GIT_FEATURE_BRANCH", "true").lower() == "true"

            git_push_agent = GitPushAgent(
                name="GitPush",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
                auto_push=auto_push,
                create_feature_branch=create_feature_branch,
            )
            self.agents.append(git_push_agent)
            self.logger.info(
                "agent_configured",
                agent="GitPushAgent",
                auto_push=auto_push,
                create_feature_branch=create_feature_branch,
            )
        except ImportError as e:
            self.logger.warning("git_push_agent_import_failed", error=str(e))

        # =====================================================================
        # Emergent System Agents: TreeQuest Verification + ShinkaEvolve
        # =====================================================================

        # TreeQuest Verification Agent - code vs docs consistency checking
        try:
            from ..agents.treequest_verification_agent import TreeQuestVerificationAgent
            treequest_agent = TreeQuestVerificationAgent(
                name="TreeQuestVerification",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(treequest_agent)
            self.logger.info("agent_configured", agent="TreeQuestVerificationAgent")
        except ImportError as e:
            self.logger.warning("treequest_verification_agent_import_failed", error=str(e))

        # ShinkaEvolve Agent - evolutionary code improvement when fixers fail
        try:
            from ..agents.shinka_evolve_agent import ShinkaEvolveAgent
            shinka_agent = ShinkaEvolveAgent(
                name="ShinkaEvolve",
                event_bus=self.event_bus,
                shared_state=self.shared_state,
                working_dir=self.working_dir,
            )
            self.agents.append(shinka_agent)
            self.logger.info("agent_configured", agent="ShinkaEvolveAgent")
        except ImportError as e:
            self.logger.warning("shinka_evolve_agent_import_failed", error=str(e))

    def _setup_event_interpreter(self) -> None:
        """
        Initialize the Event Interpreter (Handoffs Pattern) for intelligent event routing.

        The Event Interpreter acts as a triage agent that:
        1. Receives ALL events from the EventBus
        2. Makes intelligent routing decisions (LLM or rule-based)
        3. Delegates tasks to specialist agents via Handoffs pattern
        4. Preserves context across handoffs
        """
        from ..agents.event_interpreter_agent import EventInterpreterAgent

        self.logger.info(
            "setting_up_event_interpreter",
            use_llm_routing=self.use_llm_routing,
        )

        # Create the Event Interpreter
        self.event_interpreter = EventInterpreterAgent(
            event_bus=self.event_bus,
            shared_state=self.shared_state,
            working_dir=self.working_dir,
            use_llm_routing=self.use_llm_routing,
            llm_client=None,  # Will use default Anthropic client if LLM routing enabled
        )

        # Register specialist handlers with the Event Interpreter
        # Each handler wraps the agent's act() method to accept EventTask
        self._register_specialist_handlers()

        self.logger.info(
            "event_interpreter_configured",
            specialists_registered=len(self.event_interpreter._specialist_handlers),
        )

    def _register_specialist_handlers(self) -> None:
        """
        Register specialist agent handlers with the Event Interpreter.

        This maps agent names to their topic types and creates wrapper
        handlers that convert EventTask to the format agents expect.
        """
        # Mapping of topic types to agent names
        topic_to_agent = {
            TopicType.GENERATOR.value: "Generator",
            TopicType.TESTER.value: "TesterTeam",
            TopicType.VALIDATOR.value: "Validator",
            TopicType.DEPLOYER.value: "DeploymentTeam",
            TopicType.DEBUGGER.value: "ContinuousDebug",
            TopicType.UX_REVIEWER.value: "UXDesigner",
            # Backend specialist agents
            TopicType.DATABASE.value: "DatabaseAgent",
            TopicType.API.value: "APIAgent",
            TopicType.AUTH.value: "AuthAgent",
            TopicType.INFRASTRUCTURE.value: "InfrastructureAgent",
        }

        for topic, agent_name in topic_to_agent.items():
            agent = self._agent_map.get(agent_name)
            if agent:
                # Create a wrapper handler that converts EventTask to Event
                # Use closure to capture the agent reference
                handler = self._create_specialist_handler(agent)
                self.event_interpreter.register_specialist(topic, handler)
                self.logger.debug(
                    "specialist_registered",
                    topic=topic,
                    agent=agent_name,
                )

    def _create_specialist_handler(self, agent: "AutonomousAgent"):
        """
        Create a handler function for a specialist agent.

        This wrapper converts EventTask to Event format for legacy agent compatibility.
        """
        async def handler(task: EventTask) -> AgentResponse:
            """Handle delegated task from Event Interpreter."""
            # Convert EventTask back to Event for legacy agent compatibility
            try:
                event_type = EventType(task.event_type)
            except ValueError:
                event_type = EventType.AGENT_ACTING

            event = Event(
                type=event_type,
                source=task.event_source,
                data=task.event_data,
            )

            # Trigger the agent's action
            try:
                # Use the agent's should_act and act methods
                if await agent.should_act(event):
                    result = await agent.act()
                    return AgentResponse(
                        reply_from_topic=agent.name,
                        result={"action_result": result} if result else {},
                        success=True,
                        context=task.context,
                    )
                else:
                    return AgentResponse(
                        reply_from_topic=agent.name,
                        result={"skipped": True, "reason": "should_act returned False"},
                        success=True,
                        context=task.context,
                    )
            except Exception as e:
                self.logger.error(
                    "specialist_handler_error",
                    agent=agent.name,
                    error=str(e),
                )
                return AgentResponse(
                    reply_from_topic=agent.name,
                    result={},
                    success=False,
                    error_message=str(e),
                    context=task.context,
                )

        return handler

    def _setup_mcp_event_bridge(self) -> None:
        """
        Initialize the MCP Event Bridge for bidirectional EventBus <-> MCP Orchestrator integration.

        Phase 16: The Event Bridge provides:
        1. Event subscriptions that automatically trigger MCP tasks
        2. MCP task results published back to EventBus
        3. Task-to-Event mapping for coordinated automation

        Example flow:
        - DEPLOY_STARTED event -> MCP task "Start Docker containers" -> MCP_DOCKER_COMPOSE_UP event
        - BUILD_STARTED event -> MCP task "Run npm build" -> MCP_NPM_BUILD_COMPLETE event
        """
        try:
            from ..mcp.event_bridge import MCPEventBridge, get_event_bridge

            self.logger.info("setting_up_mcp_event_bridge")

            # Create bridge with our event bus and auto-publishing enabled
            self.mcp_event_bridge = MCPEventBridge(
                event_bus=self.event_bus,
                orchestrator=None,  # Will use global orchestrator
                auto_publish=True,
            )

            # Note: We don't call bridge.start() here because that subscribes to events
            # which should happen during run() to avoid premature event handling.
            # The bridge is available for manual task execution immediately.

            self.logger.info(
                "mcp_event_bridge_configured",
                mappings=len(self.mcp_event_bridge.mappings),
                auto_publish=True,
            )

        except ImportError as e:
            self.logger.warning("mcp_event_bridge_import_failed", error=str(e))
            self.mcp_event_bridge = None
        except Exception as e:
            self.logger.error("mcp_event_bridge_setup_error", error=str(e))
            self.mcp_event_bridge = None

    async def start_mcp_event_bridge(self) -> None:
        """Start the MCP Event Bridge subscriptions."""
        if self.mcp_event_bridge:
            await self.mcp_event_bridge.start()
            self.logger.info("mcp_event_bridge_started")

    async def stop_mcp_event_bridge(self) -> None:
        """Stop the MCP Event Bridge."""
        if self.mcp_event_bridge:
            await self.mcp_event_bridge.stop()
            self.logger.info("mcp_event_bridge_stopped")

    async def execute_mcp_task(self, task: str, context: dict = None) -> Any:
        """
        Execute an MCP task directly via the bridge.

        This is a convenience method for manual task execution from the orchestrator.

        Args:
            task: Natural language task description
            context: Optional task context

        Returns:
            TaskResult from MCP Orchestrator
        """
        if not self.mcp_event_bridge:
            self.logger.warning("mcp_task_no_bridge")
            return None

        return await self.mcp_event_bridge.execute_task(task, context or {})

    def add_agent(self, agent: "AutonomousAgent") -> None:
        """
        Add an external agent to the orchestrator.

        This allows integration code to add additional agents after
        orchestrator initialization.

        Args:
            agent: The autonomous agent to add
        """
        if agent.name in self._agent_map:
            self.logger.warning("agent_already_exists", agent=agent.name)
            return

        self.agents.append(agent)
        self._agent_map[agent.name] = agent
        self.logger.debug("agent_configured", agent=agent.name)

    def _inject_skills_to_agents(self) -> None:
        """
        Inject skills into agents based on skill-agent mapping.

        Uses the SkillRegistry's AGENT_SKILL_MAPPING to find the
        appropriate skill for each agent and assigns it to the agent's
        skill property (if the agent supports it).

        This enables progressive disclosure - agents only load full
        skill instructions when they need to act, saving ~75% tokens
        in idle state.
        """
        if not self.skill_registry:
            return

        injected_count = 0

        for agent in self.agents:
            # Try to get skill for this agent type
            skill = self.skill_registry.get_skill_for_agent(agent.name)

            if skill:
                # Check if agent has skill property (duck typing)
                if hasattr(agent, 'skill'):
                    agent.skill = skill
                    injected_count += 1
                    self.logger.debug(
                        "skill_injected",
                        agent=agent.name,
                        skill=skill.name,
                        tokens=skill.instruction_tokens,
                    )
                else:
                    self.logger.debug(
                        "agent_no_skill_property",
                        agent=agent.name,
                        skill=skill.name,
                    )

        if injected_count > 0:
            self.logger.info(
                "skills_injected_to_agents",
                agents_with_skills=injected_count,
                total_agents=len(self.agents),
            )

    async def _on_state_change(self, metrics: ConvergenceMetrics, event: Event = None) -> None:
        """Handle state changes."""
        # Get agent name from event source (de-HTMLize)
        agent_name = event.source if event and event.source != "__orchestrator" else "Orchestrator"

        if self.progress_callback:
            progress = get_progress_percentage(metrics, self.criteria)
            try:
                result = self.progress_callback(metrics, progress)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error("progress_callback_error", error=str(e))

        # Publish convergence update event immediately
        if event:  # Only publish if we have an event context
            await self.event_bus.publish(Event(
                type=EventType.CONVERGENCE_UPDATE_PUSH,
                source=f"agent_{agent_name}",
                data=metrics.to_dict(),
                priority=10
            ))

        # Store convergence metrics every 5 iterations or if converged
        if self.memory_tool and (metrics.iteration % 5 == 0 or metrics.confidence_score >= 0.9):
            try:
                converged, blocking_reasons = await self._check_convergence()
                project_name = os.path.basename(self.working_dir)

                await self.memory_tool.store_convergence_metrics(
                    project_name=project_name,
                    iteration=metrics.iteration,
                    confidence_score=metrics.confidence_score,
                    test_pass_rate=metrics.test_pass_rate,
                    build_success=metrics.build_success,
                    validation_errors=metrics.validation_errors,
                    type_errors=metrics.type_errors,
                    converged=converged,
                    blocking_reasons=blocking_reasons if not converged else None
                )
                self.logger.debug("convergence_metrics_stored", iteration=metrics.iteration)
            except Exception as e:
                self.logger.warning("convergence_metrics_store_failed", error=str(e))

    def _on_event(self, event: Event) -> None:
        """Log all events for debugging."""
        self.logger.debug(
            "event_observed",
            event_type=event.type.value,
            source=event.source,
            success=event.success,
        )

    async def _check_convergence(self) -> tuple[bool, list[str]]:
        """Check if the system has converged."""
        if not self._start_time:
            return False, ["Not started"]

        elapsed = (datetime.now() - self._start_time).total_seconds()
        return is_converged(
            self.shared_state.metrics,
            self.criteria,
            elapsed,
        )

    def _on_agent_acting(self, event: Event) -> None:
        """Track when an agent starts acting."""
        self._active_agents.add(event.source)
        self._last_activity_time = datetime.now()

    def _on_agent_idle(self, event: Event) -> None:
        """Track when an agent becomes idle."""
        self._active_agents.discard(event.source)
        self._last_activity_time = datetime.now()

    def _is_system_idle(self) -> bool:
        """Check if all agents are idle."""
        return len(self._active_agents) == 0

    def _get_idle_duration(self) -> float:
        """Get seconds since last activity."""
        return (datetime.now() - self._last_activity_time).total_seconds()

    async def _run_iteration_loop(self) -> None:
        """
        Run the main iteration loop.
        
        ARCHITECTURE v2.0: Idle-based convergence checking
        - Only checks convergence when system is idle
        - Waits for minimum idle duration before checking
        - More efficient than fixed 2s interval
        - FIX-C: Waits for first build before convergence checks
        """
        min_idle_for_check = 2.0  # Seconds of idle time before convergence check
        
        # FIX-C: Don't start convergence checking until first build is attempted
        first_build_seen = False

        while not self._should_stop:
            # Check if generator is pending - wait for it before iterating
            if self.shared_state.metrics.generator_pending:
                self.logger.debug(
                    "waiting_for_generator",
                    started_at=self.shared_state.metrics.generator_started_at,
                )
                await asyncio.sleep(1.0)
                continue

            # FIX-C: Wait for first build before checking convergence
            if not first_build_seen:
                if self.shared_state.metrics.build_attempted:
                    first_build_seen = True
                    self.logger.info("first_build_completed", waiting_for_convergence=True)
                else:
                    # FIX-F: Check max_time even while waiting for first build
                    if self._start_time and self.criteria.max_time_seconds:
                        elapsed = (datetime.now() - self._start_time).total_seconds()
                        if elapsed >= self.criteria.max_time_seconds:
                            self.logger.warning(
                                "max_time_reached_before_build",
                                elapsed=elapsed,
                                max_time=self.criteria.max_time_seconds,
                            )
                            break  # Exit loop - convergence check will happen in finally
                    
                    # Still waiting for first build - don't iterate yet
                    await asyncio.sleep(1.0)
                    continue

            # PUSH ARCHITECTURE: Only check convergence when system is idle
            if self.use_push_architecture:
                if not self._is_system_idle():
                    # System is busy, wait briefly and continue
                    await asyncio.sleep(self._idle_check_interval)
                    continue

                # System is idle, check if it's been idle long enough
                idle_duration = self._get_idle_duration()
                if idle_duration < min_idle_for_check:
                    await asyncio.sleep(min_idle_for_check - idle_duration)
                    continue

            # Increment iteration
            iteration = await self.shared_state.increment_iteration()

            # Enhanced iteration logging
            metrics = self.shared_state.metrics
            self.logger.info("=" * 70)
            self.logger.info(
                "[ITER] CONVERGENCE_ITERATION",
                iteration=iteration,
                max_iterations=self.criteria.max_iterations if self.criteria else "N/A",
                build_pass_rate=f"{metrics.build_pass_rate:.1%}" if metrics.build_pass_rate else "N/A",
                test_pass_rate=f"{metrics.test_pass_rate:.1%}" if metrics.test_pass_rate else "N/A",
                type_errors=metrics.type_error_count,
                confidence=f"{metrics.confidence_score:.2f}",
                active_agents=len(self._active_agents) if self.use_push_architecture else "N/A",
            )
            self.logger.info("=" * 70)

            # Check convergence
            converged, reasons = await self._check_convergence()
            if converged:
                self.logger.info("[OK] CONVERGENCE_REACHED", reasons=reasons)
                # Publish CONVERGENCE_ACHIEVED event for persistent deployment
                await self.event_bus.publish(Event(
                    type=EventType.CONVERGENCE_ACHIEVED,
                    source="Orchestrator",
                    success=True,
                    data={
                        "iteration": iteration,
                        "reasons": reasons,
                        "metrics": self.shared_state.metrics.to_dict() if hasattr(self.shared_state.metrics, 'to_dict') else {},
                    },
                ))
                break

            # Check if system is stuck (deadlock detected)
            if self.shared_state.metrics.is_stuck:
                self.logger.warning(
                    "system_stuck_detected",
                    consecutive_errors=self.shared_state.metrics.consecutive_same_errors,
                )
                # Convergence check will handle this based on criteria

            # Log blocking reasons periodically
            if iteration % 5 == 0 and reasons:
                self.logger.info("convergence_blocked", reasons=reasons[:3])

            # LEGACY: Fixed wait interval (only if not using push architecture)
            if not self.use_push_architecture:
                await asyncio.sleep(2.0)

    async def _bootstrap_file_events(self) -> int:
        """
        Scan working directory for existing code files and publish FILE_CREATED events.
        
        This bootstraps the Society Phase by ensuring all agents are aware of files
        that were created during the Initial Generation phase, even if no events
        were published at that time.
        
        ARCHITECTURE v2.0: Batched bootstrap events
        - Publishes events in batches to avoid overwhelming agents
        - Uses EVENT_BATCH_CREATED for efficient batch notification
        
        Returns:
            Number of FILE_CREATED events published
        """
        working_path = Path(self.working_dir)
        file_paths = []
        
        self.logger.debug("bootstrap_scanning", working_dir=str(working_path))
        
        try:
            for file_path in working_path.rglob("*"):
                # Skip directories
                if not file_path.is_file():
                    continue
                    
                # Skip ignored directories
                if any(ignored in file_path.parts for ignored in IGNORE_DIRS):
                    continue
                    
                # Only process code files
                if file_path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                
                # Get relative path
                try:
                    rel_path = str(file_path.relative_to(working_path))
                    file_paths.append(rel_path)
                except ValueError:
                    continue
                    
        except Exception as e:
            self.logger.warning("bootstrap_scan_error", error=str(e))
            return 0
        
        # PUSH ARCHITECTURE: Batch the events instead of publishing individually
        if self.use_push_architecture and file_paths:
            # Publish a single batch event first
            await self.event_bus.publish(Event(
                type=EventType.FILE_CREATED,
                source="orchestrator_bootstrap",
                data={
                    "trigger": "initial",  # FIX-A: Added for BuilderAgent.should_act()
                    "bootstrap": True,
                    "batch": True,
                    "file_count": len(file_paths),
                    "files": file_paths[:50],  # Include first 50 for context
                },
            ))
            self.logger.info("bootstrap_batch_published", file_count=len(file_paths))
        else:
            # LEGACY: Publish individual events
            for rel_path in file_paths:
                await self.event_bus.publish(Event(
                    type=EventType.FILE_CREATED,
                    source="orchestrator_bootstrap",
                    file_path=rel_path,
                    data={"bootstrap": True},
                ))
                
                # Log progress every 50 files
                if len(file_paths) % 50 == 0:
                    self.logger.debug("bootstrap_progress", files=len(file_paths))
                    
        return len(file_paths)

    # =========================================================================
    # ASYNC SERVICES - Run continuously parallel to Phase 3 Loop
    # =========================================================================

    async def _run_async_e2e_tests(self) -> None:
        """
        Run E2E tests continuously in the background.

        This async service runs parallel to the Phase 3 convergence loop.
        It executes E2E tests at regular intervals and reports results
        to the EventBus, allowing the GeneratorAgent to fix failures.

        Includes circuit breaker with exponential backoff on repeated failures.
        """
        self.logger.info(
            "async_e2e_service_started",
            interval=self.async_e2e_interval,
        )

        await self.event_bus.publish(Event(
            type=EventType.ASYNC_E2E_STARTED,
            source="Orchestrator",
            data={"interval": self.async_e2e_interval},
        ))

        cycle_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        base_backoff = 5.0
        max_backoff = 300.0  # 5 minutes max

        while not self._should_stop:
            try:
                # Wait for the configured interval
                await asyncio.sleep(self.async_e2e_interval)

                if self._should_stop:
                    break

                cycle_count += 1
                self.logger.info("async_e2e_cycle_starting", cycle=cycle_count)

                # Find and run E2E agent if available
                e2e_agent = self._agent_map.get("TesterTeam") or self._agent_map.get("PlaywrightE2E")

                if e2e_agent:
                    # Trigger E2E testing via event
                    await self.event_bus.publish(Event(
                        type=EventType.E2E_TEST_STARTED,
                        source="AsyncE2EService",
                        data={
                            "cycle": cycle_count,
                            "async_service": True,
                        },
                    ))

                    # The agent will respond to the event and publish results
                    # (E2E_TEST_PASSED or E2E_TEST_FAILED)
                else:
                    self.logger.warning("async_e2e_no_agent_found")

                # Publish cycle completion event
                await self.event_bus.publish(Event(
                    type=EventType.ASYNC_E2E_CYCLE_COMPLETE,
                    source="AsyncE2EService",
                    data={"cycle": cycle_count},
                ))

                # Reset error count on success
                consecutive_errors = 0

            except asyncio.CancelledError:
                self.logger.info("async_e2e_service_cancelled")
                break
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(
                    "async_e2e_service_error",
                    error=str(e),
                    consecutive_errors=consecutive_errors,
                )

                # Circuit breaker: stop after too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error(
                        "async_e2e_circuit_breaker_open",
                        message="Too many consecutive errors, stopping service",
                        errors=consecutive_errors,
                    )
                    break

                # Exponential backoff
                backoff = min(base_backoff * (2 ** (consecutive_errors - 1)), max_backoff)
                self.logger.warning(
                    "async_e2e_backoff",
                    backoff_seconds=backoff,
                    retry_count=consecutive_errors,
                )
                await asyncio.sleep(backoff)

        self.logger.info("async_e2e_service_stopped", cycles_completed=cycle_count)

    async def _run_async_ux_review(self) -> None:
        """
        Run UX review continuously in the background.

        This async service runs parallel to the Phase 3 convergence loop.
        It captures screenshots and analyzes them with Claude Vision
        at regular intervals, reporting UX issues to the EventBus.

        Includes circuit breaker with exponential backoff on repeated failures.
        """
        self.logger.info(
            "async_ux_service_started",
            interval=self.async_ux_interval,
        )

        await self.event_bus.publish(Event(
            type=EventType.ASYNC_UX_STARTED,
            source="Orchestrator",
            data={"interval": self.async_ux_interval},
        ))

        cycle_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        base_backoff = 5.0
        max_backoff = 300.0  # 5 minutes max

        while not self._should_stop:
            try:
                # Wait for the configured interval
                await asyncio.sleep(self.async_ux_interval)

                if self._should_stop:
                    break

                cycle_count += 1
                self.logger.info("async_ux_cycle_starting", cycle=cycle_count)

                # Find UX agent if available
                ux_agent = self._agent_map.get("UXDesigner")

                if ux_agent:
                    # Trigger UX review via event - simulates E2E screenshot taken
                    await self.event_bus.publish(Event(
                        type=EventType.E2E_SCREENSHOT_TAKEN,
                        source="AsyncUXService",
                        data={
                            "cycle": cycle_count,
                            "async_service": True,
                            "request_full_review": True,
                        },
                    ))

                    # The UX agent will respond and publish results
                    # (UX_ISSUE_FOUND or UX_REVIEW_PASSED)
                else:
                    self.logger.warning("async_ux_no_agent_found")

                # Publish cycle completion event
                await self.event_bus.publish(Event(
                    type=EventType.ASYNC_UX_CYCLE_COMPLETE,
                    source="AsyncUXService",
                    data={"cycle": cycle_count},
                ))

                # Reset error count on success
                consecutive_errors = 0

            except asyncio.CancelledError:
                self.logger.info("async_ux_service_cancelled")
                break
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(
                    "async_ux_service_error",
                    error=str(e),
                    consecutive_errors=consecutive_errors,
                )

                # Circuit breaker: stop after too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error(
                        "async_ux_circuit_breaker_open",
                        message="Too many consecutive errors, stopping service",
                        errors=consecutive_errors,
                    )
                    break

                # Exponential backoff
                backoff = min(base_backoff * (2 ** (consecutive_errors - 1)), max_backoff)
                self.logger.warning(
                    "async_ux_backoff",
                    backoff_seconds=backoff,
                    retry_count=consecutive_errors,
                )
                await asyncio.sleep(backoff)

        self.logger.info("async_ux_service_stopped", cycles_completed=cycle_count)

    async def _start_async_services(self) -> None:
        """
        Start all enabled async services as background tasks.

        These services run continuously parallel to the Phase 3 loop
        until convergence is reached or the orchestrator stops.
        """
        self._async_service_tasks = []

        # Start Event Interpreter processing loop if enabled
        if self.enable_event_interpreter and self.event_interpreter:
            task = asyncio.create_task(self.event_interpreter.start_processing())
            task.set_name("event_interpreter_service")
            self._async_service_tasks.append(task)
            self.logger.info("async_service_task_created", service="event_interpreter")

        if self.enable_async_e2e:
            task = asyncio.create_task(self._run_async_e2e_tests())
            task.set_name("async_e2e_service")
            self._async_service_tasks.append(task)
            self.logger.info("async_service_task_created", service="e2e")

        if self.enable_async_ux:
            task = asyncio.create_task(self._run_async_ux_review())
            task.set_name("async_ux_service")
            self._async_service_tasks.append(task)
            self.logger.info("async_service_task_created", service="ux")

        if self._async_service_tasks:
            services_list = []
            if self.enable_event_interpreter:
                services_list.append("event_interpreter")
            if self.enable_async_e2e:
                services_list.append("e2e")
            if self.enable_async_ux:
                services_list.append("ux")
            self.logger.info(
                "async_services_started",
                count=len(self._async_service_tasks),
                services=services_list,
            )

    async def _stop_async_services(self) -> None:
        """
        Cancel all running async service tasks.

        Called when convergence is reached or orchestrator stops.
        """
        # Stop Event Interpreter first if enabled
        if self.enable_event_interpreter and self.event_interpreter:
            await self.event_interpreter.stop_processing()
            self.logger.info("event_interpreter_stopped")

        if not self._async_service_tasks:
            return

        self.logger.info(
            "stopping_async_services",
            count=len(self._async_service_tasks),
        )

        for task in self._async_service_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._async_service_tasks = []
        self.logger.info("async_services_stopped")

    async def run(self) -> OrchestratorResult:
        """
        Run the orchestrator until convergence.

        Returns:
            OrchestratorResult with final state
        """
        self._start_time = datetime.now()
        await self.shared_state.start()

        # Enhanced startup logging
        self.logger.info("=" * 70)
        self.logger.info(
            "[ORCH] ORCHESTRATOR_STARTING",
            agents=len(self.agents),
            max_iterations=self.criteria.max_iterations if self.criteria else "N/A",
            architecture="push" if self.use_push_architecture else "poll",
        )
        self.logger.info("=" * 70)

        # Start monitoring if enabled
        if self.monitor:
            self.monitor.start()

        errors = []

        try:
            # Start all agents with enhanced logging
            self.logger.info("[REG] REGISTERING_AGENTS", count=len(self.agents))
            for agent in self.agents:
                await agent.start()
                triggers = [e.value for e in agent.subscribed_events]
                self.logger.info(
                    "[REG] AGENT_REGISTERED",
                    agent=agent.name,
                    triggers=triggers[:3],  # First 3 triggers
                    total_triggers=len(triggers),
                )

            # Bootstrap: Scan for existing code files and publish FILE_CREATED events
            # This ensures agents react to files generated by Initial Phase
            bootstrap_count = await self._bootstrap_file_events()
            
            if bootstrap_count > 0:
                self.logger.info("bootstrap_complete", files_published=bootstrap_count)
                # Give agents time to process bootstrap events
                await asyncio.sleep(1.0)

                # Publish GENERATION_COMPLETE to trigger post-generation agents
                # (InfrastructureAgent, SecurityScannerAgent, etc.)
                await self.event_bus.publish(Event(
                    type=EventType.GENERATION_COMPLETE,
                    source="orchestrator",
                    data={
                        "files_count": bootstrap_count,
                        "trigger": "bootstrap_complete",
                    },
                ))
                self.logger.info(
                    "generation_complete_published",
                    files_count=bootstrap_count,
                    triggers=["InfrastructureAgent", "SecurityScannerAgent", "UIIntegrationAgent"],
                )
            else:
                # No files found - publish initial trigger event as fallback
                self.logger.warning("bootstrap_no_files_found", action="publishing_initial_trigger")
                await self.event_bus.publish(Event(
                    type=EventType.FILE_MODIFIED,
                    source="orchestrator",
                    data={"trigger": "initial"},
                ))
            
            # FIX-D: Reset activity time after bootstrap to prevent premature convergence checks
            # Without this, idle_duration would already be 3+ seconds from init time
            self._last_activity_time = datetime.now()
            self.logger.debug("activity_time_reset", reason="post_bootstrap")

            # Start async services (E2E, UX) - run parallel to Phase 3 loop
            await self._start_async_services()

            # Start MCP Event Bridge subscriptions (Phase 16)
            await self.start_mcp_event_bridge()

            # Start Container Log Seeder subscriptions
            if self.container_log_seeder:
                await self.container_log_seeder.subscribe_to_events()
                self.logger.info("container_log_seeder_subscribed")

            # Start Error Receiver Server for client-side JS error reporting
            if self.enable_error_receiver:
                try:
                    from ..monitoring.error_receiver_server import ErrorReceiverServer
                    self.error_receiver_server = ErrorReceiverServer(
                        event_bus=self.event_bus,
                        port=8765,
                    )
                    await self.error_receiver_server.start()
                    self.logger.info("error_receiver_server_started", port=8765)
                except Exception as e:
                    self.logger.warning("error_receiver_server_start_failed", error=str(e))

            # Run the iteration loop
            await self._run_iteration_loop()

        except Exception as e:
            errors.append(str(e))
            self.logger.error("orchestrator_error", error=str(e))

        finally:
            # Stop Error Receiver Server
            if self.error_receiver_server:
                try:
                    await self.error_receiver_server.stop()
                    self.logger.info("error_receiver_server_stopped")
                except Exception as e:
                    self.logger.warning("error_receiver_server_stop_failed", error=str(e))

            # Stop MCP Event Bridge (Phase 16)
            await self.stop_mcp_event_bridge()

            # Stop async services (E2E, UX) first
            await self._stop_async_services()

            # Stop monitoring if enabled
            if self.monitor:
                self.monitor.stop()

            # Stop all agents
            self.logger.info("stopping_agents")
            for agent in self.agents:
                try:
                    await agent.stop()
                except Exception as e:
                    errors.append(f"Failed to stop {agent.name}: {e}")

            # Print monitoring summary if enabled
            if self.monitor:
                self.monitor.print_summary()

        # Calculate final results
        duration = (datetime.now() - self._start_time).total_seconds()
        converged, reasons = await self._check_convergence()

        result = OrchestratorResult(
            success=converged and not errors,
            converged=converged,
            convergence_reasons=reasons,
            final_metrics=self.shared_state.metrics,
            iterations=self.shared_state.metrics.iteration,
            duration_seconds=duration,
            errors=errors,
        )

        self.logger.info("=" * 70)
        self.logger.info(
            "[ORCH] ORCHESTRATOR_COMPLETE",
            success=result.success,
            converged=result.converged,
            iterations=result.iterations,
            duration_seconds=f"{duration:.1f}s",
            final_confidence=f"{result.final_metrics.confidence_score:.2f}" if result.final_metrics else "N/A",
            errors_count=len(errors),
        )
        self.logger.info("=" * 70)

        # Store final project generation results in memory
        if self.memory_tool:
            try:
                project_name = os.path.basename(self.working_dir)
                working_path = Path(self.working_dir)

                # Count generated files
                files_generated = 0
                if working_path.exists():
                    files_generated = len(list(working_path.rglob("*"))) - len(list(working_path.rglob("node_modules/*")))

                # Build key insights
                insights_parts = []
                if result.success:
                    insights_parts.append(f"Successfully converged in {result.iterations} iterations")
                else:
                    insights_parts.append(f"Did not converge after {result.iterations} iterations")

                if result.final_metrics:
                    insights_parts.append(f"Final confidence: {result.final_metrics.confidence_score:.2f}")
                    insights_parts.append(f"Test pass rate: {result.final_metrics.test_pass_rate:.2f}")

                if errors:
                    insights_parts.append(f"Errors encountered: {len(errors)}")

                key_insights = "\n".join(insights_parts)

                await self.memory_tool.store_project_generation(
                    project_name=project_name,
                    project_type=self._detect_project_type(),
                    requirements_count=0,  # Not tracked here
                    success=result.success,
                    iterations_needed=result.iterations,
                    files_generated=files_generated,
                    converged=result.converged,
                    key_insights=key_insights
                )
                self.logger.info("project_generation_stored", project_name=project_name)
            except Exception as e:
                self.logger.warning("project_generation_store_failed", error=str(e))

        # Publish final event
        await self.event_bus.publish(Event(
            type=EventType.SYSTEM_READY if result.success else EventType.SYSTEM_ERROR,
            source="orchestrator",
            success=result.success,
            data=result.to_dict(),
        ))

        return result

    def _detect_project_type(self) -> str:
        """Detect project type from working directory."""
        working_path = Path(self.working_dir)

        if (working_path / "package.json").exists():
            # Check if electron project
            try:
                import json
                with open(working_path / "package.json", "r") as f:
                    pkg = json.load(f)
                    if "electron" in pkg.get("dependencies", {}) or "electron" in pkg.get("devDependencies", {}):
                        return "electron"
            except:
                pass
            return "node"

        if (working_path / "requirements.txt").exists():
            return "python"

        if (working_path / "Cargo.toml").exists():
            return "rust"

        return "unknown"

    async def stop(self) -> None:
        """Stop the orchestrator and all agents."""
        self._should_stop = True
        for agent in self.agents:
            await agent.stop()

    def get_status(self) -> dict:
        """Get current status of the orchestrator and all agents."""
        return {
            "running": not self._should_stop,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "metrics": self.shared_state.metrics.to_dict(),
            "progress": get_progress_percentage(
                self.shared_state.metrics,
                self.criteria,
            ),
            "agents": [agent.status.to_dict() for agent in self.agents],
        }


async def run_society(
    working_dir: str,
    criteria: Optional[ConvergenceCriteria] = None,
    progress_callback: Optional[Callable] = None,
    enable_e2e_testing: bool = False,
    enable_ux_review: bool = False,
    enable_auto_docs: bool = True,
    enable_runtime_debug: bool = True,
    enable_monitoring: bool = True,
    enable_sandbox_testing: bool = False,
    enable_cloud_tests: bool = False,
    enable_continuous_sandbox: bool = False,
    sandbox_cycle_interval: int = 30,
    enable_vnc_streaming: bool = False,
    vnc_port: int = 6080,
    requirements: Optional[list[str]] = None,
    memory_tool: Optional[Any] = None,
    tech_stack: Optional[Any] = None,  # FIX-26: Added tech_stack parameter
    # Async Services: E2E and UX run continuously parallel to Phase 3
    enable_async_e2e: bool = False,
    enable_async_ux: bool = False,
    async_e2e_interval: int = 60,
    async_ux_interval: int = 120,
    # Event Interpreter (Handoffs Pattern)
    enable_event_interpreter: bool = False,
    use_llm_routing: bool = True,
    # Task 17: Backend Agent Feature Flags
    enable_database_generation: bool = True,
    enable_api_generation: bool = True,
    enable_auth_setup: bool = True,
    enable_infrastructure_setup: bool = True,
    # Phase 10: Security & Dependency Management flags
    enable_security_scanning: bool = True,
    enable_dependency_management: bool = True,
    # Task 24: Browser Console & Validation Recovery flags
    enable_browser_console: bool = True,
    enable_validation_recovery: bool = True,
) -> OrchestratorResult:
    """
    Convenience function to run the Society of Mind.

    Args:
        working_dir: Project working directory
        criteria: Optional convergence criteria
        progress_callback: Optional progress callback
        enable_e2e_testing: Enable E2E testing with Playwright
        enable_ux_review: Enable UX design review agent
        enable_auto_docs: Enable auto-generation of CLAUDE.md (default: True)
        enable_runtime_debug: Enable runtime debugging agent (default: True)
        enable_monitoring: Enable real-time agent monitoring dashboard (default: True)
        enable_sandbox_testing: Enable Docker sandbox deployment testing
        enable_cloud_tests: Enable GitHub Actions cloud testing
        enable_continuous_sandbox: Enable continuous 30-second sandbox test cycle
        sandbox_cycle_interval: Seconds between sandbox test cycles
        enable_vnc_streaming: Enable VNC streaming for Electron apps
        vnc_port: noVNC web port
        requirements: List of requirements for E2E/UX agents
        memory_tool: Optional memory tool for agents to search/store patterns
        tech_stack: Optional TechStack for technology-aware generation (FIX-26)
        enable_async_e2e: Enable continuous async E2E testing (runs parallel to Phase 3)
        enable_async_ux: Enable continuous async UX review (runs parallel to Phase 3)
        async_e2e_interval: Seconds between async E2E test cycles (default: 60)
        async_ux_interval: Seconds between async UX review cycles (default: 120)
        enable_event_interpreter: Enable Event Interpreter (Handoffs Pattern) for intelligent routing
        use_llm_routing: Use LLM for routing decisions (default: True), False = rule-based only
        enable_database_generation: Enable DatabaseAgent for schema generation (default: True)
        enable_api_generation: Enable APIAgent for REST endpoint generation (default: True)
        enable_auth_setup: Enable AuthAgent for authentication setup (default: True)
        enable_infrastructure_setup: Enable InfrastructureAgent for env/docker/CI config (default: True)

    Returns:
        OrchestratorResult
    """
    orchestrator = Orchestrator(
        working_dir=working_dir,
        criteria=criteria,
        progress_callback=progress_callback,
        enable_e2e_testing=enable_e2e_testing,
        enable_ux_review=enable_ux_review,
        enable_auto_docs=enable_auto_docs,
        enable_runtime_debug=enable_runtime_debug,
        enable_monitoring=enable_monitoring,
        enable_sandbox_testing=enable_sandbox_testing,
        enable_cloud_tests=enable_cloud_tests,
        enable_continuous_sandbox=enable_continuous_sandbox,
        sandbox_cycle_interval=sandbox_cycle_interval,
        enable_vnc_streaming=enable_vnc_streaming,
        vnc_port=vnc_port,
        requirements=requirements,
        memory_tool=memory_tool,
        tech_stack=tech_stack,  # FIX-26: Pass tech_stack
        enable_async_e2e=enable_async_e2e,
        enable_async_ux=enable_async_ux,
        async_e2e_interval=async_e2e_interval,
        async_ux_interval=async_ux_interval,
        enable_event_interpreter=enable_event_interpreter,
        use_llm_routing=use_llm_routing,
        # Task 17: Backend Agent Feature Flags
        enable_database_generation=enable_database_generation,
        enable_api_generation=enable_api_generation,
        enable_auth_setup=enable_auth_setup,
        enable_infrastructure_setup=enable_infrastructure_setup,
        # Phase 10: Security & Dependency Management flags
        enable_security_scanning=enable_security_scanning,
        enable_dependency_management=enable_dependency_management,
        # Task 24: Browser Console & Validation Recovery flags
        enable_browser_console=enable_browser_console,
        enable_validation_recovery=enable_validation_recovery,
    )
    return await orchestrator.run()
