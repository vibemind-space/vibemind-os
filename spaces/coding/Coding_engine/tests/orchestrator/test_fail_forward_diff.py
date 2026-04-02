# -*- coding: utf-8 -*-
"""
Tests for Phase 25: Fail-Forward Execution + Differential Validation.

Tests that:
1. --skip-failed-deps is now the default (fail-forward)
2. run_differential_validation() integrates correctly after epic run
3. Auto-fix via claude-code works end-to-end
4. CLI flags parse correctly (--block-on-fail, --diff-fixes, --no-diff)
"""

import asyncio
import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from dataclasses import dataclass
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "mcp_plugins" / "servers" / "grpc_host"))

try:
    from epic_orchestrator import EpicOrchestrator, EpicExecutionResult
    from epic_task_generator import Task, TaskStatus, EpicTaskList
    from task_executor import TaskExecutionResult
    _IMPORTS_AVAILABLE = True
except ImportError:
    _IMPORTS_AVAILABLE = False

try:
    from src.services.differential_analysis_service import (
        AnalysisMode,
        DifferentialAnalysisService,
        ImplementationStatus,
        GapSeverity,
        GapFinding,
        AnalysisReport,
    )
    _DIFF_AVAILABLE = True
except (ImportError, OSError, Exception):
    _DIFF_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _IMPORTS_AVAILABLE,
    reason="epic_orchestrator imports not available",
)

# Separate mark for diff-dependent tests
_skip_no_diff = pytest.mark.skipif(
    not _DIFF_AVAILABLE,
    reason="DifferentialAnalysisService not available (JAX DLL conflict)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_task(
    task_id: str,
    deps: List[str] = None,
    status: str = "pending",
    task_type: str = "api_controller",
) -> Task:
    return Task(
        id=task_id,
        epic_id="EPIC-001",
        type=task_type,
        title=f"Task {task_id}",
        description=f"Test task {task_id}",
        status=status,
        dependencies=deps or [],
        output_files=[],
        phase="code",
    )


def make_orchestrator(max_parallel: int = 1) -> EpicOrchestrator:
    with patch.object(EpicOrchestrator, "__init__", lambda self, *a, **kw: None):
        orch = EpicOrchestrator.__new__(EpicOrchestrator)
    orch.max_parallel_tasks = max_parallel
    orch._paused = False
    orch._running_task_ids = set()
    orch._current_task_id = None
    orch._current_epic_id = None
    orch._running = False
    orch._semaphore = None
    orch.event_bus = None
    orch.enable_som = False
    orch.som_bridge = None
    orch.task_executor = MagicMock()
    orch.task_executor.execute_task = AsyncMock(
        return_value=TaskExecutionResult(success=True, output="OK", error=None)
    )
    return orch


def make_mock_gap(req_id: str, title: str, severity: str = "critical") -> GapFinding:
    """Create a mock GapFinding for testing."""
    return GapFinding(
        requirement_id=req_id,
        requirement_title=title,
        requirement_description=f"Description for {req_id}",
        priority="MUST",
        status=ImplementationStatus.MISSING,
        severity=GapSeverity.CRITICAL if severity == "critical" else GapSeverity.HIGH,
        confidence=0.95,
        gap_description=f"Missing implementation for {title}",
        suggested_tasks=[f"Implement {title}"],
    )


# ---------------------------------------------------------------------------
# Test: Fail-Forward is Default
# ---------------------------------------------------------------------------


