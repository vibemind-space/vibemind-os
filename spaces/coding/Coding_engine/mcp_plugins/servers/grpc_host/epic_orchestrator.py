#!/usr/bin/env python3
"""
Epic Orchestrator - Phase 4: Iteration 11

Orchestrates the execution of all tasks for an Epic in dependency order.
Connects the "Run EPIC-XXX" button in the Dashboard to actual code generation.

Features:
- Loads task lists from JSON files
- Executes tasks in topological order (respecting dependencies)
- Handles checkpoints for user approval gates
- Publishes progress events to Dashboard via WebSocket
- Supports resume/retry of failed tasks
- Multi-Epic orchestration support
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# Fix Windows encoding for emoji characters in CLI output
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8:replace'
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass  # Older Python versions may not support reconfigure
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)

# Import from our modules
try:
    from task_executor import TaskExecutor, TaskExecutionResult, TASK_SKILL_MAPPING
    from epic_task_generator import (
        Task, TaskStatus, TaskType, EpicTaskList, EpicTaskGenerator
    )
    from epic_parser import EpicParser, Epic
except ImportError:
    from mcp_plugins.servers.grpc_host.task_executor import TaskExecutor, TaskExecutionResult, TASK_SKILL_MAPPING
    from mcp_plugins.servers.grpc_host.epic_task_generator import (
        Task, TaskStatus, TaskType, EpicTaskList, EpicTaskGenerator
    )
    from mcp_plugins.servers.grpc_host.epic_parser import EpicParser, Epic

# Phase 29: Task Enrichment
try:
    from src.autogen.task_enricher import TaskEnricher
except ImportError:
    try:
        import importlib
        _mod = importlib.import_module("src.autogen.task_enricher")
        TaskEnricher = _mod.TaskEnricher
    except Exception:
        TaskEnricher = None  # Graceful degradation


# =============================================================================
# Orchestration Result
# =============================================================================

@dataclass
class EpicExecutionResult:
    """Result of executing an entire Epic"""
    epic_id: str
    success: bool
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    duration_seconds: float = 0
    error: Optional[str] = None
    checkpoint_paused: bool = False
    checkpoint_task_id: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["progress_percent"] = self.progress_percent
        return result


class ExecutionMode(Enum):
    """Epic execution modes"""
    FULL = "full"           # Execute all pending tasks
    RESUME = "resume"       # Continue from last checkpoint
    RETRY_FAILED = "retry"  # Retry only failed tasks
    DRY_RUN = "dry_run"     # Validate without executing


# =============================================================================
# Epic Orchestrator
# =============================================================================

class EpicOrchestrator:
    """
    Orchestriert die Ausführung eines kompletten Epics.

    Responsibilities:
    - Load or generate tasks for an Epic
    - Execute tasks in dependency order (with optional parallelism)
    - Handle checkpoints and user approval gates
    - Track progress and publish WebSocket events
    - Support resume/retry functionality
    """

    # Default parallelism settings
    DEFAULT_MAX_PARALLEL = 1  # Sequential by default
    MAX_ALLOWED_PARALLEL = 20  # Safety limit for LLM API calls (increased for pipeline parallelism)

    def __init__(
        self,
        project_path: str,
        output_dir: Optional[str] = None,
        event_bus: Optional[Any] = None,
        claude_tool: Optional[Any] = None,
        max_parallel_tasks: int = 1,
        headless_mode: bool = True,
        two_stage: bool = True,
        enable_som: bool = False,
        som_config: Optional[Any] = None,
        skip_task_gen: bool = False,
    ):
        """
        Args:
            project_path: Path to the input project (requirements, specs, tasks JSON)
            output_dir: Path where generated code is written. If None, defaults to
                        <project_path>/output/. Claude CLI uses this as working directory.
            event_bus: EventBus instance for WebSocket updates
            claude_tool: Optional pre-configured ClaudeCodeTool instance
            max_parallel_tasks: Maximum number of tasks to run in parallel (1-10)
            headless_mode: If True, auto-approve checkpoints and generate dev secrets
            two_stage: If True, use two-stage LLM execution (plan then execute).
                       If False, send enriched context directly to Claude CLI.
            enable_som: If True, activate Society of Mind bridge for autonomous
                        debugging, live preview, dependency management etc.
            som_config: Optional SoMBridgeConfig for fine-tuning SoM behavior.
        """
        self.project_path = Path(project_path)
        self.output_dir = Path(output_dir) if output_dir else self.project_path / "output"
        self.event_bus = event_bus
        self.headless_mode = headless_mode
        self.skip_task_gen = skip_task_gen

        # Society of Mind integration
        self.enable_som = enable_som
        self.som_config = som_config
        self.som_bridge = None  # Initialized in run_epic() if enable_som=True

        # Parallelism configuration
        self.max_parallel_tasks = min(
            max(1, max_parallel_tasks),
            self.MAX_ALLOWED_PARALLEL
        )
        self._semaphore: Optional[asyncio.Semaphore] = None

        # Initialize components
        # Read consolidation_mode from engine_settings
        _consolidation = "feature"
        try:
            import yaml
            _settings_path = Path(project_path).parent.parent / "config" / "engine_settings.yml"
            if not _settings_path.exists():
                _settings_path = Path("/app/config/engine_settings.yml")
            if _settings_path.exists():
                with open(_settings_path) as f:
                    _cfg = yaml.safe_load(f) or {}
                _consolidation = _cfg.get("generation", {}).get("consolidation_mode", "feature")
        except Exception:
            pass
        self.task_generator = EpicTaskGenerator(str(project_path), consolidation_mode=_consolidation)
        self.task_executor = TaskExecutor(
            str(project_path),
            output_dir=str(self.output_dir),
            event_bus=event_bus,
            claude_tool=claude_tool,
            headless_mode=headless_mode,
            two_stage=two_stage,
            max_concurrent=self.max_parallel_tasks,
        )
        self.epic_parser = EpicParser(str(project_path))

        # Pass MCP Orchestrator flag from som_config to TaskExecutor
        if som_config and isinstance(som_config, dict):
            self.task_executor.use_mcp_orchestrator = som_config.get(
                'enable_mcp_orchestrator', False
            )

        # ── Live DB Sync ──
        self.db_sync = None
        try:
            from db_task_sync import DBTaskSync
            self.db_sync = DBTaskSync()
            logger.info("Live DB sync enabled")
        except Exception as e:
            logger.info("DB sync not available (using JSON only): %s", e)

        # Execution state
        self._running = False
        self._paused = False
        self._current_epic_id: Optional[str] = None
        self._current_task_id: Optional[str] = None
        self._running_task_ids: Set[str] = set()
        self._convergence_ran_diff = False  # Phase 28: Tracks if convergence loop ran diff analysis

        logger.info(
            f"EpicOrchestrator initialized for: {self.project_path} -> {self.output_dir}",
            extra={
                "max_parallel": self.max_parallel_tasks,
            }
        )

    def _set_task_status(self, task, status: str, error_message: str = "", execution_time_ms: int = 0):
        """Set task status in-memory AND sync to DB."""
        task.status = status
        if error_message:
            task.error_message = error_message
        if self.db_sync:
            try:
                self.db_sync.update_task(task.id, status, error_message, execution_time_ms)
            except Exception as e:
                logger.debug("DB sync failed for %s: %s", task.id, e)

    # =========================================================================
    # Main Execution Entry Points
    # =========================================================================

    async def run_epic(
        self,
        epic_id: str,
        mode: ExecutionMode = ExecutionMode.FULL,
        max_tasks: Optional[int] = None,
        phases: Optional[List[str]] = None,
        skip_failed_deps: bool = False,
    ) -> EpicExecutionResult:
        """
        Führt alle Tasks eines Epics aus.

        Args:
            epic_id: Epic ID (e.g., "EPIC-001")
            mode: Execution mode (FULL, RESUME, RETRY_FAILED)

        Returns:
            EpicExecutionResult with execution summary
        """
        import time
        start_time = time.time()

        self._running = True
        self._paused = False
        self._current_epic_id = epic_id

        try:
            # 0. Start Society of Mind bridge if enabled
            if self.enable_som and self.som_bridge is None:
                try:
                    from som_bridge import SoMBridge, SoMBridgeConfig
                except ImportError:
                    from mcp_plugins.servers.grpc_host.som_bridge import SoMBridge, SoMBridgeConfig

                # Support dict (from society_defaults.json) or SoMBridgeConfig
                if isinstance(self.som_config, dict):
                    som_cfg = SoMBridgeConfig(**{
                        k: v for k, v in self.som_config.items()
                        if hasattr(SoMBridgeConfig, k)
                    })
                elif isinstance(self.som_config, SoMBridgeConfig):
                    som_cfg = self.som_config
                else:
                    som_cfg = SoMBridgeConfig()

                self.som_bridge = SoMBridge(
                    project_path=str(self.project_path),
                    output_dir=str(self.output_dir),
                    config=som_cfg,
                )
                await self.som_bridge.start()

                # Pass bridge to TaskExecutor
                self.task_executor.som_bridge = self.som_bridge

                # Publish VNC URL + detected profile to Dashboard
                await self._publish_event({
                    "type": "vnc_preview_ready",
                    "url": self.som_bridge.get_vnc_url(),
                    "port": self.som_bridge.vnc_port,
                    "project_profile": (
                        self.som_bridge.project_profile.to_dict()
                        if self.som_bridge.project_profile else None
                    ),
                })

                logger.info(
                    f"SoM bridge started | agents={len(self.som_bridge.agents)} | "
                    f"vnc={self.som_bridge.get_vnc_url()}"
                )

            # 1. Load or generate tasks
            task_list = self._load_or_generate_tasks(epic_id)
            # Cache for external access (e.g., run_generation.py DB sync)
            self._last_task_list = task_list

            if not task_list or not task_list.tasks:
                return EpicExecutionResult(
                    epic_id=epic_id,
                    success=False,
                    error="No tasks found for epic",
                )

            # 1b. Phase 29: Enrich tasks with documentation context
            if TaskEnricher is not None:
                try:
                    enricher = TaskEnricher(self.project_path)
                    enricher.enrich_all(task_list)
                    logger.info(
                        f"Task enrichment complete: "
                        f"{enricher.stats.tasks_with_requirements}/{len(task_list.tasks)} tasks enriched"
                    )
                except Exception as e:
                    logger.warning(f"Task enrichment failed (non-fatal): {e}")

            # 2. Filter tasks based on mode, phases, and max count
            tasks_to_execute = self._filter_tasks_by_mode(
                task_list.tasks, mode, max_tasks=max_tasks, phases=phases
            )

            if not tasks_to_execute:
                return EpicExecutionResult(
                    epic_id=epic_id,
                    success=True,
                    total_tasks=len(task_list.tasks),
                    completed_tasks=len([t for t in task_list.tasks if t.status == "completed"]),
                )

            # 3. Publish start event
            await self._publish_event({
                "type": "epic_execution_started",
                "epic_id": epic_id,
                "total_tasks": len(tasks_to_execute),
                "mode": mode.value,
            })
            await self._publish_log(
                f"Epic {epic_id} started: {len(tasks_to_execute)} tasks to execute (mode: {mode.value})"
            )

            # 4. Execute tasks in dependency order
            result = await self._execute_tasks_in_order(
                epic_id, task_list.tasks, tasks_to_execute,
                skip_failed_deps=skip_failed_deps,
            )

            # 5. Convergence loop: validate → fix → re-run failed → repeat
            if self.enable_som and self.som_bridge and result.failed_tasks > 0:
                result = await self._convergence_loop(epic_id, task_list, result)

            # 6. Inter-epic build check
            try:
                await self._run_inter_epic_build_check(epic_id, result)
            except Exception as e:
                logger.warning(f"Post-epic build check failed (non-fatal): {e}")

            # 7. Update execution metadata
            result.duration_seconds = time.time() - start_time
            self._update_task_list_metadata(epic_id, task_list)

            # 8. Publish completion event
            await self._publish_event({
                "type": "epic_execution_completed",
                "epic_id": epic_id,
                "result": result.to_dict(),
                "data_dir": str(self.project_path),
                "output_dir": str(self.output_dir),
            })
            status_label = "SUCCESS" if result.success else "PARTIAL"
            await self._publish_log(
                f"Epic {epic_id} finished: [{status_label}] "
                f"{result.completed_tasks}/{result.total_tasks} completed, "
                f"{result.failed_tasks} failed, {result.skipped_tasks} skipped "
                f"({result.duration_seconds:.0f}s)"
            )

            return result

        except Exception as e:
            logger.error(f"Epic {epic_id} execution failed: {e}")
            return EpicExecutionResult(
                epic_id=epic_id,
                success=False,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

        finally:
            # Stop SoM bridge on completion
            if self.som_bridge:
                try:
                    await self.som_bridge.stop()
                except Exception as e:
                    logger.warning(f"SoM bridge stop error: {e}")

            self._running = False
            self._current_epic_id = None

    async def resume_epic(self, epic_id: str) -> EpicExecutionResult:
        """Resume execution from last checkpoint or failed task."""
        return await self.run_epic(epic_id, ExecutionMode.RESUME)

    async def retry_failed(self, epic_id: str) -> EpicExecutionResult:
        """Retry only failed tasks."""
        return await self.run_epic(epic_id, ExecutionMode.RETRY_FAILED)

    async def reset_epic(self, epic_id: str) -> bool:
        """Reset all tasks to pending status for a fresh run."""
        task_file = self._get_task_file_path(epic_id)

        if not task_file.exists():
            return False

        try:
            data = json.loads(task_file.read_text(encoding='utf-8'))

            for task in data.get("tasks", []):
                task["status"] = "pending"
                task["error_message"] = None
                task["retry_count"] = 0
                task["actual_minutes"] = None

            data["completed_tasks"] = 0
            data["failed_tasks"] = 0
            data["progress_percent"] = 0
            data["run_count"] = data.get("run_count", 0) + 1

            task_file.write_text(json.dumps(data, indent=2), encoding='utf-8')

            logger.info(f"Epic {epic_id} reset to pending")
            return True

        except Exception as e:
            logger.error(f"Failed to reset epic: {e}")
            return False

    # =========================================================================
    # Task Loading & Generation
    # =========================================================================

    def _load_or_generate_tasks(self, epic_id: str) -> Optional[EpicTaskList]:
        """Load existing tasks or generate new ones."""
        task_file = self._get_task_file_path(epic_id)

        # Try to load existing tasks
        if task_file.exists():
            try:
                data = json.loads(task_file.read_text(encoding='utf-8'))
                tasks = [self._dict_to_task(t) for t in data.get("tasks", [])]

                return EpicTaskList(
                    epic_id=epic_id,
                    epic_name=data.get("epic_name", ""),
                    tasks=tasks,
                    total_tasks=len(tasks),
                    completed_tasks=data.get("completed_tasks", 0),
                    failed_tasks=data.get("failed_tasks", 0),
                    progress_percent=data.get("progress_percent", 0),
                    run_count=data.get("run_count", 0),
                    last_run_at=data.get("last_run_at"),
                    created_at=data.get("created_at", ""),
                )
            except Exception as e:
                logger.warning(f"Failed to load tasks, regenerating: {e}")

        # If skip_task_gen: don't generate, only use existing files
        if self.skip_task_gen:
            logger.warning(f"skip_task_gen=True but no task file for {epic_id} — skipping epic")
            return None

        # Generate new tasks
        logger.info(f"Generating tasks for epic {epic_id}")
        task_list = self.task_generator.generate_tasks_for_epic(epic_id)

        # Save to file
        if task_list:
            self._save_task_list(task_list)

        return task_list

    async def _start_dev_server(self):
        """Auto-start dev server with autonomous debug loop.

        1. Detect framework from package.json
        2. Run prisma generate if needed
        3. Start server → wait → check if running
        4. If crash → read error → send to CLI for fix → restart
        5. Max 5 attempts before giving up
        """
        import subprocess as _sp
        import time as _time

        MAX_FIX_ATTEMPTS = 5

        try:
            output_dir = self.output_dir or self.project_path
            pkg = output_dir / "package.json"
            if not pkg.exists():
                for p in output_dir.iterdir():
                    if p.is_dir() and (p / "package.json").exists():
                        output_dir = p
                        break

            if not (output_dir / "package.json").exists():
                logger.warning("No package.json found, skipping dev server start")
                return

            # Build env
            env = dict(os.environ)
            env.pop("CLAUDECODE", None)
            env["NODE_OPTIONS"] = "--max-old-space-size=512"
            env["DATABASE_URL"] = os.environ.get(
                "DATABASE_URL",
                "postgresql://postgres:postgres@postgres:5432/coding_engine"
            )

            # Detect framework
            import json as _json
            pkg_data = _json.loads((output_dir / "package.json").read_text())
            deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            scripts = pkg_data.get("scripts", {})

            if "@nestjs/core" in deps:
                start_cmd = ["node_modules/.bin/ts-node", "-T", "src/main.ts"]
            elif "next" in deps:
                start_cmd = ["npx", "next", "dev", "-p", "3000"]
            elif "start:dev" in scripts:
                start_cmd = ["npm", "run", "start:dev"]
            elif "dev" in scripts:
                start_cmd = ["npm", "run", "dev"]
            elif "start" in scripts:
                start_cmd = ["npm", "start"]
            else:
                start_cmd = ["node", "src/main.ts"]

            log_file = str(output_dir / ".dev-server.log")
            err_file = str(output_dir / ".dev-server.err")

            for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
                logger.info(f"Dev server attempt {attempt}/{MAX_FIX_ATTEMPTS}: {start_cmd}")

                # Prisma generate before each attempt
                if (output_dir / "prisma" / "schema.prisma").exists():
                    _sp.run(["npx", "prisma", "generate"], cwd=str(output_dir),
                            capture_output=True, timeout=30, env=env)

                # Start server
                proc = _sp.Popen(
                    start_cmd, cwd=str(output_dir), env=env,
                    stdout=open(log_file, "w"),
                    stderr=open(err_file, "w"),
                    start_new_session=True,
                )

                # Wait for it to start or crash
                await asyncio.sleep(8)

                if proc.poll() is not None:
                    # Process exited — read error
                    error_text = ""
                    try:
                        error_text = Path(err_file).read_text()[:1500]
                        if not error_text.strip():
                            error_text = Path(log_file).read_text()[:1500]
                    except Exception:
                        pass

                    logger.warning(f"Dev server crashed (attempt {attempt}): {error_text[:200]}")

                    if attempt >= MAX_FIX_ATTEMPTS:
                        logger.error("Dev server failed after all attempts")
                        break

                    # Use CLI to fix the error
                    fix_prompt = (
                        "The dev server crashed with this error. "
                        "Read the source files, fix the issue, and write the corrected files.\n"
                        "IMPORTANT: Write ONLY the fixed file(s) as code blocks.\n\n"
                        f"## Error\n```\n{error_text[:1000]}\n```\n\n"
                        "## Common fixes:\n"
                        "- Wrong import path → fix the import\n"
                        "- Missing module → create the file\n"
                        "- Type error → fix the type\n"
                        "- Missing dependency → add to package.json and note it\n"
                    )

                    logger.info(f"Auto-fixing dev server error (attempt {attempt})...")

                    try:
                        claude_tool = self._get_claude_tool()
                        if claude_tool:
                            fix_result = await claude_tool.execute(
                                prompt=fix_prompt,
                                agent_type="debugging",
                                max_turns=5,
                            )
                            if fix_result.success and fix_result.files:
                                logger.info(f"Fix applied: {len(fix_result.files)} files")
                            else:
                                logger.warning(f"Fix attempt produced no files")
                    except Exception as fix_err:
                        logger.warning(f"Auto-fix failed: {fix_err}")

                    continue
                else:
                    # Process still running — check health
                    import urllib.request
                    try:
                        url = "http://localhost:3000/api/health"
                        req = urllib.request.urlopen(url, timeout=5)
                        if req.status == 200:
                            logger.info(f"Dev server healthy on attempt {attempt}")
                            return
                    except Exception:
                        # Server running but no health endpoint yet — that's OK
                        logger.info(f"Dev server running (no health endpoint yet)")
                        return

            logger.error("Dev server could not be started after %d attempts" % MAX_FIX_ATTEMPTS)

        except Exception as e:
            logger.warning(f"Failed to start dev server: {e}")

    def _save_task_list(self, task_list: EpicTaskList):
        """Save task list to JSON file."""
        task_file = self._get_task_file_path(task_list.epic_id)
        task_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "epic_id": task_list.epic_id,
            "epic_name": task_list.epic_name,
            "tasks": [self._task_to_dict(t) for t in task_list.tasks],
            "total_tasks": task_list.total_tasks,
            "completed_tasks": task_list.completed_tasks,
            "failed_tasks": task_list.failed_tasks,
            "progress_percent": task_list.progress_percent,
            "run_count": task_list.run_count,
            "last_run_at": task_list.last_run_at,
            "created_at": task_list.created_at or datetime.now().isoformat(),
            "estimated_total_minutes": task_list.estimated_total_minutes,
        }

        task_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
        logger.info(f"Saved {len(task_list.tasks)} tasks to {task_file}")

    def _get_task_file_path(self, epic_id: str) -> Path:
        """Get path to task JSON file for an epic."""
        return self.project_path / "tasks" / f"{epic_id.lower()}-tasks.json"

    # =========================================================================
    # Task Filtering
    # =========================================================================

    def _filter_tasks_by_mode(
        self,
        all_tasks: List[Task],
        mode: ExecutionMode,
        max_tasks: Optional[int] = None,
        phases: Optional[List[str]] = None,
    ) -> List[Task]:
        """Filter tasks based on execution mode, phases, and max count."""
        if mode == ExecutionMode.FULL:
            # All pending tasks
            result = [t for t in all_tasks if t.status == "pending"]

        elif mode == ExecutionMode.RESUME:
            # Pending tasks (continue from where we left off)
            result = [t for t in all_tasks if t.status == "pending"]

        elif mode == ExecutionMode.RETRY_FAILED:
            # Reset failed tasks to pending and return them
            result = []
            for task in all_tasks:
                if task.status == "failed":
                    task.status = "pending"
                    task.error_message = None
                    task.retry_count = 0
                    result.append(task)

        elif mode == ExecutionMode.DRY_RUN:
            # Return empty list (no execution)
            return []

        else:
            return []

        # Filter by phases (e.g., ["setup", "schema", "api"])
        if phases:
            result = [t for t in result if getattr(t, 'phase', '') in phases]
            logger.info(f"Phase filter {phases}: {len(result)} tasks remaining")

        # Limit task count (tasks are already in dependency order)
        if max_tasks and max_tasks > 0 and len(result) > max_tasks:
            logger.info(f"Limiting to {max_tasks} of {len(result)} tasks")
            result = result[:max_tasks]

        return result

    # =========================================================================
    # Task Execution (Supports Parallel Execution)
    # =========================================================================

    async def _execute_tasks_in_order(
        self,
        epic_id: str,
        all_tasks: List[Task],
        tasks_to_execute: List[Task],
        skip_failed_deps: bool = False,
    ) -> EpicExecutionResult:
        """
        Execute tasks in topological order based on dependencies.

        If max_parallel_tasks > 1, independent tasks will be executed in parallel.
        If skip_failed_deps is True, tasks with failed dependencies will still execute
        (failed deps are treated as completed for dependency resolution).
        """

        # Use pipeline executor for parallel mode (non-blocking, file-conflict-aware)
        if self.max_parallel_tasks > 1:
            return await self._execute_pipeline(
                epic_id, all_tasks, tasks_to_execute, skip_failed_deps
            )

        # Sequential mode below (backward-compatible, max_parallel_tasks == 1)

        # Build task lookup map
        task_map: Dict[str, Task] = {t.id: t for t in all_tasks}
        tasks_to_execute_ids: Set[str] = {t.id for t in tasks_to_execute}
        pending_ids: Set[str] = set(tasks_to_execute_ids)
        completed_ids: Set[str] = set()
        failed_ids: Set[str] = set()

        # Initialize semaphore for parallelism
        self._semaphore = asyncio.Semaphore(self.max_parallel_tasks)

        # Execution counters
        completed = 0
        failed = 0
        skipped = 0

        # Use wave-based execution for parallel processing
        while pending_ids and not self._paused:
            # Prune tasks whose dependencies have failed (skip immediately)
            # Unless skip_failed_deps is True, in which case we treat failed as completed
            pruned_this_round = False
            if not skip_failed_deps:
                for tid in list(pending_ids):
                    task = task_map[tid]
                    if self._has_failed_ancestor(task, task_map, failed_ids):
                        self._set_task_status(task, "skipped", "Dependencies not met")
                        failed_deps = [d for d in task.dependencies if d in failed_ids or (d in task_map and task_map[d].status == "failed")]
                        task.error_message = f"Dependency failed: {failed_deps}"
                        logger.warning(f"Skipping {task.id}: dependency failed ({failed_deps})")
                        skipped += 1
                        pending_ids.discard(tid)
                        pruned_this_round = True

            # Find tasks whose dependencies are all completed
            # When skip_failed_deps is True, also treat failed deps as "completed"
            ready_tasks = self._get_ready_tasks(
                pending_ids, completed_ids, task_map,
                also_treat_as_completed=failed_ids if skip_failed_deps else None,
            )

            if not ready_tasks:
                if pruned_this_round:
                    # We just pruned tasks, loop again to check for newly-ready
                    continue
                # No tasks ready and nothing pruned - true deadlock
                remaining = [task_map[tid] for tid in pending_ids]
                for task in remaining:
                    if not self._dependencies_met(task, task_map):
                        logger.warning(f"Skipping {task.id}: dependencies not met")
                        self._set_task_status(task, "skipped", "Dependencies not met")
                        skipped += 1
                        pending_ids.discard(task.id)
                if not pending_ids:
                    break
                continue

            # Execute ready tasks (parallel if configured)
            if self.max_parallel_tasks > 1 and len(ready_tasks) > 1:
                # Parallel execution
                logger.info(f"Executing {len(ready_tasks)} tasks in parallel (max {self.max_parallel_tasks})")
                results = await self._execute_parallel_batch(ready_tasks)

                for task, result in zip(ready_tasks, results):
                    pending_ids.discard(task.id)
                    if result.success:
                        completed_ids.add(task.id)
                        completed += 1
                        self._set_task_status(task, "completed", "", getattr(result, 'execution_time_ms', 0))
                        # Auto-start dev servers after setup completes
                        if task.type == "setup_deps" or "SETUP-frontend" in task.id:
                            await self._start_dev_server()
                        # Mark deps as tested when test tasks pass
                        if task.type.startswith("test_"):
                            for dep_id in task.dependencies:
                                dep = task_map.get(dep_id)
                                if dep and dep.status == "completed":
                                    dep.tested = True
                    else:
                        failed += 1
                        failed_ids.add(task.id)
                        self._set_task_status(task, "failed", result.error or "Task execution failed (no details)")
                        logger.warning(
                            f"Task {task.id} failed: {task.error_message[:100]}"
                        )
            else:
                # Sequential execution
                for task in ready_tasks:
                    if self._paused:
                        break

                    self._current_task_id = task.id

                    logger.info(f"Executing task {task.id}: {task.title}")
                    result = await self.task_executor.execute_task(task)

                    pending_ids.discard(task.id)

                    if result.success:
                        completed_ids.add(task.id)
                        completed += 1
                        self._set_task_status(task, "completed", "", getattr(result, 'execution_time_ms', 0))
                        # Auto-start dev servers after setup completes
                        if task.type == "setup_deps" or "SETUP-frontend" in task.id:
                            await self._start_dev_server()
                        # Mark deps as tested when test tasks pass
                        if task.type.startswith("test_"):
                            for dep_id in task.dependencies:
                                dep = task_map.get(dep_id)
                                if dep and dep.status == "completed":
                                    dep.tested = True
                    else:
                        failed += 1
                        failed_ids.add(task.id)
                        self._set_task_status(task, "failed", result.error or "Task execution failed (no details)")
                        logger.warning(
                            f"Task {task.id} failed: {task.error_message[:100]}"
                        )

        # Calculate final result
        all_successful = failed == 0 and skipped == 0 and len(pending_ids) == 0

        return EpicExecutionResult(
            epic_id=epic_id,
            success=all_successful,
            total_tasks=len(tasks_to_execute),
            completed_tasks=completed,
            failed_tasks=failed,
            skipped_tasks=skipped,
            checkpoint_paused=self._paused and len(pending_ids) > 0,
            checkpoint_task_id=self._current_task_id,
        )

    # =========================================================================
    # Single-Task Rerun
    # =========================================================================

    async def rerun_single_task(
        self,
        epic_id: str,
        task_id: str,
        fix_instructions: Optional[str] = None,
    ) -> TaskExecutionResult:
        """
        Rerun a single task by ID, optionally with user fix instructions.

        Resets the task to pending, injects fix instructions, and executes it.
        Does NOT re-execute dependencies.
        """
        task_list = self._load_or_generate_tasks(epic_id)
        if not task_list:
            raise ValueError(f"No task list found for epic {epic_id}")

        task_map = {t.id: t for t in task_list.tasks}
        task = task_map.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found in epic {epic_id}")

        # Reset task state
        task.status = "pending"
        task.error_message = None
        task.retry_count = 0
        if fix_instructions:
            task.user_fix_instructions = fix_instructions

        # Save before execution
        self._save_task_list(task_list)

        # Execute the single task
        logger.info(f"Rerunning task {task_id} | fix_instructions={bool(fix_instructions)}")
        result = await self.task_executor.execute_task(task)

        # Mark tested if this is a test task that passed
        if result.success and task.type.startswith("test_"):
            self._mark_related_tasks_tested(task, task_list)

        # Clear fix instructions after success
        if result.success:
            task.user_fix_instructions = None

        # Update counters
        task_list.completed_tasks = sum(1 for t in task_list.tasks if t.status == "completed")
        task_list.failed_tasks = sum(1 for t in task_list.tasks if t.status == "failed")
        task_list.progress_percent = (
            (task_list.completed_tasks / task_list.total_tasks * 100)
            if task_list.total_tasks > 0 else 0
        )

        # Save after execution
        self._save_task_list(task_list)

        return result

    def _mark_related_tasks_tested(self, test_task: Task, task_list: EpicTaskList):
        """When a test task completes, mark its dependency tasks as tested=True."""
        task_map = {t.id: t for t in task_list.tasks}
        for dep_id in test_task.dependencies:
            dep_task = task_map.get(dep_id)
            if dep_task and dep_task.status == "completed":
                dep_task.tested = True
                logger.info(f"Marked {dep_id} as tested (verified by {test_task.id})")

    def _get_ready_tasks(
        self,
        pending_ids: Set[str],
        completed_ids: Set[str],
        task_map: Dict[str, Task],
        also_treat_as_completed: Optional[Set[str]] = None,
    ) -> List[Task]:
        """
        Find tasks that are ready to execute (all dependencies completed).

        Returns up to max_parallel_tasks tasks that can be executed in parallel.
        If also_treat_as_completed is provided, those IDs count as "completed"
        for dependency resolution (used by --skip-failed-deps).
        """
        ready = []
        extra = also_treat_as_completed or set()

        for task_id in pending_ids:
            task = task_map.get(task_id)
            if not task:
                continue

            # Check if all dependencies are completed (or in the extra set)
            deps_met = all(
                dep_id in completed_ids or
                dep_id in extra or
                (dep_id in task_map and task_map[dep_id].status == "completed")
                for dep_id in task.dependencies
            )

            if deps_met:
                ready.append(task)

                # Limit batch size for parallel execution
                if len(ready) >= self.max_parallel_tasks:
                    break

        return ready

    async def _execute_parallel_batch(self, tasks: List[Task]) -> List[TaskExecutionResult]:
        """
        Execute a batch of tasks in parallel using a semaphore to limit concurrency.

        Args:
            tasks: List of tasks to execute in parallel

        Returns:
            List of TaskExecutionResult in the same order as input tasks
        """

        async def execute_with_semaphore(task: Task) -> TaskExecutionResult:
            async with self._semaphore:
                self._running_task_ids.add(task.id)
                try:
                    logger.info(f"[Parallel] Starting task {task.id}: {task.title}")
                    result = await self.task_executor.execute_task(task)
                    return result
                finally:
                    self._running_task_ids.discard(task.id)

        # Execute all tasks concurrently
        results = await asyncio.gather(
            *[execute_with_semaphore(task) for task in tasks],
            return_exceptions=True
        )

        # Convert exceptions to failed results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task {tasks[i].id} raised exception: {result}")
                processed_results.append(TaskExecutionResult(
                    success=False,
                    output="",
                    error=str(result),
                ))
            else:
                processed_results.append(result)

        return processed_results

    def _get_execution_order(
        self,
        tasks: List[Task],
        task_map: Dict[str, Task],
    ) -> List[Task]:
        """
        Topological sort of tasks based on dependencies.

        Returns tasks in execution order (dependencies first).
        """
        task_ids = {t.id for t in tasks}

        # Build adjacency list (task -> tasks that depend on it)
        dependents: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {t.id: 0 for t in tasks}

        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in task_ids:
                    dependents[dep_id].append(task.id)
                    in_degree[task.id] += 1
                elif dep_id in task_map:
                    # Dependency is outside this batch - check if completed
                    dep_task = task_map[dep_id]
                    if dep_task.status != "completed":
                        # Dependency not met, will be handled during execution
                        pass

        # Kahn's algorithm for topological sort
        queue = deque([t.id for t in tasks if in_degree[t.id] == 0])
        result = []

        while queue:
            task_id = queue.popleft()
            result.append(task_map[task_id])

            for dependent_id in dependents[task_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # Check for cycles
        if len(result) != len(tasks):
            logger.warning("Dependency cycle detected, falling back to simple order")
            # Fallback: sort by number of dependencies
            return sorted(tasks, key=lambda t: len(t.dependencies))

        return result

    def _dependencies_met(self, task: Task, task_map: Dict[str, Task]) -> bool:
        """Check if all dependencies are completed."""
        for dep_id in task.dependencies:
            dep_task = task_map.get(dep_id)
            if dep_task and dep_task.status != "completed":
                return False
        return True

    def _has_failed_ancestor(
        self,
        task: Task,
        task_map: Dict[str, Task],
        failed_ids: Set[str],
    ) -> bool:
        """Check if any direct dependency has failed (or is in failed_ids)."""
        for dep_id in task.dependencies:
            if dep_id in failed_ids:
                return True
            dep_task = task_map.get(dep_id)
            if dep_task and dep_task.status == "failed":
                return True
        return False

    # =========================================================================
    # Pipeline Parallel Execution (Phase 24)
    # =========================================================================

    def _build_task_file_map(self, tasks: List[Task]) -> Dict[str, Set[str]]:
        """
        Build mapping: task_id -> set of normalized output file paths.

        Used by pipeline executor to detect file conflicts between tasks.
        Strips #fragment suffixes (e.g. prisma/schema.prisma#AuthMethod -> prisma/schema.prisma).
        """
        result: Dict[str, Set[str]] = {}
        for task in tasks:
            files: Set[str] = set()
            for f in (task.output_files or []):
                # Normalize: strip hash fragments and trailing slashes
                base_file = f.split('#')[0].rstrip('/')
                if base_file:
                    files.add(base_file)
            result[task.id] = files
        return result

    def _get_ready_tasks_pipeline(
        self,
        pending_ids: Set[str],
        completed_ids: Set[str],
        task_map: Dict[str, Task],
        running_task_ids: Set[str],
        task_file_map: Dict[str, Set[str]],
        also_treat_as_completed: Optional[Set[str]] = None,
    ) -> List[Task]:
        """
        Find tasks ready for pipeline execution.

        A task is ready when:
        1. All dependencies are completed (or in also_treat_as_completed)
        2. No currently-running task writes to the same output file

        Returns tasks sorted by dependency count (fewer deps first).
        """
        extra = also_treat_as_completed or set()
        ready: List[Task] = []

        # Collect files being written by running tasks
        running_files: Set[str] = set()
        for rid in running_task_ids:
            running_files.update(task_file_map.get(rid, set()))

        for task_id in list(pending_ids):
            task = task_map.get(task_id)
            if not task:
                continue

            # Check if all dependencies are completed
            deps_met = all(
                dep_id in completed_ids or
                dep_id in extra or
                (dep_id in task_map and task_map[dep_id].status == "completed")
                for dep_id in task.dependencies
            )
            if not deps_met:
                continue

            # Check file conflicts with running tasks
            task_files = task_file_map.get(task_id, set())
            if task_files and task_files.intersection(running_files):
                continue  # Would conflict with a running task

            ready.append(task)

        # Sort: fewer dependencies first (more independent = higher priority)
        ready.sort(key=lambda t: len(t.dependencies))
        return ready

    async def _execute_with_file_lock(
        self,
        task: Task,
        file_locks: Dict[str, asyncio.Lock],
        task_file_map: Dict[str, Set[str]],
    ) -> TaskExecutionResult:
        """
        Execute a task with file locks for its output files.

        Acquires locks in sorted order to prevent deadlocks.
        This is defense-in-depth: the scheduler already avoids file conflicts,
        but locks provide a safety net.
        """
        files = task_file_map.get(task.id, set())

        # Acquire locks in sorted order (prevent deadlock)
        locks_to_acquire: List[asyncio.Lock] = []
        for f in sorted(files):
            if f not in file_locks:
                file_locks[f] = asyncio.Lock()
            locks_to_acquire.append(file_locks[f])

        for lock in locks_to_acquire:
            await lock.acquire()

        try:
            return await self.task_executor.execute_task(task)
        finally:
            for lock in locks_to_acquire:
                lock.release()

    def _prune_failed_descendants(
        self,
        pending_ids: Set[str],
        task_map: Dict[str, Task],
        failed_ids: Set[str],
    ) -> int:
        """
        Remove tasks with failed ancestors from pending set.

        Returns count of pruned (skipped) tasks.
        """
        pruned = 0
        for tid in list(pending_ids):
            task = task_map.get(tid)
            if not task:
                continue
            if self._has_failed_ancestor(task, task_map, failed_ids):
                self._set_task_status(task, "skipped", "Failed ancestor dependency")
                failed_deps = [
                    d for d in task.dependencies
                    if d in failed_ids or (d in task_map and task_map[d].status == "failed")
                ]
                task.error_message = f"Dependency failed: {failed_deps}"
                logger.warning(f"Skipping {task.id}: dependency failed ({failed_deps})")
                pending_ids.discard(tid)
                pruned += 1
        return pruned

    async def _publish_pipeline_progress(
        self,
        epic_id: str,
        completed: int,
        failed: int,
        skipped: int,
        total: int,
        running_ids: List[str],
    ):
        """Publish real-time pipeline progress to dashboard."""
        await self._publish_event({
            "type": "task_progress_update",
            "data": {
                "type": "pipeline_progress",
                "epic_id": epic_id,
                "completed": completed,
                "failed": failed,
                "skipped": skipped,
                "total": total,
                "running_task_ids": running_ids,
                "running_count": len(running_ids),
                "percent_complete": round((completed / total * 100), 1) if total > 0 else 0,
            },
        })

    async def _execute_pipeline(
        self,
        epic_id: str,
        all_tasks: List[Task],
        tasks_to_execute: List[Task],
        skip_failed_deps: bool = False,
    ) -> EpicExecutionResult:
        """
        Pipeline executor: continuously discovers and launches ready tasks.

        Instead of batch-then-wait-all (asyncio.gather), uses FIRST_COMPLETED
        to immediately discover and launch newly ready tasks when any task finishes.
        File-conflict detection ensures tasks sharing output files never run simultaneously.

        Args:
            epic_id: The epic being executed
            all_tasks: All tasks (for dependency lookup)
            tasks_to_execute: Tasks to actually run
            skip_failed_deps: If True, treat failed deps as completed

        Returns:
            EpicExecutionResult
        """
        # Build task lookup
        task_map: Dict[str, Task] = {t.id: t for t in all_tasks}
        pending_ids: Set[str] = {t.id for t in tasks_to_execute}
        completed_ids: Set[str] = set()
        failed_ids: Set[str] = set()

        # Build file conflict map
        task_file_map = self._build_task_file_map(tasks_to_execute)
        file_locks: Dict[str, asyncio.Lock] = {}

        # Running tasks: asyncio.Task -> task_id
        running: Dict[asyncio.Task, str] = {}

        # Counters
        completed_count = 0
        failed_count = 0
        skipped_count = 0

        logger.info(
            f"Pipeline executor started: {len(tasks_to_execute)} tasks, "
            f"max_parallel={self.max_parallel_tasks}"
        )

        while (pending_ids or running) and not self._paused:
            # 1. Prune tasks with failed ancestors
            if not skip_failed_deps:
                newly_pruned = self._prune_failed_descendants(
                    pending_ids, task_map, failed_ids
                )
                skipped_count += newly_pruned

            # 2. Find ready tasks (deps met AND no file conflict with running)
            ready = self._get_ready_tasks_pipeline(
                pending_ids, completed_ids, task_map,
                running_task_ids=set(running.values()),
                task_file_map=task_file_map,
                also_treat_as_completed=failed_ids if skip_failed_deps else None,
            )

            # 3. Launch ready tasks up to max_parallel
            for task in ready:
                if len(running) >= self.max_parallel_tasks:
                    break
                pending_ids.discard(task.id)
                self._running_task_ids.add(task.id)
                self._current_task_id = task.id
                logger.info(
                    f"[Pipeline] Launching task {task.id}: {task.title} "
                    f"(running: {len(running) + 1}/{self.max_parallel_tasks})"
                )
                await self._publish_log(
                    f"Starting task {task.id}: {task.title} "
                    f"[{task.type}] (running: {len(running) + 1}/{self.max_parallel_tasks})"
                )
                atask = asyncio.create_task(
                    self._execute_with_file_lock(task, file_locks, task_file_map)
                )
                running[atask] = task.id

            # 4. Wait for ANY task to complete (not all!)
            if running:
                done, _ = await asyncio.wait(
                    running.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=5.0,  # Periodic check for pause/new ready tasks
                )

                for atask in done:
                    task_id = running.pop(atask)
                    self._running_task_ids.discard(task_id)
                    task = task_map[task_id]

                    try:
                        result = atask.result()
                        if result.success:
                            completed_ids.add(task_id)
                            completed_count += 1
                            self._set_task_status(task, "completed", "", getattr(result, 'execution_time_ms', 0))
                            # Auto-start dev servers after setup completes
                            if task.type == "setup_deps" or "SETUP-frontend" in task.id:
                                await self._start_dev_server()
                            logger.info(
                                f"[Pipeline] Completed {task_id} "
                                f"({completed_count}/{len(tasks_to_execute)})"
                            )
                            await self._publish_log(
                                f"SUCCESS {task_id}: {task.title} "
                                f"({completed_count}/{len(tasks_to_execute)} done)"
                            )
                            # Mark deps as tested when test tasks pass
                            if task.type.startswith("test_"):
                                for dep_id in task.dependencies:
                                    dep = task_map.get(dep_id)
                                    if dep and dep.status == "completed":
                                        dep.tested = True
                        else:
                            failed_ids.add(task_id)
                            failed_count += 1
                            self._set_task_status(task, "failed", result.error or "Task execution failed (no details)")
                            logger.warning(
                                f"[Pipeline] Failed {task_id}: {task.error_message[:200]}"
                            )
                            await self._publish_log(
                                f"FAILED {task_id}: {task.error_message[:300]}",
                                level="ERROR"
                            )
                    except Exception as e:
                        failed_ids.add(task_id)
                        failed_count += 1
                        self._set_task_status(task, "failed", str(e))
                        logger.error(
                            f"[Pipeline] Exception in {task_id}: {e}"
                        )
                        await self._publish_log(
                            f"FAILED {task_id}: Exception: {e}",
                            level="ERROR"
                        )

                    # Publish progress after each completion
                    await self._publish_pipeline_progress(
                        epic_id, completed_count, failed_count,
                        skipped_count, len(tasks_to_execute),
                        list(running.values()),
                    )

            elif not pending_ids:
                break  # Nothing running, nothing pending -> done
            else:
                # Nothing ready yet (waiting for file conflicts or deps to resolve)
                await asyncio.sleep(0.5)

        # Handle pause state
        checkpoint_paused = self._paused and (len(pending_ids) > 0 or len(running) > 0)

        # Cancel any still-running tasks if paused
        if self._paused and running:
            logger.info(f"Pipeline paused, {len(running)} tasks still running")
            # Let running tasks finish naturally (don't cancel mid-execution)

        all_successful = (
            failed_count == 0 and skipped_count == 0 and len(pending_ids) == 0
        )

        logger.info(
            f"Pipeline executor finished: "
            f"{completed_count} completed, {failed_count} failed, "
            f"{skipped_count} skipped, {len(pending_ids)} remaining"
        )

        return EpicExecutionResult(
            epic_id=epic_id,
            success=all_successful,
            total_tasks=len(tasks_to_execute),
            completed_tasks=completed_count,
            failed_tasks=failed_count,
            skipped_tasks=skipped_count,
        )

    # =========================================================================
    # Convergence Loop (Post-Execution Fix & Re-Run)
    # =========================================================================

    async def _convergence_loop(
        self,
        epic_id: str,
        task_list: 'EpicTaskList',
        initial_result: EpicExecutionResult,
        max_rounds: int = 3,
    ) -> EpicExecutionResult:
        """Post-execution: validate failed tasks, fix via TaskValidator, re-run unblocked.

        This loop connects the TaskValidator (MCP + Claude CLI fix loop) to the
        Epic execution pipeline. After the initial pass, it:
        1. Loads failed tasks via TaskValidator
        2. Runs fix_loop (fix → validate → unblock downstream)
        3. Re-executes any newly-pending (unblocked) tasks
        4. Repeats until 0 failed or no progress

        Args:
            epic_id: The epic being executed
            task_list: Full EpicTaskList (for re-execution)
            initial_result: Result from the initial execution pass
            max_rounds: Maximum convergence iterations

        Returns:
            Updated EpicExecutionResult
        """
        from src.tools.task_validator import TaskValidator

        task_file = self._get_task_file_path(epic_id)
        if not task_file.exists():
            logger.warning(f"No task file for convergence: {task_file}")
            return initial_result

        validator = TaskValidator(
            task_file=str(task_file),
            output_dir=str(self.output_dir),
            som_bridge=self.som_bridge,
        )

        for round_num in range(max_rounds):
            failed = validator.get_failed_tasks()
            if not failed:
                logger.info(f"Convergence achieved in round {round_num}")
                break

            logger.info(
                f"Convergence round {round_num + 1}: {len(failed)} failed tasks"
            )

            # Publish progress to dashboard
            await self._publish_event({
                "type": "epic_convergence_round",
                "epic_id": epic_id,
                "round": round_num + 1,
                "failed_count": len(failed),
                "total_tasks": len(validator.tasks),
            })

            # Run TaskValidator fix loop
            fix_result = await validator.run_fix_loop(max_iterations=3)
            tasks_fixed = fix_result.get("tasks_fixed", 0)

            # Re-execute newly unblocked (pending) tasks
            newly_pending = validator.get_pending_tasks()
            newly_completed = 0

            if newly_pending:
                logger.info(
                    f"Re-executing {len(newly_pending)} unblocked tasks"
                )
                for task_dict in newly_pending:
                    task_obj = self._dict_to_task(task_dict)
                    if task_obj:
                        # Phase 28: Only re-run verification tasks. Code-gen tasks
                        # were already fixed by TaskValidator — check file existence.
                        agent_name, _ = TASK_SKILL_MAPPING.get(
                            task_obj.type, ("GeneratorAgent", "code-generation")
                        )
                        if agent_name == "BashExecutor":
                            # Verification task: re-run (cheap and correct)
                            exec_result = await self.task_executor.execute_task(task_obj)
                        else:
                            # Code-gen task: check if output files exist
                            output_files = [
                                f.split('#')[0] for f in (task_obj.output_files or []) if f
                            ]
                            has_output = output_files and all(
                                (self.output_dir / f).exists()
                                for f in output_files if f
                            )
                            if has_output:
                                exec_result = TaskExecutionResult(
                                    success=True,
                                    output="Fixed by TaskValidator in convergence loop",
                                )
                            else:
                                # Output files missing — need actual generation
                                exec_result = await self.task_executor.execute_task(task_obj)

                        if exec_result.success:
                            task_dict["status"] = "completed"
                            task_dict["error_message"] = None
                            newly_completed += 1
                        else:
                            task_dict["status"] = "failed"
                            task_dict["error_message"] = exec_result.error
                validator._save_tasks()

            # Trigger differential + cross-layer validation via SoM agents (Phase 27)
            if self.som_bridge and hasattr(self.som_bridge, 'event_bus') and self.som_bridge.event_bus:
                try:
                    from src.mind.event_bus import Event as SoMEvent
                    from src.mind.event_payloads import EventType as SoMEventType
                    await self.som_bridge.event_bus.publish(SoMEvent(
                        type=SoMEventType.EPIC_EXECUTION_COMPLETED,
                        source="convergence_loop",
                        data={
                            "epic_id": epic_id,
                            "round": round_num + 1,
                            "output_dir": str(self.output_dir),
                            "data_dir": str(self.project_path) if hasattr(self, 'project_path') else "",
                        },
                    ))
                    # Allow agents time to react and publish findings
                    await asyncio.sleep(10)
                    self._convergence_ran_diff = True  # Phase 28: Mark that diff ran in convergence
                except Exception as e:
                    logger.warning(f"SoM event publish failed in convergence: {e}")

            # Check if we made progress
            if tasks_fixed == 0 and newly_completed == 0:
                logger.warning("No progress in convergence round, stopping")
                break

        # Build final result from validator summary
        summary = validator.get_summary()
        initial_result.completed_tasks = summary.get("completed", 0)
        initial_result.failed_tasks = summary.get("failed", 0)
        initial_result.skipped_tasks = summary.get("skipped", 0)
        initial_result.success = summary.get("failed", 0) == 0

        return initial_result

    # =========================================================================
    # Checkpoint & Pause Control
    # =========================================================================

    def pause(self):
        """Pause execution at next task boundary."""
        self._paused = True
        logger.info(f"Execution pause requested for epic {self._current_epic_id}")

    def is_running(self) -> bool:
        """Check if orchestrator is currently running."""
        return self._running

    def is_paused(self) -> bool:
        """Check if orchestrator is paused."""
        return self._paused

    def approve_checkpoint(self, task_id: str, response: Optional[str] = None) -> bool:
        """Approve a checkpoint to continue execution."""
        return self.task_executor.approve_checkpoint(task_id, response)

    # =========================================================================
    # Parallelism Configuration
    # =========================================================================

    def get_parallel_config(self) -> Dict[str, Any]:
        """Get current parallelism configuration."""
        return {
            "max_parallel_tasks": self.max_parallel_tasks,
            "currently_running": len(self._running_task_ids),
            "running_task_ids": list(self._running_task_ids),
            "max_allowed": self.MAX_ALLOWED_PARALLEL,
        }

    def set_max_parallel_tasks(self, count: int) -> bool:
        """
        Set maximum number of parallel tasks.

        Args:
            count: Number of tasks to run in parallel (1-5)

        Returns:
            True if setting was updated successfully
        """
        if count < 1 or count > self.MAX_ALLOWED_PARALLEL:
            logger.warning(
                f"Invalid parallel count {count}, must be 1-{self.MAX_ALLOWED_PARALLEL}"
            )
            return False

        old_value = self.max_parallel_tasks
        self.max_parallel_tasks = count

        # Update semaphore if running
        if self._semaphore:
            self._semaphore = asyncio.Semaphore(count)

        logger.info(
            f"Parallel tasks updated: {old_value} -> {count}",
            extra={"epic_id": self._current_epic_id}
        )
        return True

    # =========================================================================
    # Metadata & Events
    # =========================================================================

    def _update_task_list_metadata(self, epic_id: str, task_list: EpicTaskList):
        """Update task list metadata after execution."""
        task_list.last_run_at = datetime.now().isoformat()
        task_list.run_count += 1

        completed = sum(1 for t in task_list.tasks if t.status == "completed")
        failed = sum(1 for t in task_list.tasks if t.status == "failed")

        task_list.completed_tasks = completed
        task_list.failed_tasks = failed
        task_list.progress_percent = (completed / len(task_list.tasks) * 100) if task_list.tasks else 0

        self._save_task_list(task_list)

    async def _publish_event(self, event: Dict[str, Any]):
        """Publish event to EventBus if available.

        Wraps plain dicts into Event objects when publishing to the SoM EventBus,
        which expects Event(type=EventType, ...) not raw dicts.
        Uses TASK_PROGRESS_UPDATE as the envelope event type so the WebSocket
        bridge forwards the full payload to the dashboard.
        """
        if self.event_bus:
            try:
                if hasattr(self.event_bus, 'publish'):
                    # SoM EventBus expects Event objects, not raw dicts.
                    # Wrap the dict payload inside a proper Event envelope.
                    try:
                        from src.mind.event_bus import Event as SoMEvent, EventType as SoMEventType
                        wrapped = SoMEvent(
                            type=SoMEventType.TASK_PROGRESS_UPDATE,
                            source="epic_orchestrator",
                            data=event,
                        )
                        await self.event_bus.publish(wrapped)
                    except (ImportError, Exception) as wrap_err:
                        # Fallback: try publishing raw dict (may work with non-SoM buses)
                        logger.debug(f"Could not wrap event, trying raw: {wrap_err}")
                        await self.event_bus.publish(event)
                elif hasattr(self.event_bus, 'emit'):
                    self.event_bus.emit(event)
            except Exception as e:
                logger.error(f"Failed to publish event: {e}")

    async def _publish_log(self, message: str, level: str = "INFO"):
        """Publish a log line to the dashboard Logs tab.

        Sends a log_entry event via the EventBus so that the dashboard
        WebSocket handler can append it to the Logs tab in real-time.
        """
        if self.event_bus:
            try:
                from src.mind.event_bus import Event as SoMEvent, EventType as SoMEventType
                log_event = SoMEvent(
                    type=SoMEventType.TASK_PROGRESS_UPDATE,
                    source="epic_orchestrator",
                    data={
                        "type": "task_progress_update",
                        "data": {
                            "type": "log_entry",
                            "message": f"[{level}] {message}",
                            "timestamp": datetime.now().isoformat(),
                        },
                    },
                )
                await self.event_bus.publish(log_event)
            except Exception:
                pass  # Log forwarding is best-effort

    # =========================================================================
    # Task Serialization
    # =========================================================================

    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """Convert Task to dictionary for JSON serialization."""
        return {
            "id": task.id,
            "epic_id": task.epic_id,
            "type": task.type,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "dependencies": task.dependencies,
            "estimated_minutes": task.estimated_minutes,
            "actual_minutes": task.actual_minutes,
            "error_message": task.error_message,
            "output_files": task.output_files,
            "related_requirements": task.related_requirements,
            "related_user_stories": task.related_user_stories,
            "requires_user_input": task.requires_user_input,
            "user_prompt": task.user_prompt,
            "user_response": task.user_response,
            "checkpoint": task.checkpoint,
            "auto_retry": task.auto_retry,
            "max_retries": task.max_retries,
            "retry_count": task.retry_count,
            "timeout_seconds": task.timeout_seconds,
            "phase": task.phase,
            "command": task.command,
            "success_criteria": task.success_criteria,
            "tested": getattr(task, 'tested', False),
            "user_fix_instructions": getattr(task, 'user_fix_instructions', None),
        }

    def _dict_to_task(self, data: Dict[str, Any]) -> Task:
        """Convert dictionary to Task object."""
        return Task(
            id=data.get("id", ""),
            epic_id=data.get("epic_id", ""),
            type=data.get("type", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            dependencies=data.get("dependencies", []),
            estimated_minutes=data.get("estimated_minutes", 5),
            actual_minutes=data.get("actual_minutes"),
            error_message=data.get("error_message"),
            output_files=data.get("output_files", []),
            related_requirements=data.get("related_requirements", []),
            related_user_stories=data.get("related_user_stories", []),
            requires_user_input=data.get("requires_user_input", False),
            user_prompt=data.get("user_prompt"),
            user_response=data.get("user_response"),
            checkpoint=data.get("checkpoint", False),
            auto_retry=data.get("auto_retry", True),
            max_retries=data.get("max_retries", 3),
            retry_count=data.get("retry_count", 0),
            timeout_seconds=data.get("timeout_seconds", 300),
            phase=data.get("phase", "code"),
            command=data.get("command"),
            success_criteria=data.get("success_criteria"),
            tested=data.get("tested", False),
            user_fix_instructions=data.get("user_fix_instructions"),
        )

    # =========================================================================
    # Build Check Between Epics
    # =========================================================================

    def _run_build_check(self, project_dir: str, label: str = "build_check") -> dict:
        """
        Run `npx tsc --noEmit` in the given directory and return a result dict.

        Args:
            project_dir: Directory to run the TypeScript build check in.
            label: Label for logging (e.g. "build_check" or "frontend_build_check").

        Returns:
            {"success": bool, "error_count": int, "errors": str}
        """
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=120,
                shell=(sys.platform == "win32"),
            )
            stderr_out = result.stderr or ""
            stdout_out = result.stdout or ""
            combined = (stdout_out + "\n" + stderr_out).strip()

            # Count TS error lines (format: "src/file.ts(10,5): error TS...")
            error_count = combined.count(": error TS")

            success = result.returncode == 0
            return {
                "success": success,
                "error_count": error_count,
                "errors": combined if not success else "",
            }
        except subprocess.TimeoutExpired:
            logger.warning(f"[{label}] tsc --noEmit timed out after 120s in {project_dir}")
            return {
                "success": False,
                "error_count": -1,
                "errors": "TypeScript build check timed out after 120 seconds",
            }
        except FileNotFoundError:
            logger.debug(f"[{label}] npx/tsc not found in {project_dir}, skipping build check")
            return {
                "success": True,
                "error_count": 0,
                "errors": "",
            }
        except Exception as e:
            logger.warning(f"[{label}] Build check failed unexpectedly: {e}")
            return {
                "success": False,
                "error_count": -1,
                "errors": str(e),
            }

    async def _run_inter_epic_build_check(self, epic_id: str, epic_result: EpicExecutionResult) -> dict:
        """
        Run build checks (root + frontend/) between epics.
        Logs results, stores them on the epic result, and publishes events.

        Returns the root build check result dict.
        """
        output_dir = str(self.output_dir)
        build_checks = {}

        # Root project build check
        root_check = await asyncio.get_event_loop().run_in_executor(
            None, self._run_build_check, output_dir, "build_check"
        )
        build_checks["root"] = root_check

        if root_check["success"]:
            logger.info(f"[build_check] Epic {epic_id}: TypeScript build clean (0 errors)")
        else:
            logger.warning(
                f"[build_check] Epic {epic_id}: TypeScript build has {root_check['error_count']} error(s)"
            )

        # Frontend build check if frontend/ exists
        frontend_dir = os.path.join(output_dir, "frontend")
        if os.path.isdir(frontend_dir):
            fe_check = await asyncio.get_event_loop().run_in_executor(
                None, self._run_build_check, frontend_dir, "frontend_build_check"
            )
            build_checks["frontend"] = fe_check

            if fe_check["success"]:
                logger.info(f"[frontend_build_check] Epic {epic_id}: Frontend build clean (0 errors)")
            else:
                logger.warning(
                    f"[frontend_build_check] Epic {epic_id}: Frontend build has {fe_check['error_count']} error(s)"
                )

        # Store on epic result for dashboard visibility
        epic_result_dict = epic_result.to_dict()
        epic_result_dict["build_checks"] = build_checks

        # Publish build_check event via EventBus
        await self._publish_event({
            "type": "build_check",
            "epic_id": epic_id,
            "build_checks": build_checks,
        })

        return root_check

    # =========================================================================
    # Multi-Epic Support
    # =========================================================================

    async def run_all_epics(self, epic_ids: Optional[List[str]] = None) -> Dict[str, EpicExecutionResult]:
        """
        Run multiple epics sequentially.

        Args:
            epic_ids: List of epic IDs to run. If None, runs all detected epics.

        Returns:
            Dictionary mapping epic_id to execution result
        """
        if epic_ids is None:
            # Parse all epics from project
            epics = self.epic_parser.parse_all_epics()
            epic_ids = [e.id for e in epics]

        results = {}

        for i, epic_id in enumerate(epic_ids):
            logger.info(f"Starting epic: {epic_id}")
            result = await self.run_epic(epic_id, skip_failed_deps=True)
            results[epic_id] = result

            # Run build check after each epic (before the next one starts)
            is_last = (i == len(epic_ids) - 1)
            if not is_last:
                try:
                    await self._run_inter_epic_build_check(epic_id, result)
                except Exception as e:
                    logger.warning(f"Build check after {epic_id} failed (non-fatal): {e}")

            # Stop if epic failed (unless it's just a checkpoint pause)
            if not result.success and not result.checkpoint_paused:
                logger.error(f"Epic {epic_id} failed, stopping sequence")
                break

        return results

    def get_epic_status(self, epic_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of an epic's tasks."""
        task_file = self._get_task_file_path(epic_id)

        if not task_file.exists():
            return None

        try:
            data = json.loads(task_file.read_text(encoding='utf-8'))
            return {
                "epic_id": epic_id,
                "total_tasks": data.get("total_tasks", 0),
                "completed_tasks": data.get("completed_tasks", 0),
                "failed_tasks": data.get("failed_tasks", 0),
                "progress_percent": data.get("progress_percent", 0),
                "run_count": data.get("run_count", 0),
                "last_run_at": data.get("last_run_at"),
            }
        except Exception as e:
            logger.error(f"Failed to get epic status: {e}")
            return None


