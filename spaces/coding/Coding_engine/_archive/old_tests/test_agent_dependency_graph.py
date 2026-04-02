"""Test agent dependency graph -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_dependency_graph import AgentDependencyGraph


def test_add_agent():
    dg = AgentDependencyGraph()
    eid = dg.add_agent("agent-1")
    assert len(eid) > 0
    assert eid.startswith("adg-")
    print("OK: add agent")


def test_add_dependency():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    assert dg.add_dependency("agent-1", "agent-2") is True
    deps = dg.get_dependencies("agent-1")
    assert "agent-2" in deps
    print("OK: add dependency")


def test_remove_dependency():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    dg.add_dependency("agent-1", "agent-2")
    assert dg.remove_dependency("agent-1", "agent-2") is True
    assert dg.remove_dependency("agent-1", "agent-2") is False
    print("OK: remove dependency")


def test_get_dependents():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    dg.add_agent("agent-3")
    dg.add_dependency("agent-2", "agent-1")
    dg.add_dependency("agent-3", "agent-1")
    dependents = dg.get_dependents("agent-1")
    assert "agent-2" in dependents
    assert "agent-3" in dependents
    print("OK: get dependents")


def test_get_all_dependencies():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    dg.add_agent("agent-3")
    dg.add_dependency("agent-1", "agent-2")
    dg.add_dependency("agent-2", "agent-3")
    all_deps = dg.get_all_dependencies("agent-1")
    assert "agent-2" in all_deps
    assert "agent-3" in all_deps
    print("OK: get all dependencies")


def test_cycle_detection():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    dg.add_agent("agent-3")
    dg.add_dependency("agent-1", "agent-2")
    dg.add_dependency("agent-2", "agent-3")
    assert dg.add_dependency("agent-3", "agent-1") is False  # would create cycle
    assert dg.has_cycle() is False
    print("OK: cycle detection")


def test_topological_order():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    dg.add_agent("agent-3")
    dg.add_dependency("agent-1", "agent-2")
    dg.add_dependency("agent-2", "agent-3")
    order = dg.get_topological_order()
    assert len(order) == 3
    assert order.index("agent-3") < order.index("agent-2")
    assert order.index("agent-2") < order.index("agent-1")
    print("OK: topological order")


def test_remove_agent():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    dg.add_dependency("agent-1", "agent-2")
    assert dg.remove_agent("agent-2") is True
    assert dg.remove_agent("agent-2") is False
    assert dg.get_dependencies("agent-1") == []
    print("OK: remove agent")


def test_list_agents():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.add_agent("agent-2")
    agents = dg.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    dg = AgentDependencyGraph()
    fired = []
    dg.on_change("mon", lambda a, d: fired.append(a))
    dg.add_agent("agent-1")
    assert len(fired) >= 1
    assert dg.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    stats = dg.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dg = AgentDependencyGraph()
    dg.add_agent("agent-1")
    dg.reset()
    assert dg.get_agent_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Dependency Graph Tests ===\n")
    test_add_agent()
    test_add_dependency()
    test_remove_dependency()
    test_get_dependents()
    test_get_all_dependencies()
    test_cycle_detection()
    test_topological_order()
    test_remove_agent()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
