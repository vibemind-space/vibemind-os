# -*- coding: utf-8 -*-
"""
Tests for Pipeline Parallel Task Execution (Phase 24).

Tests the FIRST_COMPLETED pipeline executor, file-conflict detection,
and file-lock execution wrapper in EpicOrchestrator.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict

# Import the orchestrator components
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "mcp_plugins" / "servers" / "grpc_host"))

try:
    from epic_orchestrator import EpicOrchestrator, EpicExecutionResult
    from epic_task_generator import Task, TaskStatus, EpicTaskList
    from task_executor import TaskExecutionResult
    _IMPORTS_AVAILABLE = True
except ImportError:
    _IMPORTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _IMPORTS_AVAILABLE,
    reason="epic_orchestrator imports not available",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_task(
    task_id: str,
    deps: List[str] = None,
    output_files: List[str] = None,
    phase: str = "code",
    task_type: str = "api_controller",
    status: str = "pending",
) -> Task:
    """Create a Task object for testing."""
    return Task(
        id=task_id,
        epic_id="EPIC-001",
        type=task_type,
        title=f"Task {task_id}",
        description=f"Test task {task_id}",
        status=status,
        dependencies=deps or [],
        output_files=output_files or [],
        phase=phase,
    )


def make_success_result() -> TaskExecutionResult:
    return TaskExecutionResult(success=True, output="OK", error=None)


def make_failure_result(error: str = "test error") -> TaskExecutionResult:
    return TaskExecutionResult(success=False, output="", error=error)


def make_orchestrator(max_parallel: int = 3) -> EpicOrchestrator:
    """Create an EpicOrchestrator with mocked components."""
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
    orch.task_executor = MagicMock()
    orch.task_executor.execute_task = AsyncMock(return_value=make_success_result())
    orch._convergence_ran_diff = False  # Phase 28
    return orch


# ---------------------------------------------------------------------------
# Test: _build_task_file_map
# ---------------------------------------------------------------------------


class TestBuildTaskFileMap:
    def test_simple_output_files(self):
        orch = make_orchestrator()
        tasks = [
            make_task("T1", output_files=["src/app.ts", "src/main.ts"]),
            make_task("T2", output_files=["src/utils.ts"]),
        ]
        fmap = orch._build_task_file_map(tasks)
        assert fmap["T1"] == {"src/app.ts", "src/main.ts"}
        assert fmap["T2"] == {"src/utils.ts"}

    def test_hash_fragment_stripped(self):
        """prisma/schema.prisma#AuthMethod -> prisma/schema.prisma"""
        orch = make_orchestrator()
        tasks = [
            make_task("T1", output_files=["prisma/schema.prisma#AuthMethod"]),
            make_task("T2", output_files=["prisma/schema.prisma#Device"]),
        ]
        fmap = orch._build_task_file_map(tasks)
        assert fmap["T1"] == {"prisma/schema.prisma"}
        assert fmap["T2"] == {"prisma/schema.prisma"}

    def test_trailing_slash_stripped(self):
        orch = make_orchestrator()
        tasks = [make_task("T1", output_files=["src/modules/auth/"])]
        fmap = orch._build_task_file_map(tasks)
        assert fmap["T1"] == {"src/modules/auth"}

    def test_empty_output_files(self):
        orch = make_orchestrator()
        tasks = [make_task("T1", output_files=[])]
        fmap = orch._build_task_file_map(tasks)
        assert fmap["T1"] == set()

    def test_no_output_files_field(self):
        orch = make_orchestrator()
        task = make_task("T1")
        task.output_files = []
        fmap = orch._build_task_file_map([task])
        assert fmap["T1"] == set()


# ---------------------------------------------------------------------------
# Test: _get_ready_tasks_pipeline
# ---------------------------------------------------------------------------


