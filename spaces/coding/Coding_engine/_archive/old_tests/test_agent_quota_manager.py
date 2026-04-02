"""Test agent quota manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_quota_manager import AgentQuotaManager


def test_set_quota():
    qm = AgentQuotaManager()
    qid = qm.set_quota("agent-1", "api_calls", 100, period_seconds=3600)
    assert len(qid) > 0
    print("OK: set quota")


def test_use_quota_allowed():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 100)
    result = qm.use_quota("a1", "api_calls", amount=1)
    assert result["allowed"] is True
    assert result["remaining"] == 99
    print("OK: use quota allowed")


def test_use_quota_exceeded():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 2)
    qm.use_quota("a1", "api_calls", amount=1)
    qm.use_quota("a1", "api_calls", amount=1)
    result = qm.use_quota("a1", "api_calls", amount=1)
    assert result["allowed"] is False
    assert result["remaining"] == 0
    print("OK: use quota exceeded")


def test_get_usage():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 10)
    qm.use_quota("a1", "api_calls", amount=3)
    usage = qm.get_usage("a1", "api_calls")
    assert usage["used"] == 3
    assert usage["limit"] == 10
    assert usage["remaining"] == 7
    print("OK: get usage")


def test_reset_quota():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 10)
    qm.use_quota("a1", "api_calls", amount=5)
    assert qm.reset_quota("a1", "api_calls") is True
    usage = qm.get_usage("a1", "api_calls")
    assert usage["used"] == 0
    print("OK: reset quota")


def test_list_quotas():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 100)
    qm.set_quota("a1", "storage", 1000)
    qm.set_quota("a2", "api_calls", 50)
    all_q = qm.list_quotas()
    assert len(all_q) == 3
    a1_q = qm.list_quotas(agent_id="a1")
    assert len(a1_q) == 2
    print("OK: list quotas")


def test_remove_quota():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 100)
    assert qm.remove_quota("a1", "api_calls") is True
    assert qm.remove_quota("a1", "api_calls") is False
    print("OK: remove quota")


def test_violations():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 2)
    qm.use_quota("a1", "api_calls", amount=1)
    qm.use_quota("a1", "api_calls", amount=1)
    qm.use_quota("a1", "api_calls", amount=1)  # violation
    violations = qm.get_violations()
    assert len(violations) >= 1
    print("OK: violations")


def test_callbacks():
    qm = AgentQuotaManager()
    fired = []
    qm.on_change("mon", lambda a, d: fired.append(a))
    qm.set_quota("a1", "api_calls", 100)
    assert len(fired) >= 1
    assert qm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 100)
    stats = qm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    qm = AgentQuotaManager()
    qm.set_quota("a1", "api_calls", 100)
    qm.reset()
    assert qm.list_quotas() == []
    print("OK: reset")


def main():
    print("=== Agent Quota Manager Tests ===\n")
    test_set_quota()
    test_use_quota_allowed()
    test_use_quota_exceeded()
    test_get_usage()
    test_reset_quota()
    test_list_quotas()
    test_remove_quota()
    test_violations()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
