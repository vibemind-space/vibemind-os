"""Test agent heartbeat monitor -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_heartbeat_monitor import AgentHeartbeatMonitor


def test_register_agent():
    hm = AgentHeartbeatMonitor()
    eid = hm.register_agent("agent-1", timeout=30.0)
    assert len(eid) > 0
    assert eid.startswith("ahm-")
    print("OK: register agent")


def test_heartbeat():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1")
    assert hm.heartbeat("agent-1") is True
    assert hm.heartbeat("nonexistent") is False
    print("OK: heartbeat")


def test_is_alive():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1", timeout=30.0)
    hm.heartbeat("agent-1")
    assert hm.is_alive("agent-1") is True
    print("OK: is alive")


def test_get_last_heartbeat():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1")
    hm.heartbeat("agent-1")
    ts = hm.get_last_heartbeat("agent-1")
    assert ts > 0
    assert hm.get_last_heartbeat("nonexistent") == 0.0
    print("OK: get last heartbeat")


def test_get_missed_count():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1", timeout=30.0)
    hm.heartbeat("agent-1")
    missed = hm.get_missed_count("agent-1")
    assert missed >= 0
    print("OK: get missed count")


def test_get_alive_agents():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1", timeout=30.0)
    hm.register_agent("agent-2", timeout=30.0)
    hm.heartbeat("agent-1")
    hm.heartbeat("agent-2")
    alive = hm.get_alive_agents()
    assert "agent-1" in alive
    assert "agent-2" in alive
    print("OK: get alive agents")


def test_list_agents():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1")
    hm.register_agent("agent-2")
    agents = hm.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    hm = AgentHeartbeatMonitor()
    fired = []
    hm.on_change("mon", lambda a, d: fired.append(a))
    hm.register_agent("agent-1")
    assert len(fired) >= 1
    assert hm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1")
    stats = hm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    hm = AgentHeartbeatMonitor()
    hm.register_agent("agent-1")
    hm.reset()
    assert hm.get_agent_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Heartbeat Monitor Tests ===\n")
    test_register_agent()
    test_heartbeat()
    test_is_alive()
    test_get_last_heartbeat()
    test_get_missed_count()
    test_get_alive_agents()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