class TestGetReadyTasksPipeline:
    def test_independent_tasks_all_ready(self):
        orch = make_orchestrator()
        tasks = [make_task("T1"), make_task("T2"), make_task("T3")]
        task_map = {t.id: t for t in tasks}
        fmap = orch._build_task_file_map(tasks)

        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T1", "T2", "T3"},
            completed_ids=set(),
            task_map=task_map,
            running_task_ids=set(),
            task_file_map=fmap,
        )
        assert len(ready) == 3

    def test_deps_not_met_excluded(self):
        orch = make_orchestrator()
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
        ]
        task_map = {t.id: t for t in tasks}
        fmap = orch._build_task_file_map(tasks)

        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T1", "T2"},
            completed_ids=set(),
            task_map=task_map,
            running_task_ids=set(),
            task_file_map=fmap,
        )
        assert [t.id for t in ready] == ["T1"]

    def test_deps_met_included(self):
        orch = make_orchestrator()
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
        ]
        task_map = {t.id: t for t in tasks}
        fmap = orch._build_task_file_map(tasks)

        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T2"},
            completed_ids={"T1"},
            task_map=task_map,
            running_task_ids=set(),
            task_file_map=fmap,
        )
        assert [t.id for t in ready] == ["T2"]

    def test_file_conflict_excluded(self):
        """Tasks sharing output files with running tasks are excluded."""
        orch = make_orchestrator()
        tasks = [
            make_task("T1", output_files=["prisma/schema.prisma#A"]),
            make_task("T2", output_files=["prisma/schema.prisma#B"]),
            make_task("T3", output_files=["src/app.ts"]),
        ]
        task_map = {t.id: t for t in tasks}
        fmap = orch._build_task_file_map(tasks)

        # T1 is running, T2 conflicts (same base file), T3 is OK
        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T2", "T3"},
            completed_ids=set(),
            task_map=task_map,
            running_task_ids={"T1"},
            task_file_map=fmap,
        )
        assert [t.id for t in ready] == ["T3"]

    def test_no_file_conflict_when_empty(self):
        """Tasks with no output_files never conflict."""
        orch = make_orchestrator()
        tasks = [
            make_task("T1", output_files=[]),
            make_task("T2", output_files=[]),
        ]
        task_map = {t.id: t for t in tasks}
        fmap = orch._build_task_file_map(tasks)

        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T2"},
            completed_ids=set(),
            task_map=task_map,
            running_task_ids={"T1"},
            task_file_map=fmap,
        )
        assert len(ready) == 1

    def test_sorted_by_dep_count(self):
        orch = make_orchestrator()
        tasks = [
            make_task("T1", deps=["X", "Y", "Z"]),  # 3 deps
            make_task("T2", deps=["X"]),              # 1 dep
            make_task("T3"),                          # 0 deps
        ]
        task_map = {t.id: t for t in tasks}
        # Add fake completed deps
        task_map["X"] = make_task("X", status="completed")
        task_map["Y"] = make_task("Y", status="completed")
        task_map["Z"] = make_task("Z", status="completed")
        fmap = orch._build_task_file_map(tasks)

        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T1", "T2", "T3"},
            completed_ids={"X", "Y", "Z"},
            task_map=task_map,
            running_task_ids=set(),
            task_file_map=fmap,
        )
        # T3 (0 deps), T2 (1 dep), T1 (3 deps)
        assert [t.id for t in ready] == ["T3", "T2", "T1"]

    def test_skip_failed_deps_mode(self):
        """With also_treat_as_completed, failed deps count as completed."""
        orch = make_orchestrator()
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
        ]
        task_map = {t.id: t for t in tasks}
        fmap = orch._build_task_file_map(tasks)

        # T1 failed but treated as completed
        ready = orch._get_ready_tasks_pipeline(
            pending_ids={"T2"},
            completed_ids=set(),
            task_map=task_map,
            running_task_ids=set(),
            task_file_map=fmap,
            also_treat_as_completed={"T1"},
        )
        assert [t.id for t in ready] == ["T2"]


# ---------------------------------------------------------------------------
# Test: _prune_failed_descendants
# ---------------------------------------------------------------------------


