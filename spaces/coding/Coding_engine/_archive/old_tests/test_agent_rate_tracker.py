"""Test agent rate tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_rate_tracker import AgentRateTracker


def test_register_agent():
    rt = AgentRateTracker()
    result = rt.register_agent("agent-1", tags=["ml"])
    assert len(result) > 0
    assert rt.register_agent("agent-1") == ""
    print("OK: register agent")


def test_record_operation():
    rt = AgentRateTracker()
    rt.register_agent("a1")
    assert rt.record_operation("a1", "api_call", success=True) is True
    assert rt.record_operation("a1", "api_call", success=False) is True
    print("OK: record operation")


def test_get_rate():
    rt = AgentRateTracker()
    rt.register_agent("a1")
    for _ in range(5):
        rt.record_operation("a1", "api_call", success=True)
    rt.record_operation("a1", "api_call", success=False)
    rate = rt.get_rate("a1", "api_call")
    assert rate["total_ops"] == 6
    assert rate["success_rate"] > 0
    print("OK: get rate")


def test_get_agent_rates():
    rt = AgentRateTracker()
    rt.register_agent("a1")
    rt.record_operation("a1", "read", success=True)
    rt.record_operation("a1", "write", success=True)
    rates = rt.get_agent_rates("a1")
    assert len(rates) >= 2
    print("OK: get agent rates")


def test_top_agents():
    rt = AgentRateTracker()
    rt.register_agent("fast")
    rt.register_agent("slow")
    for _ in range(10):
        rt.record_operation("fast", "api_call")
    for _ in range(2):
        rt.record_operation("slow", "api_call")
    top = rt.get_top_agents("api_call", limit=2)
    assert len(top) == 2
    assert top[0]["agent_id"] == "fast"
    print("OK: top agents")


def test_list_agents():
    rt = AgentRateTracker()
    rt.register_agent("a1", tags=["ml"])
    rt.register_agent("a2")
    assert len(rt.list_agents()) == 2
    assert len(rt.list_agents(tag="ml")) == 1
    print("OK: list agents")


def test_remove_agent():
    rt = AgentRateTracker()
    rt.register_agent("a1")
    assert rt.remove_agent("a1") is True
    assert rt.remove_agent("a1") is False
    print("OK: remove agent")


def test_callbacks():
    rt = AgentRateTracker()
    fired = []
    rt.on_change("mon", lambda a, d: fired.append(a))
    rt.register_agent("a1")
    assert len(fired) >= 1
    assert rt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rt = AgentRateTracker()
    rt.register_agent("a1")
    stats = rt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rt = AgentRateTracker()
    rt.register_agent("a1")
    rt.reset()
    assert rt.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Rate Tracker Tests ===\n")
    test_register_agent()
    test_record_operation()
    test_get_rate()
    test_get_agent_rates()
    test_top_agents()
    test_list_agents()
    test_remove_agent()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
