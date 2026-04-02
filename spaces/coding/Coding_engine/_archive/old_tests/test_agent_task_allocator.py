"""Test agent task allocator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_allocator import AgentTaskAllocator


def test_register_agent():
    ta = AgentTaskAllocator()
    result = ta.register_agent("agent-1", capacity=10, tags=["ml"])
    assert len(result) > 0
    assert ta.register_agent("agent-1") == ""  # dup
    print("OK: register agent")


def test_allocate():
    ta = AgentTaskAllocator()
    ta.register_agent("agent-1", capacity=5)
    aid = ta.allocate("task-1", agent_id="agent-1", priority=8)
    assert len(aid) > 0
    a = ta.get_assignment(aid)
    assert a is not None
    assert a["task_id"] == "task-1"
    print("OK: allocate")


def test_auto_allocate():
    ta = AgentTaskAllocator()
    ta.register_agent("a1", capacity=5)
    ta.register_agent("a2", capacity=5)
    ta.allocate("t1", agent_id="a1")
    ta.allocate("t2", agent_id="a1")
    # a2 has 0 tasks, a1 has 2 -- auto should pick a2
    aid = ta.allocate("t3")
    a = ta.get_assignment(aid)
    assert a["agent_id"] == "a2"
    print("OK: auto allocate")


def test_complete_task():
    ta = AgentTaskAllocator()
    ta.register_agent("a1", capacity=5)
    aid = ta.allocate("t1", agent_id="a1")
    assert ta.complete_task(aid) is True
    assert ta.complete_task(aid) is False  # already completed
    print("OK: complete task")


def test_agent_workload():
    ta = AgentTaskAllocator()
    ta.register_agent("a1", capacity=10)
    ta.allocate("t1", agent_id="a1")
    ta.allocate("t2", agent_id="a1")
    wl = ta.get_agent_workload("a1")
    assert wl["active_tasks"] == 2
    assert wl["capacity"] == 10
    assert wl["utilization"] > 0
    print("OK: agent workload")


def test_least_loaded():
    ta = AgentTaskAllocator()
    ta.register_agent("busy", capacity=5)
    ta.register_agent("idle", capacity=5)
    ta.allocate("t1", agent_id="busy")
    ta.allocate("t2", agent_id="busy")
    ll = ta.get_least_loaded()
    assert ll is not None
    assert ll["agent_id"] == "idle"
    print("OK: least loaded")


def test_list_assignments():
    ta = AgentTaskAllocator()
    ta.register_agent("a1")
    ta.allocate("t1", agent_id="a1")
    ta.allocate("t2", agent_id="a1")
    assignments = ta.list_assignments(agent_id="a1")
    assert len(assignments) == 2
    print("OK: list assignments")


def test_list_agents():
    ta = AgentTaskAllocator()
    ta.register_agent("a1", tags=["ml"])
    ta.register_agent("a2")
    assert len(ta.list_agents()) == 2
    assert len(ta.list_agents(tag="ml")) == 1
    print("OK: list agents")


def test_remove_agent():
    ta = AgentTaskAllocator()
    ta.register_agent("a1")
    assert ta.remove_agent("a1") is True
    assert ta.remove_agent("a1") is False
    print("OK: remove agent")


def test_callbacks():
    ta = AgentTaskAllocator()
    fired = []
    ta.on_change("mon", lambda a, d: fired.append(a))
    ta.register_agent("a1")
    assert len(fired) >= 1
    assert ta.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ta = AgentTaskAllocator()
    ta.register_agent("a1")
    stats = ta.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ta = AgentTaskAllocator()
    ta.register_agent("a1")
    ta.reset()
    assert ta.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Task Allocator Tests ===\n")
    test_register_agent()
    test_allocate()
    test_auto_allocate()
    test_complete_task()
    test_agent_workload()
    test_least_loaded()
    test_list_assignments()
    test_list_agents()
    test_remove_agent()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
