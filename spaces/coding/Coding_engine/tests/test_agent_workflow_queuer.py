"""Tests for AgentWorkflowQueuer."""

import sys
import os
import time
import copy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_queuer import AgentWorkflowQueuer


# ------------------------------------------------------------------
# Prefix and ID generation
# ------------------------------------------------------------------


def test_prefix():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a1", "build")
    assert rid.startswith("awqu-")


def test_unique_ids():
    q = AgentWorkflowQueuer()
    ids = [q.queue_workflow("a1", "build") for _ in range(20)]
    assert len(set(ids)) == 20


def test_id_is_string():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a1", "w")
    assert isinstance(rid, str)


# ------------------------------------------------------------------
# Fields stored correctly
# ------------------------------------------------------------------


def test_fields_stored():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("agent1", "deploy", priority=3, metadata={"env": "prod"})
    entry = q.get_queued(rid)
    assert entry is not None
    assert entry["record_id"] == rid
    assert entry["agent_id"] == "agent1"
    assert entry["workflow_name"] == "deploy"
    assert entry["priority"] == 3
    assert entry["metadata"] == {"env": "prod"}


def test_default_priority_zero():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a", "w")
    entry = q.get_queued(rid)
    assert entry["priority"] == 0


def test_default_metadata_none():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a", "w")
    entry = q.get_queued(rid)
    assert entry["metadata"] is None


# ------------------------------------------------------------------
# Deep copy of metadata
# ------------------------------------------------------------------


def test_metadata_deepcopy_on_store():
    q = AgentWorkflowQueuer()
    meta = {"key": [1, 2, 3]}
    rid = q.queue_workflow("a", "w", metadata=meta)
    meta["key"].append(4)
    entry = q.get_queued(rid)
    assert entry["metadata"]["key"] == [1, 2, 3]


def test_metadata_deepcopy_on_get():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a", "w", metadata={"x": 1})
    e1 = q.get_queued(rid)
    e1["metadata"]["x"] = 999
    e2 = q.get_queued(rid)
    assert e2["metadata"]["x"] == 1


# ------------------------------------------------------------------
# created_at
# ------------------------------------------------------------------


def test_created_at_is_set():
    q = AgentWorkflowQueuer()
    before = time.time()
    rid = q.queue_workflow("a", "w")
    after = time.time()
    entry = q.get_queued(rid)
    assert before <= entry["created_at"] <= after


# ------------------------------------------------------------------
# Validation: empty agent_id / workflow_name
# ------------------------------------------------------------------


def test_empty_agent_id_raises():
    q = AgentWorkflowQueuer()
    try:
        q.queue_workflow("", "w")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_empty_workflow_name_raises():
    q = AgentWorkflowQueuer()
    try:
        q.queue_workflow("a", "")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# ------------------------------------------------------------------
# get_queued: found / not found
# ------------------------------------------------------------------


def test_get_queued_found():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a", "w")
    assert q.get_queued(rid) is not None


def test_get_queued_not_found():
    q = AgentWorkflowQueuer()
    assert q.get_queued("awqu-doesnotexist") is None


def test_get_queued_returns_copy():
    q = AgentWorkflowQueuer()
    rid = q.queue_workflow("a", "w")
    e1 = q.get_queued(rid)
    e1["agent_id"] = "modified"
    e2 = q.get_queued(rid)
    assert e2["agent_id"] == "a"


# ------------------------------------------------------------------
# get_queued_items: all / filter / newest / limit
# ------------------------------------------------------------------


def test_get_queued_items_all():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a1", "w1")
    q.queue_workflow("a2", "w2")
    q.queue_workflow("a3", "w3")
    items = q.get_queued_items()
    assert len(items) == 3


def test_get_queued_items_filter_by_agent():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a1", "w1")
    q.queue_workflow("a2", "w2")
    q.queue_workflow("a1", "w3")
    items = q.get_queued_items(agent_id="a1")
    assert len(items) == 2
    assert all(i["agent_id"] == "a1" for i in items)


def test_get_queued_items_filter_empty_result():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a1", "w1")
    items = q.get_queued_items(agent_id="nonexistent")
    assert len(items) == 0


def test_get_queued_items_sorted_by_priority():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a", "low", priority=10)
    q.queue_workflow("a", "high", priority=1)
    q.queue_workflow("a", "mid", priority=5)
    items = q.get_queued_items()
    priorities = [i["priority"] for i in items]
    assert priorities == [1, 5, 10]


