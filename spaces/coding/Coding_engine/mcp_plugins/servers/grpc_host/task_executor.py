#!/usr/bin/env python3
"""
Task Executor - Phase 4: Iteration 11

Connects generated Tasks (from Phase 3.6) to actual LLM code generation.
Routes tasks to appropriate agents/skills based on task type.

Features:
- TASK_SKILL_MAPPING: Maps 30+ task types to agents and skills
- Claude Code Tool integration for LLM generation
- Bash execution for verification tasks
- Checkpoint handling for user approval gates
- Docker execution for container tasks
- WebSocket live updates to Dashboard
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# Import Task dataclass from epic_task_generator
try:
    from epic_task_generator import Task, TaskStatus, TaskType, EpicTaskList
except ImportError:
    from mcp_plugins.servers.grpc_host.epic_task_generator import Task, TaskStatus, TaskType, EpicTaskList

# Phase 29: Context Injector for enrichment data
try:
    from src.autogen.context_injector import ContextInjector
except ImportError:
    try:
        import importlib
        _ci_mod = importlib.import_module("src.autogen.context_injector")
        ContextInjector = _ci_mod.ContextInjector
    except Exception:
        ContextInjector = None

# NemoClaw browser debug bridge (optional)
try:
    from mcp_plugins.servers.nemoclaw_bridge import NemoClawBridge, BrowserCheckResult
except ImportError:
    NemoClawBridge = None
    BrowserCheckResult = None

# Automation_ui debug bridge (optional)
try:
    from mcp_plugins.servers.automation_ui_bridge import AutomationUIBridge, AutomationDebugResult
except ImportError:
    AutomationUIBridge = None
    AutomationDebugResult = None


# =============================================================================
# Task Execution Result
# =============================================================================

@dataclass
class TaskExecutionResult:
    """Result of executing a single task"""
    success: bool
    output: str
    error: Optional[str] = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    duration_seconds: float = 0
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Task-to-Agent/Skill Mapping
# =============================================================================

# Tuple format: (ExecutorAgent, skill_name, claude_agent, max_turns)
#   - ExecutorAgent: Internal routing (BashExecutor, DockerAgent, etc.)
#   - skill_name: .claude/skills/{name}/SKILL.md injected into prompt
#   - claude_agent: .claude/agents/{name}.md passed via --agent flag (or None)
#   - max_turns: Max agentic turns for --max-turns cost control
TASK_SKILL_MAPPING: Dict[str, Tuple[str, Optional[str], Optional[str], int]] = {
    # =========================================================================
    # Schema Tasks → database-schema-generation skill → database-agent
    # =========================================================================
    "schema_model": ("DatabaseAgent", "database-schema-generation", "database-agent", 5),
    "schema_relations": ("DatabaseAgent", "database-schema-generation", "database-agent", 5),
    "schema_migration": ("BashExecutor", None, None, 3),  # prisma migrate dev

    # =========================================================================
    # API Tasks → api-generation skill → api-generator agent
    # =========================================================================
    "api_controller": ("APIAgent", "api-generation", "api-generator", 10),
    "api_service": ("APIAgent", "api-generation", "api-generator", 10),
    "api_dto": ("APIAgent", "api-generation", "api-generator", 10),
    "api_guard": ("AuthAgent", "auth-setup", "api-generator", 10),
    "api_validation": ("APIAgent", "api-generation", "api-generator", 10),

    # =========================================================================
    # Frontend Tasks → code-generation skill → coder agent
    # =========================================================================
    "fe_page": ("GeneratorAgent", "code-generation", "coder", 10),
    "fe_component": ("GeneratorAgent", "code-generation", "coder", 10),
    "fe_hook": ("GeneratorAgent", "code-generation", "coder", 10),
    "fe_api_client": ("GeneratorAgent", "code-generation", "coder", 10),
    "fe_form": ("GeneratorAgent", "code-generation", "coder", 10),

    # =========================================================================
    # Test Tasks → test-generation / e2e-testing skill → test-runner agent
    # =========================================================================
    "test_unit": ("TesterTeamAgent", "test-generation", "test-runner", 8),
    "test_integration": ("TesterTeamAgent", "test-generation", "test-runner", 8),
    "test_e2e_happy": ("PlaywrightAgent", "e2e-testing", "test-runner", 8),
    "test_e2e_negative": ("PlaywrightAgent", "e2e-testing", "test-runner", 8),
    "test_e2e_boundary": ("PlaywrightAgent", "e2e-testing", "test-runner", 8),

    # =========================================================================
    # Verification Tasks → Bash commands (no agent, low turns)
    # =========================================================================
    "verify_schema": ("BashExecutor", None, None, 3),      # prisma validate
    "verify_build": ("BashExecutor", None, None, 3),       # npm run build
    "verify_typecheck": ("BashExecutor", None, None, 3),   # tsc --noEmit
    "verify_lint": ("BashExecutor", None, None, 3),        # eslint
    "verify_unit": ("BashExecutor", None, None, 3),        # vitest run
    "verify_integration": ("BashExecutor", None, None, 3), # npm test:integration
    "verify_e2e": ("BashExecutor", None, None, 3),         # playwright test

    # =========================================================================
    # Docker Tasks → Docker MCP Agent or Bash → deployment-agent
    # =========================================================================
    "docker_build": ("DockerAgent", None, "deployment-agent", 5),
    "docker_start": ("DockerAgent", None, "deployment-agent", 5),
    "docker_health": ("DockerAgent", None, "deployment-agent", 5),
    "docker_logs": ("DockerAgent", None, "deployment-agent", 5),
    "docker_stop": ("DockerAgent", None, "deployment-agent", 5),

    # =========================================================================
    # Setup Tasks → LLM-generated (needs full tech stack context)
    # =========================================================================
    "setup_project": ("GeneratorAgent", "environment-config", "coder", 10),  # package.json + tsconfig.json + folder structure
    "setup_env": ("GeneratorAgent", "environment-config", "coder", 8),       # .env with all required vars
    "setup_secrets": ("GeneratorAgent", "environment-config", "coder", 5),   # Secrets configuration
    "setup_database": ("GeneratorAgent", "database-schema-generation", "coder", 10),  # prisma init + schema
    "setup_docker": ("GeneratorAgent", "environment-config", "coder", 8),    # docker-compose.yml
    "setup_deps": ("BashExecutor", None, None, 3),              # npm install (after package.json exists)

    # =========================================================================
    # Checkpoint Tasks → User Approval (no agent)
    # =========================================================================
    "checkpoint_schema": ("CheckpointHandler", None, None, 3),
    "checkpoint_api": ("CheckpointHandler", None, None, 3),
    "checkpoint_fe": ("CheckpointHandler", None, None, 3),
    "checkpoint_deploy": ("CheckpointHandler", None, None, 3),

    # =========================================================================
    # Notification Tasks → Dashboard Notification (no agent)
    # =========================================================================
    "notify_secret": ("NotificationHandler", None, None, 3),
    "notify_config": ("NotificationHandler", None, None, 3),
    "notify_review": ("NotificationHandler", None, None, 3),
    "notify_error": ("NotificationHandler", None, None, 3),

    # =========================================================================
    # Legacy types (for backwards compatibility) → with agents
    # =========================================================================
    "schema": ("DatabaseAgent", "database-schema-generation", "database-agent", 5),
    "api": ("APIAgent", "api-generation", "api-generator", 10),
    "frontend": ("GeneratorAgent", "code-generation", "coder", 10),
    "test": ("TesterTeamAgent", "test-generation", "test-runner", 8),
}

# Default commands for verification tasks
VERIFICATION_COMMANDS: Dict[str, str] = {
    "verify_schema": "npx prisma validate",
    "verify_build": "npm run build",
    "verify_typecheck": "npx tsc --noEmit",
    "verify_lint": "npm run lint",
    "verify_unit": "npm run test -- --run",
    "verify_integration": "npm run test:integration -- --run",
    "verify_e2e": "npx playwright test",
    # Migration: push schema directly (DB already running as container service)
    "schema_migration": "npx prisma db push --accept-data-loss --skip-generate 2>&1 || npx prisma generate",
    "setup_deps": "npm install --legacy-peer-deps",
    # setup_project, setup_env, setup_database, setup_docker now handled by GeneratorAgent (LLM)
    # Only setup_deps remains as BashExecutor since it needs npm install after package.json exists
}


# =============================================================================
# Task Executor
# =============================================================================

class TaskExecutor:
    """
    Führt Tasks aus, indem passende Agents/Tools aufgerufen werden.

    Supports:
    - Claude Code Tool for LLM code generation
    - Bash execution for verification/setup tasks
    - Checkpoint handling for user approval gates
    - Docker commands for container management
    - WebSocket events for Dashboard live updates
    - Headless mode for automated execution without user interaction
    """

    def __init__(
        self,
        project_path: str,
        output_dir: Optional[str] = None,
        event_bus: Optional[Any] = None,
        claude_tool: Optional[Any] = None,
        headless_mode: bool = True,
        two_stage: bool = True,
        max_concurrent: int = 10,
    ):
        """
        Args:
            project_path: Path to the input project (requirements, specs, tasks JSON)
            output_dir: Path where generated code is written. If None, defaults to
                        <project_path>/output/. Claude CLI uses this as working directory.
            event_bus: EventBus instance for WebSocket updates
            claude_tool: Optional pre-configured ClaudeCodeTool instance
            headless_mode: If True, auto-approve checkpoints and generate dev secrets
            two_stage: If True, use two-stage execution (plan then execute).
                       If False, send enriched context directly to Claude CLI (saves 1 LLM call per task).
            max_concurrent: Max concurrent Claude CLI calls (passed to ClaudeCodeTool semaphore)
        """
        self.project_path = Path(project_path)
        self.output_dir = Path(output_dir) if output_dir else self.project_path / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.event_bus = event_bus
        self._claude_tool = claude_tool
        self.max_concurrent = max_concurrent
        self._checkpoint_approvals: Dict[str, asyncio.Event] = {}
        self._checkpoint_responses: Dict[str, Optional[str]] = {}
        self.headless_mode = headless_mode
        self.two_stage = two_stage

        # Society of Mind bridge (set by EpicOrchestrator when enable_som=True)
        self.som_bridge = None

        # MCP Orchestrator integration (set by EpicOrchestrator from som_config)
        self.use_mcp_orchestrator: bool = False
        self._mcp_orchestrator = None  # Lazy-initialized EventFixOrchestrator

        # NemoClaw browser debug bridge (lazy-initialized)
        self._nemoclaw_bridge = None
        self._nemoclaw_retry_counts: Dict[str, int] = {}  # task_id -> browser check retry count
        self._nemoclaw_max_retries: int = 3

        # Automation_ui debug bridge (lazy-initialized)
        self._automation_ui_bridge = None
        self._automation_ui_retry_counts: Dict[str, int] = {}
        self._automation_ui_max_retries: int = 2

        logger.info(f"TaskExecutor initialized | input={project_path} | output={self.output_dir} | headless={headless_mode} | two_stage={two_stage}")

    # =========================================================================
    # Claude Tool Lazy Loading
    # =========================================================================

    def _get_claude_tool(self):
        """Lazy load ClaudeCodeTool with output_dir as working directory"""
        if self._claude_tool is not None:
            return self._claude_tool

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool
            # Claude CLI writes code to output_dir (not the input project_path)
            self._claude_tool = ClaudeCodeTool(working_dir=str(self.output_dir), max_concurrent=self.max_concurrent)
            return self._claude_tool
        except ImportError as e:
            logger.warning(f"Could not import ClaudeCodeTool: {e}")
            return None

    # =========================================================================
    # Main Execution Entry Point
    # =========================================================================

    async def execute_task(self, task: Task) -> TaskExecutionResult:
        """
        Führt einen einzelnen Task aus.

        If a SoMBridge is attached (via EpicOrchestrator.enable_som),
        task events are published to the EventBus, and on failure the
        bridge can coordinate auto-fix before retry.

        Args:
            task: Task to execute

        Returns:
            TaskExecutionResult with success status, output, and errors
        """
        start_time = time.time()

        # 1. Update status to running
        await self._update_task_status(task, TaskStatus.RUNNING.value)

        # Notify SoM bridge of task start
        if self.som_bridge:
            try:
                await self.som_bridge.on_task_started(task)
            except Exception as e:
                logger.debug(f"SoM on_task_started failed: {e}")

        try:
            # 2. Get executor type from mapping (4-tuple: executor, skill, claude_agent, max_turns)
            mapping = TASK_SKILL_MAPPING.get(
                task.type, ("GeneratorAgent", "code-generation", "coder", 10)
            )
            agent_name, skill_name, claude_agent, max_turns = mapping

            logger.info(
                f"Executing task {task.id} | type={task.type} | agent={agent_name} "
                f"| skill={skill_name} | claude_agent={claude_agent} | max_turns={max_turns}"
            )

            # 3. Execute based on executor type
            # Route complex multi-tool tasks through MCP Orchestrator when enabled
            if self.use_mcp_orchestrator and self._should_use_orchestrator(task.type):
                result = await self._execute_via_orchestrator(task)
            elif agent_name == "BashExecutor":
                result = await self._execute_bash(task)
            elif agent_name == "CheckpointHandler":
                result = await self._handle_checkpoint(task)
            elif agent_name == "NotificationHandler":
                result = await self._handle_notification(task)
            elif agent_name == "DockerAgent":
                result = await self._execute_docker(task)
            else:
                result = await self._execute_claude(task, skill_name, claude_agent, max_turns)

            # 4. Publish result to SoM bridge (triggers agents)
            if self.som_bridge:
                try:
                    if result.success:
                        await self.som_bridge.on_task_completed(task, result)
                    else:
                        await self.som_bridge.on_task_failed(task, result)

                        # Wait for SoM auto-fix before retry
                        if task.auto_retry and task.retry_count < task.max_retries:
                            logger.info(
                                f"Waiting for SoM auto-fix on task {task.id}..."
                            )
                            fixed = await self.som_bridge.wait_for_fix(task)
                            if fixed:
                                task.retry_count += 1
                                logger.info(
                                    f"SoM fix applied for {task.id}, "
                                    f"re-validating (attempt {task.retry_count}/{task.max_retries})"
                                )
                                # Phase 28: Re-validate instead of re-generating.
                                # SoM agent already wrote the fix files.
                                agent_name, _, _, _ = TASK_SKILL_MAPPING.get(
                                    task.type, ("GeneratorAgent", "code-generation", "coder", 10)
                                )
                                if agent_name == "BashExecutor":
                                    # Verification task: re-run check to see if fix worked
                                    return await self._execute_bash(task)
                                else:
                                    # Code-gen task: SoM agent already wrote the fix
                                    result = TaskExecutionResult(
                                        success=True,
                                        output=f"SoM agent fix accepted for {task.id}",
                                    )
                                    await self._update_task_status(
                                        task, TaskStatus.COMPLETED.value
                                    )
                                    return result
                except Exception as e:
                    logger.debug(f"SoM event publishing failed: {e}")

            # 5. Handle retries if failed (standard path, no SoM)
            if not result.success and task.auto_retry and task.retry_count < task.max_retries:
                # Only do standard retry if SoM didn't already handle it
                if not self.som_bridge:
                    task.retry_count += 1
                    logger.info(f"Retrying task {task.id} (attempt {task.retry_count}/{task.max_retries})")
                    return await self.execute_task(task)

            # 5b. NemoClaw browser check (after successful code-gen tasks)
            if result.success and agent_name not in ("BashExecutor", "CheckpointHandler", "NotificationHandler"):
                browser_result = await self._run_nemoclaw_check(task)
                if browser_result and not browser_result.passed and not browser_result.skipped:
                    retries = self._nemoclaw_retry_counts.get(task.id, 0)
                    if retries < self._nemoclaw_max_retries:
                        self._nemoclaw_retry_counts[task.id] = retries + 1
                        browser_errors = "; ".join(browser_result.errors[:5])
                        logger.info(
                            f"NemoClaw browser check failed for {task.id} "
                            f"(attempt {retries + 1}/{self._nemoclaw_max_retries}): {browser_errors}"
                        )
                        # Re-execute with browser error context appended to task description
                        original_desc = task.description or ""
                        task.description = (
                            f"{original_desc}\n\n"
                            f"[AUTO-FIX] Browser check found errors after previous generation:\n"
                            f"{browser_errors}\n"
                            f"Fix these browser/UI issues in the generated code."
                        )
                        task.retry_count += 1
                        return await self.execute_task(task)
                    else:
                        logger.warning(
                            f"NemoClaw browser check still failing after "
                            f"{self._nemoclaw_max_retries} retries for {task.id}"
                        )
                        # Clear retry counter, don't block completion
                        self._nemoclaw_retry_counts.pop(task.id, None)

            # 5c. Automation_ui component debug (after successful code-gen tasks)
            if result.success and agent_name not in ("BashExecutor", "CheckpointHandler", "NotificationHandler"):
                auto_debug_result = await self._run_automation_ui_debug(task)
                if auto_debug_result and not auto_debug_result.passed and not auto_debug_result.skipped:
                    retries = self._automation_ui_retry_counts.get(task.id, 0)
                    if retries < self._automation_ui_max_retries:
                        self._automation_ui_retry_counts[task.id] = retries + 1
                        debug_errors = "; ".join(auto_debug_result.errors[:5])
                        logger.info(
                            f"Automation_ui debug found issues for {task.id} "
                            f"(attempt {retries + 1}/{self._automation_ui_max_retries}): {debug_errors}"
                        )
                        # Re-execute with debug error context appended to task description
                        original_desc = task.description or ""
                        task.description = (
                            f"{original_desc}\n\n"
                            f"[AUTO-FIX] Automation_ui debug found errors after previous generation:\n"
                            f"{debug_errors}\n"
                            f"Fix these issues in the generated code."
                        )
                        task.retry_count += 1
                        return await self.execute_task(task)
                    else:
                        logger.warning(
                            f"Automation_ui debug still finding issues after "
                            f"{self._automation_ui_max_retries} retries for {task.id}"
                        )
                        self._automation_ui_retry_counts.pop(task.id, None)

            # 6. Update final status
            if result.success:
                await self._update_task_status(task, TaskStatus.COMPLETED.value)
            else:
                await self._update_task_status(task, TaskStatus.FAILED.value, result.error)

            result.duration_seconds = time.time() - start_time
            result.retry_count = task.retry_count

            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task execution failed: {error_msg} | task_id={task.id}")
            await self._update_task_status(task, TaskStatus.FAILED.value, error_msg)
            return TaskExecutionResult(
                success=False,
                output="",
                error=error_msg,
                duration_seconds=time.time() - start_time,
            )

    # =========================================================================
    # NemoClaw Browser Debug Check
    # =========================================================================

    def _get_nemoclaw_bridge(self):
        """Lazy-initialize the NemoClaw browser debug bridge."""
        if self._nemoclaw_bridge is not None:
            return self._nemoclaw_bridge
        if NemoClawBridge is None:
            return None
        try:
            # Use sandbox app URL; if som_bridge has a container, use its port
            app_url = os.environ.get("SANDBOX_APP_URL", "http://localhost:3100")
            if self.som_bridge and hasattr(self.som_bridge, 'config'):
                app_port = getattr(self.som_bridge.config, 'app_port', 3100)
                app_url = f"http://localhost:{app_port}"

            screenshot_dir = str(self.output_dir / "reports" / "screenshots")
            self._nemoclaw_bridge = NemoClawBridge(
                app_url=app_url,
                screenshot_dir=screenshot_dir,
                enable_ai_analysis=bool(os.environ.get("OPENROUTER_API_KEY")),
            )
            logger.info(f"NemoClaw bridge initialized | app_url={app_url}")
            return self._nemoclaw_bridge
        except Exception as e:
            logger.debug(f"NemoClaw bridge init failed: {e}")
            return None

    async def _run_nemoclaw_check(self, task) -> "Optional[BrowserCheckResult]":
        """Run NemoClaw browser check after a successful code generation task.

        Returns None if bridge is unavailable or sandbox is not running.
        Returns BrowserCheckResult with check outcomes otherwise.
        Gracefully degrades if anything is unavailable.
        """
        bridge = self._get_nemoclaw_bridge()
        if bridge is None:
            return None

        # Quick reachability check before full browser launch
        try:
            reachable = await bridge.is_sandbox_reachable()
            if not reachable:
                logger.debug(f"nemoclaw: sandbox not reachable, skipping check for {task.id}")
                return None
        except Exception:
            return None

        try:
            result = await bridge.run_check()
            if result.skipped:
                logger.debug(f"nemoclaw: check skipped for {task.id}: {result.skip_reason}")
                return None
            return result
        except Exception as e:
            logger.debug(f"nemoclaw: check failed for {task.id}: {e}")
            return None

    # =========================================================================
    # Automation_ui Component Debug
    # =========================================================================

    def _get_automation_ui_bridge(self):
        """Lazy-initialize the Automation_ui debug bridge."""
        if self._automation_ui_bridge is not None:
            return self._automation_ui_bridge
        if AutomationUIBridge is None:
            return None
        try:
            backend_url = os.environ.get("AUTOMATION_UI_URL", "http://localhost:8007")
            sandbox_url = os.environ.get("SANDBOX_APP_URL", "http://localhost:3100")
            if self.som_bridge and hasattr(self.som_bridge, 'config'):
                app_port = getattr(self.som_bridge.config, 'app_port', 3100)
                sandbox_url = f"http://localhost:{app_port}"

            self._automation_ui_bridge = AutomationUIBridge(
                backend_url=backend_url,
                sandbox_url=sandbox_url,
            )
            logger.info(
                f"Automation_ui bridge initialized | "
                f"backend={backend_url} | sandbox={sandbox_url}"
            )
            return self._automation_ui_bridge
        except Exception as e:
            logger.debug(f"Automation_ui bridge init failed: {e}")
            return None

    async def _run_automation_ui_debug(self, task) -> "Optional[AutomationDebugResult]":
        """Run Automation_ui debug check for a generated component.

        Extracts component name and file path from the task metadata,
        then sends a debug instruction to Automation_ui's LLM intent agent.

        Returns None if bridge is unavailable.
        Returns AutomationDebugResult with findings otherwise.
        Gracefully degrades if Automation_ui is not running.
        """
        bridge = self._get_automation_ui_bridge()
        if bridge is None:
            return None

        # Extract component info from task
        component_name = getattr(task, 'title', '') or task.id
        file_path = ""
        if hasattr(task, 'files') and task.files:
            file_path = task.files[0] if isinstance(task.files, list) else str(task.files)
        elif hasattr(task, 'target_file'):
            file_path = str(task.target_file)

        # Use task description as extra context if available
        extra_context = ""
        if hasattr(task, 'description') and task.description:
            # Truncate to avoid overwhelming the LLM
            desc = task.description[:500]
            extra_context = f"Task description: {desc}"

        try:
            result = await bridge.debug_component(
                task_type=getattr(task, 'type', 'fe_component'),
                component_name=component_name,
                file_path=file_path,
                extra_context=extra_context,
            )
            if result.skipped:
                logger.debug(
                    f"automation_ui: debug skipped for {task.id}: {result.skip_reason}"
                )
                return None
            return result
        except Exception as e:
            logger.debug(f"automation_ui: debug failed for {task.id}: {e}")
            return None

    # =========================================================================
    # Claude Tool Execution (LLM Code Generation)
    # =========================================================================

    async def _execute_claude(
        self,
        task: Task,
        skill_name: Optional[str],
        claude_agent: Optional[str] = None,
        max_turns: Optional[int] = None,
    ) -> TaskExecutionResult:
        """
        Two-stage LLM execution:
        Stage 1: Gather context → Generate execution plan (via fast LLM call)
        Stage 2: Send execution plan → Claude CLI generates code

        The execution plan distills ~11K of raw context into a focused ~2K
        instruction set that tells Claude CLI exactly what to write.

        Args:
            task: Task to execute
            skill_name: .claude/skills/ skill name for prompt enrichment
            claude_agent: .claude/agents/ agent name for --agent flag (e.g., "coder", "database-agent")
            max_turns: Max agentic turns for --max-turns cost control
        """
        claude_tool = self._get_claude_tool()
        if claude_tool is None:
            return TaskExecutionResult(
                success=False,
                output="",
                error="ClaudeCodeTool not available",
            )

        # Stage 1: Gather all context
        context = self._gather_context(task, skill_name)

        # Stage 1b: Optionally distill into execution plan (two-stage mode)
        if self.two_stage:
            execution_plan = await self._generate_execution_plan(task, context)
        else:
            # Single-stage: wrap raw context with path rules and send directly
            execution_plan = self._wrap_plan_for_execution(task, context)

        # Get agent type based on task type
        agent_type = self._get_agent_type(task)

        try:
            # Stage 2: Execute the plan via Claude CLI
            # Pass claude_agent and max_turns for .claude integration
            result = await claude_tool.execute(
                prompt=execution_plan,
                agent_type=agent_type,
                claude_agent=claude_agent,
                max_turns=max_turns,
            )

            return TaskExecutionResult(
                success=result.success if hasattr(result, 'success') else True,
                output=result.output if hasattr(result, 'output') else str(result),
                error=result.error if hasattr(result, 'error') else None,
                files_created=result.files_created if hasattr(result, 'files_created') else [],
                files_modified=result.files_modified if hasattr(result, 'files_modified') else [],
            )

        except Exception as e:
            logger.error(f"Claude execution failed: {e} | task_id={task.id}")
            return TaskExecutionResult(
                success=False,
                output="",
                error=str(e),
            )

    async def _generate_execution_plan(self, task: Task, context: str) -> str:
        """
        Stage 1: Use a fast Anthropic API call (Haiku) to distill raw context
        into a precise execution plan.

        Input:  ~11K chars of raw context (OpenAPI, schema, existing code, user stories)
        Output: ~2-3K chars of focused instructions (exact file paths, function signatures,
                imports, business logic steps, error handling)

        Uses Anthropic API directly (not Claude CLI) for speed and cost efficiency.
        The plan is the ONLY thing sent to Claude CLI in Stage 2.
        """
        plan_prompt = f"""You are a senior architect creating a precise execution plan for a code generation task.