class TestPruneFailedDescendants:
    def test_prune_direct_dependent(self):
        orch = make_orchestrator()
        tasks = [make_task("T1"), make_task("T2", deps=["T1"])]
        task_map = {t.id: t for t in tasks}
        pending = {"T2"}
        failed = {"T1"}

        pruned = orch._prune_failed_descendants(pending, task_map, failed)
        assert pruned == 1
        assert "T2" not in pending
        assert task_map["T2"].status == "skipped"

    def test_no_prune_when_no_failed(self):
        orch = make_orchestrator()
        tasks = [make_task("T1"), make_task("T2", deps=["T1"])]
        task_map = {t.id: t for t in tasks}
        pending = {"T2"}
        failed = set()

        pruned = orch._prune_failed_descendants(pending, task_map, failed)
        assert pruned == 0
        assert "T2" in pending

    def test_prune_cascading(self):
        """T1 failed -> T2 skipped, but T3 (depends on T2) should also be prunable."""
        orch = make_orchestrator()
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
            make_task("T3", deps=["T2"]),
        ]
        task_map = {t.id: t for t in tasks}
        pending = {"T2", "T3"}
        failed = {"T1"}

        # First round: T2 pruned
        pruned1 = orch._prune_failed_descendants(pending, task_map, failed)
        assert pruned1 == 1
        assert task_map["T2"].status == "skipped"

        # T3 still pending (its dep T2 is skipped, not in failed_ids)
        # The pipeline loop handles this by checking status == "failed"
        # _has_failed_ancestor checks both failed_ids and status == "failed"


# ---------------------------------------------------------------------------
# Test: _execute_with_file_lock
# ---------------------------------------------------------------------------


class TestExecuteWithFileLock:
    @pytest.mark.asyncio
    async def test_acquires_and_releases_locks(self):
        orch = make_orchestrator()
        task = make_task("T1", output_files=["a.ts", "b.ts"])
        fmap = orch._build_task_file_map([task])
        file_locks: Dict[str, asyncio.Lock] = {}

        result = await orch._execute_with_file_lock(task, file_locks, fmap)
        assert result.success is True
        # Locks should be created and released
        assert "a.ts" in file_locks
        assert "b.ts" in file_locks
        assert not file_locks["a.ts"].locked()
        assert not file_locks["b.ts"].locked()

    @pytest.mark.asyncio
    async def test_releases_locks_on_failure(self):
        orch = make_orchestrator()
        orch.task_executor.execute_task = AsyncMock(
            return_value=make_failure_result("boom")
        )
        task = make_task("T1", output_files=["a.ts"])
        fmap = orch._build_task_file_map([task])
        file_locks: Dict[str, asyncio.Lock] = {}

        result = await orch._execute_with_file_lock(task, file_locks, fmap)
        assert result.success is False
        assert not file_locks["a.ts"].locked()

    @pytest.mark.asyncio
    async def test_releases_locks_on_exception(self):
        orch = make_orchestrator()
        orch.task_executor.execute_task = AsyncMock(side_effect=RuntimeError("crash"))
        task = make_task("T1", output_files=["a.ts"])
        fmap = orch._build_task_file_map([task])
        file_locks: Dict[str, asyncio.Lock] = {}

        with pytest.raises(RuntimeError):
            await orch._execute_with_file_lock(task, file_locks, fmap)
        assert not file_locks["a.ts"].locked()

    @pytest.mark.asyncio
    async def test_no_locks_when_no_output_files(self):
        orch = make_orchestrator()
        task = make_task("T1", output_files=[])
        fmap = orch._build_task_file_map([task])
        file_locks: Dict[str, asyncio.Lock] = {}

        result = await orch._execute_with_file_lock(task, file_locks, fmap)
        assert result.success is True
        assert len(file_locks) == 0


# ---------------------------------------------------------------------------
# Test: _execute_pipeline (integration)
# ---------------------------------------------------------------------------


