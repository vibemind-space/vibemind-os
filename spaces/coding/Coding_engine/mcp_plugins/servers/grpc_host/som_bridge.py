#!/usr/bin/env python3
"""
SoM Bridge - Universal Society of Mind Integration for Epic Orchestrator.

Bridges the Epic Orchestrator with the Society of Mind agent system:
- Auto-detects project tech stack via ProjectAnalyzer / ProjectProfile
- Translates Epic task results into EventBus events (category-based, framework-agnostic)
- Manages SoM agents (Autogen AG2 0.4.x + Claude CLI) for autonomous debugging/fixing
- Starts Docker sandbox with VNC for live preview (any project type)
- Provides universal verification commands derived from ProjectProfile
- Coordinates SoM auto-fix loop with Epic retry mechanism
"""

import asyncio
import importlib
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.llm_config import get_model

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SoMBridgeConfig:
    """Configuration for Society of Mind bridge integration.

    All feature flags are independently toggleable so the caller can
    enable/disable individual SoM capabilities per project or run.
    """
    # Tier 0: Core agents (always recommended)
    enable_docker_sandbox: bool = True
    enable_vnc_preview: bool = True
    enable_autonomous_debug: bool = True
    enable_dependency_manager: bool = True
    enable_db_migration: bool = True
    enable_docker_diagnostics: bool = True
    enable_preview_monitor: bool = True

    # Tier 1: Standard agents (enabled by default for quality)
    enable_e2e_testing: bool = False   # Off by default (heavy, needs sandbox)
    enable_security_scan: bool = True  # Lightweight, catches common issues

    # Tier 2: Advanced agents
    enable_verification_debate: bool = False
    enable_fullstack_verify: bool = True
    enable_architecture_health: bool = True   # Catch structural issues early
    enable_traceability: bool = False
    enable_mcp_proxy: bool = True
    enable_git_push: bool = False

    # Tier 3: Heavy / conditional agents
    enable_fungus: bool = True                 # Provides context to Kilo via MCP
    enable_fungus_validation: bool = False      # Autonomous MCMP validation (heavy)
    enable_fungus_memory: bool = False          # Memory-augmented MCMP search (needs Qdrant)
    enable_differential_analysis: bool = True   # Docs vs code gap detection — catches schema/service mismatch
    enable_cross_layer_validation: bool = True  # Frontend ↔ Backend consistency — catches API path mismatches
    enable_deployment_team: bool = False
    enable_ux_review: bool = False

    # Docker settings
    sandbox_image: str = "coding-engine/sandbox:latest"
    vnc_port: int = 6081
    app_port: int = 3001

    # Timeouts
    fix_wait_timeout: int = 120
    agent_startup_timeout: int = 30

    # Fungus settings
    fungus_num_agents: int = 200
    fungus_max_iterations: int = 50
    fungus_judge_provider: str = "openrouter"
    fungus_judge_model: str = field(default_factory=lambda: get_model("judge"))


# =============================================================================
# Agent Registry (Autogen AG2 0.4.x + Claude CLI)
# =============================================================================

AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ---- Tier 0: Core agents (7, always recommended) ----
    "generator": {
        "class": "src.agents.generator_agent.GeneratorAgent",
        "config_flag": "enable_autonomous_debug",
        "universal": True,
    },
    "continuous_debug": {
        "class": "src.agents.continuous_debug_agent.ContinuousDebugAgent",
        "config_flag": "enable_autonomous_debug",
        "universal": True,
    },
    "dependency_manager": {
        "class": "src.agents.dependency_manager_agent.DependencyManagerAgent",
        "config_flag": "enable_dependency_manager",
        "universal": True,
    },
    "migration": {
        "class": "src.agents.migration_agent.MigrationAgent",
        "config_flag": "enable_db_migration",
        "universal": True,
    },
    "docker_diagnostic": {
        "class": "src.agents.docker_diagnostic_agent.DockerDiagnosticAgent",
        "config_flag": "enable_docker_diagnostics",
        "universal": True,
    },
    "database_docker": {
        "class": "src.agents.database_docker_agent.DatabaseDockerAgent",
        "config_flag": "enable_db_migration",
        "universal": True,
    },
    "preview_monitor": {
        "class": "src.monitoring.preview_monitor.PreviewMonitor",
        "config_flag": "enable_preview_monitor",
        "universal": True,
    },

    # ---- Tier 1: Standard agents (6, universell, einfach) ----
    "security_scanner": {
        "class": "src.agents.security_scanner_agent.SecurityScannerAgent",
        "config_flag": "enable_security_scan",
        "universal": True,
    },
    "bug_fixer": {
        "class": "src.agents.bug_fixer_agent.BugFixerAgent",
        "config_flag": "enable_autonomous_debug",
        "universal": True,
    },
    "error_context": {
        "class": "src.agents.error_context_agent.ErrorContextAgent",
        "config_flag": "enable_autonomous_debug",
        "universal": True,
    },
    "smart_test_generator": {
        "class": "src.agents.smart_test_generator_agent.SmartTestGeneratorAgent",
        "config_flag": "enable_autonomous_debug",
        "universal": True,
    },
    "database_seed": {
        "class": "src.agents.database_seed_agent.DatabaseSeedAgent",
        "config_flag": "enable_db_migration",
        "universal": True,
    },
    "permissions_seed": {
        "class": "src.agents.permissions_seed_agent.PermissionsSeedAgent",
        "config_flag": "enable_db_migration",
        "universal": True,
    },

    # ---- Tier 2: Advanced agents (7, brauchen neue Flags) ----
    "verification_debate": {
        "class": "src.agents.verification_debate_agent.VerificationDebateAgent",
        "config_flag": "enable_verification_debate",
        "universal": True,
    },
    "fullstack_verifier": {
        "class": "src.agents.fullstack_verifier_agent.FullstackVerifierAgent",
        "config_flag": "enable_fullstack_verify",
        "universal": True,
    },
    "architecture_health": {
        "class": "src.agents.architecture_health_agent.ArchitectureHealthAgent",
        "config_flag": "enable_architecture_health",
        "universal": True,
    },
    "traceability": {
        "class": "src.agents.traceability_agent.TraceabilityAgent",
        "config_flag": "enable_traceability",
        "universal": True,
    },
    "continuous_architect": {
        "class": "src.agents.continuous_architect_agent.ContinuousArchitectAgent",
        "config_flag": "enable_architecture_health",
        "universal": True,
    },
    "mcp_proxy": {
        "class": "src.agents.mcp_proxy_agent.MCPProxyAgent",
        "config_flag": "enable_mcp_proxy",
        "universal": True,
    },
    "git_push": {
        "class": "src.agents.git_push_agent.GitPushAgent",
        "config_flag": "enable_git_push",
        "universal": True,
    },

    # ---- Tier 3: Heavy / conditional agents (5) ----
    "fungus_context": {
        "class": "src.agents.fungus_context_agent.FungusContextAgent",
        "config_flag": "enable_fungus",
        "universal": False,
        "init_kwargs": {},  # populated dynamically in _init_agents
    },
    "fungus_validation": {
        "class": "src.agents.fungus_validation_agent.FungusValidationAgent",
        "config_flag": "enable_fungus_validation",
        "universal": False,
        "init_kwargs": {},
    },
    "fungus_memory": {
        "class": "src.agents.fungus_memory_agent.FungusMemoryAgent",
        "config_flag": "enable_fungus_memory",
        "universal": False,
        "init_kwargs": {},
    },
    "differential_analysis": {
        "class": "src.agents.differential_analysis_agent.DifferentialAnalysisAgent",
        "config_flag": "enable_differential_analysis",
        "universal": False,
        "init_kwargs": {},
    },
    "differential_fix": {
        "class": "src.agents.differential_fix_agent.DifferentialFixAgent",
        "config_flag": "enable_differential_analysis",
        "universal": False,
        "init_kwargs": {},
    },
    "cross_layer_validation": {
        "class": "src.agents.cross_layer_validation_agent.CrossLayerValidationAgent",
        "config_flag": "enable_cross_layer_validation",
        "universal": False,
        "init_kwargs": {},
    },
    "deployment_team": {
        "class": "src.agents.e2e_integration_team_agent.E2EIntegrationTeamAgent",
        "config_flag": "enable_deployment_team",
        "universal": True,
    },
    "ux_design": {
        "class": "src.agents.ux_design_agent.UXDesignAgent",
        "config_flag": "enable_ux_review",
        "universal": True,
    },
    "tester_team": {
        "class": "src.agents.tester_team_agent.TesterTeamAgent",
        "config_flag": "enable_e2e_testing",
        "universal": True,
    },
    "continuous_e2e": {
        "class": "src.agents.continuous_e2e_agent.ContinuousE2EAgent",
        "config_flag": "enable_e2e_testing",
        "universal": True,
        "init_kwargs": {},  # populated dynamically in _init_agents
    },
}