Given the context below, produce a focused EXECUTION PLAN that a developer (Claude CLI) can implement directly.

The plan MUST include:
1. **File**: Exact file path to create/modify (relative to project root)
2. **Imports**: Exact import statements needed
3. **Function signature**: Method name, parameters with types, return type
4. **Business logic**: Step-by-step what the function does (numbered list)
5. **Prisma operations**: Exact Prisma calls (e.g., `prisma.user.create({{ data: {{ ... }} }})`)
6. **Error handling**: Which errors to catch, HTTP status codes to return
7. **Validation**: Input validation rules from the DTO schema
8. **Response format**: Exact response shape with types

Keep the plan CONCISE. No explanations. No alternatives. Just the plan.

---
CONTEXT:
{context}
---

Output ONLY the execution plan, nothing else."""

        try:
            plan_output = await self._call_anthropic_api(plan_prompt)

            if plan_output and len(plan_output) > 100:
                # Wrap the plan with essential path rules (reinforcement)
                execution_prompt = self._wrap_plan_for_execution(task, plan_output)
                logger.info(
                    f"Execution plan generated for {task.id} | "
                    f"context={len(context)} chars -> plan={len(execution_prompt)} chars"
                )
                return execution_prompt

        except Exception as e:
            logger.warning(f"Plan generation failed, falling back to direct prompt: {e}")

        # Fallback: use the raw context prompt directly (old behavior)
        logger.info(f"Using direct context prompt for {task.id} (plan generation unavailable)")
        return context

    async def _call_anthropic_api(self, prompt: str) -> str:
        """
        Direct Anthropic API call for fast text distillation (Stage 1 planning).
        Falls back to Claude CLI if API is unavailable.
        No file system access - pure text-in, text-out.
        """
        # Try 1: Anthropic API (fast, direct)
        try:
            import anthropic
            import os
            from dotenv import load_dotenv

            # Load API key from .env if not in environment
            if not os.environ.get("ANTHROPIC_API_KEY"):
                load_dotenv(self.project_path / ".env")
                project_root = Path(__file__).parent.parent.parent.parent
                load_dotenv(project_root / ".env")

            if os.environ.get("ANTHROPIC_API_KEY"):
                from src.llm_config import get_model
                client = anthropic.AsyncAnthropic()
                response = await client.messages.create(
                    model=get_model("mcp_standard"),
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text if response.content else ""
        except Exception as e:
            logger.info(f"Anthropic API unavailable ({e}), trying Claude CLI for planning")

        # Try 2: Claude CLI (uses OAuth, no API key needed)
        try:
            claude_tool = self._get_claude_tool()
            if claude_tool:
                plan_result = await claude_tool.execute(
                    prompt=prompt,
                    agent_type="general",
                )
                return plan_result.output if hasattr(plan_result, 'output') else str(plan_result)
        except Exception as e:
            logger.warning(f"Claude CLI planning also failed: {e}")

        # Try 3: Return empty to trigger fallback to raw context
        return ""

    def _wrap_plan_for_execution(self, task: Task, plan: str) -> str:
        """
        Wrap the execution plan with essential project rules for Stage 2.
        This is what Claude CLI actually receives.
        """
        is_setup = task.type.startswith("setup_")

        parts = [
            f"# Execute: {task.title}",
            "",
            "## Project Rules (MUST follow)",
            "- Output directory: . (current working directory — do NOT repeat the full path in file writes)",
        ]

        if is_setup:
            # Setup tasks write root config files (package.json, tsconfig.json, .env, etc.)
            parts.extend([
                "- Write config files to project ROOT: package.json, tsconfig.json, .env, docker-compose.yml",
                "- Write source code to `src/` directory",
                "- Write Prisma schema to `prisma/schema.prisma`",
                "- EVERY file MUST be a complete code block: ```language:path/to/file",
                "- Include ALL dependencies with exact versions in package.json",
            ])
        else:
            parts.extend([
                "- Write ALL source files to `src/` directory - NEVER to `generated/`",
                "- Import Prisma client from `../../generated/prisma` (relative to module)",
                "- Use existing patterns from the codebase (valibot for validation, class-based services)",
            ])

        parts.append("")

        if task.output_files:
            parts.extend([
                "## Target Files",
                *[f"- {f}" for f in task.output_files],
                "",
            ])

        parts.extend([
            "## Execution Plan (implement EXACTLY this)",
            "",
            plan,
            "",
        ])

        if is_setup:
            parts.extend([
                "## CRITICAL: Output Format",
                "Output EVERY file as a fenced code block with path:",
                "```json:package.json",
                "{ ... }",
                "```",
                "```json:tsconfig.json",
                "{ ... }",
                "```",
                "Do NOT describe files. WRITE them as code blocks.",
            ])
        else:
            parts.extend([
                "",
                "## CRITICAL: Output Format",
                "For EVERY file you create, you MUST use this EXACT format with file path annotation:",
                "",
                "```typescript:src/modules/{resource}/{resource}.controller.ts",
                "// complete file content here",
                "```",
                "",
                "## File Path Rules:",
                "- Controllers: `src/modules/{resource}/{resource}.controller.ts`",
                "- Services: `src/modules/{resource}/{resource}.service.ts`",
                "- Modules: `src/modules/{resource}/{resource}.module.ts`",
                "- DTOs: `src/modules/{resource}/dto/{name}.dto.ts`",
                "- Guards: `src/guards/{name}.guard.ts`",
                "- Validators: `src/modules/{resource}/validators/{name}.validator.ts`",
                "- React Pages: `frontend/src/pages/{Name}/{Name}.tsx`",
                "- React Components: `frontend/src/components/{Name}/{Name}.tsx`",
                "- React Hooks: `frontend/src/hooks/use{Name}.ts`",
                "- React API clients: `frontend/src/api/{name}API.ts`",
                "- Tests: `__tests__/unit/{module}.spec.ts`",
                "- Integration Tests: `__tests__/integration/{epic}/{name}.spec.ts`",
                "",
                "NEVER output code without a `language:path` annotation on the opening fence.",
                "NEVER use generic names like `file1.ts` or `index.ts` without the full path.",
                "Every code block MUST have the complete relative path from project root.",
                "",
                "## Final Check",
                "- All files written under `src/` with correct path annotations?",
                "- All imports resolve correctly (use relative paths)?",
                "- All Prisma types match schema (import from `@prisma/client`)?",
                "- Complete class with all decorators (NestJS: @Controller, @Injectable, @Module)?",
                "- No orphaned statements outside class/function bodies?",
            ])

        return "\n".join(parts)

    # =========================================================================
    # Bash Execution (Verification/Setup Tasks)
    # =========================================================================

    async def _execute_bash(self, task: Task) -> TaskExecutionResult:
        """
        Führt Bash-Command aus.

        If a SoMBridge is attached, uses universal verification commands
        derived from ProjectProfile instead of the hardcoded VERIFICATION_COMMANDS.

        Args:
            task: Task with command to execute

        Returns:
            TaskExecutionResult
        """
        # Get command: task.command > SoMBridge universal > hardcoded fallback
        command = task.command
        if not command and self.som_bridge:
            som_cmds = self.som_bridge.get_verification_commands()
            command = som_cmds.get(task.type, "")
        if not command:
            command = VERIFICATION_COMMANDS.get(task.type, "")

        if not command:
            return TaskExecutionResult(
                success=False,
                output="",
                error=f"No command specified for task type: {task.type}",
            )

        logger.info(f"Executing bash command: {command} | task_id={task.id}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=task.timeout_seconds,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return TaskExecutionResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {task.timeout_seconds}s",
                )

            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')

            return TaskExecutionResult(
                success=proc.returncode == 0,
                output=output,
                error=error_output if proc.returncode != 0 else None,
            )

        except Exception as e:
            logger.error(f"Bash execution failed: {e} | task_id={task.id}")
            return TaskExecutionResult(
                success=False,
                output="",
                error=str(e),
            )

    # =========================================================================
    # Checkpoint Handling (User Approval)
    # =========================================================================

    async def _handle_checkpoint(self, task: Task) -> TaskExecutionResult:
        """
        Wartet auf User-Approval bei Checkpoint-Tasks.

        In headless mode:
        - setup_secrets: Auto-generates development secrets
        - Other checkpoints: Auto-approved immediately

        Args:
            task: Checkpoint task requiring user approval

        Returns:
            TaskExecutionResult (success when approved)
        """
        # Headless mode: Auto-approve checkpoints
        if self.headless_mode:
            logger.info(f"Headless mode: Auto-approving checkpoint {task.id}")

            # Special handling for setup_secrets - generate dev secrets
            if task.type == "setup_secrets":
                return await self._generate_dev_secrets(task)

            # Other checkpoints: just auto-approve
            return TaskExecutionResult(
                success=True,
                output=f"Checkpoint auto-approved (headless mode): {task.title}",
            )

        # Normal mode: Wait for user approval
        # Create approval event for this checkpoint
        approval_event = asyncio.Event()
        self._checkpoint_approvals[task.id] = approval_event
        self._checkpoint_responses[task.id] = None

        # Publish checkpoint event to Dashboard
        if self.event_bus:
            await self._publish_event({
                "type": "CHECKPOINT_REACHED",
                "task_id": task.id,
                "epic_id": task.epic_id,
                "checkpoint_type": task.type,
                "prompt": task.user_prompt or f"Please review the {task.phase} phase before continuing.",
                "title": task.title,
            })

        logger.info(f"Checkpoint {task.id} waiting for user approval...")

        # Wait for approval (will be set by approve_checkpoint method)
        try:
            await asyncio.wait_for(approval_event.wait(), timeout=task.timeout_seconds)

            # Get user response if any
            user_response = self._checkpoint_responses.get(task.id)

            # Cleanup
            del self._checkpoint_approvals[task.id]
            del self._checkpoint_responses[task.id]

            return TaskExecutionResult(
                success=True,
                output=f"Checkpoint approved. User response: {user_response or 'None'}",
            )

        except asyncio.TimeoutError:
            # Cleanup
            if task.id in self._checkpoint_approvals:
                del self._checkpoint_approvals[task.id]
            if task.id in self._checkpoint_responses:
                del self._checkpoint_responses[task.id]

            return TaskExecutionResult(
                success=False,
                output="",
                error=f"Checkpoint timed out after {task.timeout_seconds}s",
            )

    async def _generate_dev_secrets(self, task: Task) -> TaskExecutionResult:
        """
        Generates development secrets for headless execution.

        Writes auto-generated secrets to .env file.
        """
        import secrets
        import base64

        logger.info(f"Generating development secrets for task {task.id}")

        # Generate secure random secrets
        dev_secrets = {
            "JWT_SECRET": base64.b64encode(secrets.token_bytes(48)).decode('utf-8'),
            "NEXTAUTH_SECRET": base64.b64encode(secrets.token_bytes(32)).decode('utf-8'),
            "SESSION_SECRET": base64.b64encode(secrets.token_bytes(32)).decode('utf-8'),
            "SMTP_USER": "dev@localhost",
            "SMTP_PASSWORD": "dev-smtp-password",
            "S3_ACCESS_KEY": "dev-s3-access-key",
            "S3_SECRET_KEY": "dev-s3-secret-key",
            "STRIPE_SECRET_KEY": "sk_test_dev_stripe_key",
            "STRIPE_WEBHOOK_SECRET": "whsec_dev_webhook_secret",
            "TWILIO_AUTH_TOKEN": "dev-twilio-token",
            "OPENAI_API_KEY": "sk-dev-openai-key",
            "GOOGLE_CLIENT_SECRET": "dev-google-client-secret",
        }

        # Check if .env exists and update it (in output_dir)
        env_file = self.output_dir / ".env"
        env_content = ""

        if env_file.exists():
            env_content = env_file.read_text(encoding='utf-8')

        # Add/update secrets in .env
        for key, value in dev_secrets.items():
            if f"{key}=" in env_content:
                # Update existing value (if it's empty or placeholder)
                import re
                pattern = rf'^{key}=.*$'
                # Only update if current value is empty or placeholder
                if re.search(rf'^{key}=\s*$', env_content, re.MULTILINE) or \
                   re.search(rf'^{key}=<.*>$', env_content, re.MULTILINE):
                    env_content = re.sub(pattern, f'{key}={value}', env_content, flags=re.MULTILINE)
            else:
                # Add new secret
                env_content += f"\n{key}={value}"

        # Write updated .env
        env_file.write_text(env_content, encoding='utf-8')

        logger.info(f"Generated {len(dev_secrets)} development secrets in .env")

        return TaskExecutionResult(
            success=True,
            output=f"Generated {len(dev_secrets)} development secrets",
            files_modified=[".env"],
        )

    def approve_checkpoint(self, task_id: str, response: Optional[str] = None) -> bool:
        """
        Approves a checkpoint, allowing execution to continue.

        Called by Dashboard API when user clicks 'Approve'.

        Args:
            task_id: ID of the checkpoint task
            response: Optional user response/feedback

        Returns:
            True if checkpoint was found and approved
        """
        if task_id in self._checkpoint_approvals:
            self._checkpoint_responses[task_id] = response
            self._checkpoint_approvals[task_id].set()
            logger.info(f"Checkpoint {task_id} approved")
            return True

        logger.warning(f"Checkpoint {task_id} not found")
        return False

    def reject_checkpoint(self, task_id: str, reason: str) -> bool:
        """
        Rejects a checkpoint, marking it as failed.

        Args:
            task_id: ID of the checkpoint task
            reason: Reason for rejection

        Returns:
            True if checkpoint was found
        """
        if task_id in self._checkpoint_approvals:
            self._checkpoint_responses[task_id] = f"REJECTED: {reason}"
            self._checkpoint_approvals[task_id].set()
            logger.info(f"Checkpoint {task_id} rejected: {reason}")
            return True
        return False

    # =========================================================================
    # Notification Handling
    # =========================================================================

    async def _handle_notification(self, task: Task) -> TaskExecutionResult:
        """
        Sends notification to Dashboard and optionally waits for user input.

        Args:
            task: Notification task

        Returns:
            TaskExecutionResult
        """
        # Publish notification event
        if self.event_bus:
            await self._publish_event({
                "type": "NOTIFICATION",
                "task_id": task.id,
                "epic_id": task.epic_id,
                "notification_type": task.type,
                "message": task.description,
                "requires_input": task.requires_user_input,
                "prompt": task.user_prompt,
            })

        if task.requires_user_input:
            # Wait like a checkpoint
            return await self._handle_checkpoint(task)

        return TaskExecutionResult(
            success=True,
            output=f"Notification sent: {task.title}",
        )

    # =========================================================================
    # Docker Execution
    # =========================================================================

    async def _execute_docker(self, task: Task) -> TaskExecutionResult:
        """
        Führt Docker-Command aus.

        Args:
            task: Docker task to execute

        Returns:
            TaskExecutionResult
        """
        # Map task types to docker commands
        docker_commands = {
            "docker_build": "docker compose build 2>/dev/null || docker-compose build",
            "docker_start": "docker compose up -d 2>/dev/null || docker-compose up -d",
            "docker_health": "docker compose ps 2>/dev/null || docker-compose ps",
            "docker_logs": "docker compose logs --tail=100 2>/dev/null || docker-compose logs --tail=100",
            "docker_stop": "docker compose down 2>/dev/null || docker-compose down",
        }

        command = task.command or docker_commands.get(task.type, "")

        if not command:
            return TaskExecutionResult(
                success=False,
                output="",
                error=f"No docker command for task type: {task.type}",
            )

        # Use bash executor for docker commands
        task_copy = Task(
            id=task.id,
            epic_id=task.epic_id,
            type=task.type,
            title=task.title,
            description=task.description,
            command=command,
            timeout_seconds=task.timeout_seconds,
        )

        return await self._execute_bash(task_copy)

    # =========================================================================
    # MCP Orchestrator Integration (35+ MCP tools via AutoGen team)
    # =========================================================================

    # Task types that benefit from multi-tool MCP orchestration
    _ORCHESTRATOR_TASK_TYPES = {
        # E2E/integration testing needs Playwright + filesystem + fetch
        "test_integration", "test_e2e_happy", "test_e2e_negative", "test_e2e_boundary",
        "verify_e2e", "verify_integration",
        # Docker tasks need Docker + filesystem + fetch tools
        "docker_build", "docker_start", "docker_health", "docker_logs", "docker_stop",
    }

    def _should_use_orchestrator(self, task_type: str) -> bool:
        """Check if a task type should be routed through MCP Orchestrator."""
        return task_type in self._ORCHESTRATOR_TASK_TYPES

    def _get_mcp_orchestrator(self):
        """Lazy-initialize the EventFixOrchestrator with 35+ MCP tools."""
        if self._mcp_orchestrator is not None:
            return self._mcp_orchestrator

        try:
            try:
                from autogen_orchestrator import EventFixOrchestrator
            except ImportError:
                from mcp_plugins.servers.grpc_host.autogen_orchestrator import EventFixOrchestrator

            self._mcp_orchestrator = EventFixOrchestrator(
                working_dir=str(self.output_dir),
                max_turns=20,
            )
            logger.info("MCP Orchestrator initialized for multi-tool task execution")
            return self._mcp_orchestrator

        except Exception as e:
            logger.warning(f"Could not initialize MCP Orchestrator: {e}")
            return None

    def _map_task_type_to_orchestrator_type(self, task_type: str) -> str:
        """Map epic task types to MCP Orchestrator task categories."""
        if task_type.startswith("test_e2e") or task_type == "verify_e2e":
            return "e2e_testing"
        elif task_type.startswith("test_") or task_type.startswith("verify_"):
            return "testing"
        elif task_type.startswith("docker_"):
            return "docker"
        return "general"

    async def _execute_via_orchestrator(self, task: Task) -> TaskExecutionResult:
        """
        Execute a task via the MCP Orchestrator (EventFixOrchestrator).

        Routes complex multi-tool tasks through AutoGen team with 35+ MCP tools
        (Playwright, filesystem, Docker, fetch, etc.) instead of single Claude CLI call.
        Falls back to standard execution path on initialization failure.
        """
        orchestrator = self._get_mcp_orchestrator()
        if orchestrator is None:
            # Fallback to standard routing
            logger.info(f"MCP Orchestrator unavailable, falling back for task {task.id}")
            agent_name, skill_name, claude_agent, max_turns = TASK_SKILL_MAPPING.get(
                task.type, ("GeneratorAgent", "code-generation", "coder", 10)
            )
            if agent_name == "DockerAgent":
                return await self._execute_docker(task)
            elif agent_name == "BashExecutor":
                return await self._execute_bash(task)
            else:
                return await self._execute_claude(task, skill_name, claude_agent, max_turns)

        # Build task description for orchestrator
        task_description = f"""Task: {task.title}
