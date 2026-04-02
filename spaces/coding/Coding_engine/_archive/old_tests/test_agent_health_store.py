"""Test agent health store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_health_store import AgentHealthStore


def test_register_agent():
    hs = AgentHealthStore()
    result = hs.register_agent("agent-1", tags=["ml"])
    assert len(result) > 0
    assert hs.register_agent("agent-1") == ""  # dup
    print("OK: register agent")


def test_record_heartbeat():
    hs = AgentHealthStore()
    hs.register_agent("agent-1")
    assert hs.record_heartbeat("agent-1") is True
    assert hs.record_heartbeat("nonexistent") is False
    print("OK: record heartbeat")


def test_report_health():
    hs = AgentHealthStore()
    hs.register_agent("agent-1")
    assert hs.report_health("agent-1", status="healthy", details={"cpu": 45}) is True
    health = hs.get_health("agent-1")
    assert health is not None
    assert health["status"] == "healthy"
    print("OK: report health")


def test_unhealthy_agents():
    hs = AgentHealthStore()
    hs.register_agent("good")
    hs.register_agent("bad")
    hs.report_health("good", status="healthy")
    hs.report_health("bad", status="unhealthy")
    unhealthy = hs.get_unhealthy_agents()
    assert len(unhealthy) >= 1
    print("OK: unhealthy agents")


def test_system_health():
    hs = AgentHealthStore()
    hs.register_agent("a1")
    hs.register_agent("a2")
    hs.report_health("a1", status="healthy")
    hs.report_health("a2", status="healthy")
    sys_health = hs.get_system_health()
    assert sys_health["total_agents"] == 2
    assert sys_health["healthy"] == 2
    assert sys_health["health_pct"] == 100.0
    print("OK: system health")


def test_list_agents():
    hs = AgentHealthStore()
    hs.register_agent("a1", tags=["ml"])
    hs.register_agent("a2")
    assert len(hs.list_agents()) == 2
    assert len(hs.list_agents(tag="ml")) == 1
    print("OK: list agents")


def test_remove_agent():
    hs = AgentHealthStore()
    hs.register_agent("a1")
    assert hs.remove_agent("a1") is True
    assert hs.remove_agent("a1") is False
    print("OK: remove agent")


def test_callbacks():
    hs = AgentHealthStore()
    fired = []
    hs.on_change("mon", lambda a, d: fired.append(a))
    hs.register_agent("a1")
    assert len(fired) >= 1
    assert hs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    hs = AgentHealthStore()
    hs.register_agent("a1")
    stats = hs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    hs = AgentHealthStore()
    hs.register_agent("a1")
    hs.reset()
    assert hs.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Health Store Tests ===\n")
    test_register_agent()
    test_record_heartbeat()
    test_report_health()
    test_unhealthy_agents()
    test_system_health()
    test_list_agents()
    test_remove_agent()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
