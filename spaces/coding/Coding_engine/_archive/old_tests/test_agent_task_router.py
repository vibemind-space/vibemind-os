"""Test agent task router -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_router import AgentTaskRouter


def test_add_route():
    tr = AgentTaskRouter()
    rid = tr.add_route("build", "agent-1", priority=5)
    assert len(rid) > 0
    assert rid.startswith("atr-")
    print("OK: add route")


def test_remove_route():
    tr = AgentTaskRouter()
    rid = tr.add_route("build", "agent-1")
    assert tr.remove_route(rid) is True
    assert tr.remove_route("nonexistent") is False
    print("OK: remove route")


def test_route_task():
    tr = AgentTaskRouter()
    tr.add_route("build", "agent-1", priority=5)
    tr.add_route("build", "agent-2", priority=10)
    best = tr.route_task("build")
    assert best == "agent-2"  # higher priority
    print("OK: route task")


def test_route_task_not_found():
    tr = AgentTaskRouter()
    assert tr.route_task("unknown-type") is None
    print("OK: route task not found")


def test_get_routes_for_type():
    tr = AgentTaskRouter()
    tr.add_route("test", "agent-1")
    tr.add_route("test", "agent-2")
    routes = tr.get_routes_for_type("test")
    assert len(routes) == 2
    print("OK: get routes for type")


def test_get_routes_for_agent():
    tr = AgentTaskRouter()
    tr.add_route("build", "agent-1")
    tr.add_route("test", "agent-1")
    routes = tr.get_routes_for_agent("agent-1")
    assert len(routes) == 2
    print("OK: get routes for agent")


def test_list_task_types():
    tr = AgentTaskRouter()
    tr.add_route("build", "agent-1")
    tr.add_route("test", "agent-2")
    types = tr.list_task_types()
    assert "build" in types
    assert "test" in types
    print("OK: list task types")


def test_callbacks():
    tr = AgentTaskRouter()
    fired = []
    tr.on_change("mon", lambda a, d: fired.append(a))
    tr.add_route("build", "agent-1")
    assert len(fired) >= 1
    assert tr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    tr = AgentTaskRouter()
    tr.add_route("build", "agent-1")
    stats = tr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    tr = AgentTaskRouter()
    tr.add_route("build", "agent-1")
    tr.reset()
    assert tr.get_route_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Task Router Tests ===\n")
    test_add_route()
    test_remove_route()
    test_route_task()
    test_route_task_not_found()
    test_get_routes_for_type()
    test_get_routes_for_agent()
    test_list_task_types()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
