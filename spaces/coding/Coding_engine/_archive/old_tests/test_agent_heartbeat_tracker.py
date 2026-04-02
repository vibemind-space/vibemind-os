"""Test agent heartbeat tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_heartbeat_tracker import AgentHeartbeatTracker


def test_register_agent():
    ht = AgentHeartbeatTracker()
    tid = ht.register_agent("agent-1", interval_seconds=30.0)
    assert len(tid) > 0
    assert tid.startswith("aht-")
    print("OK: register agent")


def test_record_heartbeat():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1")
    assert ht.record_heartbeat("agent-1") is True
    assert ht.record_heartbeat("nonexistent") is False
    print("OK: record heartbeat")


def test_is_responsive():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1", interval_seconds=3600.0)
    ht.record_heartbeat("agent-1")
    assert ht.is_responsive("agent-1") is True
    print("OK: is responsive")


def test_get_last_heartbeat():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1")
    ht.record_heartbeat("agent-1")
    last = ht.get_last_heartbeat("agent-1")
    assert last is not None
    assert last > 0
    assert ht.get_last_heartbeat("nonexistent") is None
    print("OK: get last heartbeat")


def test_get_responsive_agents():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1", interval_seconds=3600.0)
    ht.register_agent("agent-2", interval_seconds=3600.0)
    ht.record_heartbeat("agent-1")
    ht.record_heartbeat("agent-2")
    responsive = ht.get_responsive_agents()
    assert "agent-1" in responsive
    assert "agent-2" in responsive
    print("OK: get responsive agents")


def test_list_agents():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1")
    ht.register_agent("agent-2")
    agents = ht.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    ht = AgentHeartbeatTracker()
    fired = []
    ht.on_change("mon", lambda a, d: fired.append(a))
    ht.register_agent("agent-1")
    assert len(fired) >= 1
    assert ht.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1")
    stats = ht.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ht = AgentHeartbeatTracker()
    ht.register_agent("agent-1")
    ht.reset()
    assert ht.get_agent_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Heartbeat Tracker Tests ===\n")
    test_register_agent()
    test_record_heartbeat()
    test_is_responsive()
    test_get_last_heartbeat()
    test_get_responsive_agents()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
