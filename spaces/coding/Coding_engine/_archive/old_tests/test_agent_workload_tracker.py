"""Test agent workload tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_workload_tracker import AgentWorkloadTracker


def test_assign_task():
    wt = AgentWorkloadTracker()
    tid = wt.assign_task("agent-1", "build")
    assert len(tid) > 0
    assert tid.startswith("awt-")
    print("OK: assign task")


def test_complete_task():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    assert wt.complete_task("agent-1", "build") is True
    assert wt.complete_task("agent-1", "nonexistent") is False
    print("OK: complete task")


def test_get_active_tasks():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    wt.assign_task("agent-1", "test")
    active = wt.get_active_tasks("agent-1")
    assert len(active) == 2
    print("OK: get active tasks")


def test_get_utilization():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    wt.assign_task("agent-1", "test")
    util = wt.get_utilization("agent-1", capacity=10)
    assert abs(util - 0.2) < 0.01
    print("OK: get utilization")


def test_get_completed_count():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    wt.complete_task("agent-1", "build")
    wt.assign_task("agent-1", "test")
    wt.complete_task("agent-1", "test")
    assert wt.get_completed_count("agent-1") == 2
    print("OK: get completed count")


def test_list_agents():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    wt.assign_task("agent-2", "test")
    agents = wt.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    wt = AgentWorkloadTracker()
    fired = []
    wt.on_change("mon", lambda a, d: fired.append(a))
    wt.assign_task("agent-1", "build")
    assert len(fired) >= 1
    assert wt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    stats = wt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    wt = AgentWorkloadTracker()
    wt.assign_task("agent-1", "build")
    wt.reset()
    assert wt.get_task_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Workload Tracker Tests ===\n")
    test_assign_task()
    test_complete_task()
    test_get_active_tasks()
    test_get_utilization()
    test_get_completed_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
