"""Tests for AgentWorkflowRollback."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_rollback import AgentWorkflowRollback


def test_create_checkpoint_returns_id():
    svc = AgentWorkflowRollback()
    cid = svc.create_checkpoint("a1", "wf1", {"x": 1})
    assert cid.startswith("awrb-")
    assert len(cid) > len("awrb-")


def test_get_checkpoint():
    svc = AgentWorkflowRollback()
    cid = svc.create_checkpoint("a1", "wf1", {"key": "val"}, label="test")
    cp = svc.get_checkpoint(cid)
    assert cp is not None
    assert cp["agent_id"] == "a1"
    assert cp["workflow_name"] == "wf1"
    assert cp["state"] == {"key": "val"}
    assert cp["label"] == "test"
    assert cp["created_at"] > 0
    assert cp["rolled_back"] is False


def test_get_checkpoint_not_found():
    svc = AgentWorkflowRollback()
    assert svc.get_checkpoint("awrb-nonexistent") is None


def test_state_is_deep_copied():
    svc = AgentWorkflowRollback()
    original = {"nested": {"a": 1}}
    cid = svc.create_checkpoint("a1", "wf1", original)
    original["nested"]["a"] = 999
    cp = svc.get_checkpoint(cid)
    assert cp["state"]["nested"]["a"] == 1


def test_rollback():
    svc = AgentWorkflowRollback()
    cid = svc.create_checkpoint("a1", "wf1", {"step": 3})
    result = svc.rollback(cid)
    assert result["checkpoint_id"] == cid
    assert result["state"] == {"step": 3}
    assert result["rolled_back"] is True
    # Verify entry is marked as rolled back
    cp = svc.get_checkpoint(cid)
    assert cp["rolled_back"] is True


def test_rollback_not_found():
    svc = AgentWorkflowRollback()
    try:
        svc.rollback("awrb-nonexistent")
        assert False, "Expected KeyError"
    except KeyError:
        pass


def test_get_checkpoints_newest_first():
    svc = AgentWorkflowRollback()
    cid1 = svc.create_checkpoint("a1", "wf1", {"step": 1})
    cid2 = svc.create_checkpoint("a1", "wf1", {"step": 2})
    cid3 = svc.create_checkpoint("a1", "wf2", {"step": 3})
    results = svc.get_checkpoints("a1")
    assert len(results) == 3
    assert results[0]["checkpoint_id"] == cid3
    assert results[1]["checkpoint_id"] == cid2
    assert results[2]["checkpoint_id"] == cid1


def test_get_checkpoints_filter_by_workflow():
    svc = AgentWorkflowRollback()
    svc.create_checkpoint("a1", "wf1", {"x": 1})
    svc.create_checkpoint("a1", "wf2", {"x": 2})
    results = svc.get_checkpoints("a1", workflow_name="wf1")
    assert len(results) == 1
    assert results[0]["workflow_name"] == "wf1"


def test_get_latest_checkpoint():
    svc = AgentWorkflowRollback()
    svc.create_checkpoint("a1", "wf1", {"v": 1})
    svc.create_checkpoint("a1", "wf1", {"v": 2})
    latest = svc.get_latest_checkpoint("a1", "wf1")
    assert latest is not None
    assert latest["state"]["v"] == 2


def test_get_latest_checkpoint_not_found():
    svc = AgentWorkflowRollback()
    assert svc.get_latest_checkpoint("a1", "wf1") is None


def test_get_checkpoint_count():
    svc = AgentWorkflowRollback()
    assert svc.get_checkpoint_count() == 0
    svc.create_checkpoint("a1", "wf1", {})
    svc.create_checkpoint("a2", "wf1", {})
    assert svc.get_checkpoint_count() == 2
    assert svc.get_checkpoint_count("a1") == 1
    assert svc.get_checkpoint_count("a2") == 1
    assert svc.get_checkpoint_count("a3") == 0


def test_remove_checkpoint():
    svc = AgentWorkflowRollback()
    cid = svc.create_checkpoint("a1", "wf1", {"x": 1})
    assert svc.remove_checkpoint(cid) is True
    assert svc.get_checkpoint(cid) is None
    assert svc.remove_checkpoint(cid) is False


def test_get_stats():
    svc = AgentWorkflowRollback()
    svc.create_checkpoint("a1", "wf1", {})
    svc.create_checkpoint("a1", "wf2", {})
    cid3 = svc.create_checkpoint("a2", "wf1", {})
    svc.rollback(cid3)
    stats = svc.get_stats()
    assert stats["total_checkpoints"] == 3
    assert stats["total_rollbacks"] == 1


def test_reset():
    svc = AgentWorkflowRollback()
    svc.create_checkpoint("a1", "wf1", {"x": 1})
    svc.create_checkpoint("a2", "wf2", {"y": 2})
    svc.reset()
    assert svc.get_checkpoint_count() == 0
    assert svc.get_stats()["total_checkpoints"] == 0


def test_on_change_property():
    svc = AgentWorkflowRollback()
    events = []
    svc.on_change = lambda action, data: events.append((action, data))
    svc.create_checkpoint("a1", "wf1", {"x": 1})
    assert len(events) == 1
    assert events[0][0] == "checkpoint_created"
    svc.on_change = None
    svc.create_checkpoint("a1", "wf1", {"x": 2})
    assert len(events) == 1


def test_remove_callback():
    svc = AgentWorkflowRollback()
    assert svc.remove_callback("nonexistent") is False
    svc._callbacks["cb1"] = lambda a, d: None
    assert svc.remove_callback("cb1") is True
    assert "cb1" not in svc._callbacks


def test_prune_enforces_max_entries():
    svc = AgentWorkflowRollback()
    svc.MAX_ENTRIES = 5
    for i in range(8):
        svc.create_checkpoint("a1", "wf1", {"i": i})
    assert svc.get_checkpoint_count() <= 6


def test_unique_ids():
    svc = AgentWorkflowRollback()
    ids = set()
    for i in range(100):
        cid = svc.create_checkpoint("a1", "wf1", {"i": i})
        ids.add(cid)
    assert len(ids) == 100


def test_label_default_empty():
    svc = AgentWorkflowRollback()
    cid = svc.create_checkpoint("a1", "wf1", {"x": 1})
    cp = svc.get_checkpoint(cid)
    assert cp["label"] == ""


def test_rollback_returns_deep_copy():
    svc = AgentWorkflowRollback()
    cid = svc.create_checkpoint("a1", "wf1", {"nested": {"a": 1}})
    result = svc.rollback(cid)
    result["state"]["nested"]["a"] = 999
    cp = svc.get_checkpoint(cid)
    assert cp["state"]["nested"]["a"] == 1


if __name__ == "__main__":
    tests = [
        test_create_checkpoint_returns_id,
        test_get_checkpoint,
        test_get_checkpoint_not_found,
        test_state_is_deep_copied,
        test_rollback,
        test_rollback_not_found,
        test_get_checkpoints_newest_first,
        test_get_checkpoints_filter_by_workflow,
        test_get_latest_checkpoint,
        test_get_latest_checkpoint_not_found,
        test_get_checkpoint_count,
        test_remove_checkpoint,
        test_get_stats,
        test_reset,
        test_on_change_property,
        test_remove_callback,
        test_prune_enforces_max_entries,
        test_unique_ids,
        test_label_default_empty,
        test_rollback_returns_deep_copy,
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
