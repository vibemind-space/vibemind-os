# -*- coding: utf-8 -*-
"""
Task Validator - Reads failed/skipped tasks from epic JSON and drives
validation + fixing via MCP Orchestrator and Claude CLI.

Usage:
    from src.tools.task_validator import TaskValidator

    validator = TaskValidator(
        task_file="Data/.../tasks/epic-001-tasks.json",
        output_dir="output",
    )
    await validator.run_fix_loop(max_iterations=3)
"""
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()


@dataclass
class FixResult:
    """Result from attempting to fix a single task."""
    task_id: str
    success: bool
    fix_output: str = ""
    validation_output: str = ""
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Task-type → MCP validation mapping
# ---------------------------------------------------------------------------
TASK_VALIDATORS: Dict[str, Dict[str, Any]] = {
    # --- TypeScript / NestJS ---
    "verify_build": {
        "description": "Run build and check for errors",
        "task_template": "Run 'npm run build' in {output_dir} and report success/failure",
    },
    "verify_typecheck": {
        "description": "Run TypeScript type-checking",
        "task_template": "Run 'npx tsc --noEmit' in {output_dir} and report type errors",
    },
    "schema_migration": {
        "description": "Verify schema migration can run",
        "task_template": (
            "Check if docker-compose has a 'db' service, verify it is running, "
            "then run the migration command in {output_dir}"
        ),
    },
    "api_controller": {
        "description": "Verify API controller/route file exists",
        "task_template": "Check if file {output_file} exists in {output_dir} and contains route handlers",
    },
    "api_service": {
        "description": "Verify API service file exists",
        "task_template": "Check if file {output_file} exists in {output_dir} and contains service logic",
    },
    "api_guard": {
        "description": "Verify API guard/middleware file exists",
        "task_template": "Check if file {output_file} exists in {output_dir} and contains auth checks",
    },
    "api_validation": {
        "description": "Verify validation/DTO file exists",
        "task_template": "Check if file {output_file} exists in {output_dir}",
    },
    "api_module": {
        "description": "Verify module/router file exists",
        "task_template": "Check if file {output_file} exists in {output_dir} and contains module/router definition",
    },
    # --- Python ---
    "verify_build_python": {
        "description": "Compile-check Python files",
        "task_template": "Run 'python -m py_compile' on all .py files in {output_dir} and report errors",
    },
    "verify_lint_python": {
        "description": "Lint Python code",
        "task_template": "Run 'ruff check {output_dir}' and report issues",
    },
    # --- Rust ---
    "verify_build_rust": {
        "description": "Build Rust project",
        "task_template": "Run 'cargo build' in {output_dir} and report success/failure",
    },
    # --- Go ---
    "verify_build_go": {
        "description": "Build Go project",
        "task_template": "Run 'go build ./...' in {output_dir} and report success/failure",
    },
    # --- Generic (any language) ---
    "verify_unit": {
        "description": "Run unit tests",
        "task_template": "Detect the test framework in {output_dir} and run tests, report pass/fail",
    },
    "verify_lint": {
        "description": "Run linter",
        "task_template": "Detect the linter for the project in {output_dir} and run it, report issues",
    },
}

# Task-type → fix strategy
TASK_FIXERS: Dict[str, Dict[str, Any]] = {
    # --- TypeScript / NestJS ---
    "verify_build": {
        "description": "Fix build errors",
        "fix_template": (
            "The project in {output_dir} fails build with error:\n"
            "{error_message}\n\n"
            "Fix the build issue. Check package.json for build script, "
            "fix missing imports, syntax errors, or config issues.\n"
            "Working directory: {output_dir}"
        ),
    },
    "verify_typecheck": {
        "description": "Fix type errors",
        "fix_template": (
            "The project in {output_dir} has type errors:\n"
            "{error_message}\n\n"
            "Fix the type errors in the source files.\n"
            "Working directory: {output_dir}"
        ),
    },
    "schema_migration": {
        "description": "Fix schema migration issues",
        "fix_template": (
            "Schema migration failed in {output_dir}:\n"
            "{error_message}\n\n"
            "Fix the migration issue. Ensure the database service is running "
            "and the schema is valid.\n"
            "Working directory: {output_dir}"
        ),
    },
    # --- Python ---
    "verify_build_python": {
        "description": "Fix Python compilation errors",
        "fix_template": (
            "The Python project in {output_dir} has compilation errors:\n"
            "{error_message}\n\n"
            "Fix syntax errors, missing imports, or dependency issues.\n"
            "Working directory: {output_dir}"
        ),
    },
    "verify_lint_python": {
        "description": "Fix Python lint issues",
        "fix_template": (
            "The Python project in {output_dir} has lint issues:\n"
            "{error_message}\n\n"
            "Fix the linting issues reported by ruff.\n"
            "Working directory: {output_dir}"
        ),
    },
    # --- Rust ---
    "verify_build_rust": {
        "description": "Fix Rust build errors",
        "fix_template": (
            "The Rust project in {output_dir} fails cargo build:\n"
            "{error_message}\n\n"
            "Fix compilation errors, missing dependencies in Cargo.toml, "
            "or type mismatches.\n"
            "Working directory: {output_dir}"
        ),
    },
    # --- Go ---
    "verify_build_go": {
        "description": "Fix Go build errors",
        "fix_template": (
            "The Go project in {output_dir} fails go build:\n"
            "{error_message}\n\n"
            "Fix compilation errors, missing imports, or module issues.\n"
            "Working directory: {output_dir}"
        ),
    },
}


