"""Test agent lifecycle manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_lifecycle import AgentLifecycleManager, AgentState


def test_register():
    """Register an agent."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Builder", role="builder", metadata={"version": "1.0"})
    assert aid.startswith("agent-")

    agent = mgr.get_agent(aid)
    assert agent is not None
    assert agent["name"] == "Builder"
    assert agent["role"] == "builder"
    assert agent["state"] == "idle"
    assert agent["is_alive"] is True
    assert agent["metadata"]["version"] == "1.0"
    print("OK: register")


def test_unregister():
    """Unregister an agent."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Temp", groups={"team_a"})
    assert mgr.unregister(aid) is True
    assert mgr.get_agent(aid) is None
    assert mgr.unregister(aid) is False
    print("OK: unregister")


def test_find_agent():
    """Find agent by name."""
    mgr = AgentLifecycleManager()
    mgr.register("Builder")
    mgr.register("Tester")

    found = mgr.find_agent("Builder")
    assert found is not None
    assert found["name"] == "Builder"

    assert mgr.find_agent("Nonexistent") is None
    print("OK: find agent")


def test_list_agents():
    """List agents with filters."""
    mgr = AgentLifecycleManager()
    a1 = mgr.register("Builder", role="builder", groups={"team_a"})
    a2 = mgr.register("Tester", role="tester", groups={"team_a"})
    a3 = mgr.register("Deployer", role="deployer", groups={"team_b"})

    all_agents = mgr.list_agents()
    assert len(all_agents) == 3

    builders = mgr.list_agents(role="builder")
    assert len(builders) == 1
    assert builders[0]["name"] == "Builder"

    team_a = mgr.list_agents(group="team_a")
    assert len(team_a) == 2
    print("OK: list agents")


def test_set_state():
    """Set agent state."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")

    assert mgr.set_state(aid, "busy") is True
    assert mgr.get_agent(aid)["state"] == "busy"

    assert mgr.set_state(aid, "idle") is True
    assert mgr.get_agent(aid)["state"] == "idle"

    assert mgr.set_state(aid, "invalid_state") is False
    assert mgr.set_state("nonexistent", "idle") is False
    print("OK: set state")


def test_set_error():
    """Set error state."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")

    assert mgr.set_error(aid, "Out of memory") is True
    agent = mgr.get_agent(aid)
    assert agent["state"] == "error"
    assert agent["error"] == "Out of memory"
    print("OK: set error")


def test_clear_error():
    """Clear error state."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")
    mgr.set_error(aid, "OOM")

    assert mgr.clear_error(aid) is True
    agent = mgr.get_agent(aid)
    assert agent["state"] == "idle"
    assert agent["error"] == ""

    # Can't clear if not in error
    assert mgr.clear_error(aid) is False
    print("OK: clear error")


def test_heartbeat():
    """Record heartbeat."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")

    time.sleep(0.01)
    assert mgr.heartbeat(aid) is True

    agent = mgr.get_agent(aid)
    assert agent["heartbeat_age"] < 1.0
    assert agent["is_alive"] is True

    assert mgr.heartbeat("nonexistent") is False
    print("OK: heartbeat")


def test_heartbeat_with_metadata():
    """Heartbeat can update metadata."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent", metadata={"tasks": 0})

    mgr.heartbeat(aid, metadata={"tasks": 5})
    assert mgr.get_agent(aid)["metadata"]["tasks"] == 5
    print("OK: heartbeat with metadata")


def test_check_heartbeats():
    """Detect lost heartbeats."""
    mgr = AgentLifecycleManager(default_heartbeat_timeout=0.1)
    a1 = mgr.register("Active")
    a2 = mgr.register("Stale")

    time.sleep(0.15)
    mgr.heartbeat(a1)  # Keep active alive

    lost = mgr.check_heartbeats()
    assert len(lost) == 1
    assert lost[0]["agent_id"] == a2
    assert mgr.get_agent(a2)["state"] == "error"
    print("OK: check heartbeats")