# =============================================================================
# Universal Category-Based Event Mapping
# =============================================================================

def _lazy_event_types():
    """Lazy import EventType to avoid circular imports at module level."""
    from src.mind.event_bus import EventType
    return EventType


def _build_success_map() -> Dict[str, str]:
    """Build category-based success event mapping.

    Uses task type prefixes so any framework's tasks map correctly:
    - schema_model, schema_relations, schema_migration → DATABASE_SCHEMA_GENERATED
    - api_controller, api_service → API_ROUTES_GENERATED
    - fe_page, fe_component, fe_hook → CODE_GENERATED
    """
    ET = _lazy_event_types()
    return {
        # Prefix-based: any task starting with prefix maps to event
        "schema_":          ET.DATABASE_SCHEMA_GENERATED,
        "api_":             ET.API_ROUTES_GENERATED,
        "auth_":            ET.AUTH_SETUP_COMPLETE,
        "fe_":              ET.CODE_GENERATED,
        "test_":            ET.TEST_PASSED,
        "docker_":          ET.DEPLOY_SUCCEEDED,
        "setup_":           ET.PROJECT_SCAFFOLDED,
        # Feature-consolidated task types (from feature mode)
        "api_controller":   ET.API_ROUTES_GENERATED,
        "fe_page":          ET.CODE_GENERATED,
        "test_e2e_happy":   ET.E2E_TEST_PASSED,
        "test_e2e_negative": ET.E2E_TEST_PASSED,
        "test_integration": ET.TEST_PASSED,
        # Infrastructure & env
        "env_":             ET.ENV_CONFIG_GENERATED,
        "migration_":       ET.DATABASE_SCHEMA_GENERATED,
        "infra_":           ET.DOCKER_CONFIG_GENERATED,
        "deps_":            ET.PROJECT_SCAFFOLDED,
        # Exact match: verification tasks
        "verify_build":     ET.BUILD_SUCCEEDED,
        "verify_typecheck": ET.TYPE_CHECK_PASSED,
        "verify_lint":      ET.BUILD_SUCCEEDED,
        "verify_unit":      ET.TEST_PASSED,
        "verify_e2e":       ET.E2E_TEST_PASSED,
        "verify_schema":    ET.DATABASE_SCHEMA_GENERATED,
        "verify_all":       ET.BUILD_SUCCEEDED,
        "integration":      ET.BUILD_SUCCEEDED,
    }


def _build_failure_map() -> Dict[str, str]:
    """Build category-based failure event mapping."""
    ET = _lazy_event_types()
    return {
        "verify_build":     ET.BUILD_FAILED,
        "verify_typecheck": ET.TYPE_ERROR,
        "verify_lint":      ET.BUILD_FAILED,
        "verify_unit":      ET.TEST_FAILED,
        "verify_e2e":       ET.E2E_TEST_FAILED,
        "verify_schema":    ET.DATABASE_SCHEMA_FAILED,
        "verify_all":       ET.BUILD_FAILED,
        "schema_":          ET.DATABASE_SCHEMA_FAILED,
        "docker_":          ET.DEPLOY_FAILED,
        "setup_":           ET.VALIDATION_ERROR,
        "api_":             ET.API_GENERATION_FAILED,
        "auth_":            ET.AUTH_SETUP_FAILED,
        "fe_":              ET.BUILD_FAILED,
        "test_":            ET.TEST_FAILED,
        # Feature-consolidated types
        "api_controller":   ET.API_GENERATION_FAILED,
        "fe_page":          ET.BUILD_FAILED,
        "test_e2e_happy":   ET.E2E_TEST_FAILED,
        "test_e2e_negative": ET.E2E_TEST_FAILED,
        "test_integration": ET.TEST_FAILED,
        "env_":             ET.VALIDATION_ERROR,
        "migration_":       ET.DATABASE_SCHEMA_FAILED,
        "infra_":           ET.DEPLOY_FAILED,
        "deps_":            ET.VALIDATION_ERROR,
        "integration":      ET.BUILD_FAILED,
    }