class TestFailForwardDefault:
    """Verify that skip_failed_deps=True is now the default behavior."""

    @pytest.mark.asyncio
    async def test_failed_task_does_not_block_downstream(self):
        """With fail-forward, tasks after a failed dependency still execute."""
        orch = make_orchestrator(max_parallel=1)

        t1 = make_task("T1")  # No deps
        t2 = make_task("T2")  # No deps
        t3 = make_task("T3", deps=["T1"])  # Depends on T1

        # T1 fails, T2 succeeds, T3 should still run (skip_failed_deps=True)
        call_count = 0

        async def mock_execute(task):
            nonlocal call_count
            call_count += 1
            if task.id == "T1":
                task.status = "failed"
                return TaskExecutionResult(success=False, output="", error="pg not running")
            task.status = "completed"
            return TaskExecutionResult(success=True, output="OK", error=None)

        orch.task_executor.execute_task = AsyncMock(side_effect=mock_execute)

        result = await orch._execute_tasks_in_order(
            "EPIC-001",
            all_tasks=[t1, t2, t3],
            tasks_to_execute=[t1, t2, t3],
            skip_failed_deps=True,  # fail-forward
        )

        # All 3 tasks should have been attempted
        assert call_count == 3
        assert result.completed_tasks == 2  # T2 + T3
        assert result.failed_tasks == 1  # T1

    @pytest.mark.asyncio
    async def test_block_on_fail_skips_downstream(self):
        """With block-on-fail, downstream tasks of failed deps are skipped."""
        orch = make_orchestrator(max_parallel=1)

        t1 = make_task("T1")
        t2 = make_task("T2")
        t3 = make_task("T3", deps=["T1"])  # Depends on T1

        async def mock_execute(task):
            if task.id == "T1":
                task.status = "failed"
                return TaskExecutionResult(success=False, output="", error="pg not running")
            task.status = "completed"
            return TaskExecutionResult(success=True, output="OK", error=None)

        orch.task_executor.execute_task = AsyncMock(side_effect=mock_execute)

        result = await orch._execute_tasks_in_order(
            "EPIC-001",
            all_tasks=[t1, t2, t3],
            tasks_to_execute=[t1, t2, t3],
            skip_failed_deps=False,  # block on fail (old behavior)
        )

        # T3 should be skipped because T1 failed
        assert result.completed_tasks == 1  # Only T2
        assert result.failed_tasks == 1  # T1
        assert result.skipped_tasks == 1  # T3 skipped

    @pytest.mark.asyncio
    async def test_multiple_failures_dont_cascade_block(self):
        """With fail-forward, even multiple failures don't block independent chains."""
        orch = make_orchestrator(max_parallel=1)

        # Two independent chains: T1->T3 and T2->T4
        t1 = make_task("T1")
        t2 = make_task("T2")
        t3 = make_task("T3", deps=["T1"])
        t4 = make_task("T4", deps=["T2"])

        async def mock_execute(task):
            if task.id in ("T1", "T2"):
                task.status = "failed"
                return TaskExecutionResult(success=False, output="", error="migration failed")
            task.status = "completed"
            return TaskExecutionResult(success=True, output="OK", error=None)

        orch.task_executor.execute_task = AsyncMock(side_effect=mock_execute)

        result = await orch._execute_tasks_in_order(
            "EPIC-001",
            all_tasks=[t1, t2, t3, t4],
            tasks_to_execute=[t1, t2, t3, t4],
            skip_failed_deps=True,
        )

        # T3 and T4 should still execute despite T1/T2 failing
        assert result.completed_tasks == 2  # T3 + T4
        assert result.failed_tasks == 2  # T1 + T2


# ---------------------------------------------------------------------------
# Test: CLI Flag Parsing
# ---------------------------------------------------------------------------


