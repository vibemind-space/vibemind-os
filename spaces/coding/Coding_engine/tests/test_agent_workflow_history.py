"""Tests for AgentWorkflowHistory."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_history import AgentWorkflowHistory


def test_record_execution_returns_id():
    h = AgentWorkflowHistory()
    eid = h.record_execution("a1", "deploy")
    assert eid.startswith("awh-"), f"Expected prefix awh-, got {eid}"
    assert len(eid) > 4


def test_get_execution():
    h = AgentWorkflowHistory()
    eid = h.record_execution("a1", "build", status="success", duration_ms=500)
    rec = h.get_execution(eid)
    assert rec is not None
    assert rec["agent_id"] == "a1"
    assert rec["workflow_name"] == "build"
    assert rec["status"] == "success"
    assert rec["duration_ms"] == 500


def test_get_execution_not_found():
    h = AgentWorkflowHistory()
    assert h.get_execution("awh-nonexistent") is None


def test_record_execution_defaults():
    h = AgentWorkflowHistory()
    eid = h.record_execution("a1", "test")
    rec = h.get_execution(eid)
    assert rec["status"] == "success"
    assert rec["duration_ms"] == 0
    assert rec["metadata"] == {}


def test_record_execution_with_metadata():
    h = AgentWorkflowHistory()
    eid = h.record_execution("a1", "deploy", metadata={"version": "1.0"})
    rec = h.get_execution(eid)
    assert rec["metadata"] == {"version": "1.0"}


def test_get_history_newest_first():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build", duration_ms=100)
    h.record_execution("a1", "build", duration_ms=200)
    h.record_execution("a1", "build", duration_ms=300)
    hist = h.get_history("a1")
    assert len(hist) == 3
    assert hist[0]["duration_ms"] == 300
    assert hist[2]["duration_ms"] == 100


def test_get_history_filter_workflow_name():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build")
    h.record_execution("a1", "deploy")
    h.record_execution("a1", "build")
    hist = h.get_history("a1", workflow_name="build")
    assert len(hist) == 2
    for e in hist:
        assert e["workflow_name"] == "build"


def test_get_history_filter_status():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build", status="success")
    h.record_execution("a1", "build", status="failure")
    h.record_execution("a1", "build", status="success")
    hist = h.get_history("a1", status="failure")
    assert len(hist) == 1
    assert hist[0]["status"] == "failure"


def test_get_history_limit():
    h = AgentWorkflowHistory()
    for i in range(10):
        h.record_execution("a1", "build", duration_ms=i)
    hist = h.get_history("a1", limit=3)
    assert len(hist) == 3


def test_get_latest_execution():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "deploy", duration_ms=100)
    h.record_execution("a1", "deploy", duration_ms=200)
    h.record_execution("a1", "deploy", duration_ms=300)
    latest = h.get_latest_execution("a1", "deploy")
    assert latest is not None
    assert latest["duration_ms"] == 300


def test_get_latest_execution_none():
    h = AgentWorkflowHistory()
    assert h.get_latest_execution("a1", "nonexistent") is None


def test_get_execution_count():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build")
    h.record_execution("a1", "deploy")
    h.record_execution("a2", "build")
    assert h.get_execution_count() == 3
    assert h.get_execution_count(agent_id="a1") == 2
    assert h.get_execution_count(agent_id="a2") == 1


def test_get_execution_count_by_status():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build", status="success")
    h.record_execution("a1", "build", status="failure")
    h.record_execution("a1", "build", status="success")
    assert h.get_execution_count(status="success") == 2
    assert h.get_execution_count(status="failure") == 1


def test_get_average_duration():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build", duration_ms=100)
    h.record_execution("a1", "build", duration_ms=200)
    h.record_execution("a1", "build", duration_ms=300)
    avg = h.get_average_duration("a1", "build")
    assert avg == 200.0


def test_get_average_duration_empty():
    h = AgentWorkflowHistory()
    assert h.get_average_duration("a1", "build") == 0.0


def test_clear_history():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build")
    h.record_execution("a1", "deploy")
    h.record_execution("a2", "build")
    removed = h.clear_history("a1")
    assert removed == 2
    assert h.get_execution_count(agent_id="a1") == 0
    assert h.get_execution_count(agent_id="a2") == 1


def test_get_stats():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build", status="success")
    h.record_execution("a1", "deploy", status="failure")
    h.record_execution("a2", "build", status="success")
    stats = h.get_stats()
    assert stats["total_executions"] == 3
    assert stats["unique_agents"] == 2
    assert stats["success_count"] == 2
    assert stats["failure_count"] == 1


def test_reset():
    h = AgentWorkflowHistory()
    h.record_execution("a1", "build")
    h.on_change = lambda e, d: None
    h._callbacks["cb1"] = lambda e, d: None
    h.reset()
    assert h.get_execution_count() == 0
    assert h.on_change is None
    assert len(h._callbacks) == 0


def test_on_change_callback():
    events = []
    h = AgentWorkflowHistory()
    h.on_change = lambda event, data: events.append((event, data))
    h.record_execution("a1", "build")
    assert len(events) == 1
    assert events[0][0] == "execution_recorded"


def test_remove_callback():
    h = AgentWorkflowHistory()
    h._callbacks["cb1"] = lambda e, d: None
    assert h.remove_callback("cb1") is True
    assert h.remove_callback("cb1") is False


def test_unique_ids():
    h = AgentWorkflowHistory()
    ids = set()
    for _ in range(100):
        eid = h.record_execution("a1", "build")
        ids.add(eid)
    assert len(ids) == 100


def test_pruning():
    h = AgentWorkflowHistory()
    h.MAX_ENTRIES = 10
    for i in range(15):
        h.record_execution("a1", "build", duration_ms=i)
    assert len(h._state.entries) <= 10


if __name__ == "__main__":
    tests = [
        test_record_execution_returns_id,
        test_get_execution,
        test_get_execution_not_found,
        test_record_execution_defaults,
        test_record_execution_with_metadata,
        test_get_history_newest_first,
        test_get_history_filter_workflow_name,
        test_get_history_filter_status,
        test_get_history_limit,
        test_get_latest_execution,
        test_get_latest_execution_none,
        test_get_execution_count,
        test_get_execution_count_by_status,
        test_get_average_duration,
        test_get_average_duration_empty,
        test_clear_history,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_unique_ids,
        test_pruning,
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
