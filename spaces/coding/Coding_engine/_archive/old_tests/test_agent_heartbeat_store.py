"""Test agent heartbeat store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_heartbeat_store import AgentHeartbeatStore


def test_register():
    hb = AgentHeartbeatStore()
    eid = hb.register("agent-1", interval_seconds=30, metadata={"role": "worker"})
    assert len(eid) > 0
    assert hb.register("agent-1") == ""  # dup
    print("OK: register")


def test_beat():
    hb = AgentHeartbeatStore()
    hb.register("agent-1", interval_seconds=30)
    assert hb.beat("agent-1") is True
    assert hb.beat("nonexistent") is False
    print("OK: beat")


def test_check_alive():
    hb = AgentHeartbeatStore()
    hb.register("agent-1", interval_seconds=30)
    hb.beat("agent-1")
    assert hb.check_alive("agent-1") is True
    print("OK: check alive")


def test_check_dead():
    hb = AgentHeartbeatStore()
    hb.register("agent-1", interval_seconds=0.01)
    hb.beat("agent-1")
    import time
    time.sleep(0.02)
    assert hb.check_alive("agent-1") is False
    print("OK: check dead")


def test_get_status():
    hb = AgentHeartbeatStore()
    hb.register("agent-1", interval_seconds=30)
    hb.beat("agent-1")
    status = hb.get_status("agent-1")
    assert status is not None
    assert status["agent_id"] == "agent-1"
    print("OK: get status")


def test_get_dead_agents():
    hb = AgentHeartbeatStore()
    hb.register("agent-1", interval_seconds=0.01)
    hb.register("agent-2", interval_seconds=300)
    hb.beat("agent-1")
    hb.beat("agent-2")
    import time
    time.sleep(0.02)
    dead = hb.get_dead_agents()
    assert "agent-1" in dead
    assert "agent-2" not in dead
    print("OK: get dead agents")


def test_get_all_statuses():
    hb = AgentHeartbeatStore()
    hb.register("agent-1")
    hb.register("agent-2")
    statuses = hb.get_all_statuses()
    assert len(statuses) == 2
    print("OK: get all statuses")


def test_unregister():
    hb = AgentHeartbeatStore()
    hb.register("agent-1")
    assert hb.unregister("agent-1") is True
    assert hb.unregister("agent-1") is False
    print("OK: unregister")


def test_callbacks():
    hb = AgentHeartbeatStore()
    fired = []
    hb.on_change("mon", lambda a, d: fired.append(a))
    hb.register("agent-1")
    assert len(fired) >= 1
    assert hb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    hb = AgentHeartbeatStore()
    hb.register("agent-1")
    stats = hb.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    hb = AgentHeartbeatStore()
    hb.register("agent-1")
    hb.reset()
    assert hb.get_all_statuses() == []
    print("OK: reset")


def main():
    print("=== Agent Heartbeat Store Tests ===\n")
    test_register()
    test_beat()
    test_check_alive()
    test_check_dead()
    test_get_status()
    test_get_dead_agents()
    test_get_all_statuses()
    test_unregister()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
