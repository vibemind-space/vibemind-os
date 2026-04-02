"""Test agent scheduling policy -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_scheduling_policy import AgentSchedulingPolicy


def test_create_policy():
    sp = AgentSchedulingPolicy()
    pid = sp.create_policy("agent-1", policy_type="fifo", max_concurrent=3)
    assert len(pid) > 0
    assert pid.startswith("asp-")
    print("OK: create policy")


def test_get_policy():
    sp = AgentSchedulingPolicy()
    sp.create_policy("agent-1", policy_type="priority", max_concurrent=5)
    pol = sp.get_policy("agent-1")
    assert pol is not None
    assert pol["policy_type"] == "priority"
    assert pol["max_concurrent"] == 5
    assert sp.get_policy("nonexistent") is None
    print("OK: get policy")


def test_update_policy():
    sp = AgentSchedulingPolicy()
    sp.create_policy("agent-1", policy_type="fifo", max_concurrent=2)
    assert sp.update_policy("agent-1", policy_type="round-robin", max_concurrent=4) is True
    pol = sp.get_policy("agent-1")
    assert pol["policy_type"] == "round-robin"
    assert pol["max_concurrent"] == 4
    print("OK: update policy")


def test_can_schedule():
    sp = AgentSchedulingPolicy()
    sp.create_policy("agent-1", max_concurrent=3)
    assert sp.can_schedule("agent-1", current_running=2) is True
    assert sp.can_schedule("agent-1", current_running=3) is False
    print("OK: can schedule")


def test_list_agents():
    sp = AgentSchedulingPolicy()
    sp.create_policy("agent-1")
    sp.create_policy("agent-2")
    agents = sp.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    sp = AgentSchedulingPolicy()
    fired = []
    sp.on_change("mon", lambda a, d: fired.append(a))
    sp.create_policy("agent-1")
    assert len(fired) >= 1
    assert sp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sp = AgentSchedulingPolicy()
    sp.create_policy("agent-1")
    stats = sp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sp = AgentSchedulingPolicy()
    sp.create_policy("agent-1")
    sp.reset()
    assert sp.get_policy_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Scheduling Policy Tests ===\n")
    test_create_policy()
    test_get_policy()
    test_update_policy()
    test_can_schedule()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 8 TESTS PASSED ===")


if __name__ == "__main__":
    main()