def test_get_queued_items_newest_last_same_priority():
    q = AgentWorkflowQueuer()
    r1 = q.queue_workflow("a", "first", priority=0)
    r2 = q.queue_workflow("a", "second", priority=0)
    r3 = q.queue_workflow("a", "third", priority=0)
    items = q.get_queued_items()
    rids = [i["record_id"] for i in items]
    assert rids == [r1, r2, r3]


def test_get_queued_items_returns_copies():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a", "w")
    items = q.get_queued_items()
    items[0]["agent_id"] = "modified"
    assert q.get_queued_items()[0]["agent_id"] == "a"


# ------------------------------------------------------------------
# get_queued_count
# ------------------------------------------------------------------


def test_get_queued_count_all():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a1", "w1")
    q.queue_workflow("a2", "w2")
    assert q.get_queued_count() == 2


def test_get_queued_count_by_agent():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a1", "w1")
    q.queue_workflow("a2", "w2")
    q.queue_workflow("a1", "w3")
    assert q.get_queued_count(agent_id="a1") == 2
    assert q.get_queued_count(agent_id="a2") == 1


def test_get_queued_count_zero():
    q = AgentWorkflowQueuer()
    assert q.get_queued_count() == 0


# ------------------------------------------------------------------
# get_stats
# ------------------------------------------------------------------


def test_stats_empty():
    q = AgentWorkflowQueuer()
    stats = q.get_stats()
    assert stats["total_queued"] == 0
    assert stats["unique_agents"] == 0


def test_stats_populated():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a1", "w1")
    q.queue_workflow("a2", "w2")
    q.queue_workflow("a1", "w3")
    stats = q.get_stats()
    assert stats["total_queued"] == 3
    assert stats["unique_agents"] == 2


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------


def test_on_change_fires_on_queue():
    q = AgentWorkflowQueuer()
    events = []
    q.on_change = lambda e, d: events.append((e, d))
    q.queue_workflow("a", "w")
    assert len(events) == 1
    assert events[0][0] == "queued"


def test_named_callback_fires():
    q = AgentWorkflowQueuer()
    events = []
    q._state.callbacks["cb1"] = lambda e, d: events.append((e, d))
    q.queue_workflow("a", "w")
    assert len(events) == 1
    assert events[0][0] == "queued"


def test_remove_callback():
    q = AgentWorkflowQueuer()
    q._state.callbacks["cb1"] = lambda e, d: None
    assert q.remove_callback("cb1") is True
    assert "cb1" not in q._state.callbacks


def test_remove_callback_nonexistent():
    q = AgentWorkflowQueuer()
    assert q.remove_callback("nope") is False


def test_callback_error_does_not_raise():
    q = AgentWorkflowQueuer()
    q._state.callbacks["bad"] = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
    # Should not raise
    q.queue_workflow("a", "w")


def test_on_change_error_does_not_raise():
    q = AgentWorkflowQueuer()
    q.on_change = lambda e, d: (_ for _ in ()).throw(RuntimeError("boom"))
    q.queue_workflow("a", "w")


# ------------------------------------------------------------------
# Pruning
# ------------------------------------------------------------------


def test_prune_removes_oldest():
    q = AgentWorkflowQueuer()
    q.MAX_ENTRIES = 5
    ids = []
    for i in range(8):
        ids.append(q.queue_workflow(f"a{i}", f"w{i}"))
    assert len(q._state.entries) == 5
    # Oldest 3 should be gone
    for old_id in ids[:3]:
        assert q.get_queued(old_id) is None
    # Newest 5 should remain
    for new_id in ids[3:]:
        assert q.get_queued(new_id) is not None


def test_prune_no_op_under_limit():
    q = AgentWorkflowQueuer()
    q.MAX_ENTRIES = 5
    for i in range(5):
        q.queue_workflow(f"a{i}", f"w{i}")
    assert len(q._state.entries) == 5


def test_prune_exact_at_limit():
    q = AgentWorkflowQueuer()
    q.MAX_ENTRIES = 5
    for i in range(5):
        q.queue_workflow(f"a{i}", f"w{i}")
    assert len(q._state.entries) == 5
    # Adding one more triggers prune
    q.queue_workflow("extra", "wextra")
    assert len(q._state.entries) == 5


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------


def test_reset_clears_entries():
    q = AgentWorkflowQueuer()
    q.queue_workflow("a", "w")
    q.reset()
    assert q.get_queued_count() == 0
    assert len(q._state.entries) == 0


def test_reset_fires_event():
    q = AgentWorkflowQueuer()
    events = []
    q.on_change = lambda e, d: events.append(e)
    q.reset()
    assert "reset" in events


def test_reset_clears_callbacks():
    q = AgentWorkflowQueuer()
    q._state.callbacks["cb1"] = lambda e, d: None
    q.reset()
    assert len(q._state.callbacks) == 0