Description: {task.description}
Type: {task.type}
Working directory: {self.output_dir}

Execute this task using the available MCP tools. Write all files to the working directory."""

        orchestrator_type = self._map_task_type_to_orchestrator_type(task.type)

        try:
            result = await orchestrator.execute_task(
                task=task_description,
                task_type=orchestrator_type,
                context={"epic_id": task.epic_id, "task_id": task.id},
                task_id=task.id,
            )

            success = result.status == "completed"
            return TaskExecutionResult(
                success=success,
                output=str(result.result) if result.result else "",
                error=result.error if not success else None,
            )

        except Exception as e:
            logger.error(f"MCP Orchestrator execution failed: {e} | task_id={task.id}")
            # Fallback to standard execution
            agent_name, skill_name, claude_agent, max_turns = TASK_SKILL_MAPPING.get(
                task.type, ("GeneratorAgent", "code-generation", "coder", 10)
            )
            if agent_name == "DockerAgent":
                return await self._execute_docker(task)
            elif agent_name == "BashExecutor":
                return await self._execute_bash(task)
            else:
                return await self._execute_claude(task, skill_name, claude_agent, max_turns)

    # =========================================================================
    # Prompt Generation
    # =========================================================================

    def _gather_context(self, task: Task, skill_name: Optional[str] = None) -> str:
        """
        Stage 1 input: Gathers all raw context for a task.

        Collects project structure, tech stack, schema, OpenAPI contracts,
        data dictionary, design assets, user stories, Gherkin tests,
        existing code patterns, and task details into a single context string.

        Context sources are loaded selectively based on task type:
        - schema_* → data dictionary (entity fields), Prisma schema
        - api_*    → OpenAPI spec, Prisma schema, user stories
        - fe_*     → screen mockups, design tokens, user stories
        - test_*   → Gherkin scenarios, user stories
        - All      → tech stack, project structure, existing code

        Args:
            task: Task to gather context for
            skill_name: Optional skill name to include context from

        Returns:
            Raw context string for Stage 1 distillation
        """
        prompt_parts = []

        # =====================================================================
        # 1. PROJECT CONTEXT: Working directory and folder structure
        # =====================================================================
        project_structure = self._get_project_structure()
        prompt_parts.extend([
            "## Output Directory (where you write ALL files)",
            "Working directory: . (current directory — write files with paths like `src/modules/...`)",
            "",
            "## CRITICAL: File Path Rules",
            "- ALL source code MUST be written to the `src/` directory inside the output dir",
            "- NEVER write code files to `generated/` - that directory is ONLY for Prisma client output",
            "- Module structure: `src/modules/<module-name>/`",
            "- Guards: `src/guards/`",
            "- Shared lib: `src/lib/`",
            "- DTOs: `src/modules/<module-name>/dto/`",
            "- Validators: `src/modules/<module-name>/validators/`",
            "",
        ])

        if project_structure:
            prompt_parts.extend([
                "## Existing Project Structure",
                project_structure,
                "",
            ])

        # =====================================================================
        # 2. TECH STACK: Technology choices from project specs
        # =====================================================================
        tech_stack = self._get_tech_stack_context()
        if tech_stack:
            prompt_parts.extend([
                "## Technology Stack",
                f"```json\n{tech_stack}\n```",
                "",
            ])

        # =====================================================================
        # 2b. BACKEND API ROUTES: Inject real routes for frontend tasks
        # =====================================================================
        if task.type.startswith("fe_"):
            backend_routes = self._get_backend_routes()
            if backend_routes:
                prompt_parts.extend([backend_routes, ""])

        # =====================================================================
        # 3. AGENT PREFIX: Role-specific folder path instructions
        # =====================================================================
        agent_type = self._get_agent_type(task)
        agent_prefix = self._get_agent_prefix(agent_type)
        if agent_prefix:
            prompt_parts.extend([
                "## Your Role",
                agent_prefix,
                "",
            ])

        # =====================================================================
        # 4. DATA DICTIONARY: Entity definitions for schema tasks
        # =====================================================================
        if task.type.startswith("schema_"):
            dict_context = self._get_data_dictionary_context(task)
            if dict_context:
                prompt_parts.extend([
                    "## Entity Definition (from Data Dictionary - implement EXACTLY these fields)",
                    dict_context,
                    "",
                ])

        # =====================================================================
        # 5. SCHEMA CONTEXT: Prisma schema for API/service/dto tasks
        # =====================================================================
        if task.type in ("api_controller", "api_service", "api_dto", "api_guard",
                         "api_validation", "schema_model", "schema_relations"):
            schema_context = self._get_schema_context()
            if schema_context:
                prompt_parts.extend([
                    "## Database Schema (Prisma)",
                    schema_context,
                    "",
                ])

        # =====================================================================
        # 6. OPENAPI CONTRACT: Full endpoint spec for API tasks
        # =====================================================================
        if task.type in ("api_controller", "api_service", "api_dto", "api_guard",
                         "api_validation"):
            api_contract = self._get_openapi_contract(task)
            if api_contract:
                prompt_parts.extend([
                    "## API Contract (from OpenAPI spec - implement EXACTLY this)",
                    api_contract,
                    "",
                ])

        # =====================================================================
        # 7. DESIGN CONTEXT: Screen mockups + design tokens for frontend tasks
        # =====================================================================
        if task.type.startswith("fe_"):
            design_context = self._get_design_context(task)
            if design_context:
                prompt_parts.extend([
                    "## UI Design Context",
                    design_context,
                    "",
                ])

        # =====================================================================
        # 8. USER STORY CONTEXT: Enriched requirements
        # =====================================================================
        if task.related_requirements or task.related_user_stories:
            story_context = self._get_user_story_context(task)
            if story_context:
                prompt_parts.extend([
                    "## User Story / Requirements Context",
                    story_context,
                    "",
                ])

        # =====================================================================
        # 9. TEST CONTEXT: Gherkin scenarios for test tasks
        # =====================================================================
        if task.type.startswith("test_"):
            test_context = self._get_test_context(task)
            if test_context:
                prompt_parts.extend([
                    "## Test Scenarios (Gherkin - implement these EXACT scenarios)",
                    test_context,
                    "",
                ])

        # =====================================================================
        # 10. EXISTING CODE CONTEXT: Relevant files from project (fungus-like)
        # =====================================================================
        code_context = self._get_relevant_code_context(task)
        if code_context:
            prompt_parts.extend([
                "## Existing Code (follow these patterns)",
                code_context,
                "",
            ])

        # =====================================================================
        # 10b. NestJS MODULE TEMPLATE (if no existing code found)
        # =====================================================================
        if not code_context and (task.type.startswith("api_") or "API" in task.id):
            prompt_parts.extend([
                "## NestJS Module Template (follow this EXACT structure)",
                "Each feature module MUST have these files:",
                "",
                "```typescript:src/modules/example/example.module.ts",
                "import { Module } from '@nestjs/common';",
                "import { ExampleController } from './example.controller';",
                "import { ExampleService } from './example.service';",
                "",
                "@Module({",
                "  controllers: [ExampleController],",
                "  providers: [ExampleService],",
                "  exports: [ExampleService],",
                "})",
                "export class ExampleModule {}",
                "```",
                "",
                "```typescript:src/modules/example/example.controller.ts",
                "import { Controller, Get, Post, Body, Param, UseGuards } from '@nestjs/common';",
                "import { ExampleService } from './example.service';",
                "import { JwtAuthGuard } from '../../guards/jwt-auth.guard';",
                "",
                "@Controller('example')",
                "@UseGuards(JwtAuthGuard)",
                "export class ExampleController {",
                "  constructor(private readonly exampleService: ExampleService) {}",
                "",
                "  @Get()",
                "  async findAll() { return this.exampleService.findAll(); }",
                "",
                "  @Get(':id')",
                "  async findOne(@Param('id') id: string) { return this.exampleService.findOne(id); }",
                "}",
                "```",
                "",
                "```typescript:src/modules/example/example.service.ts",
                "import { Injectable } from '@nestjs/common';",
                "import { PrismaService } from '../../prisma/prisma.service';",
                "",
                "@Injectable()",
                "export class ExampleService {",
                "  constructor(private prisma: PrismaService) {}",
                "",
                "  async findAll() { return this.prisma.example.findMany(); }",
                "  async findOne(id: string) { return this.prisma.example.findUnique({ where: { id } }); }",
                "}",
                "```",
                "",
                "IMPORTANT: Generate COMPLETE files, not fragments. Every class needs its decorators.",
                "",
            ])

        # =====================================================================
        # 11. TASK DETAILS
        # =====================================================================
        prompt_parts.extend([
            f"# Task: {task.title}",
            "",
            "## Description",
            task.description,
            "",
        ])

        if skill_name:
            prompt_parts.extend([
                f"## Skill Context: {skill_name}",
                f"Implement following {skill_name} patterns.",
                "",
            ])

        if task.output_files:
            prompt_parts.extend([
                "## Expected Output Files (write to these EXACT paths)",
                *[f"- {f}" for f in task.output_files],
                "",
            ])

        if task.related_requirements:
            prompt_parts.extend([
                "## Related Requirements",
                *[f"- {r}" for r in task.related_requirements],
                "",
            ])

        if task.related_user_stories:
            prompt_parts.extend([
                "## Related User Stories",
                *[f"- {us}" for us in task.related_user_stories],
                "",
            ])

        if task.success_criteria:
            prompt_parts.extend([
                "## Success Criteria",
                task.success_criteria,
                "",
            ])

        # =====================================================================
        # 11b. USER FIX INSTRUCTIONS (injected on rerun with context)
        # =====================================================================
        if getattr(task, 'user_fix_instructions', None):
            prompt_parts.extend([
                "## USER FIX INSTRUCTIONS (CRITICAL - follow these)",
                "The user provided these instructions to fix issues from the previous attempt:",
                task.user_fix_instructions,
                "",
                "## Previous Error",
                task.error_message or "No previous error.",
                "",
            ])

        # =====================================================================
        # 11c. Phase 29: ENRICHMENT CONTEXT (diagrams, gaps, DTOs from docs)
        # =====================================================================
        if ContextInjector is not None:
            enrichment_text = ContextInjector.format_enrichment(task)
            if enrichment_text:
                prompt_parts.extend([enrichment_text, ""])

            story_detail_text = ContextInjector.format_user_stories_detail(task)
            if story_detail_text:
                prompt_parts.extend([story_detail_text, ""])

        # =====================================================================
        # 12. INSTRUCTIONS: Task-type-specific (no Prisma for frontend/tests)
        # =====================================================================
        prompt_parts.extend([
            "## Instructions",
            "Implement this task now. Write code to the EXACT file paths specified.",
            "Output directory: . (current working directory — use relative paths like `src/modules/...`)",
        ])

        if task.type.startswith("fe_"):
            prompt_parts.extend([
                "IMPORTANT: All source files go under `src/` - NEVER under `generated/`.",
                "Use functional React components with TypeScript (.tsx).",
                "Follow the design tokens for colors, spacing, and typography.",
            ])
        elif task.type.startswith("test_"):
            prompt_parts.extend([
                "Use Playwright for E2E tests, Vitest for unit/integration tests.",
                "NO MOCKS - real database, real HTTP calls.",
                "Follow the Gherkin scenarios exactly.",
            ])
        elif task.type.startswith("schema_"):
            prompt_parts.extend([
                "Write Prisma schema syntax (not TypeScript).",
                "Include ALL fields from the data dictionary.",
                "Add proper field types, constraints, and relations.",
            ])
        else:
            prompt_parts.extend([
                "IMPORTANT: All source files go under `src/` - NEVER under `generated/`.",
                "Follow existing patterns in the codebase. Use TypeScript with proper types.",
                "Import Prisma client from `../../generated/prisma` (relative to module).",
            ])

        return "\n".join(prompt_parts)

    def _get_project_structure(self) -> str:
        """Get existing project folder structure from output_dir for context."""
        try:
            src_path = self.output_dir / "src"
            if not src_path.exists():
                return ""

            lines = ["```"]
            lines.append("src/")
            for item in sorted(src_path.iterdir()):
                if item.is_dir():
                    lines.append(f"  {item.name}/")
                    for sub in sorted(item.iterdir()):
                        if sub.is_dir():
                            lines.append(f"    {sub.name}/")
                            for sub2 in sorted(sub.iterdir()):
                                if sub2.is_file() and sub2.suffix in ('.ts', '.tsx'):
                                    lines.append(f"      {sub2.name}")
                                elif sub2.is_dir():
                                    lines.append(f"      {sub2.name}/")
                                    for sub3 in sorted(sub2.iterdir()):
                                        if sub3.is_file():
                                            lines.append(f"        {sub3.name}")
                        elif sub.is_file() and sub.suffix in ('.ts', '.tsx'):
                            lines.append(f"    {sub.name}")
                elif item.is_file() and item.suffix in ('.ts', '.tsx'):
                    lines.append(f"  {item.name}")
            lines.append("```")
            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"Failed to get project structure: {e}")
            return ""

    def _get_agent_prefix(self, agent_type: str) -> str:
        """Get role-specific instructions with explicit folder paths."""
        prefixes = {
            "backend": """You are a NestJS/TypeScript backend expert.