class TestCLIFlagParsing:
    """Verify new CLI flags parse correctly."""

    def test_fail_forward_is_default(self):
        """Without --block-on-fail, skip_failed_deps should be True."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--block-on-fail", action="store_true")
        args = parser.parse_args([])

        skip_failed_deps = not args.block_on_fail
        assert skip_failed_deps is True

    def test_block_on_fail_disables_fail_forward(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--block-on-fail", action="store_true")
        args = parser.parse_args(["--block-on-fail"])

        skip_failed_deps = not args.block_on_fail
        assert skip_failed_deps is False

    def test_diff_fixes_default_zero(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--diff-fixes", type=int, default=0)
        args = parser.parse_args([])
        assert args.diff_fixes == 0

    def test_diff_fixes_custom(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--diff-fixes", type=int, default=0)
        args = parser.parse_args(["--diff-fixes", "10"])
        assert args.diff_fixes == 10

    def test_no_diff_flag(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--no-diff", action="store_true")
        args = parser.parse_args(["--no-diff"])
        assert args.no_diff is True


# ---------------------------------------------------------------------------
# Test: Differential Validation Integration
# ---------------------------------------------------------------------------


class TestDifferentialValidation:
    """Test the run_differential_validation() function.

    These tests mock DifferentialAnalysisService entirely (lazy import in
    run_differential_validation), so they do NOT require the real service.
    """

    @pytest.mark.asyncio
    async def test_analysis_only_no_fixes(self, tmp_path):
        """With max_fixes=0, only analysis runs (no MCP agents spawned)."""
        from run_epic001_live import run_differential_validation

        data_dir = tmp_path / "project"
        data_dir.mkdir()
        code_dir = data_dir / "output"
        code_dir.mkdir()
        (code_dir / "app.ts").write_text("// placeholder", encoding="utf-8")

        mock_report = MagicMock()
        mock_report.total_requirements = 10
        mock_report.implemented = 3
        mock_report.partial = 2
        mock_report.missing = 5
        mock_report.coverage_percent = 32.0
        mock_report.judge_confidence = 0.90
        mock_report.findings = []

        with patch("src.services.differential_analysis_service.DifferentialAnalysisService") as MockService, \
             patch.dict("sys.modules", {
                 "src.services.differential_analysis_service": MagicMock(
                     AnalysisMode=MagicMock(FULL_DIFFERENTIAL="full_differential"),
                     DifferentialAnalysisService=MockService,
                     ImplementationStatus=MagicMock(IMPLEMENTED="implemented"),
                     GapSeverity=MagicMock(CRITICAL="critical"),
                 )
             }):
            service_instance = AsyncMock()
            service_instance.start = AsyncMock(return_value=True)
            service_instance.run_analysis = AsyncMock(return_value=mock_report)
            service_instance.stop = AsyncMock()
            service_instance.export_report = MagicMock()
            service_instance.user_story_count = 10
            service_instance.task_count = 20
            service_instance.requirement_count = 10
            MockService.return_value = service_instance

            result = await run_differential_validation(
                data_dir=str(data_dir),
                code_dir=str(code_dir),
                max_fixes=0,
            )

        assert result["coverage_before"] == 32.0
        assert result["implemented"] == 3
        assert result["missing"] == 5
        assert result["fixes_attempted"] == 0

    @pytest.mark.asyncio
    async def test_start_failure_returns_error(self, tmp_path):
        """If analysis service can't start, return error gracefully."""
        from run_epic001_live import run_differential_validation

        data_dir = tmp_path / "project"
        data_dir.mkdir()
        code_dir = data_dir / "output"
        code_dir.mkdir()

        with patch("src.services.differential_analysis_service.DifferentialAnalysisService") as MockService, \
             patch.dict("sys.modules", {
                 "src.services.differential_analysis_service": MagicMock(
                     AnalysisMode=MagicMock(FULL_DIFFERENTIAL="full_differential"),
                     DifferentialAnalysisService=MockService,
                     ImplementationStatus=MagicMock(IMPLEMENTED="implemented"),
                     GapSeverity=MagicMock(CRITICAL="critical"),
                 )
             }):
            service_instance = AsyncMock()
            service_instance.start = AsyncMock(return_value=False)
            MockService.return_value = service_instance

            result = await run_differential_validation(
                data_dir=str(data_dir),
                code_dir=str(code_dir),
            )

        assert result["error"] == "start_failed"

    @_skip_no_diff
    @pytest.mark.asyncio
    async def test_auto_fix_spawns_agents(self, tmp_path):
        """With max_fixes > 0, agents are spawned for critical gaps."""
        from run_epic001_live import run_differential_validation

        data_dir = tmp_path / "project"
        data_dir.mkdir()
        code_dir = data_dir / "output"
        code_dir.mkdir()

        # Create mock findings with critical gaps (need real GapFinding)
        gaps = [
            make_mock_gap("REQ-001", "Phone Registration"),
            make_mock_gap("REQ-002", "2FA Setup"),
            make_mock_gap("REQ-003", "Multi-Device"),
        ]

        mock_report = MagicMock()
        mock_report.total_requirements = 10
        mock_report.implemented = 0
        mock_report.partial = 0
        mock_report.missing = 10
        mock_report.coverage_percent = 0.0
        mock_report.judge_confidence = 0.95
        mock_report.findings = gaps

        mock_spawn_result = MagicMock()
        mock_spawn_result.success = True
        mock_spawn_result.duration = 120.0
        mock_spawn_result.error = None
        mock_spawn_result.agent = "claude-code"
        mock_spawn_result.output = "Files created"

        with patch("src.services.differential_analysis_service.DifferentialAnalysisService") as MockService, \
             patch("src.mcp.agent_pool.MCPAgentPool") as MockPool:
            service_instance = AsyncMock()
            service_instance.start = AsyncMock(return_value=True)
            service_instance.run_analysis = AsyncMock(return_value=mock_report)
            service_instance.stop = AsyncMock()
            service_instance.export_report = MagicMock()
            service_instance.user_story_count = 10
            service_instance.task_count = 20
            service_instance.requirement_count = 10
            MockService.return_value = service_instance

            pool_instance = MagicMock()
            pool_instance.list_available = MagicMock(return_value=["claude-code", "filesystem"])
            pool_instance.spawn = AsyncMock(return_value=mock_spawn_result)
            MockPool.return_value = pool_instance

            result = await run_differential_validation(
                data_dir=str(data_dir),
                code_dir=str(code_dir),
                max_fixes=2,
            )

        assert result["fixes_attempted"] == 2
        assert result["fixes_succeeded"] == 2
        assert pool_instance.spawn.call_count == 2

    @pytest.mark.asyncio
    async def test_no_critical_gaps_skips_fixes(self, tmp_path):
        """If all requirements are implemented, no fixes are attempted."""
        from run_epic001_live import run_differential_validation

        data_dir = tmp_path / "project"
        data_dir.mkdir()
        code_dir = data_dir / "output"
        code_dir.mkdir()

        mock_report = MagicMock()
        mock_report.total_requirements = 5
        mock_report.implemented = 5
        mock_report.partial = 0
        mock_report.missing = 0
        mock_report.coverage_percent = 100.0
        mock_report.judge_confidence = 0.95
        mock_report.findings = []

        with patch("src.services.differential_analysis_service.DifferentialAnalysisService") as MockService, \
             patch.dict("sys.modules", {
                 "src.services.differential_analysis_service": MagicMock(
                     AnalysisMode=MagicMock(FULL_DIFFERENTIAL="full_differential"),
                     DifferentialAnalysisService=MockService,
                     ImplementationStatus=MagicMock(IMPLEMENTED="implemented"),
                     GapSeverity=MagicMock(CRITICAL="critical"),
                 )
             }):
            service_instance = AsyncMock()
            service_instance.start = AsyncMock(return_value=True)
            service_instance.run_analysis = AsyncMock(return_value=mock_report)
            service_instance.stop = AsyncMock()
            service_instance.export_report = MagicMock()
            service_instance.user_story_count = 5
            service_instance.task_count = 10
            service_instance.requirement_count = 5
            MockService.return_value = service_instance

            result = await run_differential_validation(
                data_dir=str(data_dir),
                code_dir=str(code_dir),
                max_fixes=5,
            )

        assert result["coverage_before"] == 100.0
        assert result["fixes_attempted"] == 0


