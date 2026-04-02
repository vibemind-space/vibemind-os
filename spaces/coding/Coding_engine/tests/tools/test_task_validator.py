# -*- coding: utf-8 -*-
"""
Tests for TaskValidator - Phase 13.

Verifies:
- Task loading from JSON
- Query helpers (failed, skipped, blocked_by)
- Validation task building
- Fix task building
- Dependency unblocking logic
- Dry run report
- Fix loop flow (mocked orchestrator)
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.tools.task_validator import (
    TaskValidator,
    FixResult,
    TASK_VALIDATORS,
    TASK_FIXERS,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_task(
    task_id: str,
    status: str = "completed",
    task_type: str = "api_controller",
    title: str = "Test task",
    dependencies: list = None,
    error_message: str = None,
    output_files: list = None,
    command: str = None,
    success_criteria: str = None,
) -> dict:
    """Create a minimal task dict."""
    return {
        "id": task_id,
        "epic_id": "EPIC-001",
        "type": task_type,
        "title": title,
        "description": f"Description for {title}",
        "status": status,
        "dependencies": dependencies or [],
        "estimated_minutes": 2,
        "actual_minutes": None,
        "error_message": error_message,
        "output_files": output_files or [],
        "related_requirements": [],
        "related_user_stories": [],
        "requires_user_input": False,
        "user_prompt": None,
        "user_response": None,
        "checkpoint": False,
        "auto_retry": True,
        "max_retries": 3,
        "retry_count": 0,
        "timeout_seconds": 300,
        "phase": "code",
        "command": command,
        "success_criteria": success_criteria,
    }


def _write_task_file(tmp_path: Path, tasks: list) -> Path:
    """Write a task file and return its path."""
    task_file = tmp_path / "tasks" / "epic-001-tasks.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "epic_id": "EPIC-001",
        "epic_name": "Test Epic",
        "tasks": tasks,
        "total_tasks": len(tasks),
        "completed_tasks": len([t for t in tasks if t["status"] == "completed"]),
        "failed_tasks": len([t for t in tasks if t["status"] == "failed"]),
        "progress_percent": 0,
        "run_count": 1,
        "last_run_at": "2026-02-07T00:00:00",
        "created_at": "2026-02-07T00:00:00",
        "estimated_total_minutes": 60,
    }

    task_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return task_file


@dataclass
class MockTaskResult:
    """Mock for MCPOrchestrator TaskResult."""
    task: str
    success: bool
    steps_executed: int
    total_duration: float
    output: Any
    errors: List[Dict[str, str]]
    plan: Optional[Any] = None


# =============================================================================
# Test: Loading
# =============================================================================

class TestTaskValidatorLoading:
    """Test task loading from JSON."""

    def test_load_tasks_from_file(self, tmp_path):
        """Should load tasks from a valid JSON file."""
        tasks = [
            _make_task("T1", status="completed"),
            _make_task("T2", status="failed", error_message="build error"),
            _make_task("T3", status="skipped", dependencies=["T2"]),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        assert len(validator.tasks) == 3

    def test_load_nonexistent_file_raises(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            TaskValidator(task_file=str(tmp_path / "nonexistent.json"), output_dir=".")

    def test_load_empty_tasks(self, tmp_path):
        """Should handle empty task list."""
        task_file = _write_task_file(tmp_path, [])
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        assert len(validator.tasks) == 0
        assert validator.get_failed_tasks() == []


# =============================================================================
# Test: Query helpers
# =============================================================================

class TestTaskValidatorQueries:
    """Test query helper methods."""

    @pytest.fixture
    def validator(self, tmp_path):
        tasks = [
            _make_task("T1", status="completed"),
            _make_task("T2", status="completed"),
            _make_task("T3", status="failed", error_message="no such service: db"),
            _make_task("T4", status="failed", error_message="Missing script: build"),
            _make_task("T5", status="skipped", dependencies=["T3"]),
            _make_task("T6", status="skipped", dependencies=["T4"]),
            _make_task("T7", status="skipped", dependencies=["T4", "T3"]),
            _make_task("T8", status="pending"),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        return TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

    def test_get_failed_tasks(self, validator):
        """Should return only failed tasks."""
        failed = validator.get_failed_tasks()
        assert len(failed) == 2
        assert {t["id"] for t in failed} == {"T3", "T4"}

    def test_get_skipped_tasks(self, validator):
        """Should return only skipped tasks."""
        skipped = validator.get_skipped_tasks()
        assert len(skipped) == 3
        assert {t["id"] for t in skipped} == {"T5", "T6", "T7"}

    def test_get_completed_tasks(self, validator):
        """Should return only completed tasks."""
        assert len(validator.get_completed_tasks()) == 2

    def test_get_pending_tasks(self, validator):
        """Should return only pending tasks."""
        assert len(validator.get_pending_tasks()) == 1

    def test_get_task_by_id(self, validator):
        """Should find a task by ID."""
        task = validator.get_task("T3")
        assert task is not None
        assert task["status"] == "failed"

    def test_get_task_not_found(self, validator):
        """Should return None for unknown ID."""
        assert validator.get_task("NONEXISTENT") is None

    def test_get_blocked_by(self, validator):
        """Should return tasks blocked by a given task."""
        blocked = validator.get_blocked_by("T4")
        assert len(blocked) == 2
        assert {t["id"] for t in blocked} == {"T6", "T7"}

    def test_get_summary(self, validator):
        """Should return correct status counts."""
        summary = validator.get_summary()
        assert summary["completed"] == 2
        assert summary["failed"] == 2
        assert summary["skipped"] == 3
        assert summary["pending"] == 1


# =============================================================================
# Test: Validation / Fix task building
# =============================================================================

class TestTaskBuildStrings:
    """Test _build_validation_task and _build_fix_task."""

    @pytest.fixture
    def validator(self, tmp_path):
        tasks = [
            _make_task(
                "BUILD-1",
                status="failed",
                task_type="verify_build",
                error_message='Missing script: "build"',
                command="npm run build",
                success_criteria="Build completes without errors",
            ),
            _make_task(
                "MIGRATE-1",
                status="failed",
                task_type="schema_migration",
                error_message="no such service: db",
                output_files=["prisma/migrations/*_device/"],
            ),
            _make_task(
                "CTRL-1",
                status="failed",
                task_type="api_controller",
                output_files=["src/controllers/users.controller.ts"],
            ),
            _make_task(
                "UNKNOWN-1",
                status="failed",
                task_type="custom_thing",
                title="Custom task",
                success_criteria="Custom check passes",
            ),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        return TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

    def test_build_validation_verify_build(self, validator):
        """verify_build tasks should use npm run build template."""
        task = validator.get_task("BUILD-1")
        val_str = validator._build_validation_task(task)
        assert "npm run build" in val_str

    def test_build_validation_schema_migration(self, validator):
        """schema_migration tasks should mention docker-compose and prisma."""
        task = validator.get_task("MIGRATE-1")
        val_str = validator._build_validation_task(task)
        assert "docker-compose" in val_str or "prisma" in val_str

    def test_build_validation_api_controller(self, validator):
        """api_controller tasks should check file existence."""
        task = validator.get_task("CTRL-1")
        val_str = validator._build_validation_task(task)
        assert "users.controller.ts" in val_str
        assert "route handler" in val_str.lower()

    def test_build_validation_fallback(self, validator):
        """Unknown task types should use fallback with title/criteria."""
        task = validator.get_task("UNKNOWN-1")
        val_str = validator._build_validation_task(task)
        assert "Custom task" in val_str
        assert "Custom check passes" in val_str

    def test_build_fix_verify_build(self, validator):
        """verify_build fix should mention build script."""
        task = validator.get_task("BUILD-1")
        fix_str = validator._build_fix_task(task)
        assert "claude_execute" in fix_str
        assert "build" in fix_str.lower()
        assert 'Missing script: "build"' in fix_str

    def test_build_fix_schema_migration(self, validator):
        """schema_migration fix should mention docker/prisma."""
        task = validator.get_task("MIGRATE-1")
        fix_str = validator._build_fix_task(task)
        assert "claude_execute" in fix_str
        assert "no such service: db" in fix_str

    def test_build_fix_fallback(self, validator):
        """Unknown task types should use generic Claude CLI fix."""
        task = validator.get_task("UNKNOWN-1")
        fix_str = validator._build_fix_task(task)
        assert "claude_execute" in fix_str
        assert "Custom task" in fix_str


# =============================================================================
# Test: Unblock dependents
# =============================================================================

class TestUnblockDependents:
    """Test _unblock_dependents logic."""

    @pytest.fixture
    def validator(self, tmp_path):
        tasks = [
            _make_task("A", status="completed"),
            _make_task("B", status="failed"),
            _make_task("C", status="skipped", dependencies=["B"]),
            _make_task("D", status="skipped", dependencies=["A", "B"]),
            _make_task("E", status="skipped", dependencies=["A"]),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        return TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

    def test_unblock_single_dep(self, validator):
        """When B is fixed, C (depends only on B) should become pending."""
        # Simulate fixing B
        validator.get_task("B")["status"] = "completed"
        unblocked = validator._unblock_dependents("B")

        assert "C" in unblocked
        assert validator.get_task("C")["status"] == "pending"

    def test_unblock_multi_dep(self, validator):
        """D depends on A (completed) + B. After fixing B, D should unblock."""
        validator.get_task("B")["status"] = "completed"
        unblocked = validator._unblock_dependents("B")

        assert "D" in unblocked
        assert validator.get_task("D")["status"] == "pending"

    def test_no_unblock_if_other_dep_still_failed(self, tmp_path):
        """Should not unblock if another dependency is still failed."""
        tasks = [
            _make_task("X", status="failed"),
            _make_task("Y", status="failed"),
            _make_task("Z", status="skipped", dependencies=["X", "Y"]),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        # Fix only X
        validator.get_task("X")["status"] = "completed"
        unblocked = validator._unblock_dependents("X")

        assert "Z" not in unblocked
        assert validator.get_task("Z")["status"] == "skipped"

    def test_unblock_does_not_touch_non_skipped(self, validator):
        """E is skipped but depends only on A (already completed). Fixing B should not touch E."""
        validator.get_task("B")["status"] = "completed"
        unblocked = validator._unblock_dependents("B")

        # E depends on A (completed), not B - so it shouldn't be in unblocked list
        assert "E" not in unblocked


# =============================================================================
# Test: Dry run
# =============================================================================

class TestDryRun:
    """Test dry run report."""

    def test_dry_run_report(self, tmp_path):
        tasks = [
            _make_task("F1", status="failed", task_type="verify_build",
                       error_message="Missing script"),
            _make_task("F2", status="failed", task_type="schema_migration",
                       error_message="no such service: db"),
            _make_task("S1", status="skipped", dependencies=["F1"]),
            _make_task("S2", status="skipped", dependencies=["F1"]),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        report = validator._dry_run_report()

        assert report["dry_run"] is True
        assert len(report["failed_tasks"]) == 2
        assert report["total_blocked"] == 2

        # verify_build should have a fixer
        build_item = next(i for i in report["failed_tasks"] if i["type"] == "verify_build")
        assert build_item["has_fixer"] is True
        assert build_item["blocks_count"] == 2

    def test_dry_run_no_failures(self, tmp_path):
        tasks = [_make_task("OK1", status="completed")]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        report = validator._dry_run_report()
        assert report["failed_tasks"] == []
        assert report["total_blocked"] == 0


# =============================================================================
# Test: Save tasks
# =============================================================================

class TestSaveTasks:
    """Test _save_tasks persists changes to disk."""

    def test_save_updates_file(self, tmp_path):
        tasks = [
            _make_task("T1", status="failed"),
            _make_task("T2", status="skipped", dependencies=["T1"]),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        # Simulate fixing T1
        validator.get_task("T1")["status"] = "completed"
        validator.get_task("T1")["error_message"] = None
        validator._save_tasks()

        # Re-read from disk
        with open(task_file, "r", encoding="utf-8") as f:
            saved = json.load(f)

        saved_t1 = next(t for t in saved["tasks"] if t["id"] == "T1")
        assert saved_t1["status"] == "completed"
        assert saved["completed_tasks"] == 1
        assert saved["failed_tasks"] == 0


# =============================================================================
# Test: Fix loop with mocked orchestrator
# =============================================================================

class TestFixLoop:
    """Test run_fix_loop with mocked MCPOrchestrator."""

    @pytest.mark.asyncio
    async def test_fix_loop_dry_run(self, tmp_path):
        """Dry run should not call orchestrator."""
        tasks = [
            _make_task("F1", status="failed", task_type="verify_build",
                       error_message="Missing script"),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        result = await validator.run_fix_loop(dry_run=True)

        assert result["dry_run"] is True
        # Task should still be failed
        assert validator.get_task("F1")["status"] == "failed"

    @pytest.mark.asyncio
    async def test_fix_loop_fixes_task(self, tmp_path):
        """Fix loop should mark task as completed when fix + validation succeed."""
        tasks = [
            _make_task("F1", status="failed", task_type="verify_build",
                       error_message="Missing script: build"),
            _make_task("S1", status="skipped", dependencies=["F1"]),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        # Mock orchestrator to return success
        mock_result = MockTaskResult(
            task="fix", success=True, steps_executed=2,
            total_duration=1.0, output="Fixed", errors=[],
        )
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute_task = AsyncMock(return_value=mock_result)

        with patch.object(validator, "_get_orchestrator", return_value=mock_orchestrator):
            result = await validator.run_fix_loop(max_iterations=1)

        assert result["tasks_fixed"] == 1
        assert validator.get_task("F1")["status"] == "completed"
        assert validator.get_task("S1")["status"] == "pending"  # unblocked

    @pytest.mark.asyncio
    async def test_fix_loop_handles_fix_failure(self, tmp_path):
        """Fix loop should handle failed fix attempts gracefully."""
        tasks = [
            _make_task("F1", status="failed", task_type="verify_build",
                       error_message="Missing script"),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        # Mock orchestrator to return failure
        mock_result = MockTaskResult(
            task="fix", success=False, steps_executed=0,
            total_duration=0.5, output=None, errors=[{"error": "Claude CLI failed"}],
        )
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute_task = AsyncMock(return_value=mock_result)

        with patch.object(validator, "_get_orchestrator", return_value=mock_orchestrator):
            result = await validator.run_fix_loop(max_iterations=2)

        assert result["tasks_fixed"] == 0
        assert validator.get_task("F1")["status"] == "failed"

    @pytest.mark.asyncio
    async def test_fix_loop_validation_fails_after_fix(self, tmp_path):
        """Should not mark task completed if fix succeeds but validation fails."""
        tasks = [
            _make_task("F1", status="failed", task_type="verify_build",
                       error_message="Missing script"),
        ]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        # Fix returns success, validation returns failure
        fix_result = MockTaskResult(
            task="fix", success=True, steps_executed=1,
            total_duration=1.0, output="Script added", errors=[],
        )
        val_result = MockTaskResult(
            task="validate", success=False, steps_executed=1,
            total_duration=0.5, output="Build still fails", errors=[{"error": "tsc error"}],
        )
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute_task = AsyncMock(side_effect=[fix_result, val_result])

        with patch.object(validator, "_get_orchestrator", return_value=mock_orchestrator):
            result = await validator.run_fix_loop(max_iterations=1)

        assert result["tasks_fixed"] == 0
        assert validator.get_task("F1")["status"] == "failed"

    @pytest.mark.asyncio
    async def test_fix_loop_no_failed_tasks(self, tmp_path):
        """Should do nothing if no tasks are failed."""
        tasks = [_make_task("OK1", status="completed")]
        task_file = _write_task_file(tmp_path, tasks)
        validator = TaskValidator(task_file=str(task_file), output_dir=str(tmp_path))

        result = await validator.run_fix_loop()

        assert result["tasks_attempted"] == 0
        assert result["tasks_fixed"] == 0


# =============================================================================
# Test: FixResult dataclass
# =============================================================================

class TestFixResult:
    """Test FixResult dataclass."""

    def test_fix_result_defaults(self):
        r = FixResult(task_id="T1", success=True)
        assert r.fix_output == ""
        assert r.validation_output == ""
        assert r.errors == []

    def test_fix_result_with_data(self):
        r = FixResult(
            task_id="T1", success=False,
            fix_output="attempted fix", errors=["failed"],
        )
        assert not r.success
        assert r.fix_output == "attempted fix"


# =============================================================================
# Test: Constants
# =============================================================================

class TestConstants:
    """Test TASK_VALIDATORS and TASK_FIXERS constants."""

    def test_verify_build_has_validator(self):
        assert "verify_build" in TASK_VALIDATORS

    def test_verify_build_has_fixer(self):
        assert "verify_build" in TASK_FIXERS

    def test_schema_migration_has_validator(self):
        assert "schema_migration" in TASK_VALIDATORS

    def test_schema_migration_has_fixer(self):
        assert "schema_migration" in TASK_FIXERS

    def test_api_controller_has_validator(self):
        assert "api_controller" in TASK_VALIDATORS

    def test_all_validators_have_template(self):
        for key, val in TASK_VALIDATORS.items():
            assert "task_template" in val, f"{key} missing task_template"

    def test_all_fixers_have_template(self):
        for key, val in TASK_FIXERS.items():
            assert "fix_template" in val, f"{key} missing fix_template"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