- Controllers go in: src/modules/<module>/<module>.controller.ts
- Services go in: src/modules/<module>/<module>.service.ts
- DTOs go in: src/modules/<module>/dto/<name>.dto.ts
- Guards go in: src/guards/<name>.guard.ts
- Validators go in: src/modules/<module>/validators/<name>.validator.ts
- Database client: src/lib/database.ts
- Use Prisma ORM imported from '../../generated/prisma'
- Use class-based controllers with decorators (@Controller, @Get, @Post, etc.)
- Use dependency injection for services""",
            "frontend": """You are a Web React/TypeScript frontend expert building a BROWSER-BASED web application.
- Pages go in: frontend/src/pages/{Name}/{Name}.tsx
- Components go in: frontend/src/components/{Name}/{Name}.tsx
- Hooks go in: frontend/src/hooks/use{Name}.ts
- API clients go in: frontend/src/api/{name}API.ts
- IMPORTANT: ALL React/frontend files MUST be under the frontend/ directory, NOT src/
- Use functional components with TypeScript (.tsx)
- Use modern React patterns (hooks, context, react-router-dom)
- CRITICAL: Use ONLY the backend API endpoints listed in the context. Do NOT invent API paths.
- API base URL comes from `import.meta.env.VITE_API_BASE_URL`
- All API calls must match the exact paths from the backend endpoints list
- CRITICAL: This is a WEB application using Vite + React, NOT a mobile app.
  * Use standard HTML elements (div, span, button, input) NOT React Native components
  * Use CSS/Tailwind/CSS-in-JS for styling, NOT StyleSheet.create()
  * Use react-router-dom for navigation, NOT @react-navigation/native
  * NEVER import from 'react-native', 'react-native-paper', '@react-navigation/*'
  * Use fetch/axios for API calls, NOT react-native AsyncStorage""",
            "testing": """You are a testing expert.
