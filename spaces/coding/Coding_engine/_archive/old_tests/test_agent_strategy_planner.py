"""Test agent strategy planner."""
import sys
sys.path.insert(0, ".")

from src.services.agent_strategy_planner import AgentStrategyPlanner


def test_create_strategy():
    """Create and retrieve strategy."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("Deploy v2", agent="orchestrator",
                              goals=["deploy", "verify"], tags=["sprint1"])
    assert sid.startswith("str-")

    s = sp.get_strategy(sid)
    assert s is not None
    assert s["name"] == "Deploy v2"
    assert s["agent"] == "orchestrator"
    assert s["status"] == "draft"
    assert s["goals"] == ["deploy", "verify"]
    assert s["steps"] == []

    assert sp.remove_strategy(sid) is True
    assert sp.remove_strategy(sid) is False
    print("OK: create strategy")


def test_invalid_strategy():
    """Invalid strategy rejected."""
    sp = AgentStrategyPlanner()
    assert sp.create_strategy("") == ""
    print("OK: invalid strategy")


def test_duplicate_name():
    """Duplicate name rejected."""
    sp = AgentStrategyPlanner()
    sp.create_strategy("deploy")
    assert sp.create_strategy("deploy") == ""
    print("OK: duplicate name")


def test_max_strategies():
    """Max strategies enforced."""
    sp = AgentStrategyPlanner(max_strategies=2)
    sp.create_strategy("a")
    sp.create_strategy("b")
    assert sp.create_strategy("c") == ""
    print("OK: max strategies")


def test_activate():
    """Activate strategy."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    assert sp.activate_strategy(sid) is True
    assert sp.get_strategy(sid)["status"] == "active"
    assert sp.activate_strategy(sid) is False  # not draft anymore
    print("OK: activate")


def test_cancel():
    """Cancel strategy."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    assert sp.cancel_strategy(sid) is True
    assert sp.get_strategy(sid)["status"] == "cancelled"
    assert sp.cancel_strategy(sid) is False
    print("OK: cancel")


def test_add_step():
    """Add and retrieve steps."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")

    s1 = sp.add_step(sid, "Build", description="Build the app")
    assert s1.startswith("stp-")

    step = sp.get_step(s1)
    assert step is not None
    assert step["name"] == "Build"
    assert step["status"] == "pending"
    assert step["order"] == 0

    s2 = sp.add_step(sid, "Deploy")
    step2 = sp.get_step(s2)
    assert step2["order"] == 1
    print("OK: add step")


def test_invalid_step():
    """Invalid step rejected."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    assert sp.add_step(sid, "") == ""
    assert sp.add_step("nonexistent", "step") == ""
    assert sp.add_step(sid, "step", depends_on=["nonexistent"]) == ""
    print("OK: invalid step")


def test_step_lifecycle():
    """Step start, complete lifecycle."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.activate_strategy(sid)
    s1 = sp.add_step(sid, "Build")

    assert sp.start_step(s1) is True
    assert sp.get_step(s1)["status"] == "running"
    assert sp.get_strategy(sid)["status"] == "executing"

    assert sp.complete_step(s1, result="success") is True
    assert sp.get_step(s1)["status"] == "completed"
    assert sp.get_step(s1)["result"] == "success"
    assert sp.get_strategy(sid)["status"] == "completed"
    print("OK: step lifecycle")


def test_step_fail():
    """Step failure marks strategy as failed."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.activate_strategy(sid)
    s1 = sp.add_step(sid, "Build")

    sp.start_step(s1)
    assert sp.fail_step(s1, result="error") is True
    assert sp.get_step(s1)["status"] == "failed"
    assert sp.get_strategy(sid)["status"] == "failed"
    print("OK: step fail")


def test_step_skip():
    """Skip step."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.activate_strategy(sid)
    s1 = sp.add_step(sid, "Optional")

    assert sp.skip_step(s1) is True
    assert sp.get_step(s1)["status"] == "skipped"
    assert sp.get_strategy(sid)["status"] == "completed"
    print("OK: step skip")


