"""Test agent resource monitor -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_resource_monitor import AgentResourceMonitor


def test_record_usage():
    rm = AgentResourceMonitor()
    sid = rm.record_usage("agent-1", "cpu", 45.5, unit="%", tags=["system"])
    assert len(sid) > 0
    print("OK: record usage")


def test_get_latest_usage():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 40.0)
    import time
    time.sleep(0.01)
    rm.record_usage("agent-1", "cpu", 60.0)
    latest = rm.get_latest_usage("agent-1", "cpu")
    assert latest is not None
    assert latest["value"] == 60.0
    print("OK: get latest usage")


def test_get_usage_history():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 40.0)
    rm.record_usage("agent-1", "cpu", 50.0)
    rm.record_usage("agent-1", "cpu", 60.0)
    history = rm.get_usage_history("agent-1", resource_type="cpu")
    assert len(history) == 3
    print("OK: get usage history")


def test_set_and_check_threshold():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 85.0)
    assert rm.set_threshold("agent-1", "cpu", 80.0) is True
    result = rm.check_threshold("agent-1", "cpu")
    assert result["exceeded"] is True
    assert result["current"] == 85.0
    assert result["max"] == 80.0
    print("OK: set and check threshold")


def test_threshold_not_exceeded():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "memory", 50.0)
    rm.set_threshold("agent-1", "memory", 80.0)
    result = rm.check_threshold("agent-1", "memory")
    assert result["exceeded"] is False
    print("OK: threshold not exceeded")


def test_agent_resource_summary():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 50.0)
    rm.record_usage("agent-1", "memory", 70.0)
    summary = rm.get_agent_resource_summary("agent-1")
    assert len(summary) > 0
    print("OK: agent resource summary")


def test_list_monitored_agents():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 50.0)
    rm.record_usage("agent-2", "cpu", 60.0)
    agents = rm.list_monitored_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list monitored agents")


def test_purge():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 50.0)
    import time
    time.sleep(0.01)
    count = rm.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    rm = AgentResourceMonitor()
    fired = []
    rm.on_change("mon", lambda a, d: fired.append(a))
    rm.record_usage("agent-1", "cpu", 50.0)
    assert len(fired) >= 1
    assert rm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 50.0)
    stats = rm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rm = AgentResourceMonitor()
    rm.record_usage("agent-1", "cpu", 50.0)
    rm.reset()
    assert rm.list_monitored_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Resource Monitor Tests ===\n")
    test_record_usage()
    test_get_latest_usage()
    test_get_usage_history()
    test_set_and_check_threshold()
    test_threshold_not_exceeded()
    test_agent_resource_summary()
    test_list_monitored_agents()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
