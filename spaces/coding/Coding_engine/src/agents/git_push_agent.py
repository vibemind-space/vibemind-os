# -*- coding: utf-8 -*-
"""
GitPushAgent - Autonomous agent for Git operations after code generation.

Listens for:
- CONVERGENCE_ACHIEVED: All criteria met, commit and push generated code
- BUILD_SUCCEEDED + TESTS_PASSED: Checkpoint commit after successful build
- GENERATION_COMPLETE: Final commit after generation finishes

Uses MCPToolRegistry git tools for:
- git status, add, commit, push
- Branch creation for feature branches
- Commit message generation via LLM

This agent runs AFTER generation converges to persist the generated code
to a Git repository, ensuring no work is lost.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from ..mind.event_bus import (
    Event,
    EventBus,
    EventType,
    git_commit_created_event,
    git_push_failed_event,
    git_push_started_event,
    git_push_succeeded_event,
    system_error_event,
)
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


class GitPushAgent(AutonomousAgent):
    """
    Autonomous agent that commits and pushes generated code to Git.

    Triggers on:
    - CONVERGENCE_ACHIEVED: All generation criteria met
    - GENERATION_COMPLETE: Generation pipeline finished

    Uses subprocess-based git operations (same pattern as MCPToolRegistry).
    Generates meaningful commit messages based on what was generated/fixed.
    """

    def __init__(
        self,
        *args,
        auto_push: bool = False,
        branch_prefix: str = "gen",
        create_feature_branch: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.auto_push = auto_push
        self.branch_prefix = branch_prefix
        self.create_feature_branch = create_feature_branch
        self._last_commit_time: Optional[datetime] = None
        self._commit_cooldown = 30  # Minimum seconds between commits
        self._commits_made: list[dict] = []
        self._generation_name: Optional[str] = None

        # Track whether we've already committed for the current generation
        self._convergence_committed = False

        self.logger.info(
            "git_push_agent_configured",
            auto_push=auto_push,
            create_feature_branch=create_feature_branch,
            branch_prefix=branch_prefix,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.CONVERGENCE_ACHIEVED,
            EventType.GENERATION_COMPLETE,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Act when convergence is achieved or generation completes."""
        if self._convergence_committed:
            return False

        for event in events:
            if event.type in (EventType.CONVERGENCE_ACHIEVED, EventType.GENERATION_COMPLETE):
                # Respect cooldown
                if self._last_commit_time:
                    elapsed = (datetime.now() - self._last_commit_time).total_seconds()
                    if elapsed < self._commit_cooldown:
                        return False
                return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Commit and optionally push generated code.

        Workflow:
        1. Check if we're in a git repo
        2. Create feature branch if configured
        3. Stage all generated files
        4. Generate commit message from events
        5. Commit
        6. Push if auto_push is enabled
        """
        try:
            # Extract generation context from events
            generation_context = self._extract_generation_context(events)

            # Step 1: Verify git repo
            if not await self._is_git_repo():
                await self._init_git_repo()

            # Step 2: Check for changes
            status = await self._git_status()
            if not status.get("has_changes"):
                self.logger.info("git_no_changes", message="No changes to commit")
                return None

            changed_files = status.get("changed_files", [])

            # Step 3: Create feature branch if configured
            branch = await self._get_current_branch()
            if self.create_feature_branch and branch in ("main", "master"):
                new_branch = self._generate_branch_name(generation_context)
                success = await self._create_branch(new_branch)
                if success:
                    branch = new_branch
                    self.logger.info("git_branch_created", branch=branch)

            # Publish start event
            await self.event_bus.publish(git_push_started_event(
                source=self.name,
                branch=branch,
                files_changed=changed_files[:20],
            ))

            # Step 4: Stage files
            await self._git_add()

            # Step 5: Generate commit message
            commit_message = self._generate_commit_message(
                generation_context, changed_files
            )

            # Step 6: Commit
            commit_result = await self._git_commit(commit_message)
            if not commit_result.get("success"):
                error = commit_result.get("error", "Unknown commit error")
                self.logger.error("git_commit_failed", error=error)
                return git_push_failed_event(
                    source=self.name,
                    branch=branch,
                    error=error,
                    error_type="commit_failed",
                )

            commit_hash = commit_result.get("hash", "unknown")
            self._last_commit_time = datetime.now()
            self._convergence_committed = True

            self._commits_made.append({
                "hash": commit_hash,
                "message": commit_message,
                "branch": branch,
                "files": len(changed_files),
                "timestamp": datetime.now().isoformat(),
            })

            # Publish commit created event
            await self.event_bus.publish(git_commit_created_event(
                source=self.name,
                commit_hash=commit_hash,
                commit_message=commit_message,
                branch=branch,
                files_committed=changed_files[:50],
            ))

            self.logger.info(
                "git_commit_created",
                hash=commit_hash[:8],
                message=commit_message[:80],
                files=len(changed_files),
                branch=branch,
            )

            # Step 7: Push if auto_push is enabled
            if self.auto_push:
                push_result = await self._git_push(branch=branch)
                if push_result.get("success"):
                    self.logger.info(
                        "git_push_succeeded",
                        branch=branch,
                        hash=commit_hash[:8],
                    )
                    return git_push_succeeded_event(
                        source=self.name,
                        branch=branch,
                        commit_hash=commit_hash,
                        commit_message=commit_message,
                        files_committed=changed_files[:50],
                    )
                else:
                    push_error = push_result.get("error", "Unknown push error")
                    error_type = self._classify_push_error(push_error)
                    self.logger.warning(
                        "git_push_failed",
                        error=push_error,
                        error_type=error_type,
                    )
                    return git_push_failed_event(
                        source=self.name,
                        branch=branch,
                        error=push_error,
                        error_type=error_type,
                    )

            # If not auto-pushing, still return success for the commit
            return git_push_succeeded_event(
                source=self.name,
                branch=branch,
                commit_hash=commit_hash,
                commit_message=commit_message,
                files_committed=changed_files[:50],
            )

        except Exception as e:
            self.logger.error("git_push_agent_error", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=f"GitPushAgent error: {str(e)}",
                error_type="git_operation",
                recoverable=True,
            )

    def _get_action_description(self) -> str:
        return "Committing and pushing generated code to Git"

    # =========================================================================
    # Git Operations (subprocess-based, same pattern as MCPToolRegistry)
    # =========================================================================

    async def _run_git(self, *args: str, timeout: int = 30) -> dict:
        """Run a git command and return structured result."""
        cmd = ["git"] + list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode("utf-8", errors="replace").strip(),
                "stderr": stderr.decode("utf-8", errors="replace").strip(),
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Git command timed out: {' '.join(cmd)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _is_git_repo(self) -> bool:
        """Check if working_dir is inside a git repository."""
        result = await self._run_git("rev-parse", "--is-inside-work-tree")
        return result.get("success", False) and result.get("stdout") == "true"

    async def _init_git_repo(self) -> bool:
        """Initialize a new git repository."""
        result = await self._run_git("init")
        if result.get("success"):
            self.logger.info("git_repo_initialized", working_dir=self.working_dir)
            await self.event_bus.publish(Event(
                type=EventType.GIT_REPO_INITIALIZED,
                source=self.name,
                data={"working_dir": self.working_dir},
            ))
        return result.get("success", False)

    async def _git_status(self) -> dict:
        """Get git status with parsed file list."""
        result = await self._run_git("status", "--porcelain")
        if not result.get("success"):
            return {"has_changes": False, "error": result.get("error")}

        stdout = result.get("stdout", "")
        if not stdout.strip():
            return {"has_changes": False, "changed_files": []}

        files = []
        for line in stdout.split("\n"):
            if line.strip():
                # Porcelain format: XY filename
                status_code = line[:2]
                filepath = line[3:].strip()
                files.append(filepath)

        return {
            "has_changes": len(files) > 0,
            "changed_files": files,
            "file_count": len(files),
        }

    async def _get_current_branch(self) -> str:
        """Get current branch name."""
        result = await self._run_git("branch", "--show-current")
        if result.get("success"):
            branch = result.get("stdout", "").strip()
            return branch if branch else "main"
        return "main"

    async def _create_branch(self, branch_name: str) -> bool:
        """Create and checkout a new branch."""
        result = await self._run_git("checkout", "-b", branch_name)
        return result.get("success", False)

    async def _git_add(self, files: str = ".") -> bool:
        """Stage files for commit."""
        result = await self._run_git("add", files)
        return result.get("success", False)

    async def _git_commit(self, message: str) -> dict:
        """Create a commit and return hash."""
        result = await self._run_git("commit", "-m", message)
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("stderr") or result.get("stdout") or "Commit failed",
            }

        # Extract commit hash
        hash_result = await self._run_git("rev-parse", "--short", "HEAD")
        commit_hash = hash_result.get("stdout", "unknown") if hash_result.get("success") else "unknown"

        return {
            "success": True,
            "hash": commit_hash,
            "output": result.get("stdout", ""),
        }

    async def _git_push(self, remote: str = "origin", branch: str = "") -> dict:
        """Push to remote."""
        args = ["push"]
        if branch:
            args.extend(["-u", remote, branch])
        else:
            args.append(remote)

        result = await self._run_git(*args, timeout=60)
        return {
            "success": result.get("success", False),
            "output": result.get("stdout") or result.get("stderr"),
            "error": result.get("stderr") if not result.get("success") else None,
        }

    # =========================================================================
    # Commit Message Generation
    # =========================================================================

    def _extract_generation_context(self, events: list[Event]) -> dict:
        """Extract context from events for commit message generation."""
        context = {
            "event_types": [],
            "files_generated": [],
            "errors_fixed": 0,
            "tests_passed": False,
            "build_succeeded": False,
            "project_name": None,
        }

        for event in events:
            context["event_types"].append(event.type.value)

            if event.data:
                if "project_name" in event.data:
                    context["project_name"] = event.data["project_name"]
                if "files_created" in event.data:
                    context["files_generated"].extend(event.data["files_created"])
                if "errors_fixed" in event.data:
                    context["errors_fixed"] += event.data.get("errors_fixed", 0)

            if event.type == EventType.CONVERGENCE_ACHIEVED:
                context["build_succeeded"] = True
                context["tests_passed"] = True

        # Try to detect project name from working dir
        if not context["project_name"]:
            context["project_name"] = Path(self.working_dir).name

        return context

    def _generate_commit_message(
        self, context: dict, changed_files: list[str]
    ) -> str:
        """Generate a meaningful commit message from generation context."""
        project_name = context.get("project_name", "project")
        file_count = len(changed_files)

        # Categorize changed files
        categories = self._categorize_files(changed_files)

        # Build commit message
        parts = []

        if EventType.CONVERGENCE_ACHIEVED.value in context.get("event_types", []):
            parts.append(f"feat({project_name}): autonomous code generation complete")
        elif EventType.GENERATION_COMPLETE.value in context.get("event_types", []):
            parts.append(f"feat({project_name}): code generation finished")
        else:
            parts.append(f"chore({project_name}): generated code checkpoint")

        # Add summary line
        summary_parts = []
        if categories.get("components"):
            summary_parts.append(f"{len(categories['components'])} components")
        if categories.get("api_routes"):
            summary_parts.append(f"{len(categories['api_routes'])} API routes")
        if categories.get("tests"):
            summary_parts.append(f"{len(categories['tests'])} tests")
        if categories.get("configs"):
            summary_parts.append(f"{len(categories['configs'])} configs")
        if categories.get("schemas"):
            summary_parts.append(f"{len(categories['schemas'])} schemas")

        if summary_parts:
            parts.append(f"\nGenerated: {', '.join(summary_parts)}")

        parts.append(f"\nTotal files: {file_count}")

        if context.get("build_succeeded"):
            parts.append("Build: passing")
        if context.get("tests_passed"):
            parts.append("Tests: passing")
        if context.get("errors_fixed", 0) > 0:
            parts.append(f"Errors fixed: {context['errors_fixed']}")

        parts.append("\nGenerated by Coding Engine (Society of Mind)")

        return "\n".join(parts)

    def _categorize_files(self, files: list[str]) -> dict:
        """Categorize changed files by type."""
        categories: dict[str, list[str]] = {
            "components": [],
            "api_routes": [],
            "tests": [],
            "configs": [],
            "schemas": [],
            "styles": [],
            "other": [],
        }

        for f in files:
            f_lower = f.lower()
            if any(ext in f_lower for ext in [".tsx", ".jsx"]) and "test" not in f_lower:
                categories["components"].append(f)
            elif "route" in f_lower or "api" in f_lower or "endpoint" in f_lower:
                categories["api_routes"].append(f)
            elif "test" in f_lower or "spec" in f_lower:
                categories["tests"].append(f)
            elif any(cfg in f_lower for cfg in [
                "config", ".env", "docker", "package.json", "tsconfig",
                "vite.config", "vitest", ".yml", ".yaml",
            ]):
                categories["configs"].append(f)
            elif "schema" in f_lower or "prisma" in f_lower or "migration" in f_lower:
                categories["schemas"].append(f)
            elif any(ext in f_lower for ext in [".css", ".scss", ".less"]):
                categories["styles"].append(f)
            else:
                categories["other"].append(f)

        return categories

    def _generate_branch_name(self, context: dict) -> str:
        """Generate a branch name for the feature."""
        project_name = context.get("project_name", "generated")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        # Sanitize project name for branch name
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', project_name)[:30]
        return f"{self.branch_prefix}/{safe_name}-{timestamp}"

    def _classify_push_error(self, error: str) -> str:
        """Classify a git push error type."""
        error_lower = error.lower()
        if "authentication" in error_lower or "permission" in error_lower or "403" in error_lower:
            return "auth"
        if "conflict" in error_lower or "rejected" in error_lower or "non-fast-forward" in error_lower:
            return "conflict"
        if "could not resolve" in error_lower or "connection" in error_lower or "timeout" in error_lower:
            return "network"
        if "does not appear to be a git repository" in error_lower or "no such remote" in error_lower:
            return "no_remote"
        return "unknown"

    # =========================================================================
    # Public API
    # =========================================================================

    def get_commit_history(self) -> list[dict]:
        """Return list of commits made by this agent."""
        return list(self._commits_made)

    def reset_convergence_state(self) -> None:
        """Reset convergence commit state for new generation runs."""
        self._convergence_committed = False