class TaskValidator:
    """
    Reads task JSON, validates via MCP tools, fixes via Claude CLI,
    and unblocks downstream skipped tasks.
    """

    def __init__(self, task_file: str, output_dir: str, som_bridge: Optional[Any] = None):
        """
        Args:
            task_file: Path to epic-*-tasks.json
            output_dir: Project output directory (where generated code lives)
            som_bridge: Optional SoMBridge for universal verification commands
                        and project profile context
        """
        self.task_file = Path(task_file)
        self.output_dir = Path(output_dir)
        self.som_bridge = som_bridge
        self._data: Dict[str, Any] = {}
        self.tasks: List[Dict[str, Any]] = []
        self._load_tasks()

    # ------------------------------------------------------------------
    # Loading / Saving
    # ------------------------------------------------------------------

    def _load_tasks(self):
        """Load tasks from JSON file."""
        if not self.task_file.exists():
            raise FileNotFoundError(f"Task file not found: {self.task_file}")

        with open(self.task_file, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        self.tasks = self._data.get("tasks", [])
        logger.info(
            "task_validator_loaded",
            task_file=str(self.task_file),
            total=len(self.tasks),
            failed=len(self.get_failed_tasks()),
            skipped=len(self.get_skipped_tasks()),
        )

    def _save_tasks(self):
        """Write updated tasks back to JSON file."""
        self._data["tasks"] = self.tasks
        # Update summary counts
        self._data["completed_tasks"] = len(
            [t for t in self.tasks if t["status"] == "completed"]
        )
        self._data["failed_tasks"] = len(
            [t for t in self.tasks if t["status"] == "failed"]
        )

        with open(self.task_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

        logger.info(
            "task_validator_saved",
            completed=self._data["completed_tasks"],
            failed=self._data["failed_tasks"],
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_failed_tasks(self) -> List[Dict[str, Any]]:
        """Return tasks with status='failed'."""
        return [t for t in self.tasks if t["status"] == "failed"]

    def get_skipped_tasks(self) -> List[Dict[str, Any]]:
        """Return tasks with status='skipped'."""
        return [t for t in self.tasks if t["status"] == "skipped"]

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Return tasks with status='pending'."""
        return [t for t in self.tasks if t["status"] == "pending"]

    def get_completed_tasks(self) -> List[Dict[str, Any]]:
        """Return tasks with status='completed'."""
        return [t for t in self.tasks if t["status"] == "completed"]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by its ID."""
        for t in self.tasks:
            if t["id"] == task_id:
                return t
        return None

    def get_blocked_by(self, task_id: str) -> List[Dict[str, Any]]:
        """Return tasks whose dependencies include task_id."""
        return [
            t for t in self.tasks
            if task_id in t.get("dependencies", [])
        ]

    def get_summary(self) -> Dict[str, int]:
        """Return status summary counts."""
        counts: Dict[str, int] = {}
        for t in self.tasks:
            s = t["status"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Orchestrator helpers
    # ------------------------------------------------------------------

    def _get_orchestrator(self):
        """Create an MCPOrchestrator instance (lazy, no import at module level)."""
        from src.mcp.mcp_orchestrator import MCPOrchestrator

        return MCPOrchestrator(
            working_dir=str(self.output_dir),
            recovery_enabled=True,
            publish_events=False,
        )

    def _build_validation_task(self, task: Dict[str, Any]) -> str:
        """Build an MCP validation task string from a task dict.

        Resolution order:
        1. SoMBridge universal commands (project-profile-aware)
        2. Static TASK_VALIDATORS (language-specific fallback)
        3. Generic validation from task metadata
        """
        task_type = task.get("type", "")

        # 1. Try SoMBridge universal commands (auto-detected for project type)
        if self.som_bridge:
            universal_cmds = self.som_bridge.get_verification_commands()
            if task_type in universal_cmds:
                cmd = universal_cmds[task_type]
                return (
                    f"Run '{cmd}' in {self.output_dir} and report success/failure.\n"
                    f"Task: {task.get('title', '')}"
                )

        # 2. Static TASK_VALIDATORS
        validator = TASK_VALIDATORS.get(task_type)
        if validator:
            output_files = task.get("output_files", [])
            output_file = output_files[0] if output_files else ""
            return validator["task_template"].format(
                output_dir=str(self.output_dir),
                output_file=output_file,
            )

        # 3. Fallback: use task description + success_criteria
        parts = [f"Validate: {task.get('title', task.get('description', ''))}"]
        if task.get("success_criteria"):
            parts.append(f"Success criteria: {task['success_criteria']}")
        if task.get("output_files"):
            parts.append(f"Expected files: {', '.join(task['output_files'])}")
        parts.append(f"Working directory: {self.output_dir}")
        return "\n".join(parts)

    def _get_profile_context(self) -> str:
        """Get project profile context from SoMBridge if available."""
        if not self.som_bridge or not self.som_bridge.project_profile:
            return ""
        p = self.som_bridge.project_profile
        techs = []
        if hasattr(p, 'technologies'):
            techs = [t.value if hasattr(t, 'value') else str(t) for t in p.technologies]
        return (
            f"\nProject type: {p.project_type.value if hasattr(p.project_type, 'value') else p.project_type}"
            f"\nLanguage: {p.primary_language}"
            f"\nTechnologies: {techs}"
        )

    def _build_fix_task(self, task: Dict[str, Any]) -> str:
        """Build an MCP fix task string (uses Claude CLI for code fixes).

        Injects project profile context from SoMBridge when available
        so fixes are framework-aware.
        """
        task_type = task.get("type", "")
        profile_ctx = self._get_profile_context()
        fixer = TASK_FIXERS.get(task_type)

        if fixer:
            return (
                "Use the claude_execute tool to fix this issue:\n\n"
                + fixer["fix_template"].format(
                    output_dir=str(self.output_dir),
                    error_message=task.get("error_message", "Unknown error"),
                )
                + profile_ctx
            )

        # Fallback: generic fix prompt via Claude CLI
        return (
            "Use the claude_execute tool to fix this issue:\n\n"
            f"Task: {task.get('title', '')}\n"
            f"Description: {task.get('description', '')}\n"
            f"Error: {task.get('error_message', 'Unknown error')}\n"
            f"Command: {task.get('command', 'N/A')}\n"
            f"Success criteria: {task.get('success_criteria', 'N/A')}\n"
            f"Output files: {task.get('output_files', [])}\n"
            f"Working directory: {self.output_dir}"
            + profile_ctx
        )

    # ------------------------------------------------------------------
    # Validate / Fix single task
    # ------------------------------------------------------------------

    async def validate_task(self, task: Dict[str, Any]) -> FixResult:
        """Validate a single task using MCP tools."""
        task_id = task["id"]
        validation_str = self._build_validation_task(task)

        logger.info("task_validator_validating", task_id=task_id, task_type=task.get("type"))

        try:
            orchestrator = self._get_orchestrator()
            result = await orchestrator.execute_task(
                task=validation_str,
                context={
                    "phase": "task_validation",
                    "task_id": task_id,
                    "task_type": task.get("type", ""),
                    "output_dir": str(self.output_dir),
                },
            )

            return FixResult(
                task_id=task_id,
                success=result.success,
                validation_output=str(result.output)[:2000] if result.output else "",
                errors=[e.get("error", str(e)) for e in (result.errors or [])],
            )
        except Exception as e:
            logger.error("task_validator_validate_error", task_id=task_id, error=str(e))
            return FixResult(
                task_id=task_id,
                success=False,
                errors=[str(e)],
            )

    async def fix_task(self, task: Dict[str, Any]) -> FixResult:
        """Fix a failed task using Claude CLI via MCP."""
        task_id = task["id"]
        fix_str = self._build_fix_task(task)

        logger.info("task_validator_fixing", task_id=task_id, task_type=task.get("type"))

        try:
            orchestrator = self._get_orchestrator()
            result = await orchestrator.execute_task(
                task=fix_str,
                context={
                    "phase": "task_fix",
                    "task_id": task_id,
                    "task_type": task.get("type", ""),
                    "output_dir": str(self.output_dir),
                    "error_message": task.get("error_message", ""),
                },
            )

            return FixResult(
                task_id=task_id,
                success=result.success,
                fix_output=str(result.output)[:2000] if result.output else "",
                errors=[e.get("error", str(e)) for e in (result.errors or [])],
            )
        except Exception as e:
            logger.error("task_validator_fix_error", task_id=task_id, error=str(e))
            return FixResult(
                task_id=task_id,
                success=False,
                errors=[str(e)],
            )

    # ------------------------------------------------------------------
    # Unblock downstream
    # ------------------------------------------------------------------

    def _unblock_dependents(self, fixed_task_id: str):
        """Set skipped tasks back to pending if all their blockers are resolved."""
        unblocked = []
        for task in self.tasks:
            if task["status"] != "skipped":
                continue
            deps = task.get("dependencies", [])
            if fixed_task_id not in deps:
                continue
            # Check if ALL dependencies are now completed
            all_deps_ok = all(
                (self.get_task(dep) or {}).get("status") == "completed"
                for dep in deps
            )
            if all_deps_ok:
                task["status"] = "pending"
                unblocked.append(task["id"])

        if unblocked:
            logger.info(
                "task_validator_unblocked",
                fixed=fixed_task_id,
                unblocked_count=len(unblocked),
                unblocked_ids=unblocked[:10],
            )

        return unblocked

    # ------------------------------------------------------------------
    # Main fix loop
    # ------------------------------------------------------------------

    async def run_fix_loop(
        self,
        max_iterations: int = 3,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Main loop: fix failed tasks → re-validate → unblock downstream.

        Args:
            max_iterations: Max fix attempts per task
            dry_run: If True, only report what would be done

        Returns:
            Summary dict with before/after counts and per-task results
        """
        before = self.get_summary()
        results: List[Dict[str, Any]] = []

        logger.info("task_validator_loop_start", before=before, max_iterations=max_iterations)

        if dry_run:
            return self._dry_run_report()

        failed = self.get_failed_tasks()
        for task in failed:
            task_id = task["id"]
            task_result = {
                "task_id": task_id,
                "type": task.get("type"),
                "title": task.get("title"),
                "iterations": 0,
                "fixed": False,
                "errors": [],
            }

            for iteration in range(max_iterations):
                task_result["iterations"] = iteration + 1

                # Step 1: attempt fix
                fix_res = await self.fix_task(task)
                if not fix_res.success:
                    task_result["errors"].append(
                        f"Fix attempt {iteration+1} failed: {fix_res.errors}"
                    )
                    continue

                # Step 2: re-validate
                val_res = await self.validate_task(task)
                if val_res.success:
                    task["status"] = "completed"
                    task["error_message"] = None
                    task_result["fixed"] = True
                    self._unblock_dependents(task_id)
                    logger.info("task_validator_task_fixed", task_id=task_id, iteration=iteration+1)
                    break
                else:
                    task_result["errors"].append(
                        f"Validation after fix {iteration+1} failed: {val_res.errors}"
                    )

            results.append(task_result)

        self._save_tasks()

        after = self.get_summary()
        summary = {
            "before": before,
            "after": after,
            "tasks_attempted": len(results),
            "tasks_fixed": sum(1 for r in results if r["fixed"]),
            "results": results,
        }

        logger.info("task_validator_loop_done", **{k: v for k, v in summary.items() if k != "results"})
        return summary

    def _dry_run_report(self) -> Dict[str, Any]:
        """Generate a report of what would be done without executing."""
        failed = self.get_failed_tasks()
        skipped = self.get_skipped_tasks()
        plan = []

        for task in failed:
            task_type = task.get("type", "unknown")
            blocked = self.get_blocked_by(task["id"])
            plan.append({
                "task_id": task["id"],
                "type": task_type,
                "title": task.get("title"),
                "error": task.get("error_message", "")[:200],
                "has_fixer": task_type in TASK_FIXERS,
                "has_validator": task_type in TASK_VALIDATORS,
                "blocks_count": len(blocked),
                "fix_strategy": TASK_FIXERS.get(task_type, {}).get("description", "generic Claude CLI fix"),
            })

        return {
            "dry_run": True,
            "summary": self.get_summary(),
            "failed_tasks": plan,
            "total_blocked": len(skipped),
        }
