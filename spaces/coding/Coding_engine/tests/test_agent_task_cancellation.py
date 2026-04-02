"""Tests for AgentTaskCancellation service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_cancellation import AgentTaskCancellation


def test_request_cancellation_returns_id():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "build")
    assert cid.startswith("atc-")
    assert len(cid) > 4


def test_request_cancellation_with_reason():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "build", reason="timeout")
    entry = mgr.get_cancellation(cid)
    assert entry["reason"] == "timeout"


def test_request_cancellation_empty_agent_id():
    mgr = AgentTaskCancellation()
    assert mgr.request_cancellation("", "build") == ""


def test_request_cancellation_empty_task_name():
    mgr = AgentTaskCancellation()
    assert mgr.request_cancellation("agent-1", "") == ""


def test_confirm_cancellation():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "deploy")
    assert mgr.confirm_cancellation(cid) is True
    entry = mgr.get_cancellation(cid)
    assert entry["status"] == "confirmed"
    assert entry["confirmed_at"] is not None


def test_confirm_cancellation_invalid_id():
    mgr = AgentTaskCancellation()
    assert mgr.confirm_cancellation("atc-nonexistent") is False


def test_confirm_already_confirmed():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "deploy")
    mgr.confirm_cancellation(cid)
    assert mgr.confirm_cancellation(cid) is False


def test_reject_cancellation():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "test")
    assert mgr.reject_cancellation(cid, reason="not allowed") is True
    entry = mgr.get_cancellation(cid)
    assert entry["status"] == "rejected"
    assert entry["rejection_reason"] == "not allowed"


def test_reject_cancellation_invalid_id():
    mgr = AgentTaskCancellation()
    assert mgr.reject_cancellation("atc-nonexistent") is False


def test_get_cancellation_missing():
    mgr = AgentTaskCancellation()
    assert mgr.get_cancellation("atc-nope") == {}


def test_get_cancellations_by_agent():
    mgr = AgentTaskCancellation()
    mgr.request_cancellation("agent-1", "build")
    mgr.request_cancellation("agent-1", "test")
    mgr.request_cancellation("agent-2", "deploy")
    results = mgr.get_cancellations("agent-1")
    assert len(results) == 2
    assert all(r["agent_id"] == "agent-1" for r in results)


def test_get_cancellations_by_status():
    mgr = AgentTaskCancellation()
    cid1 = mgr.request_cancellation("agent-1", "build")
    mgr.request_cancellation("agent-1", "test")
    mgr.confirm_cancellation(cid1)
    results = mgr.get_cancellations("agent-1", status="confirmed")
    assert len(results) == 1
    assert results[0]["task_name"] == "build"


def test_is_cancelled_true():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "build")
    mgr.confirm_cancellation(cid)
    assert mgr.is_cancelled("agent-1", "build") is True


def test_is_cancelled_false_when_only_requested():
    mgr = AgentTaskCancellation()
    mgr.request_cancellation("agent-1", "build")
    assert mgr.is_cancelled("agent-1", "build") is False


def test_is_cancelled_false_when_rejected():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "build")
    mgr.reject_cancellation(cid)
    assert mgr.is_cancelled("agent-1", "build") is False


def test_get_cancellation_count():
    mgr = AgentTaskCancellation()
    mgr.request_cancellation("agent-1", "a")
    cid2 = mgr.request_cancellation("agent-1", "b")
    mgr.request_cancellation("agent-2", "c")
    mgr.confirm_cancellation(cid2)
    assert mgr.get_cancellation_count() == 3
    assert mgr.get_cancellation_count(agent_id="agent-1") == 2
    assert mgr.get_cancellation_count(status="confirmed") == 1
    assert mgr.get_cancellation_count(agent_id="agent-2", status="requested") == 1


def test_get_stats():
    mgr = AgentTaskCancellation()
    cid1 = mgr.request_cancellation("agent-1", "a")
    cid2 = mgr.request_cancellation("agent-1", "b")
    mgr.request_cancellation("agent-1", "c")
    mgr.confirm_cancellation(cid1)
    mgr.reject_cancellation(cid2)
    stats = mgr.get_stats()
    assert stats["total_cancellations"] == 3
    assert stats["requested"] == 1
    assert stats["confirmed"] == 1
    assert stats["rejected"] == 1


def test_reset():
    mgr = AgentTaskCancellation()
    mgr.request_cancellation("agent-1", "build")
    mgr.reset()
    assert mgr.get_cancellation_count() == 0
    assert mgr.get_stats()["total_cancellations"] == 0


def test_on_change_callback():
    events = []
    mgr = AgentTaskCancellation()
    mgr.on_change = lambda evt, data: events.append(evt)
    mgr.request_cancellation("agent-1", "build")
    assert "cancellation_requested" in events


def test_remove_callback():
    mgr = AgentTaskCancellation()
    mgr._callbacks["cb1"] = lambda e, d: None
    assert mgr.remove_callback("cb1") is True
    assert mgr.remove_callback("cb1") is False


def test_entry_fields():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "deploy", reason="oom")
    entry = mgr.get_cancellation(cid)
    assert entry["cancellation_id"] == cid
    assert entry["agent_id"] == "agent-1"
    assert entry["task_name"] == "deploy"
    assert entry["reason"] == "oom"
    assert entry["status"] == "requested"
    assert isinstance(entry["requested_at"], float)
    assert entry["confirmed_at"] is None
    assert isinstance(entry["created_at"], float)


def test_reject_without_reason():
    mgr = AgentTaskCancellation()
    cid = mgr.request_cancellation("agent-1", "task")
    mgr.reject_cancellation(cid)
    entry = mgr.get_cancellation(cid)
    assert entry["status"] == "rejected"
    assert "rejection_reason" not in entry


if __name__ == "__main__":
    tests = [
        test_request_cancellation_returns_id,
        test_request_cancellation_with_reason,
        test_request_cancellation_empty_agent_id,
        test_request_cancellation_empty_task_name,
        test_confirm_cancellation,
        test_confirm_cancellation_invalid_id,
        test_confirm_already_confirmed,
        test_reject_cancellation,
        test_reject_cancellation_invalid_id,
        test_get_cancellation_missing,
        test_get_cancellations_by_agent,
        test_get_cancellations_by_status,
        test_is_cancelled_true,
        test_is_cancelled_false_when_only_requested,
        test_is_cancelled_false_when_rejected,
        test_get_cancellation_count,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_entry_fields,
        test_reject_without_reason,
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