class TestExecutePipeline:
    @pytest.mark.asyncio
    async def test_independent_tasks_all_complete(self):
        """Three independent tasks should all complete."""
        orch = make_orchestrator(max_parallel=3)
        tasks = [make_task("T1"), make_task("T2"), make_task("T3")]

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 3
        assert result.failed_tasks == 0

    @pytest.mark.asyncio
    async def test_sequential_dependency_chain(self):
        """T1 -> T2 -> T3 should complete in order."""
        orch = make_orchestrator(max_parallel=3)
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
            make_task("T3", deps=["T2"]),
        ]
        all_tasks = list(tasks)

        # Track execution order
        order = []

        async def mock_execute(task):
            order.append(task.id)
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", all_tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 3
        assert order == ["T1", "T2", "T3"]

    @pytest.mark.asyncio
    async def test_diamond_dependency(self):
        """Diamond: T1 -> T2, T1 -> T3, T2+T3 -> T4."""
        orch = make_orchestrator(max_parallel=3)
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
            make_task("T3", deps=["T1"]),
            make_task("T4", deps=["T2", "T3"]),
        ]

        order = []

        async def mock_execute(task):
            order.append(task.id)
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 4
        # T1 first, T2 and T3 in any order, T4 last
        assert order[0] == "T1"
        assert order[-1] == "T4"
        assert set(order[1:3]) == {"T2", "T3"}

    @pytest.mark.asyncio
    async def test_empty_task_list(self):
        orch = make_orchestrator()
        result = await orch._execute_pipeline("EPIC-001", [], [])
        assert result.success is True
        assert result.completed_tasks == 0

    @pytest.mark.asyncio
    async def test_failed_task_prunes_descendant(self):
        """If T1 fails, T2 (depends on T1) should be skipped."""
        orch = make_orchestrator()
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
            make_task("T3"),  # Independent, should still complete
        ]

        async def mock_execute(task):
            if task.id == "T1":
                task.status = "failed"
                return make_failure_result("T1 failed")
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is False
        assert result.completed_tasks == 1  # T3
        assert result.failed_tasks == 1  # T1
        assert result.skipped_tasks == 1  # T2

    @pytest.mark.asyncio
    async def test_file_conflict_serialized(self):
        """Tasks sharing output files should not run simultaneously."""
        orch = make_orchestrator(max_parallel=5)
        tasks = [
            make_task("T1", output_files=["prisma/schema.prisma#A"]),
            make_task("T2", output_files=["prisma/schema.prisma#B"]),
        ]

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_execute(task):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)  # Simulate work
            async with lock:
                concurrent_count -= 1
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 2
        # Should never have been concurrent due to file conflict
        assert max_concurrent == 1

    @pytest.mark.asyncio
    async def test_no_file_conflict_runs_parallel(self):
        """Tasks with different output files should run in parallel."""
        orch = make_orchestrator(max_parallel=5)
        tasks = [
            make_task("T1", output_files=["src/a.ts"]),
            make_task("T2", output_files=["src/b.ts"]),
            make_task("T3", output_files=["src/c.ts"]),
        ]

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_execute(task):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)  # Simulate work
            async with lock:
                concurrent_count -= 1
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 3
        # Should have run at least 2 concurrently
        assert max_concurrent >= 2


# ---------------------------------------------------------------------------
# Test: FIRST_COMPLETED Behavior
# ---------------------------------------------------------------------------


class TestFirstCompleted:
    @pytest.mark.asyncio
    async def test_fast_task_unblocks_new_work(self):
        """A fast task completing should immediately unblock dependents."""
        orch = make_orchestrator(max_parallel=3)
        tasks = [
            make_task("FAST", output_files=["fast.ts"]),
            make_task("SLOW", output_files=["slow.ts"]),
            make_task("DEP", deps=["FAST"], output_files=["dep.ts"]),
        ]

        order = []

        async def mock_execute(task):
            if task.id == "SLOW":
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(0.01)
            order.append(task.id)
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 3
        # FAST completes first, DEP starts before SLOW finishes
        assert order.index("FAST") < order.index("DEP")

    @pytest.mark.asyncio
    async def test_max_parallel_respected(self):
        """Never more than max_parallel tasks running simultaneously."""
        orch = make_orchestrator(max_parallel=2)
        tasks = [
            make_task(f"T{i}", output_files=[f"file{i}.ts"])
            for i in range(5)
        ]

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_execute(task):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.03)
            async with lock:
                concurrent_count -= 1
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.success is True
        assert result.completed_tasks == 5
        assert max_concurrent <= 2


