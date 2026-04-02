"""Tests for AgentRetryPolicy."""

import sys

sys.path.insert(0, ".")

from src.services.agent_retry_policy import AgentRetryPolicy


def test_create_policy():
    svc = AgentRetryPolicy()
    pid = svc.create_policy("agent-1", "fetch", max_retries=5, backoff_factor=3.0)
    assert pid.startswith("arp-"), f"Expected arp- prefix, got {pid}"
    assert len(svc.policies) == 1
    print("  PASSED test_create_policy")


def test_get_policy():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch", max_retries=4, backoff_factor=2.0, retryable_errors=["timeout"])
    result = svc.get_policy("agent-1", "fetch")
    assert result is not None
    assert result["max_retries"] == 4
    assert result["retryable_errors"] == ["timeout"]
    assert svc.get_policy("agent-1", "missing") is None
    print("  PASSED test_get_policy")


def test_should_retry_within_limit():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch", max_retries=3)
    assert svc.should_retry("agent-1", "fetch", 0) is True
    assert svc.should_retry("agent-1", "fetch", 1) is True
    assert svc.should_retry("agent-1", "fetch", 2) is True
    print("  PASSED test_should_retry_within_limit")


def test_should_retry_exceeded():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch", max_retries=3)
    assert svc.should_retry("agent-1", "fetch", 3) is False
    assert svc.should_retry("agent-1", "fetch", 5) is False
    assert svc.should_retry("agent-1", "nope", 0) is False
    print("  PASSED test_should_retry_exceeded")


def test_should_retry_error_filter():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch", retryable_errors=["timeout", "503"])
    assert svc.should_retry("agent-1", "fetch", 0, error_type="timeout") is True
    assert svc.should_retry("agent-1", "fetch", 0, error_type="503") is True
    assert svc.should_retry("agent-1", "fetch", 0, error_type="404") is False
    print("  PASSED test_should_retry_error_filter")


def test_get_backoff():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch", backoff_factor=2.0)
    assert svc.get_backoff("agent-1", "fetch", 0) == 1.0  # 2^0
    assert svc.get_backoff("agent-1", "fetch", 1) == 2.0  # 2^1
    assert svc.get_backoff("agent-1", "fetch", 3) == 8.0  # 2^3
    assert svc.get_backoff("agent-1", "missing", 1) == 0.0
    print("  PASSED test_get_backoff")


def test_remove_policy():
    svc = AgentRetryPolicy()
    pid = svc.create_policy("agent-1", "fetch")
    assert svc.remove_policy(pid) is True
    assert svc.remove_policy(pid) is False
    assert len(svc.policies) == 0
    print("  PASSED test_remove_policy")


def test_get_policy_count():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch")
    svc.create_policy("agent-1", "parse")
    svc.create_policy("agent-2", "fetch")
    assert svc.get_policy_count() == 3
    assert svc.get_policy_count("agent-1") == 2
    assert svc.get_policy_count("agent-2") == 1
    assert svc.get_policy_count("agent-3") == 0
    print("  PASSED test_get_policy_count")


def test_list_agents():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-b", "op1")
    svc.create_policy("agent-a", "op2")
    svc.create_policy("agent-b", "op3")
    agents = svc.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  PASSED test_list_agents")


def test_callbacks():
    svc = AgentRetryPolicy()
    events = []
    svc.on_change("cb1", lambda action, detail: events.append((action, detail)))
    svc.create_policy("agent-1", "fetch")
    assert len(events) == 1
    assert events[0][0] == "create_policy"
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False
    svc.create_policy("agent-1", "parse")
    assert len(events) == 1  # no new events after removing callback
    print("  PASSED test_callbacks")


def test_stats():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch")
    svc.should_retry("agent-1", "fetch", 0)
    svc.get_backoff("agent-1", "fetch", 0)
    stats = svc.get_stats()
    assert stats["policies_created"] == 1
    assert stats["retries_checked"] == 1
    assert stats["backoffs_computed"] == 1
    assert stats["current_policies"] == 1
    print("  PASSED test_stats")


def test_reset():
    svc = AgentRetryPolicy()
    svc.create_policy("agent-1", "fetch")
    svc.on_change("cb1", lambda a, d: None)
    svc.reset()
    assert len(svc.policies) == 0
    assert svc.get_stats()["current_callbacks"] == 0
    assert svc.get_stats()["current_policies"] == 0
    print("  PASSED test_reset")


def main():
    tests = [
        test_create_policy,
        test_get_policy,
        test_should_retry_within_limit,
        test_should_retry_exceeded,
        test_should_retry_error_filter,
        test_get_backoff,
        test_remove_policy,
        test_get_policy_count,
        test_list_agents,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
    print(f"=== ALL {len(tests)} TESTS PASSED ===")


if __name__ == "__main__":
    main()
