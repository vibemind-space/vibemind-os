"""Tests for AgentWorkflowSnapshot."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_snapshot import AgentWorkflowSnapshot


def test_take_snapshot_returns_id():
    svc = AgentWorkflowSnapshot()
    sid = svc.take_snapshot("a1", "wf1", {"x": 1})
    assert sid.startswith("awss-")
    assert len(sid) > len("awss-")


def test_get_snapshot():
    svc = AgentWorkflowSnapshot()
    sid = svc.take_snapshot("a1", "wf1", {"key": "val"}, label="test")
    snap = svc.get_snapshot(sid)
    assert snap is not None
    assert snap["agent_id"] == "a1"
    assert snap["workflow_name"] == "wf1"
    assert snap["state"] == {"key": "val"}
    assert snap["label"] == "test"
    assert snap["created_at"] > 0


def test_get_snapshot_not_found():
    svc = AgentWorkflowSnapshot()
    assert svc.get_snapshot("awss-nonexistent") is None


def test_state_is_deep_copied():
    svc = AgentWorkflowSnapshot()
    original = {"nested": {"a": 1}}
    sid = svc.take_snapshot("a1", "wf1", original)
    original["nested"]["a"] = 999
    snap = svc.get_snapshot(sid)
    assert snap["state"]["nested"]["a"] == 1


def test_get_snapshots_newest_first():
    svc = AgentWorkflowSnapshot()
    sid1 = svc.take_snapshot("a1", "wf1", {"step": 1})
    sid2 = svc.take_snapshot("a1", "wf1", {"step": 2})
    sid3 = svc.take_snapshot("a1", "wf2", {"step": 3})
    results = svc.get_snapshots("a1")
    assert len(results) == 3
    assert results[0]["snapshot_id"] == sid3
    assert results[1]["snapshot_id"] == sid2
    assert results[2]["snapshot_id"] == sid1


def test_get_snapshots_filter_by_workflow():
    svc = AgentWorkflowSnapshot()
    svc.take_snapshot("a1", "wf1", {"x": 1})
    svc.take_snapshot("a1", "wf2", {"x": 2})
    results = svc.get_snapshots("a1", workflow_name="wf1")
    assert len(results) == 1
    assert results[0]["workflow_name"] == "wf1"


def test_get_snapshots_limit():
    svc = AgentWorkflowSnapshot()
    for i in range(10):
        svc.take_snapshot("a1", "wf1", {"i": i})
    results = svc.get_snapshots("a1", limit=3)
    assert len(results) == 3


def test_get_latest_snapshot():
    svc = AgentWorkflowSnapshot()
    svc.take_snapshot("a1", "wf1", {"v": 1})
    svc.take_snapshot("a1", "wf1", {"v": 2})
    latest = svc.get_latest_snapshot("a1", "wf1")
    assert latest is not None
    assert latest["state"]["v"] == 2


def test_get_latest_snapshot_not_found():
    svc = AgentWorkflowSnapshot()
    assert svc.get_latest_snapshot("a1", "wf1") is None


def test_compare_snapshots_identical():
    svc = AgentWorkflowSnapshot()
    sid1 = svc.take_snapshot("a1", "wf1", {"a": 1, "b": 2})
    sid2 = svc.take_snapshot("a1", "wf1", {"a": 1, "b": 2})
    diff = svc.compare_snapshots(sid1, sid2)
    assert diff == {"added": [], "removed": [], "changed": []}


def test_compare_snapshots_differences():
    svc = AgentWorkflowSnapshot()
    sid1 = svc.take_snapshot("a1", "wf1", {"a": 1, "b": 2, "c": 3})
    sid2 = svc.take_snapshot("a1", "wf1", {"b": 99, "c": 3, "d": 4})
    diff = svc.compare_snapshots(sid1, sid2)
    assert "a" in diff["removed"]
    assert "d" in diff["added"]
    assert "b" in diff["changed"]
    assert "c" not in diff["changed"]


def test_compare_snapshots_missing():
    svc = AgentWorkflowSnapshot()
    sid1 = svc.take_snapshot("a1", "wf1", {"a": 1})
    diff = svc.compare_snapshots(sid1, "awss-nonexistent")
    assert diff == {"added": [], "removed": [], "changed": []}


def test_get_snapshot_count():
    svc = AgentWorkflowSnapshot()
    assert svc.get_snapshot_count() == 0
    svc.take_snapshot("a1", "wf1", {})
    svc.take_snapshot("a2", "wf1", {})
    assert svc.get_snapshot_count() == 2
    assert svc.get_snapshot_count("a1") == 1
    assert svc.get_snapshot_count("a2") == 1
    assert svc.get_snapshot_count("a3") == 0


def test_remove_snapshot():
    svc = AgentWorkflowSnapshot()
    sid = svc.take_snapshot("a1", "wf1", {"x": 1})
    assert svc.remove_snapshot(sid) is True
    assert svc.get_snapshot(sid) is None
    assert svc.remove_snapshot(sid) is False


def test_get_stats():
    svc = AgentWorkflowSnapshot()
    svc.take_snapshot("a1", "wf1", {})
    svc.take_snapshot("a1", "wf2", {})
    svc.take_snapshot("a2", "wf1", {})
    stats = svc.get_stats()
    assert stats["total_snapshots"] == 3
    assert stats["unique_agents"] == 2
    assert stats["unique_workflows"] == 2


def test_reset():
    svc = AgentWorkflowSnapshot()
    svc.take_snapshot("a1", "wf1", {"x": 1})
    svc.take_snapshot("a2", "wf2", {"y": 2})
    svc.reset()
    assert svc.get_snapshot_count() == 0
    assert svc.get_stats()["total_snapshots"] == 0


def test_on_change_property():
    svc = AgentWorkflowSnapshot()
    events = []
    svc.on_change = lambda action, data: events.append((action, data))
    svc.take_snapshot("a1", "wf1", {"x": 1})
    assert len(events) == 1
    assert events[0][0] == "snapshot_taken"
    svc.on_change = None
    svc.take_snapshot("a1", "wf1", {"x": 2})
    assert len(events) == 1


def test_remove_callback():
    svc = AgentWorkflowSnapshot()
    assert svc.remove_callback("nonexistent") is False
    svc._callbacks["cb1"] = lambda a, d: None
    assert svc.remove_callback("cb1") is True
    assert "cb1" not in svc._callbacks


def test_prune_enforces_max_entries():
    svc = AgentWorkflowSnapshot()
    svc.MAX_ENTRIES = 5
    for i in range(8):
        svc.take_snapshot("a1", "wf1", {"i": i})
    assert svc.get_snapshot_count() <= 6  # pruned on next insert after exceeding


def test_unique_ids():
    svc = AgentWorkflowSnapshot()
    ids = set()
    for i in range(100):
        sid = svc.take_snapshot("a1", "wf1", {"i": i})
        ids.add(sid)
    assert len(ids) == 100


def test_label_default_empty():
    svc = AgentWorkflowSnapshot()
    sid = svc.take_snapshot("a1", "wf1", {"x": 1})
    snap = svc.get_snapshot(sid)
    assert snap["label"] == ""


if __name__ == "__main__":
    tests = [
        test_take_snapshot_returns_id,
        test_get_snapshot,
        test_get_snapshot_not_found,
        test_state_is_deep_copied,
        test_get_snapshots_newest_first,
        test_get_snapshots_filter_by_workflow,
        test_get_snapshots_limit,
        test_get_latest_snapshot,
        test_get_latest_snapshot_not_found,
        test_compare_snapshots_identical,
        test_compare_snapshots_differences,
        test_compare_snapshots_missing,
        test_get_snapshot_count,
        test_remove_snapshot,
        test_get_stats,
        test_reset,
        test_on_change_property,
        test_remove_callback,
        test_prune_enforces_max_entries,
        test_unique_ids,
        test_label_default_empty,
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
