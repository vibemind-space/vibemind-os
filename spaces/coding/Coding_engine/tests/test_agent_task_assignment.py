"""Tests for AgentTaskAssignment."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_assignment import AgentTaskAssignment


def test_assign_task_basic():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "build-api")
    assert aid != ""
    assert aid.startswith("ata-")


def test_assign_task_with_priority_and_metadata():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "deploy", priority=1, metadata={"env": "prod"})
    entry = mgr.get_assignment(aid)
    assert entry["priority"] == 1
    assert entry["metadata"] == {"env": "prod"}
    assert entry["status"] == "assigned"


def test_assign_task_empty_agent():
    mgr = AgentTaskAssignment()
    assert mgr.assign_task("", "task-a") == ""


def test_assign_task_empty_task_name():
    mgr = AgentTaskAssignment()
    assert mgr.assign_task("agent-1", "") == ""


def test_complete_assignment():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "task-a")
    assert mgr.complete_assignment(aid, result={"ok": True}) is True
    entry = mgr.get_assignment(aid)
    assert entry["status"] == "completed"
    assert entry["completed_at"] is not None
    assert entry["result"] == {"ok": True}


def test_complete_nonexistent():
    mgr = AgentTaskAssignment()
    assert mgr.complete_assignment("ata-doesnotexist") is False


def test_complete_already_completed():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "task-a")
    mgr.complete_assignment(aid)
    assert mgr.complete_assignment(aid) is False


def test_reassign():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "task-a")
    assert mgr.reassign(aid, "agent-2") is True
    entry = mgr.get_assignment(aid)
    assert entry["agent_id"] == "agent-2"
    assert entry["reassigned"] is True


def test_reassign_nonexistent():
    mgr = AgentTaskAssignment()
    assert mgr.reassign("ata-nope", "agent-2") is False


def test_reassign_completed_fails():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "task-a")
    mgr.complete_assignment(aid)
    assert mgr.reassign(aid, "agent-2") is False


def test_reassign_empty_agent():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "task-a")
    assert mgr.reassign(aid, "") is False


def test_get_assignment_missing():
    mgr = AgentTaskAssignment()
    assert mgr.get_assignment("ata-nope") == {}


def test_get_assignments_filter():
    mgr = AgentTaskAssignment()
    mgr.assign_task("agent-1", "task-a")
    aid2 = mgr.assign_task("agent-1", "task-b")
    mgr.assign_task("agent-2", "task-c")
    mgr.complete_assignment(aid2)
    all_a1 = mgr.get_assignments("agent-1")
    assert len(all_a1) == 2
    assigned_a1 = mgr.get_assignments("agent-1", status="assigned")
    assert len(assigned_a1) == 1


def test_get_pending_assignments():
    mgr = AgentTaskAssignment()
    mgr.assign_task("agent-1", "task-a")
    aid2 = mgr.assign_task("agent-1", "task-b")
    mgr.complete_assignment(aid2)
    pending = mgr.get_pending_assignments("agent-1")
    assert len(pending) == 1
    assert pending[0]["status"] == "assigned"


def test_get_assignment_count():
    mgr = AgentTaskAssignment()
    mgr.assign_task("agent-1", "task-a")
    mgr.assign_task("agent-1", "task-b")
    mgr.assign_task("agent-2", "task-c")
    assert mgr.get_assignment_count() == 3
    assert mgr.get_assignment_count(agent_id="agent-1") == 2
    assert mgr.get_assignment_count(status="assigned") == 3


def test_get_agent_workload():
    mgr = AgentTaskAssignment()
    mgr.assign_task("agent-1", "task-a")
    mgr.assign_task("agent-1", "task-b")
    aid3 = mgr.assign_task("agent-2", "task-c")
    mgr.complete_assignment(aid3)
    workload = mgr.get_agent_workload()
    assert workload["agent-1"] == 2
    assert "agent-2" not in workload


def test_get_stats():
    mgr = AgentTaskAssignment()
    aid1 = mgr.assign_task("agent-1", "task-a")
    mgr.assign_task("agent-1", "task-b")
    mgr.complete_assignment(aid1)
    aid3 = mgr.assign_task("agent-2", "task-c")
    mgr.reassign(aid3, "agent-3")
    stats = mgr.get_stats()
    assert stats["total_assignments"] == 3
    assert stats["assigned"] == 2
    assert stats["completed"] == 1
    assert stats["reassigned"] == 1


def test_reset():
    mgr = AgentTaskAssignment()
    mgr.assign_task("agent-1", "task-a")
    mgr.reset()
    assert mgr.get_assignment_count() == 0
    assert mgr.get_agent_workload() == {}


def test_on_change_callback():
    events = []
    mgr = AgentTaskAssignment()
    mgr.on_change = lambda event, data: events.append(event)
    aid = mgr.assign_task("agent-1", "task-a")
    mgr.complete_assignment(aid)
    assert "assigned" in events
    assert "completed" in events


def test_remove_callback():
    mgr = AgentTaskAssignment()
    mgr._callbacks["cb1"] = lambda e, d: None
    assert mgr.remove_callback("cb1") is True
    assert mgr.remove_callback("cb1") is False


def test_assigned_at_and_created_at():
    mgr = AgentTaskAssignment()
    aid = mgr.assign_task("agent-1", "task-a")
    entry = mgr.get_assignment(aid)
    assert entry["assigned_at"] > 0
    assert entry["created_at"] > 0
    assert entry["completed_at"] is None


if __name__ == "__main__":
    tests = [
        test_assign_task_basic,
        test_assign_task_with_priority_and_metadata,
        test_assign_task_empty_agent,
        test_assign_task_empty_task_name,
        test_complete_assignment,
        test_complete_nonexistent,
        test_complete_already_completed,
        test_reassign,
        test_reassign_nonexistent,
        test_reassign_completed_fails,
        test_reassign_empty_agent,
        test_get_assignment_missing,
        test_get_assignments_filter,
        test_get_pending_assignments,
        test_get_assignment_count,
        test_get_agent_workload,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_assigned_at_and_created_at,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