def test_request_shutdown():
    """Request graceful shutdown."""
    shutdown_log = []
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent",
                        shutdown_handler=lambda aid, reason: shutdown_log.append(reason))

    assert mgr.request_shutdown(aid, reason="maintenance") is True
    assert mgr.get_agent(aid)["state"] == "stopping"
    assert shutdown_log == ["maintenance"]

    # Can't shutdown already stopped
    mgr.confirm_shutdown(aid)
    assert mgr.request_shutdown(aid) is False
    print("OK: request shutdown")


def test_confirm_shutdown():
    """Confirm shutdown."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")

    # Can't confirm if not stopping
    assert mgr.confirm_shutdown(aid) is False

    mgr.request_shutdown(aid)
    assert mgr.confirm_shutdown(aid) is True
    assert mgr.get_agent(aid)["state"] == "stopped"
    print("OK: confirm shutdown")


def test_shutdown_group():
    """Shutdown all agents in a group."""
    mgr = AgentLifecycleManager()
    mgr.register("A", groups={"workers"})
    mgr.register("B", groups={"workers"})
    mgr.register("C", groups={"managers"})

    count = mgr.shutdown_group("workers", reason="deploy")
    assert count == 2

    workers = mgr.list_agents(group="workers")
    assert all(w["state"] == "stopping" for w in workers)
    print("OK: shutdown group")


def test_groups():
    """Group management."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")

    assert mgr.add_to_group(aid, "team_a") is True
    assert mgr.add_to_group("nonexistent", "x") is False

    group = mgr.get_group("team_a")
    assert len(group) == 1

    assert mgr.remove_from_group(aid, "team_a") is True
    assert mgr.remove_from_group(aid, "team_a") is False  # Not in group

    groups = mgr.list_groups()
    assert "team_a" not in groups  # Empty now
    print("OK: groups")


def test_lifecycle_events():
    """Track lifecycle events."""
    mgr = AgentLifecycleManager()
    aid = mgr.register("Agent")
    mgr.set_state(aid, "busy")
    mgr.set_state(aid, "idle")

    events = mgr.get_events(agent_id=aid)
    assert len(events) >= 3  # registered + 2 state changes

    state_events = mgr.get_events(event_type="state_changed")
    assert len(state_events) == 2
    print("OK: lifecycle events")


def test_list_agents_by_state():
    """Filter agents by state."""
    mgr = AgentLifecycleManager()
    a1 = mgr.register("Active")
    a2 = mgr.register("Busy")
    mgr.set_state(a2, "busy")

    idle = mgr.list_agents(state="idle")
    assert len(idle) == 1
    assert idle[0]["name"] == "Active"

    busy = mgr.list_agents(state="busy")
    assert len(busy) == 1
    print("OK: list agents by state")


def test_stats():
    """Stats are accurate."""
    mgr = AgentLifecycleManager()
    a1 = mgr.register("A")
    a2 = mgr.register("B")
    mgr.set_state(a1, "busy")
    mgr.request_shutdown(a2)
    mgr.confirm_shutdown(a2)

    stats = mgr.get_stats()
    assert stats["total_registered"] == 2
    assert stats["total_stopped"] == 1
    assert stats["total_agents"] == 2
    assert stats["by_state"]["busy"] == 1
    assert stats["by_state"]["stopped"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mgr = AgentLifecycleManager()
    mgr.register("A", groups={"team"})

    mgr.reset()
    assert mgr.list_agents() == []
    assert mgr.get_events() == []
    stats = mgr.get_stats()
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Lifecycle Manager Tests ===\n")
    test_register()
    test_unregister()
    test_find_agent()
    test_list_agents()
    test_set_state()
    test_set_error()
    test_clear_error()
    test_heartbeat()
    test_heartbeat_with_metadata()
    test_check_heartbeats()
    test_request_shutdown()
    test_confirm_shutdown()
    test_shutdown_group()
    test_groups()
    test_lifecycle_events()
    test_list_agents_by_state()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
