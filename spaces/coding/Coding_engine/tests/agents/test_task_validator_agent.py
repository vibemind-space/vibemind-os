# -*- coding: utf-8 -*-
"""
Tests for TaskValidatorAgent - Phase 14.

Verifies:
- Subscribes to EPIC_EXECUTION_COMPLETED
- should_act() logic (failed_tasks > 0)
- act() calls TaskValidator.run_fix_loop()
- Publishes EPIC_TASK_COMPLETED per fixed task
- Publishes TASK_VALIDATION_COMPLETE summary
- _find_task_file() resolves correctly
- Guard against concurrent runs
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from src.agents.task_validator_agent import TaskValidatorAgent
from src.mind.event_bus import EventType, Event


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def shared_state():
    state = MagicMock()
    state.get_metrics = MagicMock(return_value=MagicMock())
    state.context_bridge = None
    state.tech_stack = {}
    return state


@pytest.fixture
def agent(event_bus, shared_state, tmp_path):
    return TaskValidatorAgent(
        name="TaskValidator",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(tmp_path),
    )


def _epic_completed_event(failed_tasks: int = 3, epic_id: str = "EPIC-001") -> Event:
    """Create an EPIC_EXECUTION_COMPLETED event."""
    return Event(
        type=EventType.EPIC_EXECUTION_COMPLETED,
        source="EpicOrchestrator",
        data={
            "epic_id": epic_id,
            "result": {
                "epic_id": epic_id,
                "success": failed_tasks == 0,
                "total_tasks": 200,
                "completed_tasks": 200 - failed_tasks,
                "failed_tasks": failed_tasks,
                "skipped_tasks": 0,
                "duration_seconds": 120.0,
            },
        },
    )


# =============================================================================
# Test: Subscribed Events
# =============================================================================

class TestSubscribedEvents:
    def test_subscribes_to_epic_execution_completed(self, agent):
        assert EventType.EPIC_EXECUTION_COMPLETED in agent.subscribed_events

    def test_only_subscribes_to_one_event(self, agent):
        assert len(agent.subscribed_events) == 1


# =============================================================================
# Test: should_act
# =============================================================================

class TestShouldAct:
    @pytest.mark.asyncio
    async def test_should_act_when_failed_tasks(self, agent):
        events = [_epic_completed_event(failed_tasks=3)]
        assert await agent.should_act(events) is True

    @pytest.mark.asyncio
    async def test_should_not_act_when_no_failures(self, agent):
        events = [_epic_completed_event(failed_tasks=0)]
        assert await agent.should_act(events) is False

    @pytest.mark.asyncio
    async def test_should_not_act_when_empty_events(self, agent):
        assert await agent.should_act([]) is False

    @pytest.mark.asyncio
    async def test_should_not_act_when_already_running(self, agent):
        agent._running = True
        events = [_epic_completed_event(failed_tasks=3)]
        assert await agent.should_act(events) is False

    @pytest.mark.asyncio
    async def test_should_not_act_on_wrong_event(self, agent):
        wrong_event = Event(
            type=EventType.EPIC_TASK_COMPLETED,
            source="test",
            data={},
        )
        assert await agent.should_act([wrong_event]) is False


# =============================================================================
# Test: act
# =============================================================================

class TestAct:
    @pytest.mark.asyncio
    async def test_act_calls_fix_loop(self, agent, tmp_path):
        """act() should call TaskValidator.run_fix_loop()."""
        # Create a task file so _find_task_file works
        task_dir = Path("Data/all_services/test_project/tasks")
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "epic-001-tasks.json"
        task_file.write_text(json.dumps({
            "epic_id": "EPIC-001",
            "epic_name": "Test",
            "tasks": [],
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "progress_percent": 0,
            "run_count": 1,
            "last_run_at": "",
            "created_at": "",
            "estimated_total_minutes": 0,
        }), encoding="utf-8")

        mock_summary = {
            "before": {"failed": 3},
            "after": {"failed": 0, "completed": 200},
            "tasks_attempted": 3,
            "tasks_fixed": 3,
            "results": [
                {"task_id": "T1", "fixed": True, "iterations": 1},
                {"task_id": "T2", "fixed": True, "iterations": 2},
                {"task_id": "T3", "fixed": True, "iterations": 1},
            ],
        }

        try:
            with patch("src.tools.task_validator.TaskValidator") as MockTV:
                mock_instance = MagicMock()
                mock_instance.run_fix_loop = AsyncMock(return_value=mock_summary)
                MockTV.return_value = mock_instance

                events = [_epic_completed_event(failed_tasks=3)]
                result_event = await agent.act(events)

                # Verify fix loop was called
                mock_instance.run_fix_loop.assert_awaited_once_with(max_iterations=3)

                # Verify summary event returned
                assert result_event is not None
                assert result_event.type == EventType.TASK_VALIDATION_COMPLETE
                assert result_event.data["tasks_fixed"] == 3
                assert result_event.data["epic_id"] == "EPIC-001"
        finally:
            # Cleanup
            task_file.unlink(missing_ok=True)
            task_dir.rmdir()
            task_dir.parent.rmdir()

    @pytest.mark.asyncio
    async def test_act_publishes_per_fix_events(self, agent, event_bus):
        """act() should publish EPIC_TASK_COMPLETED for each fixed task."""
        task_dir = Path("Data/all_services/test_project2/tasks")
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "epic-001-tasks.json"
        task_file.write_text(json.dumps({
            "epic_id": "EPIC-001", "epic_name": "Test", "tasks": [],
            "total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0,
            "progress_percent": 0, "run_count": 1, "last_run_at": "",
            "created_at": "", "estimated_total_minutes": 0,
        }), encoding="utf-8")

        mock_summary = {
            "before": {"failed": 2}, "after": {"failed": 0},
            "tasks_attempted": 2, "tasks_fixed": 2,
            "results": [
                {"task_id": "T1", "fixed": True, "iterations": 1},
                {"task_id": "T2", "fixed": False, "iterations": 3},
            ],
        }

        try:
            with patch("src.tools.task_validator.TaskValidator") as MockTV:
                mock_instance = MagicMock()
                mock_instance.run_fix_loop = AsyncMock(return_value=mock_summary)
                MockTV.return_value = mock_instance

                events = [_epic_completed_event(failed_tasks=2)]
                await agent.act(events)

                # Should publish EPIC_TASK_COMPLETED for T1 (fixed) but not T2 (not fixed)
                calls = event_bus.publish.call_args_list
                epic_task_events = [
                    c for c in calls
                    if c[0][0].type == EventType.EPIC_TASK_COMPLETED
                ]
                assert len(epic_task_events) == 1
                assert epic_task_events[0][0][0].data["task_id"] == "T1"
        finally:
            task_file.unlink(missing_ok=True)
            task_dir.rmdir()
            task_dir.parent.rmdir()

    @pytest.mark.asyncio
    async def test_act_returns_none_when_no_task_file(self, agent):
        """act() should return None if task file not found."""
        events = [_epic_completed_event(failed_tasks=3, epic_id="NONEXISTENT-999")]
        result = await agent.act(events)
        assert result is None

    @pytest.mark.asyncio
    async def test_act_resets_running_flag(self, agent):
        """_running should be reset even if act() fails."""
        events = [_epic_completed_event(failed_tasks=3, epic_id="NONEXISTENT")]
        await agent.act(events)
        assert agent._running is False

    @pytest.mark.asyncio
    async def test_act_handles_exception(self, agent):
        """act() should catch exceptions and return None."""
        task_dir = Path("Data/all_services/test_project3/tasks")
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "epic-001-tasks.json"
        task_file.write_text(json.dumps({
            "epic_id": "EPIC-001", "epic_name": "Test", "tasks": [],
            "total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0,
            "progress_percent": 0, "run_count": 1, "last_run_at": "",
            "created_at": "", "estimated_total_minutes": 0,
        }), encoding="utf-8")

        try:
            with patch("src.tools.task_validator.TaskValidator") as MockTV:
                MockTV.side_effect = RuntimeError("Orchestrator down")

                events = [_epic_completed_event(failed_tasks=3)]
                result = await agent.act(events)

                assert result is None
                assert agent._running is False
        finally:
            task_file.unlink(missing_ok=True)
            task_dir.rmdir()
            task_dir.parent.rmdir()


# =============================================================================
# Test: _find_task_file
# =============================================================================

class TestFindTaskFile:
    def test_finds_existing_task_file(self, agent):
        """Should find task file in Data/all_services/*/tasks/."""
        task_dir = Path("Data/all_services/test_find_project/tasks")
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "epic-001-tasks.json"
        task_file.write_text("{}", encoding="utf-8")

        try:
            found = agent._find_task_file("EPIC-001")
            assert found is not None
            assert found.name == "epic-001-tasks.json"
        finally:
            task_file.unlink(missing_ok=True)
            task_dir.rmdir()
            task_dir.parent.rmdir()

    def test_returns_none_for_missing_epic(self, agent):
        """Should return None if no matching task file exists."""
        result = agent._find_task_file("NONEXISTENT-999")
        assert result is None


# =============================================================================
# Test: Concurrency guard
# =============================================================================

class TestConcurrencyGuard:
    @pytest.mark.asyncio
    async def test_running_flag_prevents_double_run(self, agent):
        """When _running is True, should_act returns False."""
        agent._running = True
        events = [_epic_completed_event(failed_tasks=5)]
        assert await agent.should_act(events) is False

    @pytest.mark.asyncio
    async def test_running_flag_cleared_after_act(self, agent):
        """_running should be False after act() completes."""
        events = [_epic_completed_event(failed_tasks=3, epic_id="NONEXISTENT")]
        await agent.act(events)
        assert agent._running is False


# =============================================================================
# Test: TASK_VALIDATION_COMPLETE EventType exists
# =============================================================================

class TestEventType:
    def test_task_validation_complete_exists(self):
        assert hasattr(EventType, "TASK_VALIDATION_COMPLETE")
        assert EventType.TASK_VALIDATION_COMPLETE == "task_validation_complete"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
