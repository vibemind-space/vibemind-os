"""Tests for AgentTaskReassigner."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_reassigner import AgentTaskReassigner


# -- ID generation --

def test_id_has_prefix():
    s = AgentTaskReassigner()
    rid = s.reassign("t1", "a1", "a2")
    assert rid.startswith("atra-")


def test_id_uniqueness():
    s = AgentTaskReassigner()
    ids = {s.reassign("t1", "a1", "a2") for _ in range(20)}
    assert len(ids) == 20


# -- reassign stores fields --

def test_reassign_stores_fields():
    s = AgentTaskReassigner()
    rid = s.reassign("t1", "a1", "a2", reason="busy", metadata={"k": "v"})
    entry = s.get_reassignment(rid)
    assert entry["record_id"] == rid
    assert entry["task_id"] == "t1"
    assert entry["from_agent"] == "a1"
    assert entry["to_agent"] == "a2"
    assert entry["reason"] == "busy"
    assert entry["metadata"] == {"k": "v"}


def test_metadata_deepcopy():
    s = AgentTaskReassigner()
    meta = {"key": [1, 2]}
    rid = s.reassign("t1", "a1", "a2", metadata=meta)
    meta["key"].append(3)
    entry = s.get_reassignment(rid)
    assert entry["metadata"]["key"] == [1, 2]


def test_created_at_is_set():
    s = AgentTaskReassigner()
    before = time.time()
    rid = s.reassign("t1", "a1", "a2")
    after = time.time()
    entry = s.get_reassignment(rid)
    assert before <= entry["created_at"] <= after


# -- empty / invalid input --

def test_empty_task_id_returns_empty():
    s = AgentTaskReassigner()
    assert s.reassign("", "a1", "a2") == ""


def test_empty_from_agent_returns_empty():
    s = AgentTaskReassigner()
    assert s.reassign("t1", "", "a2") == ""


def test_empty_to_agent_returns_empty():
    s = AgentTaskReassigner()
    assert s.reassign("t1", "a1", "") == ""


# -- get_reassignment --

def test_get_reassignment_found():
    s = AgentTaskReassigner()
    rid = s.reassign("t1", "a1", "a2")
    entry = s.get_reassignment(rid)
    assert entry is not None
    assert entry["task_id"] == "t1"


def test_get_reassignment_not_found():
    s = AgentTaskReassigner()
    assert s.get_reassignment("nonexistent") is None


def test_get_reassignment_returns_copy():
    s = AgentTaskReassigner()
    rid = s.reassign("t1", "a1", "a2")
    e1 = s.get_reassignment(rid)
    e2 = s.get_reassignment(rid)
    assert e1 is not e2


# -- get_reassignments (list) --

def test_get_reassignments_all():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reassign("t2", "a3", "a4")
    results = s.get_reassignments()
    assert len(results) == 2


def test_get_reassignments_filter_from_agent():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reassign("t2", "a3", "a4")
    s.reassign("t3", "a1", "a5")
    results = s.get_reassignments(from_agent="a1")
    assert len(results) == 2
    assert all(r["from_agent"] == "a1" for r in results)


def test_get_reassignments_newest_first():
    s = AgentTaskReassigner()
    r1 = s.reassign("t1", "a1", "a2")
    r2 = s.reassign("t2", "a1", "a3")
    results = s.get_reassignments()
    assert results[0]["record_id"] == r2
    assert results[1]["record_id"] == r1


def test_get_reassignments_limit():
    s = AgentTaskReassigner()
    for i in range(10):
        s.reassign(f"t{i}", "a1", "a2")
    results = s.get_reassignments(limit=3)
    assert len(results) == 3


# -- get_reassignment_count --

def test_count_total():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reassign("t2", "a3", "a4")
    assert s.get_reassignment_count() == 2


def test_count_filtered():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reassign("t2", "a3", "a4")
    s.reassign("t3", "a1", "a5")
    assert s.get_reassignment_count(from_agent="a1") == 2


def test_count_empty():
    s = AgentTaskReassigner()
    assert s.get_reassignment_count() == 0


# -- get_stats --

def test_stats_empty():
    s = AgentTaskReassigner()
    stats = s.get_stats()
    assert stats["total_reassignments"] == 0
    assert stats["unique_agents"] == 0


def test_stats_with_data():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reassign("t2", "a1", "a3")
    stats = s.get_stats()
    assert stats["total_reassignments"] == 2
    # unique agents: a1, a2, a3 (both from and to)
    assert stats["unique_agents"] == 3


# -- callbacks --

def test_on_change_callback():
    s = AgentTaskReassigner()
    calls = []
    s.on_change = lambda action, data: calls.append((action, data))
    s.reassign("t1", "a1", "a2")
    assert len(calls) == 1
    assert calls[0][0] == "reassigned"


def test_callback_via_state():
    s = AgentTaskReassigner()
    calls = []
    s._state.callbacks["cb1"] = lambda action, data: calls.append(action)
    s.reassign("t1", "a1", "a2")
    assert calls == ["reassigned"]


def test_remove_callback_true():
    s = AgentTaskReassigner()
    s._state.callbacks["cb1"] = lambda a, d: None
    assert s.remove_callback("cb1") is True


def test_remove_callback_false():
    s = AgentTaskReassigner()
    assert s.remove_callback("nonexistent") is False


# -- prune --

def test_prune_removes_oldest():
    s = AgentTaskReassigner()
    s.MAX_ENTRIES = 5
    for i in range(8):
        s.reassign(f"t{i}", "a1", "a2")
    assert s.get_reassignment_count() < 8


# -- reset --

def test_reset_clears_entries():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reset()
    assert s.get_reassignment_count() == 0


def test_reset_clears_callbacks():
    s = AgentTaskReassigner()
    s._state.callbacks["cb1"] = lambda a, d: None
    s.on_change = lambda a, d: None
    s.reset()
    assert len(s._state.callbacks) == 0
    assert s.on_change is None


def test_reset_resets_seq():
    s = AgentTaskReassigner()
    s.reassign("t1", "a1", "a2")
    s.reset()
    assert s._state._seq == 0


def test_reassign_default_reason_empty():
    s = AgentTaskReassigner()
    rid = s.reassign("t1", "a1", "a2")
    entry = s.get_reassignment(rid)
    assert entry["reason"] == ""


def test_reassign_default_metadata_empty_dict():
    s = AgentTaskReassigner()
    rid = s.reassign("t1", "a1", "a2")
    entry = s.get_reassignment(rid)
    assert entry["metadata"] == {}


def test_get_reassignments_empty():
    s = AgentTaskReassigner()
    assert s.get_reassignments() == []


def test_stats_unique_agents_counts_both_directions():
    s = AgentTaskReassigner()
    # a1 -> a2, so unique agents = {a1, a2}
    s.reassign("t1", "a1", "a2")
    stats = s.get_stats()
    assert stats["unique_agents"] == 2


def test_on_change_property_getter():
    s = AgentTaskReassigner()
    assert s.on_change is None
    fn = lambda a, d: None
    s.on_change = fn
    assert s.on_change is fn