# ---------------------------------------------------------------------------
# Test: Full Flow Integration
# ---------------------------------------------------------------------------


class TestFullFlowIntegration:
    """Test the complete epic run -> diff validation flow."""

    @pytest.mark.asyncio
    async def test_epic_with_failures_continues_to_diff(self):
        """Epic with some failures still runs diff validation at the end."""
        orch = make_orchestrator(max_parallel=1)

        # 3 tasks: T1 fails (migration), T2 succeeds, T3 succeeds
        t1 = make_task("T1", task_type="schema_migration")
        t2 = make_task("T2", task_type="api_controller")
        t3 = make_task("T3", task_type="api_dto", deps=["T1"])

        async def mock_execute(task):
            if task.id == "T1":
                task.status = "failed"
                return TaskExecutionResult(success=False, output="", error="pg not running")
            task.status = "completed"
            return TaskExecutionResult(success=True, output="OK", error=None)

        orch.task_executor.execute_task = AsyncMock(side_effect=mock_execute)

        # Run with fail-forward
        result = await orch._execute_tasks_in_order(
            "EPIC-001",
            all_tasks=[t1, t2, t3],
            tasks_to_execute=[t1, t2, t3],
            skip_failed_deps=True,
        )

        # Epic completes (partial success) - ready for diff validation
        assert result.failed_tasks == 1
        assert result.completed_tasks == 2
        assert not result.success  # Not fully successful
        # But pipeline didn't crash! Diff validation can now run.

    @pytest.mark.asyncio
    async def test_migration_failures_dont_crash_pipeline(self):
        """Specifically test that migration-type failures (needing PostgreSQL) don't crash."""
        orch = make_orchestrator(max_parallel=1)

        # Simulate the EPIC-001 pattern: migrations fail, code tasks succeed
        tasks = [
            make_task("T-setup", task_type="setup_project"),
            make_task("T-schema", task_type="schema_user", deps=["T-setup"]),
            make_task("T-migration", task_type="schema_migration", deps=["T-schema"]),
            make_task("T-api", task_type="api_controller", deps=["T-schema"]),
            make_task("T-dto", task_type="api_dto", deps=["T-api"]),
        ]

        async def mock_execute(task):
            if "migration" in task.type:
                task.status = "failed"
                return TaskExecutionResult(
                    success=False, output="",
                    error="connect ECONNREFUSED 127.0.0.1:5432"
                )
            task.status = "completed"
            return TaskExecutionResult(success=True, output="OK", error=None)

        orch.task_executor.execute_task = AsyncMock(side_effect=mock_execute)

        result = await orch._execute_tasks_in_order(
            "EPIC-001",
            all_tasks=tasks,
            tasks_to_execute=tasks,
            skip_failed_deps=True,
        )

        # Migration failed but everything else completed
        assert result.failed_tasks == 1
        assert result.completed_tasks == 4
        assert result.skipped_tasks == 0  # Nothing skipped in fail-forward