def test_step_dependencies():
    """Steps with dependencies."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.activate_strategy(sid)
    s1 = sp.add_step(sid, "Build")
    s2 = sp.add_step(sid, "Deploy", depends_on=[s1])

    # Can't start s2 before s1 is done
    assert sp.start_step(s2) is False

    sp.start_step(s1)
    sp.complete_step(s1)

    # Now s2 can start
    assert sp.start_step(s2) is True
    print("OK: step dependencies")


def test_get_next_steps():
    """Get next executable steps."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.activate_strategy(sid)
    s1 = sp.add_step(sid, "Build")
    s2 = sp.add_step(sid, "Test", depends_on=[s1])
    s3 = sp.add_step(sid, "Lint")  # no deps, parallel with s1

    next_steps = sp.get_next_steps(sid)
    names = [s["name"] for s in next_steps]
    assert "Build" in names
    assert "Lint" in names
    assert "Test" not in names
    print("OK: get next steps")


def test_get_strategy_steps():
    """Get all steps for strategy."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.add_step(sid, "a")
    sp.add_step(sid, "b")

    steps = sp.get_strategy_steps(sid)
    assert len(steps) == 2
    print("OK: get strategy steps")


def test_get_by_name():
    """Get strategy by name."""
    sp = AgentStrategyPlanner()
    sp.create_strategy("my_strategy")

    s = sp.get_strategy_by_name("my_strategy")
    assert s is not None
    assert s["name"] == "my_strategy"
    assert sp.get_strategy_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_strategies():
    """List strategies with filters."""
    sp = AgentStrategyPlanner()
    sp.create_strategy("a", agent="agent_a", tags=["t1"])
    sid2 = sp.create_strategy("b", agent="agent_b")
    sp.activate_strategy(sid2)

    all_s = sp.list_strategies()
    assert len(all_s) == 2

    by_agent = sp.list_strategies(agent="agent_a")
    assert len(by_agent) == 1

    by_status = sp.list_strategies(status="active")
    assert len(by_status) == 1

    by_tag = sp.list_strategies(tag="t1")
    assert len(by_tag) == 1
    print("OK: list strategies")


def test_remove_cascades():
    """Remove strategy cascades to steps."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    s1 = sp.add_step(sid, "step1")

    sp.remove_strategy(sid)
    assert sp.get_step(s1) is None
    print("OK: remove cascades")


def test_callback():
    """Callback fires on events."""
    sp = AgentStrategyPlanner()
    fired = []
    sp.on_change("mon", lambda a, d: fired.append(a))

    sid = sp.create_strategy("test")
    assert "strategy_created" in fired

    sp.activate_strategy(sid)
    assert "strategy_activated" in fired

    s1 = sp.add_step(sid, "step")
    assert "step_added" in fired

    sp.start_step(s1)
    assert "step_started" in fired

    sp.complete_step(s1)
    assert "step_completed" in fired
    assert "strategy_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    sp = AgentStrategyPlanner()
    assert sp.on_change("mon", lambda a, d: None) is True
    assert sp.on_change("mon", lambda a, d: None) is False
    assert sp.remove_callback("mon") is True
    assert sp.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.activate_strategy(sid)
    s1 = sp.add_step(sid, "step")
    sp.start_step(s1)
    sp.complete_step(s1)

    stats = sp.get_stats()
    assert stats["total_strategies"] == 1
    assert stats["total_steps"] == 1
    assert stats["total_completed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sp = AgentStrategyPlanner()
    sid = sp.create_strategy("test")
    sp.add_step(sid, "step")

    sp.reset()
    assert sp.list_strategies() == []
    stats = sp.get_stats()
    assert stats["current_strategies"] == 0
    assert stats["current_steps"] == 0
    print("OK: reset")


def main():
    print("=== Agent Strategy Planner Tests ===\n")
    test_create_strategy()
    test_invalid_strategy()
    test_duplicate_name()
    test_max_strategies()
    test_activate()
    test_cancel()
    test_add_step()
    test_invalid_step()
    test_step_lifecycle()
    test_step_fail()
    test_step_skip()
    test_step_dependencies()
    test_get_next_steps()
    test_get_strategy_steps()
    test_get_by_name()
    test_list_strategies()
    test_remove_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