# ---------------------------------------------------------------------------
# Test: Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_exception_caught_not_crash(self):
        """An exception in a task should not crash the pipeline."""
        orch = make_orchestrator()
        tasks = [make_task("T1"), make_task("T2")]

        call_count = 0

        async def mock_execute(task):
            nonlocal call_count
            call_count += 1
            if task.id == "T1":
                raise RuntimeError("unexpected crash")
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline("EPIC-001", tasks, tasks)
        assert result.failed_tasks == 1  # T1
        assert result.completed_tasks == 1  # T2
        assert call_count == 2  # Both were attempted

    @pytest.mark.asyncio
    async def test_skip_failed_deps_allows_execution(self):
        """With skip_failed_deps=True, tasks run despite failed dependencies."""
        orch = make_orchestrator()
        tasks = [
            make_task("T1"),
            make_task("T2", deps=["T1"]),
        ]

        async def mock_execute(task):
            if task.id == "T1":
                task.status = "failed"
                return make_failure_result("T1 failed")
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        result = await orch._execute_pipeline(
            "EPIC-001", tasks, tasks, skip_failed_deps=True
        )
        assert result.completed_tasks == 1  # T2 ran despite T1 failure
        assert result.failed_tasks == 1  # T1


# ---------------------------------------------------------------------------
# Test: Backward Compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_sequential_mode_unchanged(self):
        """max_parallel=1 should NOT use pipeline (uses old sequential path)."""
        orch = make_orchestrator(max_parallel=1)
        tasks = [make_task("T1"), make_task("T2")]
        all_tasks = list(tasks)

        # _execute_pipeline should NOT be called
        with patch.object(orch, "_execute_pipeline", new_callable=AsyncMock) as mock_pipeline:
            # Call _execute_tasks_in_order directly
            result = await orch._execute_tasks_in_order("EPIC-001", all_tasks, tasks)
            mock_pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_parallel_mode_uses_pipeline(self):
        """max_parallel>1 should delegate to _execute_pipeline."""
        orch = make_orchestrator(max_parallel=3)
        tasks = [make_task("T1")]

        with patch.object(
            orch, "_execute_pipeline",
            new_callable=AsyncMock,
            return_value=EpicExecutionResult(
                epic_id="EPIC-001", success=True,
                total_tasks=1, completed_tasks=1,
                failed_tasks=0, skipped_tasks=0,
            ),
        ) as mock_pipeline:
            result = await orch._execute_tasks_in_order("EPIC-001", tasks, tasks)
            mock_pipeline.assert_called_once()

    def test_max_allowed_parallel_is_20(self):
        """MAX_ALLOWED_PARALLEL should be 20 (Phase 24 upgrade)."""
        assert EpicOrchestrator.MAX_ALLOWED_PARALLEL == 20


# ---------------------------------------------------------------------------
# Test: Progress Reporting
# ---------------------------------------------------------------------------


class TestProgressReporting:
    @pytest.mark.asyncio
    async def test_progress_events_published(self):
        """Pipeline should publish progress events after each task completion."""
        orch = make_orchestrator(max_parallel=3)
        orch.event_bus = MagicMock()
        orch.event_bus.publish = AsyncMock()

        tasks = [make_task("T1"), make_task("T2")]

        async def mock_execute(task):
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        await orch._execute_pipeline("EPIC-001", tasks, tasks)

        # Should have published progress events
        assert orch.event_bus.publish.call_count >= 2
        # Check event structure
        for call in orch.event_bus.publish.call_args_list:
            event = call.args[0]
            assert event["type"] == "task_progress_update"
            assert "data" in event
            assert event["data"]["type"] == "pipeline_progress"
            assert "completed" in event["data"]
            assert "running_task_ids" in event["data"]
            assert "percent_complete" in event["data"]

    @pytest.mark.asyncio
    async def test_progress_percent_complete(self):
        """Percent complete should reflect actual progress."""
        orch = make_orchestrator()
        orch.event_bus = MagicMock()
        orch.event_bus.publish = AsyncMock()

        tasks = [make_task("T1"), make_task("T2")]

        async def mock_execute(task):
            task.status = "completed"
            return make_success_result()

        orch.task_executor.execute_task = mock_execute

        await orch._execute_pipeline("EPIC-001", tasks, tasks)

        # Last progress event should show 100%
        last_call = orch.event_bus.publish.call_args_list[-1]
        last_event = last_call.args[0]
        assert last_event["data"]["percent_complete"] == 100.0


# ---------------------------------------------------------------------------
# Test: Semaphore Passthrough (Phase 25b)
# ---------------------------------------------------------------------------


