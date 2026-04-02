"""Tests for AgentWorkflowRetry."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_retry import AgentWorkflowRetry, AgentWorkflowRetryState


def test_register_policy_returns_id():
    r = AgentWorkflowRetry()
    pid = r.register_policy("default")
    assert isinstance(pid, str)
    assert pid.startswith("awr-")


def test_register_policy_empty_name_returns_empty():
    r = AgentWorkflowRetry()
    assert r.register_policy("") == ""


def test_register_policy_stores_fields():
    r = AgentWorkflowRetry()
    pid = r.register_policy("my_policy", max_retries=5, backoff_seconds=2.0, backoff_multiplier=3.0)
    assert pid != ""
    stats = r.get_stats()
    assert stats["total_policies"] == 1


def test_start_retry_returns_id():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    rid = r.start_retry(pid, "agent1", "build")
    assert isinstance(rid, str)
    assert rid.startswith("awr-")


def test_start_retry_invalid_policy_returns_empty():
    r = AgentWorkflowRetry()
    assert r.start_retry("bad-id", "agent1", "build") == ""


def test_start_retry_empty_agent_returns_empty():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    assert r.start_retry(pid, "", "build") == ""


def test_start_retry_creates_active_entry():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    rid = r.start_retry(pid, "agent1", "deploy")
    entry = r.get_retry(rid)
    assert entry["status"] == "active"
    assert entry["attempt"] == 0
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "deploy"
    assert entry["errors"] == []


def test_record_attempt_success():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=3)
    rid = r.start_retry(pid, "a1", "w1")
    result = r.record_attempt(rid, success=True)
    assert result["status"] == "succeeded"
    assert result["attempt"] == 1
    assert result["next_backoff_seconds"] is None


def test_record_attempt_failure_not_exhausted():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=3, backoff_seconds=1.0, backoff_multiplier=2.0)
    rid = r.start_retry(pid, "a1", "w1")
    result = r.record_attempt(rid, success=False, error="timeout")
    assert result["status"] == "active"
    assert result["attempt"] == 1
    assert result["next_backoff_seconds"] == 1.0  # 1.0 * 2.0^0


def test_record_attempt_exhausted():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=2, backoff_seconds=1.0, backoff_multiplier=2.0)
    rid = r.start_retry(pid, "a1", "w1")
    r.record_attempt(rid, success=False, error="err1")
    result = r.record_attempt(rid, success=False, error="err2")
    assert result["status"] == "exhausted"
    assert result["attempt"] == 2
    assert result["next_backoff_seconds"] is None


def test_record_attempt_backoff_multiplier():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=5, backoff_seconds=1.0, backoff_multiplier=2.0)
    rid = r.start_retry(pid, "a1", "w1")
    r1 = r.record_attempt(rid, success=False)
    r2 = r.record_attempt(rid, success=False)
    r3 = r.record_attempt(rid, success=False)
    assert r1["next_backoff_seconds"] == 1.0   # 1.0 * 2^0
    assert r2["next_backoff_seconds"] == 2.0   # 1.0 * 2^1
    assert r3["next_backoff_seconds"] == 4.0   # 1.0 * 2^2


def test_record_attempt_errors_tracked():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=5)
    rid = r.start_retry(pid, "a1", "w1")
    r.record_attempt(rid, success=False, error="e1")
    r.record_attempt(rid, success=False, error="e2")
    entry = r.get_retry(rid)
    assert entry["errors"] == ["e1", "e2"]


def test_record_attempt_invalid_retry_returns_empty():
    r = AgentWorkflowRetry()
    assert r.record_attempt("bad-id", success=True) == {}


def test_get_retry_missing_returns_empty():
    r = AgentWorkflowRetry()
    assert r.get_retry("nonexistent") == {}


def test_get_retries_by_agent():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    r.start_retry(pid, "a1", "w1")
    r.start_retry(pid, "a1", "w2")
    r.start_retry(pid, "a2", "w3")
    retries = r.get_retries("a1")
    assert len(retries) == 2


def test_get_retries_by_status():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=1)
    rid1 = r.start_retry(pid, "a1", "w1")
    rid2 = r.start_retry(pid, "a1", "w2")
    r.record_attempt(rid1, success=True)
    active = r.get_retries("a1", status="active")
    assert len(active) == 1
    assert active[0]["retry_id"] == rid2


def test_get_retry_count_all():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    r.start_retry(pid, "a1", "w1")
    r.start_retry(pid, "a2", "w2")
    assert r.get_retry_count() == 2


def test_get_retry_count_by_agent():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    r.start_retry(pid, "a1", "w1")
    r.start_retry(pid, "a1", "w2")
    r.start_retry(pid, "a2", "w3")
    assert r.get_retry_count(agent_id="a1") == 2
    assert r.get_retry_count(agent_id="a2") == 1


def test_get_retry_count_by_status():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=1)
    rid1 = r.start_retry(pid, "a1", "w1")
    r.start_retry(pid, "a1", "w2")
    r.record_attempt(rid1, success=True)
    assert r.get_retry_count(status="succeeded") == 1
    assert r.get_retry_count(status="active") == 1


def test_get_stats():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1", max_retries=1)
    pid2 = r.register_policy("p2")
    rid1 = r.start_retry(pid, "a1", "w1")
    rid2 = r.start_retry(pid, "a1", "w2")
    rid3 = r.start_retry(pid2, "a2", "w3")
    r.record_attempt(rid1, success=True)
    r.record_attempt(rid2, success=False)
    stats = r.get_stats()
    assert stats["total_policies"] == 2
    assert stats["total_retries"] == 3
    assert stats["succeeded"] == 1
    assert stats["exhausted"] == 1
    assert stats["active_retries"] == 1


def test_reset_clears_everything():
    r = AgentWorkflowRetry()
    pid = r.register_policy("p1")
    r.start_retry(pid, "a1", "w1")
    r.reset()
    stats = r.get_stats()
    assert stats["total_policies"] == 0
    assert stats["total_retries"] == 0


def test_on_change_callback():
    events = []
    r = AgentWorkflowRetry()
    r.on_change = lambda event, data: events.append(event)
    r.register_policy("p1")
    assert "policy_registered" in events


def test_remove_callback():
    r = AgentWorkflowRetry()
    r._callbacks["cb1"] = lambda e, d: None
    assert r.remove_callback("cb1") is True
    assert r.remove_callback("cb1") is False


def test_unique_ids():
    r = AgentWorkflowRetry()
    ids = set()
    for i in range(50):
        pid = r.register_policy(f"p{i}")
        ids.add(pid)
    assert len(ids) == 50


def test_dataclass_state_defaults():
    state = AgentWorkflowRetryState()
    assert state.entries == {}
    assert state._seq == 0


if __name__ == "__main__":
    tests = [
        test_register_policy_returns_id,
        test_register_policy_empty_name_returns_empty,
        test_register_policy_stores_fields,
        test_start_retry_returns_id,
        test_start_retry_invalid_policy_returns_empty,
        test_start_retry_empty_agent_returns_empty,
        test_start_retry_creates_active_entry,
        test_record_attempt_success,
        test_record_attempt_failure_not_exhausted,
        test_record_attempt_exhausted,
        test_record_attempt_backoff_multiplier,
        test_record_attempt_errors_tracked,
        test_record_attempt_invalid_retry_returns_empty,
        test_get_retry_missing_returns_empty,
        test_get_retries_by_agent,
        test_get_retries_by_status,
        test_get_retry_count_all,
        test_get_retry_count_by_agent,
        test_get_retry_count_by_status,
        test_get_stats,
        test_reset_clears_everything,
        test_on_change_callback,
        test_remove_callback,
        test_unique_ids,
        test_dataclass_state_defaults,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{passed + failed} tests passed")
