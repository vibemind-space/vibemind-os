"""Tests for AgentWorkflowCheckpoint service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_checkpoint import AgentWorkflowCheckpoint


def test_create_checkpoint_returns_id():
    cp = AgentWorkflowCheckpoint()
    cid = cp.create_checkpoint("a1", "wf1", "step1", {"progress": 50})
    assert cid.startswith("awcp-")
    assert len(cid) > len("awcp-")


def test_create_checkpoint_unique_ids():
    cp = AgentWorkflowCheckpoint()
    id1 = cp.create_checkpoint("a1", "wf1", "s1", {})
    id2 = cp.create_checkpoint("a1", "wf1", "s2", {})
    assert id1 != id2


def test_get_checkpoint_by_id():
    cp = AgentWorkflowCheckpoint()
    cid = cp.create_checkpoint("a1", "wf1", "step1", {"x": 1})
    entry = cp.get_checkpoint(cid)
    assert entry is not None
    assert entry["checkpoint_id"] == cid
    assert entry["agent_id"] == "a1"
    assert entry["workflow_name"] == "wf1"
    assert entry["checkpoint_name"] == "step1"
    assert entry["state"] == {"x": 1}


def test_get_checkpoint_not_found():
    cp = AgentWorkflowCheckpoint()
    assert cp.get_checkpoint("awcp-nonexistent") is None


def test_get_checkpoint_returns_dict():
    cp = AgentWorkflowCheckpoint()
    cid = cp.create_checkpoint("a1", "wf1", "s1", {"k": "v"})
    result = cp.get_checkpoint(cid)
    assert isinstance(result, dict)


def test_get_checkpoints_for_agent():
    cp = AgentWorkflowCheckpoint()
    cp.create_checkpoint("a1", "wf1", "s1", {})
    cp.create_checkpoint("a1", "wf2", "s1", {})
    cp.create_checkpoint("a2", "wf1", "s1", {})
    results = cp.get_checkpoints("a1")
    assert len(results) == 2
    assert all(r["agent_id"] == "a1" for r in results)


def test_get_checkpoints_filter_workflow():
    cp = AgentWorkflowCheckpoint()
    cp.create_checkpoint("a1", "wf1", "s1", {})
    cp.create_checkpoint("a1", "wf2", "s1", {})
    results = cp.get_checkpoints("a1", workflow_name="wf1")
    assert len(results) == 1
    assert results[0]["workflow_name"] == "wf1"


def test_get_checkpoints_newest_first():
    cp = AgentWorkflowCheckpoint()
    cp.create_checkpoint("a1", "wf1", "s1", {"order": 1})
    cp.create_checkpoint("a1", "wf1", "s2", {"order": 2})
    cp.create_checkpoint("a1", "wf1", "s3", {"order": 3})
    results = cp.get_checkpoints("a1")
    assert results[0]["state"]["order"] == 3
    assert results[-1]["state"]["order"] == 1


def test_get_checkpoints_limit():
    cp = AgentWorkflowCheckpoint()
    for i in range(10):
        cp.create_checkpoint("a1", "wf1", f"s{i}", {"i": i})
    results = cp.get_checkpoints("a1", limit=3)
    assert len(results) == 3


def test_get_checkpoints_default_limit():
    cp = AgentWorkflowCheckpoint()
    for i in range(60):
        cp.create_checkpoint("a1", "wf1", f"s{i}", {})
    results = cp.get_checkpoints("a1")
    assert len(results) == 50


def test_get_checkpoints_empty():
    cp = AgentWorkflowCheckpoint()
    results = cp.get_checkpoints("a1")
    assert results == []


def test_restore_checkpoint():
    cp = AgentWorkflowCheckpoint()
    cid = cp.create_checkpoint("a1", "wf1", "s1", {"val": 42})
    restored = cp.restore_checkpoint(cid)
    assert restored == {"val": 42}


def test_restore_checkpoint_deep_copy():
    cp = AgentWorkflowCheckpoint()
    original = {"nested": {"value": 1}}
    cid = cp.create_checkpoint("a1", "wf1", "s1", original)
    restored = cp.restore_checkpoint(cid)
    restored["nested"]["value"] = 999
    restored2 = cp.restore_checkpoint(cid)
    assert restored2["nested"]["value"] == 1


def test_restore_checkpoint_not_found():
    cp = AgentWorkflowCheckpoint()
    assert cp.restore_checkpoint("awcp-missing") is None


def test_remove_checkpoint():
    cp = AgentWorkflowCheckpoint()
    cid = cp.create_checkpoint("a1", "wf1", "s1", {})
    assert cp.remove_checkpoint(cid) is True
    assert cp.get_checkpoint(cid) is None


def test_remove_checkpoint_not_found():
    cp = AgentWorkflowCheckpoint()
    assert cp.remove_checkpoint("awcp-missing") is False


def test_get_stats():
    cp = AgentWorkflowCheckpoint()
    cp.create_checkpoint("a1", "wf1", "s1", {})
    cp.create_checkpoint("a2", "wf2", "s2", {})
    cp.create_checkpoint("a1", "wf3", "s1", {})
    stats = cp.get_stats()
    assert stats["total_checkpoints"] == 3
    assert stats["unique_agents"] == 2
    assert stats["unique_workflows"] == 3


def test_get_stats_empty():
    cp = AgentWorkflowCheckpoint()
    stats = cp.get_stats()
    assert stats["total_checkpoints"] == 0
    assert stats["unique_agents"] == 0
    assert stats["unique_workflows"] == 0


def test_reset():
    cp = AgentWorkflowCheckpoint()
    cp.create_checkpoint("a1", "wf1", "s1", {})
    cp._callbacks["cb1"] = lambda a, d: None
    cp.on_change = lambda a, d: None
    cp.reset()
    assert cp.get_stats()["total_checkpoints"] == 0
    assert len(cp._callbacks) == 0
    assert cp.on_change is None


def test_on_change_callback_create():
    events = []
    cp = AgentWorkflowCheckpoint()
    cp.on_change = lambda action, data: events.append(action)
    cp.create_checkpoint("a1", "wf1", "s1", {})
    assert "checkpoint_created" in events


def test_on_change_callback_remove():
    events = []
    cp = AgentWorkflowCheckpoint()
    cp.on_change = lambda action, data: events.append(action)
    cid = cp.create_checkpoint("a1", "wf1", "s1", {})
    cp.remove_checkpoint(cid)
    assert "checkpoint_removed" in events


def test_on_change_callback_restore():
    events = []
    cp = AgentWorkflowCheckpoint()
    cp.on_change = lambda action, data: events.append(action)
    cid = cp.create_checkpoint("a1", "wf1", "s1", {})
    cp.restore_checkpoint(cid)
    assert "checkpoint_restored" in events


def test_on_change_getter_setter():
    cp = AgentWorkflowCheckpoint()
    assert cp.on_change is None
    handler = lambda a, d: None
    cp.on_change = handler
    assert cp.on_change is handler


def test_remove_callback():
    cp = AgentWorkflowCheckpoint()
    cp._callbacks["cb1"] = lambda a, d: None
    assert cp.remove_callback("cb1") is True
    assert cp.remove_callback("cb1") is False


def test_remove_callback_nonexistent():
    cp = AgentWorkflowCheckpoint()
    assert cp.remove_callback("nope") is False


def test_callbacks_dict_fires():
    events = []
    cp = AgentWorkflowCheckpoint()
    cp._callbacks["tracker"] = lambda action, data: events.append((action, data["checkpoint_id"]))
    cid = cp.create_checkpoint("a1", "wf1", "s1", {})
    assert len(events) == 1
    assert events[0][0] == "checkpoint_created"
    assert events[0][1] == cid


def test_callback_exception_silenced():
    cp = AgentWorkflowCheckpoint()
    cp._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
    cp.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("crash"))
    # Should not raise
    cid = cp.create_checkpoint("a1", "wf1", "s1", {})
    assert cid.startswith("awcp-")


def test_create_checkpoint_deep_copies_input():
    cp = AgentWorkflowCheckpoint()
    original = {"nested": {"value": 1}}
    cid = cp.create_checkpoint("a1", "wf1", "s1", original)
    original["nested"]["value"] = 999
    entry = cp.get_checkpoint(cid)
    assert entry["state"]["nested"]["value"] == 1


def test_pruning():
    cp = AgentWorkflowCheckpoint()
    cp.MAX_ENTRIES = 5
    ids = []
    for i in range(7):
        ids.append(cp.create_checkpoint("a1", "wf1", f"s{i}", {"i": i}))
    # After adding 7 with max 5, oldest should be pruned
    assert len(cp._state.entries) <= 6  # pruning happens before insert
    stats = cp.get_stats()
    assert stats["total_checkpoints"] <= 6


def test_prefix_and_max_entries():
    assert AgentWorkflowCheckpoint.PREFIX == "awcp-"
    assert AgentWorkflowCheckpoint.MAX_ENTRIES == 10000


if __name__ == "__main__":
    tests = [
        test_create_checkpoint_returns_id,
        test_create_checkpoint_unique_ids,
        test_get_checkpoint_by_id,
        test_get_checkpoint_not_found,
        test_get_checkpoint_returns_dict,
        test_get_checkpoints_for_agent,
        test_get_checkpoints_filter_workflow,
        test_get_checkpoints_newest_first,
        test_get_checkpoints_limit,
        test_get_checkpoints_default_limit,
        test_get_checkpoints_empty,
        test_restore_checkpoint,
        test_restore_checkpoint_deep_copy,
        test_restore_checkpoint_not_found,
        test_remove_checkpoint,
        test_remove_checkpoint_not_found,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_callback_create,
        test_on_change_callback_remove,
        test_on_change_callback_restore,
        test_on_change_getter_setter,
        test_remove_callback,
        test_remove_callback_nonexistent,
        test_callbacks_dict_fires,
        test_callback_exception_silenced,
        test_create_checkpoint_deep_copies_input,
        test_pruning,
        test_prefix_and_max_entries,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