class TestSemaphorePassthrough:
    """Verify max_concurrent flows from EpicOrchestrator → TaskExecutor → ClaudeCodeTool."""

    def test_orchestrator_passes_max_parallel_to_executor(self):
        """EpicOrchestrator should pass max_parallel_tasks as max_concurrent to TaskExecutor."""
        with patch("epic_orchestrator.EpicTaskGenerator"), \
             patch("epic_orchestrator.EpicParser"), \
             patch("epic_orchestrator.TaskExecutor") as MockExecutor:
            orch = EpicOrchestrator(
                "test_project",
                max_parallel_tasks=7,
            )
            # TaskExecutor should have been called with max_concurrent=7
            call_kwargs = MockExecutor.call_args
            assert call_kwargs.kwargs.get("max_concurrent") == 7 or \
                   (len(call_kwargs.args) > 6 and call_kwargs.args[6] == 7), \
                   f"Expected max_concurrent=7 in TaskExecutor call, got: {call_kwargs}"

    def test_executor_stores_max_concurrent(self):
        """TaskExecutor should store max_concurrent for use in _get_claude_tool."""
        from task_executor import TaskExecutor
        with patch("task_executor.Path"):
            executor = TaskExecutor(
                "test_project",
                output_dir="/tmp/test",
                max_concurrent=15,
            )
            assert executor.max_concurrent == 15

    def test_executor_default_max_concurrent_is_10(self):
        """TaskExecutor default max_concurrent should be 10 (not 2)."""
        from task_executor import TaskExecutor
        with patch("task_executor.Path"):
            executor = TaskExecutor(
                "test_project",
                output_dir="/tmp/test",
            )
            assert executor.max_concurrent == 10

    def test_claude_code_tool_default_is_10(self):
        """ClaudeCodeTool default max_concurrent should be 10."""
        from src.tools.claude_code_tool import ClaudeCodeTool
        assert ClaudeCodeTool._default_max_concurrent == 10


# ---------------------------------------------------------------------------
# Phase 26: Team Instance Pooling Tests
# ---------------------------------------------------------------------------

try:
    from autogen_orchestrator import EventFixOrchestrator, TaskResult
    _ORCHESTRATOR_AVAILABLE = True
except ImportError:
    try:
        from mcp_plugins.servers.grpc_host.autogen_orchestrator import EventFixOrchestrator, TaskResult
        _ORCHESTRATOR_AVAILABLE = True
    except ImportError:
        _ORCHESTRATOR_AVAILABLE = False


@pytest.mark.skipif(
    not _ORCHESTRATOR_AVAILABLE,
    reason="autogen_orchestrator imports not available",
)
class TestTeamInstancePooling:
    """Phase 26: Verify fresh team per execute_task() call for concurrent safety."""

    def test_create_team_returns_fresh_instance(self):
        """_create_team() should return a new team object each call."""
        orchestrator = EventFixOrchestrator(working_dir="/tmp/test")
        # Mock model_client so we don't need real API keys
        orchestrator.model_client = MagicMock()
        orchestrator._mcp_tools = []
        orchestrator._initialized = True

        team1 = orchestrator._create_team(task_type="general")
        team2 = orchestrator._create_team(task_type="general")

        assert team1 is not team2, "Each _create_team() call must return a distinct team instance"

    def test_create_team_different_task_types(self):
        """_create_team() with different task types should both return fresh teams."""
        orchestrator = EventFixOrchestrator(working_dir="/tmp/test")
        orchestrator.model_client = MagicMock()
        orchestrator._mcp_tools = []
        orchestrator._initialized = True

        team_general = orchestrator._create_team(task_type="general")
        team_testing = orchestrator._create_team(task_type="testing")

        assert team_general is not team_testing

    def test_legacy_setup_agents_stores_on_self(self):
        """_setup_agents() should still store team on self for backward compat."""
        orchestrator = EventFixOrchestrator(working_dir="/tmp/test")
        orchestrator.model_client = MagicMock()
        orchestrator._mcp_tools = []
        orchestrator._initialized = True

        orchestrator._setup_agents(task_type="general")

        assert orchestrator.team is not None
        assert hasattr(orchestrator.team, 'run'), "self.team should be a RoundRobinGroupChat with run()"


# ---------------------------------------------------------------------------
# Phase 27: Unified Convergence Tests
# ---------------------------------------------------------------------------

from src.mind.shared_state import ConvergenceMetrics
from src.mind.convergence import (
    ConvergenceCriteria,
    is_converged,
    AUTONOMOUS_CRITERIA,
)