# =============================================================================
# Test
# =============================================================================

async def test_epic_orchestrator():
    """Test the EpicOrchestrator"""
    print("=== Epic Orchestrator Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    orchestrator = EpicOrchestrator(str(test_path))

    # Test 1: Get epic status (before generation)
    print("1. Get epic status (before):")
    status = orchestrator.get_epic_status("EPIC-001")
    print(f"   Status: {status}")

    # Test 2: Load or generate tasks
    print("\n2. Load/generate tasks:")
    task_list = orchestrator._load_or_generate_tasks("EPIC-001")
    if task_list:
        print(f"   Tasks loaded: {len(task_list.tasks)}")
        print(f"   First 3 tasks:")
        for task in task_list.tasks[:3]:
            print(f"     - {task.id}: {task.title}")
    else:
        print("   No tasks generated")

    # Test 3: Get execution order
    print("\n3. Execution order (first 5):")
    if task_list and task_list.tasks:
        task_map = {t.id: t for t in task_list.tasks}
        pending = [t for t in task_list.tasks if t.status == "pending"]
        order = orchestrator._get_execution_order(pending[:10], task_map)
        for i, task in enumerate(order[:5]):
            deps = len(task.dependencies)
            print(f"   {i+1}. {task.id} ({deps} deps)")

    # Test 4: Dependency check
    print("\n4. Dependency check:")
    if task_list and len(task_list.tasks) > 5:
        task = task_list.tasks[5]
        met = orchestrator._dependencies_met(task, task_map)
        print(f"   Task: {task.id}")
        print(f"   Dependencies: {task.dependencies}")
        print(f"   Dependencies met: {met}")

    # Test 5: Get epic status (after)
    print("\n5. Get epic status (after):")
    status = orchestrator.get_epic_status("EPIC-001")
    print(f"   Status: {status}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_epic_orchestrator())
