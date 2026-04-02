"""Test agent delegation router."""
import sys
sys.path.insert(0, ".")

from src.services.agent_delegation_router import AgentDelegationRouter


def test_register():
    """Register and retrieve agent."""
    dr = AgentDelegationRouter()
    rid = dr.register_agent("worker1", capabilities=["coding", "testing"], tags=["core"])
    assert rid.startswith("dlg-")

    a = dr.get_agent(rid)
    assert a is not None
    assert a["agent"] == "worker1"
    assert a["capabilities"] == ["coding", "testing"]
    assert a["available"] is True

    assert dr.unregister_agent(rid) is True
    assert dr.unregister_agent(rid) is False
    print("OK: register")


def test_invalid_register():
    """Invalid registration rejected."""
    dr = AgentDelegationRouter()
    assert dr.register_agent("") == ""
    print("OK: invalid register")


def test_duplicate():
    """Duplicate agent rejected."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"])
    assert dr.register_agent("w1", capabilities=["testing"]) == ""
    print("OK: duplicate")


def test_max_agents():
    """Max agents enforced."""
    dr = AgentDelegationRouter(max_agents=2)
    dr.register_agent("a", capabilities=["c"])
    dr.register_agent("b", capabilities=["c"])
    assert dr.register_agent("c", capabilities=["c"]) == ""
    print("OK: max agents")


def test_get_by_name():
    """Get agent by name."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"])

    a = dr.get_by_name("w1")
    assert a is not None
    assert dr.get_by_name("nonexistent") is None
    print("OK: get by name")


def test_route_least_loaded():
    """Route with least_loaded strategy."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], max_concurrent=10)
    dr.register_agent("w2", capabilities=["coding"], max_concurrent=10)

    # Route first task
    agent = dr.route("task1", "coding", strategy="least_loaded")
    assert agent in ("w1", "w2")

    # Route more to w1 to make it loaded
    for i in range(5):
        dr.route(f"extra_{i}", "coding")

    # After several routes, should balance
    print("OK: route least loaded")


def test_route_priority():
    """Route with priority strategy."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], priority=1)
    dr.register_agent("w2", capabilities=["coding"], priority=10)

    agent = dr.route("task1", "coding", strategy="priority")
    assert agent == "w2"
    print("OK: route priority")


def test_route_no_match():
    """Route with no matching capability."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"])

    assert dr.route("task1", "design") is None
    assert dr.get_stats()["total_no_match"] == 1
    print("OK: route no match")


def test_route_capacity_full():
    """Route rejected when all agents at capacity."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], max_concurrent=1)

    assert dr.route("task1", "coding") == "w1"
    assert dr.route("task2", "coding") is None  # at capacity
    print("OK: route capacity full")


def test_complete_task():
    """Complete task frees capacity."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], max_concurrent=1)

    dr.route("task1", "coding")
    assert dr.route("task2", "coding") is None

    assert dr.complete_task("w1") is True
    assert dr.route("task2", "coding") == "w1"

    a = dr.get_by_name("w1")
    assert a["total_completed"] == 1
    print("OK: complete task")


def test_fail_task():
    """Fail task frees capacity."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], max_concurrent=1)

    dr.route("task1", "coding")
    assert dr.fail_task("w1") is True

    a = dr.get_by_name("w1")
    assert a["total_failed"] == 1
    assert a["current_load"] == 0
    print("OK: fail task")


def test_enable_disable():
    """Enable/disable agent."""
    dr = AgentDelegationRouter()
    rid = dr.register_agent("w1", capabilities=["coding"])

    assert dr.disable_agent(rid) is True
    assert dr.disable_agent(rid) is False  # already disabled
    assert dr.route("task1", "coding") is None  # disabled

    assert dr.enable_agent(rid) is True
    assert dr.enable_agent(rid) is False  # already enabled
    assert dr.route("task1", "coding") == "w1"
    print("OK: enable disable")


def test_get_available():
    """Get available agents."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], max_concurrent=1)
    dr.register_agent("w2", capabilities=["coding"], max_concurrent=10)

    dr.route("task1", "coding")  # fills w1 if chosen, or w2

    avail = dr.get_available_agents(capability="coding")
    # at least one should be available
    assert len(avail) >= 1
    print("OK: get available")


def test_list_agents():
    """List agents with filters."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"], tags=["core"])
    dr.register_agent("w2", capabilities=["testing"])

    all_a = dr.list_agents()
    assert len(all_a) == 2

    by_cap = dr.list_agents(capability="coding")
    assert len(by_cap) == 1

    by_tag = dr.list_agents(tag="core")
    assert len(by_tag) == 1
    print("OK: list agents")


def test_history():
    """Routing history."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding", "testing"])

    dr.route("task1", "coding")
    dr.route("task2", "testing")

    hist = dr.get_history()
    assert len(hist) == 2

    by_agent = dr.get_history(agent="w1")
    assert len(by_agent) == 2

    by_cap = dr.get_history(capability="coding")
    assert len(by_cap) == 1

    limited = dr.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    dr = AgentDelegationRouter()
    fired = []
    dr.on_change("mon", lambda a, d: fired.append(a))

    dr.register_agent("w1", capabilities=["coding"])
    assert "agent_registered" in fired

    dr.route("task1", "coding")
    assert "task_routed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    dr = AgentDelegationRouter()
    assert dr.on_change("mon", lambda a, d: None) is True
    assert dr.on_change("mon", lambda a, d: None) is False
    assert dr.remove_callback("mon") is True
    assert dr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"])
    dr.route("task1", "coding")
    dr.route("task2", "nonexistent")  # no match

    stats = dr.get_stats()
    assert stats["current_agents"] == 1
    assert stats["total_registered"] == 1
    assert stats["total_routed"] == 1
    assert stats["total_no_match"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dr = AgentDelegationRouter()
    dr.register_agent("w1", capabilities=["coding"])

    dr.reset()
    assert dr.list_agents() == []
    stats = dr.get_stats()
    assert stats["current_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Delegation Router Tests ===\n")
    test_register()
    test_invalid_register()
    test_duplicate()
    test_max_agents()
    test_get_by_name()
    test_route_least_loaded()
    test_route_priority()
    test_route_no_match()
    test_route_capacity_full()
    test_complete_task()
    test_fail_task()
    test_enable_disable()
    test_get_available()
    test_list_agents()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