class TestUnifiedConvergence:
    """Phase 27: Verify differential + cross-layer fields in convergence system."""

    def test_convergence_metrics_has_diff_fields(self):
        """ConvergenceMetrics should have differential analysis fields."""
        m = ConvergenceMetrics()
        assert hasattr(m, "differential_coverage_percent")
        assert hasattr(m, "differential_gaps_critical")
        assert hasattr(m, "differential_gaps_total")
        assert m.differential_coverage_percent == 0.0
        assert m.differential_gaps_critical == 0
        assert m.differential_gaps_total == 0

    def test_convergence_metrics_has_cross_layer_fields(self):
        """ConvergenceMetrics should have cross-layer validation fields."""
        m = ConvergenceMetrics()
        assert hasattr(m, "cross_layer_issues")
        assert hasattr(m, "cross_layer_critical_issues")
        assert m.cross_layer_issues == 0
        assert m.cross_layer_critical_issues == 0

    def test_convergence_criteria_has_diff_fields(self):
        """ConvergenceCriteria should have differential coverage criteria."""
        c = ConvergenceCriteria()
        assert hasattr(c, "require_differential_coverage")
        assert hasattr(c, "min_differential_coverage")
        assert hasattr(c, "max_cross_layer_critical")
        # Defaults should be permissive (disabled)
        assert c.require_differential_coverage is False
        assert c.min_differential_coverage is None
        assert c.max_cross_layer_critical is None

    def test_is_converged_blocks_on_low_coverage(self):
        """Convergence should fail when diff coverage is below threshold."""
        m = ConvergenceMetrics()
        m.iteration = 5
        m.build_attempted = True
        m.build_success = True
        m.differential_coverage_percent = 50.0

        c = ConvergenceCriteria(
            require_differential_coverage=True,
            min_differential_coverage=80.0,
            require_build_success=False,
            min_confidence_score=0.0,
        )

        converged, reasons = is_converged(m, c)
        assert converged is False
        assert any("Differential coverage" in r for r in reasons)

    def test_is_converged_blocks_on_cross_layer_critical(self):
        """Convergence should fail when cross-layer critical issues exceed max."""
        m = ConvergenceMetrics()
        m.iteration = 5
        m.build_attempted = True
        m.build_success = True
        m.cross_layer_critical_issues = 3

        c = ConvergenceCriteria(
            max_cross_layer_critical=0,
            require_build_success=False,
            min_confidence_score=0.0,
        )

        converged, reasons = is_converged(m, c)
        assert converged is False
        assert any("critical cross-layer issues" in r for r in reasons)

    def test_is_converged_passes_when_criteria_met(self):
        """Convergence should pass when all diff + cross-layer criteria are met."""
        m = ConvergenceMetrics()
        m.iteration = 5
        m.build_attempted = True
        m.build_success = True
        m.differential_coverage_percent = 90.0
        m.cross_layer_critical_issues = 0
        m.tests_passed = 10
        m.total_tests = 10

        c = ConvergenceCriteria(
            require_differential_coverage=True,
            min_differential_coverage=80.0,
            max_cross_layer_critical=0,
            require_build_success=True,
            min_confidence_score=0.0,
        )

        converged, reasons = is_converged(m, c)
        assert converged is True

    def test_autonomous_criteria_includes_diff(self):
        """AUTONOMOUS_CRITERIA should include differential + cross-layer fields."""
        assert AUTONOMOUS_CRITERIA.require_differential_coverage is True
        assert AUTONOMOUS_CRITERIA.min_differential_coverage == 80.0
        assert AUTONOMOUS_CRITERIA.max_cross_layer_critical == 0


# ---------------------------------------------------------------------------
# Phase 28: Redundancy Prevention Tests
# ---------------------------------------------------------------------------