- Unit tests go in: tests/unit/
- Integration tests go in: tests/integration/
- E2E tests go in: tests/e2e/
- Use Vitest for unit/integration tests
- Use Playwright for E2E tests
- NO MOCKS - real database, real HTTP calls""",
            "devops": """You are a DevOps expert.
- Docker configs go in project root
- Scripts go in: scripts/
- CI/CD goes in: .github/workflows/""",
        }
        return prefixes.get(agent_type, "")

    def _get_tech_stack_context(self) -> str:
        """Load technology stack from tech_stack/tech_stack.json."""
        try:
            ts_path = self.project_path / "tech_stack" / "tech_stack.json"
            if not ts_path.exists():
                # Also check tech_stack.json at project root
                ts_path = self.project_path / "tech_stack.json"
            if not ts_path.exists():
                return ""
            content = ts_path.read_text(encoding='utf-8')
            if len(content) > 2000:
                content = content[:2000] + "..."
            return content
        except Exception as e:
            logger.debug(f"Failed to load tech stack: {e}")
            return ""

    def _get_backend_routes(self) -> str:
        """
        Parse api_documentation.md and return a formatted list of backend API endpoints.

        Used to inject real backend routes into frontend task context so that
        generated API clients use the correct paths instead of guessing.

        Returns:
            Formatted string with all backend endpoints, or empty string if
            no api_documentation.md is found.
        """
        try:
            api_doc_path = self.project_path / "api" / "api_documentation.md"
            if not api_doc_path.exists():
                logger.debug("No api/api_documentation.md found — skipping backend route injection")
                return ""

            content = api_doc_path.read_text(encoding="utf-8")

            # Parse endpoints using the same regex as APIDocumentationParser
            endpoint_pattern = re.compile(
                r"^####\s+`?(GET|POST|PUT|DELETE|PATCH)`?\s+(/[^\s]+)", re.MULTILINE
            )
            # Capture summaries: bold text on the line(s) following the endpoint header
            summary_pattern = re.compile(r"^\*\*([^*]+)\*\*$", re.MULTILINE)

            lines = content.split("\n")
            endpoints: list[str] = []
            current_resource = ""

            for i, line in enumerate(lines):
                # Track resource headers (### ResourceName)
                if line.startswith("### ") and not line.startswith("####"):
                    current_resource = line.lstrip("# ").strip()
                    continue

                ep_match = endpoint_pattern.match(line)
                if ep_match:
                    method = ep_match.group(1)
                    path = ep_match.group(2)
                    # Look ahead for summary (bold text within next 3 lines)
                    summary = ""
                    for j in range(i + 1, min(i + 4, len(lines))):
                        s_match = summary_pattern.match(lines[j])
                        if s_match:
                            summary = s_match.group(1).strip()
                            break
                    entry = f"{method} {path}"
                    if summary:
                        entry += f" - {summary}"
                    endpoints.append(entry)

            if not endpoints:
                logger.debug("api_documentation.md found but no endpoints parsed")
                return ""

            header = (
                "## Available Backend API Endpoints\n"
                "Use these EXACT paths in your API client. Do NOT invent new paths.\n"
                "API base URL: `import.meta.env.VITE_API_BASE_URL`\n"
            )
            route_list = "\n".join(f"- {ep}" for ep in endpoints)
            result = f"{header}\n{route_list}"

            logger.info(f"Injected {len(endpoints)} backend API routes into frontend context")
            return result

        except Exception as e:
            logger.debug(f"Failed to parse backend routes: {e}")
            return ""

    def _get_schema_context(self) -> str:
        """Load Prisma schema for API/service tasks. Checks output_dir first, then project_path."""
        try:
            # Check output_dir first (generated schema), then input project_path
            schema_path = self.output_dir / "prisma" / "schema.prisma"
            if not schema_path.exists():
                schema_path = self.project_path / "prisma" / "schema.prisma"
            if schema_path.exists():
                content = schema_path.read_text(encoding='utf-8')
                # Truncate if too long (keep models, skip comments)
                if len(content) > 4000:
                    content = content[:4000] + "\n... (truncated)"
                return f"```prisma\n{content}\n```"
        except Exception as e:
            logger.debug(f"Failed to load schema: {e}")
        return ""

    def _get_data_dictionary_context(self, task: Task) -> str:
        """Load entity definition from data/data_dictionary.md for schema/API tasks."""
        try:
            dict_path = self.project_path / "data" / "data_dictionary.md"
            if not dict_path.exists():
                return ""
            content = dict_path.read_text(encoding='utf-8')

            # Extract the entity name from task ID
            entity_name = self._detect_entity_from_task(task)
            if not entity_name:
                return ""

            # Find entity section: "### Entity: AuthMethod" or "### AuthMethod" or "## AuthMethod"
            import re
            patterns = [
                rf'###\s+Entity:\s+{re.escape(entity_name)}\b',
                rf'###\s+{re.escape(entity_name)}\b',
                rf'##\s+{re.escape(entity_name)}\b',
            ]
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    start = match.start()
                    # Find end (next ### or ## heading at same or higher level)
                    end_match = re.search(r'\n#{2,3}\s', content[start + 1:])
                    end = start + 1 + end_match.start() if end_match else min(len(content), start + 3000)
                    section = content[start:end].strip()
                    if len(section) > 3000:
                        section = section[:3000] + "\n... (truncated)"
                    return section
            return ""
        except Exception as e:
            logger.debug(f"Failed to load data dictionary: {e}")
            return ""

    def _detect_entity_from_task(self, task: Task) -> Optional[str]:
        """Extract entity name from task ID like EPIC-001-SCHEMA-AuthMethod-model."""
        import re
        match = re.search(r'SCHEMA-(\w+)-(?:model|relations|migration)', task.id)
        if match:
            return match.group(1)
        # For API tasks, derive from the module name
        module = self._detect_module_from_task(task)
        return module.capitalize() if module else None

    def _get_design_context(self, task: Task) -> str:
        """Load UI design context for frontend tasks: screen mockup + design tokens."""
        parts = []

        # 1. Find relevant screen mockup
        screens_dir = self.project_path / "ui_design" / "screens"
        if screens_dir.exists():
            for screen_file in sorted(screens_dir.glob("screen-*.md")):
                try:
                    content = screen_file.read_text(encoding='utf-8')
                    if self._screen_matches_task(content, task):
                        if len(content) > 3000:
                            content = content[:3000] + "\n... (truncated)"
                        parts.append(f"### Screen Design\n{content}")
                        break
                except Exception:
                    continue

        # 2. Load design tokens (compact, always useful for frontend)
        tokens_path = self.project_path / "ui_design" / "design_tokens.json"
        if tokens_path.exists():
            try:
                tokens = tokens_path.read_text(encoding='utf-8')
                if len(tokens) > 2000:
                    tokens = tokens[:2000] + "\n... (truncated)"
                parts.append(f"### Design Tokens\n```json\n{tokens}\n```")
            except Exception:
                pass

        return "\n\n".join(parts)

    def _screen_matches_task(self, screen_content: str, task: Task) -> bool:
        """Check if a screen mockup relates to this frontend task."""
        screen_lower = screen_content.lower()
        # Build keywords from task ID and title
        keywords = []
        task_text = (task.id + " " + task.title).lower()

        if "login" in task_text:
            keywords = ["login", "register", "/register", "/login", "phone registration"]
        elif "profile" in task_text:
            keywords = ["profile", "/profile"]
        elif "settings" in task_text or "setting" in task_text:
            keywords = ["settings", "/settings", "privacy"]
        elif "chat" in task_text or "message" in task_text:
            keywords = ["chat", "/chat", "message", "conversation"]
        elif "contact" in task_text:
            keywords = ["contact", "/contacts"]
        else:
            # Fallback: extract page name from task ID (e.g., FE-LoginPage → loginpage)
            import re
            match = re.search(r'FE-(\w+)', task.id)
            if match:
                keywords = [match.group(1).lower()]

        return any(kw in screen_lower for kw in keywords)

    def _get_test_context(self, task: Task) -> str:
        """Load Gherkin test scenarios for test tasks from testing/test_documentation.md."""
        try:
            test_path = self.project_path / "testing" / "test_documentation.md"
            if not test_path.exists():
                return ""
            content = test_path.read_text(encoding='utf-8')

            # Find relevant feature/scenario by user story ID or task title
            search_terms = list(task.related_user_stories or [])
            # Also try matching by task title keywords
            if not search_terms and task.title:
                search_terms = [task.title[:60]]

            for term in search_terms:
                idx = content.find(term)
                if idx >= 0:
                    # Walk back to ### heading (wraps the entire feature block including gherkin)
                    start = content.rfind('\n### ', 0, idx)
                    if start < 0:
                        start = max(0, idx - 500)
                    else:
                        start += 1  # skip the newline
                    # Find end (next ### heading or end of file)
                    end = content.find('\n### ', start + 10)
                    if end < 0:
                        end = min(len(content), start + 4000)
                    section = content[start:end].strip()
                    if len(section) > 4000:
                        section = section[:4000] + "..."
                    return section

            return ""
        except Exception as e:
            logger.debug(f"Failed to load test context: {e}")
            return ""

    def _get_relevant_code_context(self, task: Task) -> str:
        """
        Load relevant existing code files for pattern matching (fungus-like).
        Reads from output_dir where generated code lives.
        """
        try:
            src_path = self.output_dir / "src"
            if not src_path.exists():
                return ""

            # Determine which module this task relates to
            module_name = self._detect_module_from_task(task)
            if not module_name:
                return ""

            module_path = src_path / "modules" / module_name
            if not module_path.exists():
                # Try finding a similar module for patterns
                modules_path = src_path / "modules"
                if modules_path.exists():
                    for other_module in sorted(modules_path.iterdir()):
                        if other_module.is_dir():
                            module_path = other_module
                            break  # Use first existing module as template
                    else:
                        return ""
                else:
                    return ""

            # Collect relevant files (max 3 files, max 2000 chars each)
            parts = []
            files_shown = 0
            for f in sorted(module_path.rglob("*.ts")):
                if files_shown >= 3:
                    break
                try:
                    content = f.read_text(encoding='utf-8')
                    if len(content) > 2000:
                        content = content[:2000] + "\n// ... (truncated)"
                    rel_path = f.relative_to(self.output_dir)
                    parts.append(f"### {rel_path}")
                    parts.append(f"```typescript\n{content}\n```")
                    files_shown += 1
                except Exception:
                    continue

            # Also include guard pattern if exists
            guards_path = src_path / "guards"
            if guards_path.exists() and task.type in ("api_guard",):
                for f in sorted(guards_path.glob("*.ts"))[:1]:
                    try:
                        content = f.read_text(encoding='utf-8')[:1500]
                        rel_path = f.relative_to(self.output_dir)
                        parts.append(f"### {rel_path}")
                        parts.append(f"```typescript\n{content}\n```")
                    except Exception:
                        continue

            return "\n\n".join(parts) if parts else ""

        except Exception as e:
            logger.debug(f"Failed to load code context: {e}")
            return ""

    def _detect_module_from_task(self, task: Task) -> Optional[str]:
        """Detect which module a task belongs to from task ID or title."""
        task_id_lower = task.id.lower()

        # Map API path segments to module names
        module_mappings = {
            "auth": "auth",
            "2fa": "auth",
            "biometric": "auth",
            "pin": "users",
            "users": "users",
            "sessions": "sessions",
            "passkeys": "passkeys",
            "app-lock": "app-lock",
            "app_lock": "app-lock",
            "phone": "users",
            "device": "users",
        }

        for key, module in module_mappings.items():
            if key in task_id_lower:
                return module

        return None

    def _get_openapi_contract(self, task: Task) -> str:
        """
        Extract the relevant OpenAPI endpoint spec for this task.
        Provides full request/response schemas, status codes, and descriptions.
        """
        try:
            spec_path = self.project_path / "api" / "openapi_spec.yaml"
            if not spec_path.exists():
                return ""

            content = spec_path.read_text(encoding='utf-8')

            # Extract API path from task ID
            # Task ID format: EPIC-001-API-POST-api_v1_users_phone-registrations-controller
            api_path = self._extract_api_path(task)
            http_method = self._extract_http_method(task)

            if not api_path:
                return ""

            # Find the relevant path section in the YAML
            import re

            # Build the path pattern (e.g., /api/v1/users/phone-registrations)
            lines = content.split('\n')
            capturing = False
            captured_lines = []
            indent_level = 0
            path_found = False

            for i, line in enumerate(lines):
                # Look for the path
                stripped = line.strip()
                if stripped.startswith(api_path + ':') or stripped == api_path + ':':
                    capturing = True
                    indent_level = len(line) - len(line.lstrip())
                    captured_lines.append(line)
                    path_found = True
                    continue

                if capturing:
                    current_indent = len(line) - len(line.lstrip()) if line.strip() else indent_level + 1
                    if line.strip() and current_indent <= indent_level:
                        capturing = False
                        break
                    captured_lines.append(line)

            if not captured_lines:
                return ""

            # Also find referenced schemas
            path_content = '\n'.join(captured_lines)
            schema_refs = re.findall(r"\$ref:\s*['\"]#/components/schemas/(\w+)['\"]", path_content)

            # Extract schema definitions
            schema_parts = []
            for schema_name in set(schema_refs):
                schema_content = self._extract_schema_definition(lines, schema_name)
                if schema_content:
                    schema_parts.append(schema_content)

            result = f"### Endpoint: {http_method.upper()} {api_path}\n"
            result += f"```yaml\n{path_content}\n```\n"

            if schema_parts:
                result += "\n### Request/Response Schemas\n"
                result += "```yaml\n" + "\n".join(schema_parts) + "\n```"

            return result

        except Exception as e:
            logger.debug(f"Failed to load OpenAPI contract: {e}")
            return ""

    def _extract_api_path(self, task: Task) -> str:
        """Extract the API path from a task ID like EPIC-001-API-POST-api_v1_users_phone-registrations-controller."""
        task_id = task.id
        # Remove prefix: EPIC-001-API-POST- or EPIC-001-API-GET-, etc.
        import re
        match = re.search(r'API-(?:POST|GET|PUT|DELETE|PATCH)-(.+?)-(controller|service|dto|guard|validation)$', task_id)
        if not match:
            return ""

        raw_path = match.group(1)
        # Convert underscores back to slashes: api_v1_users_phone-registrations -> /api/v1/users/phone-registrations
        path = '/' + raw_path.replace('_', '/')
        return path

    def _extract_http_method(self, task: Task) -> str:
        """Extract HTTP method from task ID."""
        import re
        match = re.search(r'API-(POST|GET|PUT|DELETE|PATCH)-', task.id)
        return match.group(1).lower() if match else "get"

    def _extract_schema_definition(self, lines: list, schema_name: str) -> str:
        """Extract a schema definition from OpenAPI YAML lines."""
        capturing = False
        captured = []
        indent_level = 0

        for line in lines:
            stripped = line.strip()
            if stripped == f"{schema_name}:" and not capturing:
                # Check it's under schemas section
                capturing = True
                indent_level = len(line) - len(line.lstrip())
                captured.append(line)
                continue

            if capturing:
                current_indent = len(line) - len(line.lstrip()) if line.strip() else indent_level + 1
                if line.strip() and current_indent <= indent_level:
                    break
                captured.append(line)

        return '\n'.join(captured) if captured else ""

    def _get_user_story_context(self, task: Task) -> str:
        """
        Load user story and requirements context for the task.

        For requirement IDs (e.g., WA-AUTH-001): finds the user story linked to
        that requirement via "**Linked Requirement:** WA-AUTH-001" pattern, then
        captures the full user story with acceptance criteria.

        For user story IDs (e.g., US-001): directly finds the ## US-001 heading.
        """
        try:
            stories_path = self.project_path / "user_stories" / "user_stories.md"
            if not stories_path.exists():
                return ""

            content = stories_path.read_text(encoding='utf-8')
            relevant_parts = []
            seen = set()  # Deduplicate sections

            # Match by requirement IDs → find linked user stories
            for req_id in (task.related_requirements or []):
                # Search for user stories linked to this requirement
                # Pattern in user_stories.md: "**Linked Requirement:** WA-AUTH-001"
                search = f"**Linked Requirement:** {req_id}"
                idx = content.find(search)
                if idx >= 0:
                    # Walk back to the ## US-XXX heading
                    start = content.rfind('\n## ', 0, idx)
                    if start < 0:
                        start = max(0, idx - 200)
                    else:
                        start += 1  # skip the newline
                    # Find end (next ## heading)
                    end = content.find('\n## ', idx + len(search))
                    if end < 0:
                        end = min(len(content), idx + 2000)
                    section = content[start:end].strip()
                    section_key = section[:100]  # Use prefix for dedup
                    if section_key not in seen and len(section) > 20:
                        if len(section) > 2000:
                            section = section[:2000] + "..."
                        relevant_parts.append(section)
                        seen.add(section_key)

            # Match by user story IDs directly (e.g., US-001)
            for us_id in (task.related_user_stories or []):
                idx = content.find(f"## {us_id}")
                if idx < 0:
                    idx = content.find(us_id)
                if idx >= 0:
                    end = content.find('\n## ', idx + 1)
                    if end < 0:
                        end = min(len(content), idx + 1500)
                    section = content[idx:end].strip()
                    section_key = section[:100]
                    if section_key not in seen:
                        if len(section) > 1500:
                            section = section[:1500] + "..."
                        relevant_parts.append(section)
                        seen.add(section_key)

            return "\n\n".join(relevant_parts[:5]) if relevant_parts else ""

        except Exception as e:
            logger.debug(f"Failed to load user story context: {e}")
            return ""

    def _get_agent_type(self, task: Task) -> str:
        """
        Bestimmt Agent-Type basierend auf Task-Type für ClaudeCodeTool.

        Args:
            task: Task to get agent type for

        Returns:
            Agent type name (general, backend, frontend, testing, devops)
        """
        task_type = task.type

        if task_type.startswith("schema_"):
            return "backend"
        elif task_type.startswith("api_"):
            return "backend"
        elif task_type.startswith("fe_"):
            return "frontend"
        elif task_type.startswith("test_"):
            return "testing"
        elif task_type.startswith("setup_"):
            return "devops"
        elif task_type.startswith("docker_"):
            return "devops"
        else:
            return "general"

    def _get_context_profile(self, task: Task) -> str:
        """
        Bestimmt Context-Profile basierend auf Task-Type.

        Args:
            task: Task to get context profile for

        Returns:
            Context profile name
        """
        task_type = task.type

        if task_type.startswith("schema_"):
            return "backend"
        elif task_type.startswith("api_"):
            return "backend"
        elif task_type.startswith("fe_"):
            return "frontend"
        elif task_type.startswith("test_"):
            return "testing"
        elif task_type.startswith("setup_"):
            return "devops"
        elif task_type.startswith("docker_"):
            return "devops"
        else:
            return "general"

    # =========================================================================
    # Status Updates & Events
    # =========================================================================

    async def _update_task_status(
        self,
        task: Task,
        status: str,
        error: Optional[str] = None,
    ):
        """
        Aktualisiert Task-Status und sendet WebSocket Event.

        Args:
            task: Task to update
            status: New status value
            error: Optional error message
        """
        task.status = status
        if error:
            task.error_message = error

        # Save to JSON file
        self._save_task_to_json(task)

        # Send WebSocket event
        await self._publish_event({
            "type": "task_progress_update",
            "data": {
                "type": "task_status_changed",
                "epic_id": task.epic_id,
                "task_id": task.id,
                "task_title": task.title,
                "status": status,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
        })

    async def _publish_event(self, event: Dict[str, Any]):
        """
        Publishes event to EventBus if available.

        Creates proper Event objects for the full EventBus implementation,
        or falls back to dict-based publishing for simpler event buses.

        Args:
            event: Event data to publish
        """
        if self.event_bus:
            try:
                # Try to import Event and EventType from the EventBus module
                # This handles both full EventBus and simpler implementations
                if hasattr(self.event_bus, 'publish'):
                    # Check if this is the full EventBus that needs Event objects
                    try:
                        from src.mind.event_bus import Event, EventType

                        # Map event type string to EventType enum
                        event_type_str = event.get("type", "TASK_PROGRESS_UPDATE")
                        if hasattr(EventType, event_type_str.upper()):
                            event_type = getattr(EventType, event_type_str.upper())
                        else:
                            event_type = EventType.TASK_PROGRESS_UPDATE

                        # Create proper Event object
                        event_obj = Event(
                            type=event_type,
                            source="task_executor",
                            data=event.get("data", event),
                        )
                        await self.event_bus.publish(event_obj)
                    except ImportError:
                        # Fall back to dict-based publishing
                        await self.event_bus.publish(event)
                elif hasattr(self.event_bus, 'emit'):
                    self.event_bus.emit(event)
                else:
                    logger.warning("EventBus has no publish/emit method")
            except Exception as e:
                logger.error(f"Failed to publish event: {e}")

    def _save_task_to_json(self, task: Task):
        """
        Speichert aktualisierten Task in JSON-Datei.

        Args:
            task: Task to save
        """
        tasks_dir = self.project_path / "tasks"
        if not tasks_dir.exists():
            return

        task_file = tasks_dir / f"{task.epic_id.lower()}-tasks.json"

        if not task_file.exists():
            return

        try:
            data = json.loads(task_file.read_text(encoding='utf-8'))

            for i, t in enumerate(data.get("tasks", [])):
                if t.get("id") == task.id:
                    data["tasks"][i]["status"] = task.status
                    data["tasks"][i]["error_message"] = task.error_message
                    data["tasks"][i]["retry_count"] = task.retry_count
                    data["tasks"][i]["actual_minutes"] = task.actual_minutes
                    break

            # Update progress
            tasks = data.get("tasks", [])
            completed = sum(1 for t in tasks if t.get("status") == "completed")
            failed = sum(1 for t in tasks if t.get("status") == "failed")
            total = len(tasks)

            data["completed_tasks"] = completed
            data["failed_tasks"] = failed
            data["progress_percent"] = (completed / total * 100) if total > 0 else 0
            data["last_run_at"] = datetime.now().isoformat()

            task_file.write_text(json.dumps(data, indent=2), encoding='utf-8')

        except Exception as e:
            logger.error(f"Failed to save task to JSON: {e}")


# =============================================================================
# Test
# =============================================================================

async def test_task_executor():
    """Test the TaskExecutor"""
    print("=== Task Executor Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    executor = TaskExecutor(str(test_path))

    # Test 1: Bash execution
    print("1. Test Bash execution:")
    bash_task = Task(
        id="test-bash",
        epic_id="TEST",
        type="verify_build",
        title="Test bash execution",
        description="Run echo test",
        command="echo 'Hello from TaskExecutor'",
    )
    result = await executor.execute_task(bash_task)
    print(f"   Success: {result.success}")
    print(f"   Output: {result.output.strip()}")

    # Test 2: Prompt generation
    print("\n2. Test prompt generation:")
    code_task = Task(
        id="test-code",
        epic_id="EPIC-001",
        type="schema_model",
        title="Create User model",
        description="Create Prisma User model with id, email, password",
        output_files=["prisma/schema.prisma"],
        related_requirements=["WA-AUTH-001"],
    )
    prompt = executor._gather_context(code_task)
    print(f"   Generated prompt:\n{prompt[:300]}...")

    # Test 3: Context profile
    print("\n3. Test context profile selection:")
    for task_type in ["schema_model", "api_controller", "fe_page", "test_unit"]:
        task = Task(id="test", epic_id="TEST", type=task_type, title="", description="")
        profile = executor._get_context_profile(task)
        print(f"   {task_type} -> {profile}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_task_executor())
