"""Tests for AgentWorkflowScheduler."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.agent_workflow_scheduler import (
    AgentWorkflowScheduler,
    AgentWorkflowSchedulerState,
)


def test_init():
    s = AgentWorkflowScheduler()
    assert s._state is not None
    assert s._callbacks == {}
    assert s._on_change is None
    assert isinstance(s._state, AgentWorkflowSchedulerState)


def test_generate_id_prefix():
    s = AgentWorkflowScheduler()
    sid = s._generate_id("test")
    assert sid.startswith("aws2-")
    assert len(sid) == 5 + 16


def test_generate_id_unique():
    s = AgentWorkflowScheduler()
    id1 = s._generate_id("test")
    id2 = s._generate_id("test")
    assert id1 != id2


def test_schedule_workflow_basic():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow("agent1", "wf1")
    assert sid.startswith("aws2-")
    entry = s.get_schedule(sid)
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "wf1"
    assert entry["status"] == "scheduled"
    assert entry["run_count"] == 0


def test_schedule_workflow_with_params():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow(
        "agent1", "wf2", interval_seconds=60, delay_seconds=10, max_runs=5, metadata={"key": "val"}
    )
    entry = s.get_schedule(sid)
    assert entry["interval_seconds"] == 60
    assert entry["delay_seconds"] == 10
    assert entry["max_runs"] == 5
    assert entry["metadata"] == {"key": "val"}
    assert entry["next_run_at"] >= entry["created_at"] + 10 - 1


def test_trigger_workflow():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow("agent1", "wf1", interval_seconds=30)
    result = s.trigger_workflow(sid)
    assert result["schedule_id"] == sid
    assert result["run_count"] == 1
    assert result["workflow_name"] == "wf1"
    entry = s.get_schedule(sid)
    assert entry["run_count"] == 1
    assert "last_run_at" in entry


def test_trigger_workflow_max_runs():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow("agent1", "wf1", max_runs=2)
    s.trigger_workflow(sid)
    result = s.trigger_workflow(sid)
    assert result["status"] == "completed"


def test_trigger_workflow_not_found():
    s = AgentWorkflowScheduler()
    try:
        s.trigger_workflow("aws2-nonexistent12345")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_get_schedule_not_found():
    s = AgentWorkflowScheduler()
    try:
        s.get_schedule("aws2-nonexistent12345")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_get_schedules():
    s = AgentWorkflowScheduler()
    s.schedule_workflow("agent1", "wf1")
    s.schedule_workflow("agent1", "wf2")
    s.schedule_workflow("agent2", "wf3")
    schedules = s.get_schedules("agent1")
    assert len(schedules) == 2
    assert all(e["agent_id"] == "agent1" for e in schedules)


def test_pause_schedule():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow("agent1", "wf1")
    assert s.pause_schedule(sid) is True
    entry = s.get_schedule(sid)
    assert entry["status"] == "paused"


def test_pause_not_found():
    s = AgentWorkflowScheduler()
    assert s.pause_schedule("aws2-doesnotexist00") is False


def test_resume_schedule():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow("agent1", "wf1")
    s.pause_schedule(sid)
    assert s.resume_schedule(sid) is True
    entry = s.get_schedule(sid)
    assert entry["status"] == "scheduled"


def test_cancel_schedule():
    s = AgentWorkflowScheduler()
    sid = s.schedule_workflow("agent1", "wf1")
    assert s.cancel_schedule(sid) is True
    entry = s.get_schedule(sid)
    assert entry["status"] == "cancelled"


def test_cancel_not_found():
    s = AgentWorkflowScheduler()
    assert s.cancel_schedule("aws2-doesnotexist00") is False


def test_get_due_workflows():
    s = AgentWorkflowScheduler()
    sid1 = s.schedule_workflow("agent1", "wf1", delay_seconds=0)
    sid2 = s.schedule_workflow("agent1", "wf2", delay_seconds=9999)
    time.sleep(0.01)
    due = s.get_due_workflows()
    due_ids = [d["schedule_id"] for d in due]
    assert sid1 in due_ids
    assert sid2 not in due_ids


def test_get_schedule_count():
    s = AgentWorkflowScheduler()
    s.schedule_workflow("agent1", "wf1")
    s.schedule_workflow("agent1", "wf2")
    s.schedule_workflow("agent2", "wf3")
    assert s.get_schedule_count() == 3
    assert s.get_schedule_count("agent1") == 2
    assert s.get_schedule_count("agent2") == 1
    assert s.get_schedule_count("agent99") == 0


def test_get_stats():
    s = AgentWorkflowScheduler()
    sid1 = s.schedule_workflow("agent1", "wf1")
    sid2 = s.schedule_workflow("agent1", "wf2")
    s.trigger_workflow(sid1)
    s.trigger_workflow(sid1)
    s.pause_schedule(sid2)
    stats = s.get_stats()
    assert stats["total_schedules"] == 2
    assert stats["total_triggers"] == 2
    assert stats["active_schedules"] == 1
    assert stats["paused_schedules"] == 1


def test_reset():
    s = AgentWorkflowScheduler()
    s.schedule_workflow("agent1", "wf1")
    s._callbacks["test"] = lambda e, d: None
    s.on_change = lambda e, d: None
    s.reset()
    assert s.get_schedule_count() == 0
    assert s._callbacks == {}
    assert s._on_change is None


def test_on_change_callback():
    events = []
    s = AgentWorkflowScheduler()
    s.on_change = lambda e, d: events.append(e)
    s.schedule_workflow("agent1", "wf1")
    assert "schedule_workflow" in events


def test_remove_callback():
    s = AgentWorkflowScheduler()
    s._callbacks["cb1"] = lambda e, d: None
    assert s.remove_callback("cb1") is True
    assert s.remove_callback("cb1") is False
    assert s.remove_callback("nonexistent") is False


def test_fire_exception_handling():
    s = AgentWorkflowScheduler()
    s.on_change = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
    s._callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(ValueError("oops"))
    # Should not raise
    sid = s.schedule_workflow("agent1", "wf1")
    assert sid.startswith("aws2-")


def test_prune():
    s = AgentWorkflowScheduler()
    s.MAX_ENTRIES = 5
    for i in range(8):
        s.schedule_workflow(f"agent{i}", f"wf{i}")
    assert len(s._state.entries) == 5


ALL_TESTS = [
    test_init,
    test_generate_id_prefix,
    test_generate_id_unique,
    test_schedule_workflow_basic,
    test_schedule_workflow_with_params,
    test_trigger_workflow,
    test_trigger_workflow_max_runs,
    test_trigger_workflow_not_found,
    test_get_schedule_not_found,
    test_get_schedules,
    test_pause_schedule,
    test_pause_not_found,
    test_resume_schedule,
    test_cancel_schedule,
    test_cancel_not_found,
    test_get_due_workflows,
    test_get_schedule_count,
    test_get_stats,
    test_reset,
    test_on_change_callback,
    test_remove_callback,
    test_fire_exception_handling,
    test_prune,
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    for t in ALL_TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    total = passed + failed
    print(f"{passed}/{total} tests passed")