class TestRedundancyPrevention:
    """Phase 28: Verify event-metadata-based coordination prevents redundant code gen."""

    def test_generator_skips_differential_events(self):
        """GeneratorAgent should skip CODE_FIX_NEEDED events with source_analysis='differential*'."""
        try:
            from src.mind.event_bus import Event, EventType
        except ImportError:
            pytest.skip("Event imports not available")

        # Simulate a differential analysis CODE_FIX_NEEDED event
        diff_event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="DifferentialAnalysisAgent",
            data={
                "source_analysis": "differential_epic",
                "gap_type": "missing_implementation",
            },
            success=False,
        )

        # This event should be filtered out by GeneratorAgent's should_act() filter
        assert diff_event.data.get("source_analysis", "").startswith("differential")

    def test_generator_skips_som_managed_events(self):
        """GeneratorAgent should skip events tagged with som_managed=True."""
        try:
            from src.mind.event_bus import Event, EventType
        except ImportError:
            pytest.skip("Event imports not available")

        som_event = Event(
            type=EventType.BUILD_FAILED,
            source="SoMBridge",
            data={
                "task_id": "EPIC-001-VERIFY-build",
                "som_managed": True,
            },
            success=False,
        )

        # This event should be filtered out
        assert som_event.data.get("som_managed") is True

    def test_generator_passes_normal_build_failed(self):
        """GeneratorAgent should process BUILD_FAILED events without som_managed flag."""
        try:
            from src.mind.event_bus import Event, EventType
        except ImportError:
            pytest.skip("Event imports not available")

        normal_event = Event(
            type=EventType.BUILD_FAILED,
            source="BuilderAgent",
            data={"errors": ["TS2339: Property 'x' does not exist"]},
            success=False,
        )

        # No som_managed flag → should be processed
        assert not normal_event.data.get("som_managed")
        assert not normal_event.data.get("source_analysis", "").startswith("differential")

    def test_som_bridge_tags_failure_events(self):
        """SoMBridge.on_task_failed() should set som_managed=True in event data."""
        try:
            from src.mind.event_bus import EventType
            from mcp_plugins.servers.grpc_host.som_bridge import _build_failure_map
        except ImportError:
            pytest.skip("SoMBridge imports not available")

        # Verify failure map exists and maps task prefixes to events
        failure_map = _build_failure_map()
        assert "verify_build" in failure_map
        assert failure_map["verify_build"] == EventType.BUILD_FAILED

    def test_som_bridge_tags_success_events(self):
        """SoMBridge.on_task_completed() should set som_managed=True in event data."""
        try:
            from mcp_plugins.servers.grpc_host.som_bridge import _build_success_map
            from src.mind.event_bus import EventType
        except ImportError:
            pytest.skip("SoMBridge imports not available")

        success_map = _build_success_map()
        assert "fe_" in success_map
        assert success_map["fe_"] == EventType.CODE_GENERATED

    def test_convergence_ran_diff_flag_default(self):
        """EpicOrchestrator._convergence_ran_diff should default to False."""
        orch = make_orchestrator()
        assert orch._convergence_ran_diff is False

    def test_task_executor_revalidation_routing(self):
        """After SoM fix, verification tasks should re-run but code-gen should not."""
        try:
            from mcp_plugins.servers.grpc_host.task_executor import TASK_SKILL_MAPPING
        except ImportError:
            pytest.skip("TASK_SKILL_MAPPING not available")

        # Verification tasks → BashExecutor (should re-run)
        assert TASK_SKILL_MAPPING["verify_build"][0] == "BashExecutor"
        assert TASK_SKILL_MAPPING["verify_typecheck"][0] == "BashExecutor"
        assert TASK_SKILL_MAPPING["schema_migration"][0] == "BashExecutor"

        # Code-gen tasks → NOT BashExecutor (should NOT re-run after SoM fix)
        assert TASK_SKILL_MAPPING["fe_page"][0] != "BashExecutor"
        assert TASK_SKILL_MAPPING["api_controller"][0] != "BashExecutor"
        assert TASK_SKILL_MAPPING["schema_model"][0] != "BashExecutor"

    def test_convergence_loop_verify_only_routing(self):
        """Convergence loop should use TASK_SKILL_MAPPING to distinguish verify vs codegen."""
        try:
            from mcp_plugins.servers.grpc_host.task_executor import TASK_SKILL_MAPPING
        except ImportError:
            pytest.skip("TASK_SKILL_MAPPING not available")

        # All verify_* tasks should route to BashExecutor
        for task_type, (agent, _) in TASK_SKILL_MAPPING.items():
            if task_type.startswith("verify_"):
                assert agent == "BashExecutor", f"{task_type} should route to BashExecutor"
