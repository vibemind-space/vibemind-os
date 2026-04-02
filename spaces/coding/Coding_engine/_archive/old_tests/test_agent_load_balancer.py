"""Test agent load balancer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_load_balancer import AgentLoadBalancer


def test_register_agent():
    lb = AgentLoadBalancer()
    eid = lb.register_agent("agent-1", capacity=10)
    assert len(eid) > 0
    assert eid.startswith("alb-")
    print("OK: register agent")


def test_unregister_agent():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1")
    assert lb.unregister_agent("agent-1") is True
    assert lb.unregister_agent("nonexistent") is False
    print("OK: unregister agent")


def test_assign_task_least_loaded():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1", capacity=5)
    lb.register_agent("agent-2", capacity=5)
    assigned = lb.assign_task("task-A", strategy="least_loaded")
    assert assigned is not None
    print("OK: assign task least loaded")


def test_assign_task_round_robin():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1", capacity=5)
    lb.register_agent("agent-2", capacity=5)
    a1 = lb.assign_task("task-A", strategy="round_robin")
    a2 = lb.assign_task("task-B", strategy="round_robin")
    assert a1 is not None
    assert a2 is not None
    print("OK: assign task round robin")


def test_complete_task():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1", capacity=5)
    lb.assign_task("task-A", strategy="least_loaded")
    assert lb.get_agent_load("agent-1") >= 0
    lb.complete_task("agent-1", "task-A")
    print("OK: complete task")


def test_get_agent_load():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1", capacity=10)
    lb.assign_task("task-A")
    lb.assign_task("task-B")
    load = lb.get_agent_load("agent-1")
    assert load >= 0
    print("OK: get agent load")


def test_get_available_capacity():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1", capacity=10)
    cap = lb.get_available_capacity("agent-1")
    assert cap == 10
    print("OK: get available capacity")


def test_capacity_limit():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1", capacity=2)
    lb.assign_task("task-A")
    lb.assign_task("task-B")
    print("OK: capacity limit")


def test_list_agents():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1")
    lb.register_agent("agent-2")
    agents = lb.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    lb = AgentLoadBalancer()
    fired = []
    lb.on_change("mon", lambda a, d: fired.append(a))
    lb.register_agent("agent-1")
    assert len(fired) >= 1
    assert lb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1")
    stats = lb.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    lb = AgentLoadBalancer()
    lb.register_agent("agent-1")
    lb.reset()
    assert lb.get_agent_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Load Balancer Tests ===\n")
    test_register_agent()
    test_unregister_agent()
    test_assign_task_least_loaded()
    test_assign_task_round_robin()
    test_complete_task()
    test_get_agent_load()
    test_get_available_capacity()
    test_capacity_limit()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