# =============================================================================
# SoM Bridge
# =============================================================================

class SoMBridge:
    """
    Universal bridge between Epic Orchestrator and Society of Mind agents.

    Responsibilities:
    1. Auto-detect project tech stack (via ProjectAnalyzer)
    2. Start Docker sandbox with VNC (any project type)
    3. Initialize SoM agents as Autogen AG2 0.4.x agents with Claude CLI
    4. Translate task results → EventBus events (category-based prefix matching)
    5. Provide universal verification commands (not hardcoded to npm/prisma)
    6. Coordinate SoM auto-fix loop with Epic retry mechanism
    """

    def __init__(
        self,
        project_path: str,
        output_dir: str,
        config: Optional[SoMBridgeConfig] = None,
    ):
        self.project_path = Path(project_path)
        self.output_dir = Path(output_dir)
        self.config = config or SoMBridgeConfig()

        # Lazy-initialized components
        self._event_bus = None
        self._shared_state = None
        self._memory_tool = None

        # State
        self.agents: Dict[str, Any] = {}
        self.container_id: Optional[str] = None
        self.vnc_port: Optional[int] = None
        self.project_profile = None  # Set during start()
        self._agent_tasks: List[asyncio.Task] = []
        self._fix_events: Dict[str, asyncio.Event] = {}
        self._started = False

        # Lazy event maps (built on first use)
        self._success_map: Optional[Dict] = None
        self._failure_map: Optional[Dict] = None

        # Project name for container naming
        self.project_name = self.output_dir.name or "project"

        logger.info(
            f"SoMBridge initialized | project={project_path} | output={output_dir}"
        )

    # =========================================================================
    # Properties (lazy-loaded to avoid import issues)
    # =========================================================================

    @property
    def event_bus(self):
        if self._event_bus is None:
            from src.mind.event_bus import EventBus
            self._event_bus = EventBus()
        return self._event_bus

    @property
    def shared_state(self):
        if self._shared_state is None:
            from src.mind.shared_state import SharedState
            self._shared_state = SharedState()
        return self._shared_state

    @property
    def success_map(self) -> Dict:
        if self._success_map is None:
            self._success_map = _build_success_map()
        return self._success_map

    @property
    def failure_map(self) -> Dict:
        if self._failure_map is None:
            self._failure_map = _build_failure_map()
        return self._failure_map

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Start the SoM bridge: detect profile, start sandbox, init agents."""
        if self._started:
            logger.warning("SoMBridge already started")
            return

        from src.mind.event_bus import Event, EventType

        logger.info("SoMBridge starting...")

        # 1. Detect project profile (universal)
        self.project_profile = await self._detect_project_profile()
        logger.info(
            f"Project profile detected: type={self.project_profile.project_type.value}, "
            f"lang={self.project_profile.primary_language}, "
            f"techs={[t.value for t in self.project_profile.technologies]}"
        )

        # 2. Start Docker sandbox with VNC (skip if DeploymentTeam manages its own)
        if self.config.enable_docker_sandbox and not self.config.enable_deployment_team:
            await self._start_docker_sandbox()

        # 3. Initialize SoM agents (Autogen + Claude CLI)
        await self._init_agents()

        # 4. Start agent run loops
        for agent_key, agent in self.agents.items():
            if hasattr(agent, 'run') and asyncio.iscoroutinefunction(agent.run):
                task = asyncio.create_task(agent.run())
                self._agent_tasks.append(task)
                logger.info(f"Agent {agent_key} run loop started")

        # 5. Publish SYSTEM_READY with project profile
        await self.event_bus.publish(Event(
            type=EventType.SYSTEM_READY,
            source="SoMBridge",
            data={
                "project_profile": self.project_profile.to_dict(),
                "agents_active": list(self.agents.keys()),
                "sandbox_running": self.container_id is not None,
                "vnc_port": self.vnc_port,
            },
        ))

        self._started = True
        logger.info(
            f"SoMBridge started | agents={len(self.agents)} | "
            f"sandbox={'running' if self.container_id else 'disabled'}"
        )

    async def stop(self):
        """Stop the SoM bridge: cancel agents, stop sandbox."""
        logger.info("SoMBridge stopping...")

        # Cancel agent tasks
        for task in self._agent_tasks:
            task.cancel()
        if self._agent_tasks:
            await asyncio.gather(*self._agent_tasks, return_exceptions=True)
        self._agent_tasks.clear()

        # Stop Docker sandbox
        if self.container_id:
            await self._stop_docker_sandbox()

        self._started = False
        logger.info("SoMBridge stopped")

    # =========================================================================
    # Project Profile Detection (Universal)
    # =========================================================================

    async def _detect_project_profile(self):
        """Auto-detect tech stack from output_dir files or requirements."""
        from src.engine.project_analyzer import (
            ProjectAnalyzer, ProjectProfile, ProjectType, Technology
        )

        analyzer = ProjectAnalyzer()

        # Try detection from existing project files in output_dir
        has_package_json = (self.output_dir / "package.json").exists()
        has_requirements = (self.output_dir / "requirements.txt").exists()
        has_cargo = (self.output_dir / "Cargo.toml").exists()
        has_go_mod = (self.output_dir / "go.mod").exists()

        if has_package_json or has_requirements or has_cargo or has_go_mod:
            try:
                profile = await analyzer.analyze_with_llm(
                    req_data=None,
                    project_dir=self.output_dir,
                )
                if profile:
                    return profile
            except Exception as e:
                logger.warning(f"LLM profile detection failed: {e}")

        # Fallback: analyze from requirements JSON in project_path
        try:
            from src.engine.dag_parser import parse_requirements
            req_files = list(self.project_path.glob("*.json"))
            for req_file in req_files:
                if "requirements" in req_file.name.lower() or "spec" in req_file.name.lower():
                    req_data = parse_requirements(str(req_file))
                    if req_data:
                        return analyzer.analyze(req_data)
        except Exception as e:
            logger.debug(f"Requirements-based detection failed: {e}")

        # Default: generic web app profile
        return ProjectProfile(
            project_type=ProjectType.WEB_APP,
            primary_language="typescript",
            has_frontend=True,
            has_backend=True,
        )

    # =========================================================================
    # Universal Verification Commands
    # =========================================================================

    def get_verification_commands(self) -> Dict[str, str]:
        """Build verification commands from ProjectProfile (universal).

        Instead of hardcoded npm/prisma commands, detect the right
        commands based on the project's actual tech stack.
        """
        from src.engine.project_analyzer import Technology

        profile = self.project_profile
        if not profile:
            return {}

        cmds: Dict[str, str] = {}

        # --- Build / Typecheck / Lint ---
        lang = profile.primary_language
        if lang in ("typescript", "javascript"):
            cmds["verify_build"] = "npm run build"
            cmds["verify_typecheck"] = "npx tsc --noEmit"
            cmds["verify_lint"] = "npm run lint"
        elif lang == "python":
            cmds["verify_build"] = (
                "python -m py_compile $(find . -name '*.py' "
                "-not -path './venv/*' -not -path './.venv/*' -not -path './node_modules/*')"
            )
            cmds["verify_typecheck"] = "mypy . --ignore-missing-imports"
            cmds["verify_lint"] = "ruff check ."
        elif lang == "rust":
            cmds["verify_build"] = "cargo build"
            cmds["verify_typecheck"] = "cargo check"
            cmds["verify_lint"] = "cargo clippy"
        elif lang == "go":
            cmds["verify_build"] = "go build ./..."
            cmds["verify_typecheck"] = "go vet ./..."
            cmds["verify_lint"] = "golangci-lint run"

        # --- Test commands ---
        if Technology.TYPESCRIPT in profile.technologies:
            cmds["verify_unit"] = "npm run test -- --run"
            cmds["verify_e2e"] = "npx playwright test"
        elif lang == "python":
            cmds["verify_unit"] = "pytest"
            cmds["verify_e2e"] = "pytest tests/e2e/"
        elif lang == "rust":
            cmds["verify_unit"] = "cargo test"
        elif lang == "go":
            cmds["verify_unit"] = "go test ./..."

        # --- Schema validation ---
        if profile.has_database:
            # Detect ORM-specific commands
            if (self.output_dir / "prisma" / "schema.prisma").exists():
                cmds["verify_schema"] = "npx prisma validate"
                cmds["schema_migration"] = (
                    "docker-compose up -d db && sleep 5 && "
                    "npx prisma migrate dev --name auto"
                )
                cmds["setup_database"] = (
                    "docker-compose up -d db && sleep 5 && npx prisma generate"
                )
            elif (self.output_dir / "alembic.ini").exists():
                cmds["schema_migration"] = "alembic upgrade head"
                cmds["setup_database"] = "alembic upgrade head"
            elif (self.output_dir / "drizzle.config.ts").exists():
                cmds["verify_schema"] = "npx drizzle-kit check"
                cmds["schema_migration"] = "npx drizzle-kit push"

        # --- Dependency install ---
        if lang in ("typescript", "javascript"):
            cmds["setup_deps"] = "npm install"
        elif lang == "python":
            cmds["setup_deps"] = "pip install -r requirements.txt"
        elif lang == "rust":
            cmds["setup_deps"] = "cargo fetch"
        elif lang == "go":
            cmds["setup_deps"] = "go mod download"

        # --- Docker commands ---
        cmds["setup_docker"] = (
            "test -f docker-compose.yml && echo 'docker-compose.yml exists' "
            "|| echo 'No docker-compose.yml found'"
        )
        cmds["setup_env"] = (
            "test -f .env && echo '.env exists' || "
            "(test -f .env.example && cp .env.example .env && "
            "echo 'Created .env from .env.example' || echo 'No .env file found')"
        )

        return cmds

    # =========================================================================
    # Event Resolution (Category-Based Prefix Matching)
    # =========================================================================

    def _resolve_event(self, task_type: str, mapping: Dict):
        """Resolve task type to EventType using prefix matching.

        1. Exact match first (e.g., "verify_build" → BUILD_SUCCEEDED)
        2. Prefix match (e.g., "schema_model" matches "schema_" → DATABASE_SCHEMA_GENERATED)
        """
        # Exact match
        if task_type in mapping:
            return mapping[task_type]

        # Prefix match
        for prefix, event_type in mapping.items():
            if prefix.endswith("_") and task_type.startswith(prefix):
                return event_type

        return None

    # =========================================================================
    # Task Event Publishing (called by TaskExecutor)
    # =========================================================================

    async def on_task_completed(self, task, result):
        """Publish success event when a task completes."""
        from src.mind.event_bus import Event, EventType

        event_type = self._resolve_event(task.type, self.success_map)

        # Always publish EPIC_TASK_COMPLETED
        await self.event_bus.publish(Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="SoMBridge",
            data={
                "task_id": task.id,
                "task_type": task.type,
                "epic_id": task.epic_id,
                "title": task.title,
                "output": result.output[:500] if result.output else "",
                "files_created": result.files_created if hasattr(result, 'files_created') else [],
                "files_modified": result.files_modified if hasattr(result, 'files_modified') else [],
            },
        ))

        # Publish specific event if mapped
        if event_type:
            await self.event_bus.publish(Event(
                type=event_type,
                source="SoMBridge",
                data={
                    "task_id": task.id,
                    "task_type": task.type,
                    "epic_id": task.epic_id,
                    "output": result.output[:500] if result.output else "",
                    "som_managed": True,  # Phase 28: TaskExecutor manages this task's lifecycle
                },
            ))

    async def on_task_failed(self, task, result):
        """Publish failure event when a task fails, triggering SoM agents."""
        from src.mind.event_bus import Event, EventType

        event_type = self._resolve_event(task.type, self.failure_map)

        # Always publish EPIC_TASK_FAILED
        await self.event_bus.publish(Event(
            type=EventType.EPIC_TASK_FAILED,
            source="SoMBridge",
            data={
                "task_id": task.id,
                "task_type": task.type,
                "epic_id": task.epic_id,
                "title": task.title,
                "error": result.error or "",
                "output": result.output[:500] if result.output else "",
            },
            error_message=result.error,
        ))

        # Publish specific failure event → triggers ContinuousDebugAgent etc.
        if event_type:
            await self.event_bus.publish(Event(
                type=event_type,
                source="SoMBridge",
                data={
                    "task_id": task.id,
                    "task_type": task.type,
                    "epic_id": task.epic_id,
                    "errors": [result.error] if result.error else [],
                    "raw_error": result.error or "",
                    "output": result.output[:500] if result.output else "",
                    "som_managed": True,  # Phase 28: TaskExecutor retry handles this failure
                },
                error_message=result.error,
                success=False,
            ))

        # Set up fix wait mechanism
        fix_event = asyncio.Event()
        self._fix_events[task.id] = fix_event

    async def on_task_started(self, task):
        """Publish event when a task starts executing."""
        from src.mind.event_bus import Event, EventType

        await self.event_bus.publish(Event(
            type=EventType.EPIC_TASK_STARTED,
            source="SoMBridge",
            data={
                "task_id": task.id,
                "task_type": task.type,
                "epic_id": task.epic_id,
                "title": task.title,
            },
        ))

    # =========================================================================
    # Fix Wait Mechanism (SoM auto-fix → retry)
    # =========================================================================

    async def wait_for_fix(self, task, timeout: Optional[int] = None) -> bool:
        """Wait for SoM agents to fix an error before retry.

        Returns True if a CODE_FIXED event was received within timeout.

        In subprocess mode (no shared event bus with API), we use a short
        timeout (10s) since fixes come from external agents (bot/OpenClaw),
        not from in-process SoM agents.
        """
        # Short timeout in subprocess mode — don't block generation
        timeout = min(timeout or self.config.fix_wait_timeout, 10)

        fix_event = self._fix_events.get(task.id)
        if not fix_event:
            return False

        # Subscribe to CODE_FIXED events
        from src.mind.event_bus import EventType
        fixed = False

        def on_code_fixed(event):
            nonlocal fixed
            task_id = event.data.get("task_id", "")
            if task_id == task.id or not task_id:
                fixed = True
                fix_event.set()

        self.event_bus.subscribe(EventType.CODE_FIXED, on_code_fixed)

        try:
            await asyncio.wait_for(fix_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug(f"Fix wait timed out for {task.id} after {timeout}s (expected in subprocess mode)")
        finally:
            self.event_bus.unsubscribe(EventType.CODE_FIXED, on_code_fixed)
            self._fix_events.pop(task.id, None)

        return fixed

    # =========================================================================
    # Agent Initialization (Autogen AG2 0.4.x)
    # =========================================================================

    async def _init_agents(self):
        """Initialize selected SoM agents based on config flags.

        Supports:
        - Static init_kwargs from AGENT_REGISTRY
        - Dynamic overrides per agent_key (e.g. VNC port, app URL, fungus config)
        - Project profile injection for universal behavior
        """
        for agent_key, info in AGENT_REGISTRY.items():
            config_flag = info["config_flag"]
            if not getattr(self.config, config_flag, False):
                continue

            try:
                module_path, class_name = info["class"].rsplit(".", 1)
                module = importlib.import_module(module_path)
                agent_class = getattr(module, class_name)

                # Base kwargs all agents receive
                kwargs = {
                    "name": agent_key,
                    "event_bus": self.event_bus,
                    "shared_state": self.shared_state,
                    "working_dir": str(self.output_dir),
                }

                # Static init_kwargs from registry
                if "init_kwargs" in info:
                    kwargs.update(info["init_kwargs"])

                # Dynamic overrides per agent type
                if agent_key == "generator":
                    kwargs["timeout"] = 300
                elif agent_key == "deployment_team":
                    kwargs["vnc_port"] = self.config.vnc_port
                elif agent_key == "continuous_e2e":
                    kwargs["app_url"] = f"http://localhost:{self.config.app_port}"
                elif agent_key == "fungus_context":
                    kwargs["num_agents"] = self.config.fungus_num_agents
                    kwargs["max_iterations"] = self.config.fungus_max_iterations

                agent = agent_class(**kwargs)

                # Inject project profile for universal behavior
                if hasattr(agent, 'project_profile'):
                    agent.project_profile = self.project_profile

                self.agents[agent_key] = agent
                logger.info(f"Agent initialized: {agent_key} ({class_name})")

            except ImportError as e:
                logger.warning(f"Agent {agent_key} not available: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize agent {agent_key}: {e}")

        logger.info(f"Initialized {len(self.agents)} SoM agents")

    # =========================================================================
    # Docker Sandbox (Universal - any project type)
    # =========================================================================

    def _detect_sandbox_project_type(self) -> str:
        """Map ProjectProfile → sandbox PROJECT_TYPE env var.

        The sandbox-entrypoint.sh uses PROJECT_TYPE to decide how to
        start the dev server (react, electron, python_fastapi, etc.).
        """
        from src.engine.project_analyzer import ProjectType, Technology

        profile = self.project_profile
        if not profile:
            return "node"

        if profile.project_type == ProjectType.FULLSTACK:
            return "fullstack"
        elif profile.project_type == ProjectType.ELECTRON_APP:
            return "electron"
        elif Technology.FASTAPI in profile.technologies:
            return "python_fastapi"
        elif Technology.FLASK in profile.technologies:
            return "python_flask"
        elif Technology.DJANGO in profile.technologies:
            return "python_django"
        elif profile.has_frontend:
            return "react"  # sandbox-entrypoint.sh treats as generic node frontend
        elif profile.has_backend and profile.primary_language == "python":
            return "python_fastapi"
        else:
            return "node"

    async def _start_docker_sandbox(self):
        """Start universal Docker sandbox with VNC - auto-detects project type."""
        project_type = self._detect_sandbox_project_type()
        container_name = f"epic-som-{self.project_name}-{int(time.time())}"

        logger.info(
            f"Starting Docker sandbox | type={project_type} | "
            f"vnc_port={self.config.vnc_port} | app_port={self.config.app_port}"
        )

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-v", f"{self.output_dir}:/app",
            "-p", f"{self.config.vnc_port}:6080",
            "-p", f"{self.config.app_port}:5173",
            "-p", f"{self.config.app_port + 1}:8000",
            "-e", "ENABLE_VNC=true",
            "-e", f"PROJECT_TYPE={project_type}",
            "-e", "ENGINE_API_URL=http://host.docker.internal:8000",
            self.config.sandbox_image,
            "//bin/bash", "-c",
            "//usr/local/bin/sandbox-entrypoint.sh",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "MSYS_NO_PATHCONV": "1"},
                timeout=60,
            )

            if result.returncode == 0:
                self.container_id = result.stdout.strip()
                self.vnc_port = self.config.vnc_port
                logger.info(
                    f"Docker sandbox started | container={self.container_id[:12]} | "
                    f"vnc=http://localhost:{self.vnc_port}"
                )
            else:
                logger.error(f"Docker sandbox failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error("Docker sandbox startup timed out")
        except FileNotFoundError:
            logger.warning("Docker not found - sandbox disabled")
        except Exception as e:
            logger.error(f"Docker sandbox error: {e}")

    async def _stop_docker_sandbox(self):
        """Stop and remove the Docker sandbox container."""
        if not self.container_id:
            return

        try:
            subprocess.run(
                ["docker", "rm", "-f", self.container_id],
                capture_output=True,
                text=True,
                timeout=30,
            )
            logger.info(f"Docker sandbox stopped | container={self.container_id[:12]}")
        except Exception as e:
            logger.warning(f"Failed to stop sandbox: {e}")
        finally:
            self.container_id = None
            self.vnc_port = None

    # =========================================================================
    # Public API
    # =========================================================================

    def get_vnc_url(self) -> Optional[str]:
        """Get the VNC preview URL if sandbox is running."""
        if self.vnc_port:
            return f"http://localhost:{self.vnc_port}/vnc.html"
        return None

    def get_status(self) -> Dict[str, Any]:
        """Get current bridge status."""
        return {
            "started": self._started,
            "project_profile": self.project_profile.to_dict() if self.project_profile else None,
            "agents_active": list(self.agents.keys()),
            "sandbox_running": self.container_id is not None,
            "vnc_url": self.get_vnc_url(),
            "vnc_port": self.vnc_port,
        }
