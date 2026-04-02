"""Tests for AgentTaskEscalation service."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_escalation import AgentTaskEscalation


def test_escalate_returns_id():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "timeout exceeded")
    assert eid.startswith("ate-")
    assert len(eid) > 4


def test_escalate_stores_fields():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "cpu spike", level="critical", metadata={"cpu": 99})
    entry = mgr.get_escalation(eid)
    assert entry["escalation_id"] == eid
    assert entry["task_id"] == "task-1"
    assert entry["reason"] == "cpu spike"
    assert entry["level"] == "critical"
    assert entry["metadata"] == {"cpu": 99}
    assert entry["resolved"] is False
    assert entry["resolution"] == ""
    assert isinstance(entry["created_at"], float)
    assert entry["resolved_at"] is None


def test_escalate_default_level():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "some reason")
    entry = mgr.get_escalation(eid)
    assert entry["level"] == "warning"


def test_escalate_invalid_level_defaults_to_warning():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "reason", level="unknown")
    entry = mgr.get_escalation(eid)
    assert entry["level"] == "warning"


def test_escalate_empty_task_id():
    mgr = AgentTaskEscalation()
    assert mgr.escalate("", "reason") == ""


def test_escalate_empty_reason():
    mgr = AgentTaskEscalation()
    assert mgr.escalate("task-1", "") == ""


def test_escalate_no_metadata():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "reason")
    entry = mgr.get_escalation(eid)
    assert entry["metadata"] == {}


def test_get_escalation_missing():
    mgr = AgentTaskEscalation()
    assert mgr.get_escalation("ate-nonexistent") is None


def test_get_escalations_all():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1")
    mgr.escalate("task-2", "r2")
    mgr.escalate("task-1", "r3")
    results = mgr.get_escalations()
    assert len(results) == 3


def test_get_escalations_by_task_id():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1")
    mgr.escalate("task-2", "r2")
    mgr.escalate("task-1", "r3")
    results = mgr.get_escalations(task_id="task-1")
    assert len(results) == 2
    assert all(e["task_id"] == "task-1" for e in results)


def test_get_escalations_by_level():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1", level="info")
    mgr.escalate("task-1", "r2", level="critical")
    mgr.escalate("task-1", "r3", level="info")
    results = mgr.get_escalations(level="info")
    assert len(results) == 2
    assert all(e["level"] == "info" for e in results)


def test_get_escalations_newest_first():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "first")
    mgr.escalate("task-1", "second")
    results = mgr.get_escalations()
    assert results[0]["reason"] == "second"
    assert results[1]["reason"] == "first"


def test_get_escalations_limit():
    mgr = AgentTaskEscalation()
    for i in range(10):
        mgr.escalate("task-1", f"reason-{i}")
    results = mgr.get_escalations(limit=3)
    assert len(results) == 3


def test_get_escalations_combined_filters():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1", level="info")
    mgr.escalate("task-1", "r2", level="critical")
    mgr.escalate("task-2", "r3", level="info")
    results = mgr.get_escalations(task_id="task-1", level="info")
    assert len(results) == 1
    assert results[0]["reason"] == "r1"


def test_resolve_escalation():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "issue")
    assert mgr.resolve_escalation(eid, "fixed it") is True
    entry = mgr.get_escalation(eid)
    assert entry["resolved"] is True
    assert entry["resolution"] == "fixed it"
    assert isinstance(entry["resolved_at"], float)


def test_resolve_escalation_no_resolution_text():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "issue")
    assert mgr.resolve_escalation(eid) is True
    entry = mgr.get_escalation(eid)
    assert entry["resolved"] is True
    assert entry["resolution"] == ""


def test_resolve_escalation_already_resolved():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "issue")
    mgr.resolve_escalation(eid, "done")
    assert mgr.resolve_escalation(eid, "again") is False


def test_resolve_escalation_invalid_id():
    mgr = AgentTaskEscalation()
    assert mgr.resolve_escalation("ate-nonexistent") is False


def test_get_escalation_count_all():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1")
    mgr.escalate("task-2", "r2")
    assert mgr.get_escalation_count() == 2


def test_get_escalation_count_by_task_id():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1")
    mgr.escalate("task-2", "r2")
    mgr.escalate("task-1", "r3")
    assert mgr.get_escalation_count(task_id="task-1") == 2


def test_get_escalation_count_by_level():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "r1", level="info")
    mgr.escalate("task-1", "r2", level="critical")
    mgr.escalate("task-1", "r3", level="info")
    assert mgr.get_escalation_count(level="info") == 2


def test_get_stats():
    mgr = AgentTaskEscalation()
    e1 = mgr.escalate("task-1", "r1", level="info")
    mgr.escalate("task-1", "r2", level="critical")
    mgr.escalate("task-2", "r3", level="warning")
    mgr.resolve_escalation(e1)
    stats = mgr.get_stats()
    assert stats["total_escalations"] == 3
    assert stats["resolved_count"] == 1
    assert stats["by_level"]["info"] == 1
    assert stats["by_level"]["critical"] == 1
    assert stats["by_level"]["warning"] == 1


def test_get_stats_empty():
    mgr = AgentTaskEscalation()
    stats = mgr.get_stats()
    assert stats["total_escalations"] == 0
    assert stats["resolved_count"] == 0
    assert stats["by_level"] == {}


def test_reset():
    mgr = AgentTaskEscalation()
    mgr.escalate("task-1", "reason")
    mgr._callbacks["cb1"] = lambda e, d: None
    mgr.on_change = lambda e, d: None
    mgr.reset()
    assert mgr.get_escalation_count() == 0
    assert mgr.get_stats()["total_escalations"] == 0
    assert mgr.on_change is None
    assert len(mgr._callbacks) == 0


def test_on_change_callback_on_escalate():
    events = []
    mgr = AgentTaskEscalation()
    mgr.on_change = lambda evt, data: events.append((evt, data))
    mgr.escalate("task-1", "reason")
    assert len(events) == 1
    assert events[0][0] == "escalation_created"


def test_on_change_callback_on_resolve():
    events = []
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "reason")
    mgr.on_change = lambda evt, data: events.append(evt)
    mgr.resolve_escalation(eid, "fixed")
    assert "escalation_resolved" in events


def test_named_callbacks():
    events = []
    mgr = AgentTaskEscalation()
    mgr._callbacks["cb1"] = lambda evt, data: events.append(evt)
    mgr.escalate("task-1", "reason")
    assert "escalation_created" in events


def test_remove_callback():
    mgr = AgentTaskEscalation()
    mgr._callbacks["cb1"] = lambda e, d: None
    assert mgr.remove_callback("cb1") is True
    assert mgr.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    mgr = AgentTaskEscalation()
    assert mgr.remove_callback("nope") is False


def test_callback_exception_silenced():
    mgr = AgentTaskEscalation()
    mgr.on_change = lambda e, d: (_ for _ in ()).throw(ValueError("boom"))
    # Should not raise
    eid = mgr.escalate("task-1", "reason")
    assert eid.startswith("ate-")


def test_named_callback_exception_silenced():
    mgr = AgentTaskEscalation()
    mgr._callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("fail"))
    eid = mgr.escalate("task-1", "reason")
    assert eid.startswith("ate-")


def test_pruning_evicts_oldest():
    mgr = AgentTaskEscalation()
    mgr.MAX_ENTRIES = 5
    ids = []
    for i in range(6):
        eid = mgr.escalate(f"task-{i}", f"reason-{i}")
        ids.append(eid)
    # Should have pruned the oldest to stay at MAX_ENTRIES
    assert len(mgr._state.entries) <= 5
    # The first entry should have been evicted
    assert mgr.get_escalation(ids[0]) is None


def test_unique_ids():
    mgr = AgentTaskEscalation()
    ids = set()
    for i in range(50):
        eid = mgr.escalate("task-1", f"reason-{i}")
        ids.add(eid)
    assert len(ids) == 50


def test_info_level():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "just fyi", level="info")
    assert mgr.get_escalation(eid)["level"] == "info"


def test_critical_level():
    mgr = AgentTaskEscalation()
    eid = mgr.escalate("task-1", "system down", level="critical")
    assert mgr.get_escalation(eid)["level"] == "critical"


if __name__ == "__main__":
    tests = [
        test_escalate_returns_id,
        test_escalate_stores_fields,
        test_escalate_default_level,
        test_escalate_invalid_level_defaults_to_warning,
        test_escalate_empty_task_id,
        test_escalate_empty_reason,
        test_escalate_no_metadata,
        test_get_escalation_missing,
        test_get_escalations_all,
        test_get_escalations_by_task_id,
        test_get_escalations_by_level,
        test_get_escalations_newest_first,
        test_get_escalations_limit,
        test_get_escalations_combined_filters,
        test_resolve_escalation,
        test_resolve_escalation_no_resolution_text,
        test_resolve_escalation_already_resolved,
        test_resolve_escalation_invalid_id,
        test_get_escalation_count_all,
        test_get_escalation_count_by_task_id,
        test_get_escalation_count_by_level,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_callback_on_escalate,
        test_on_change_callback_on_resolve,
        test_named_callbacks,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_callback_exception_silenced,
        test_named_callback_exception_silenced,
        test_pruning_evicts_oldest,
        test_unique_ids,
        test_info_level,
        test_critical_level,
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
