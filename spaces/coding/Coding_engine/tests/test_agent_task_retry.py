"""Tests for AgentTaskRetry service."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_retry import AgentTaskRetry


def test_register_policy_returns_id():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1")
    assert pid.startswith("atr-")
    assert len(pid) > 4


def test_register_policy_stores_fields():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1", max_retries=5, backoff="exponential", metadata={"k": "v"})
    p = mgr.get_policy(pid)
    assert p["policy_id"] == pid
    assert p["task_id"] == "task-1"
    assert p["max_retries"] == 5
    assert p["backoff"] == "exponential"
    assert p["metadata"] == {"k": "v"}
    assert p["attempts"] == []
    assert p["total_attempts"] == 0
    assert isinstance(p["created_at"], float)


def test_register_policy_default_values():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1")
    p = mgr.get_policy(pid)
    assert p["max_retries"] == 3
    assert p["backoff"] == "fixed"
    assert p["metadata"] == {}


def test_register_policy_invalid_backoff_defaults_to_fixed():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1", backoff="unknown")
    p = mgr.get_policy(pid)
    assert p["backoff"] == "fixed"


def test_register_policy_empty_task_id():
    mgr = AgentTaskRetry()
    assert mgr.register_policy("") == ""


def test_register_policy_negative_max_retries():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1", max_retries=-1)
    p = mgr.get_policy(pid)
    assert p["max_retries"] == 0


def test_record_attempt_success():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1")
    assert mgr.record_attempt(pid, success=True) is True
    p = mgr.get_policy(pid)
    assert p["total_attempts"] == 1
    assert p["successful_attempts"] == 1
    assert p["failed_attempts"] == 0


def test_record_attempt_failure():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1")
    assert mgr.record_attempt(pid, success=False, error="timeout") is True
    p = mgr.get_policy(pid)
    assert p["total_attempts"] == 1
    assert p["failed_attempts"] == 1
    assert p["attempts"][0]["error"] == "timeout"
    assert p["attempts"][0]["success"] is False


def test_record_attempt_unknown_policy():
    mgr = AgentTaskRetry()
    assert mgr.record_attempt("nonexistent") is False


def test_record_attempt_empty_policy_id():
    mgr = AgentTaskRetry()
    assert mgr.record_attempt("") is False


def test_get_policy_none_for_missing():
    mgr = AgentTaskRetry()
    assert mgr.get_policy("nope") is None
    assert mgr.get_policy("") is None


def test_get_policies_newest_first():
    mgr = AgentTaskRetry()
    p1 = mgr.register_policy("task-1")
    p2 = mgr.register_policy("task-1")
    policies = mgr.get_policies("task-1")
    assert policies[0]["policy_id"] == p2
    assert policies[1]["policy_id"] == p1


def test_get_policies_filter_by_task_id():
    mgr = AgentTaskRetry()
    mgr.register_policy("task-1")
    mgr.register_policy("task-2")
    mgr.register_policy("task-1")
    assert len(mgr.get_policies("task-1")) == 2
    assert len(mgr.get_policies("task-2")) == 1


def test_get_policies_limit():
    mgr = AgentTaskRetry()
    for _ in range(10):
        mgr.register_policy("task-1")
    assert len(mgr.get_policies(limit=5)) == 5


def test_get_policies_all():
    mgr = AgentTaskRetry()
    mgr.register_policy("task-1")
    mgr.register_policy("task-2")
    assert len(mgr.get_policies()) == 2


def test_should_retry_true():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1", max_retries=3)
    mgr.record_attempt(pid, success=False, error="err")
    assert mgr.should_retry(pid) is True


def test_should_retry_false_exhausted():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1", max_retries=2)
    mgr.record_attempt(pid, success=False, error="err")
    mgr.record_attempt(pid, success=False, error="err")
    assert mgr.should_retry(pid) is False


def test_should_retry_false_after_success():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1", max_retries=5)
    mgr.record_attempt(pid, success=True)
    assert mgr.should_retry(pid) is False


def test_should_retry_unknown_policy():
    mgr = AgentTaskRetry()
    assert mgr.should_retry("nonexistent") is False


def test_get_policy_count_all():
    mgr = AgentTaskRetry()
    mgr.register_policy("task-1")
    mgr.register_policy("task-2")
    assert mgr.get_policy_count() == 2


def test_get_policy_count_filtered():
    mgr = AgentTaskRetry()
    mgr.register_policy("task-1")
    mgr.register_policy("task-2")
    mgr.register_policy("task-1")
    assert mgr.get_policy_count("task-1") == 2
    assert mgr.get_policy_count("task-2") == 1


def test_get_stats_empty():
    mgr = AgentTaskRetry()
    stats = mgr.get_stats()
    assert stats["total_policies"] == 0
    assert stats["total_attempts"] == 0
    assert stats["success_rate"] == 0.0


def test_get_stats_with_data():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1")
    mgr.record_attempt(pid, success=True)
    mgr.record_attempt(pid, success=False, error="err")
    stats = mgr.get_stats()
    assert stats["total_policies"] == 1
    assert stats["total_attempts"] == 2
    assert stats["success_rate"] == 0.5


def test_reset_clears_state():
    mgr = AgentTaskRetry()
    mgr.register_policy("task-1")
    mgr.register_policy("task-2")
    mgr.reset()
    assert mgr.get_policy_count() == 0
    assert mgr.get_stats()["total_policies"] == 0


def test_on_change_property():
    mgr = AgentTaskRetry()
    assert mgr.on_change is None
    events = []
    mgr.on_change = lambda a, d: events.append((a, d))
    mgr.register_policy("task-1")
    assert len(events) == 1
    assert events[0][0] == "policy_registered"


def test_on_change_fires_on_attempt():
    mgr = AgentTaskRetry()
    events = []
    mgr.on_change = lambda a, d: events.append((a, d))
    pid = mgr.register_policy("task-1")
    mgr.record_attempt(pid, success=True)
    assert any(e[0] == "attempt_recorded" for e in events)


def test_remove_callback():
    mgr = AgentTaskRetry()
    mgr._callbacks["cb1"] = lambda a, d: None
    assert mgr.remove_callback("cb1") is True
    assert mgr.remove_callback("cb1") is False


def test_fire_silent_exceptions():
    mgr = AgentTaskRetry()

    def bad_cb(a, d):
        raise RuntimeError("boom")

    mgr.on_change = bad_cb
    # Should not raise
    pid = mgr.register_policy("task-1")
    assert pid != ""


def test_unique_ids():
    mgr = AgentTaskRetry()
    ids = set()
    for _ in range(100):
        pid = mgr.register_policy("task-1")
        ids.add(pid)
    assert len(ids) == 100


def test_record_attempt_increments_attempt_number():
    mgr = AgentTaskRetry()
    pid = mgr.register_policy("task-1")
    mgr.record_attempt(pid, success=False, error="e1")
    mgr.record_attempt(pid, success=False, error="e2")
    mgr.record_attempt(pid, success=True)
    p = mgr.get_policy(pid)
    assert p["attempts"][0]["attempt_number"] == 1
    assert p["attempts"][1]["attempt_number"] == 2
    assert p["attempts"][2]["attempt_number"] == 3
