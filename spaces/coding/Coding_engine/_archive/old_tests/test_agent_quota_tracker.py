"""Test agent quota tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_quota_tracker import AgentQuotaTracker


def test_set_quota():
    qt = AgentQuotaTracker()
    qid = qt.set_quota("agent-1", "api_calls", 100)
    assert len(qid) > 0
    assert qid.startswith("aqt-")
    print("OK: set quota")


def test_use_quota():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 5)
    assert qt.use_quota("agent-1", "api_calls", 3) is True
    assert qt.use_quota("agent-1", "api_calls", 2) is True
    assert qt.use_quota("agent-1", "api_calls", 1) is False  # exceeded
    print("OK: use quota")


def test_get_remaining_quota():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 10)
    qt.use_quota("agent-1", "api_calls", 3)
    assert qt.get_remaining_quota("agent-1", "api_calls") == 7
    print("OK: get remaining quota")


def test_get_usage():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 10)
    qt.use_quota("agent-1", "api_calls", 4)
    usage = qt.get_usage("agent-1", "api_calls")
    assert usage["used"] == 4
    assert usage["limit"] == 10
    assert usage["remaining"] == 6
    print("OK: get usage")


def test_reset_quota():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 5)
    qt.use_quota("agent-1", "api_calls", 5)
    assert qt.use_quota("agent-1", "api_calls") is False
    assert qt.reset_quota("agent-1", "api_calls") is True
    assert qt.use_quota("agent-1", "api_calls") is True
    assert qt.reset_quota("agent-1", "nonexistent") is False
    print("OK: reset quota")


def test_get_quota_count():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 10)
    qt.set_quota("agent-2", "storage", 100)
    assert qt.get_quota_count() == 2
    assert qt.get_quota_count("agent-1") == 1
    print("OK: get quota count")


def test_list_agents():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 10)
    qt.set_quota("agent-2", "storage", 100)
    agents = qt.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    qt = AgentQuotaTracker()
    fired = []
    qt.on_change("mon", lambda a, d: fired.append(a))
    qt.set_quota("agent-1", "api_calls", 10)
    assert len(fired) >= 1
    assert qt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 10)
    stats = qt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    qt = AgentQuotaTracker()
    qt.set_quota("agent-1", "api_calls", 10)
    qt.reset()
    assert qt.get_quota_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Quota Tracker Tests ===\n")
    test_set_quota()
    test_use_quota()
    test_get_remaining_quota()
    test_get_usage()
    test_reset_quota()
    test_get_quota_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
