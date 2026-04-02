"""Tests for AgentTaskBlocker service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_blocker import AgentTaskBlocker


# -- prefix and id generation --

def test_block_returns_id_with_prefix():
    s = AgentTaskBlocker()
    rid = s.block("t1", "a1")
    assert rid.startswith("atbl-")
    assert len(rid) > len("atbl-")


def test_block_returns_unique_ids():
    s = AgentTaskBlocker()
    r1 = s.block("t1", "a1")
    r2 = s.block("t1", "a1")
    assert r1 != r2


# -- fields stored correctly --

def test_block_stores_all_fields():
    s = AgentTaskBlocker()
    rid = s.block("t1", "a1", reason="quota", metadata={"key": "val"})
    entry = s.get_block(rid)
    assert entry["record_id"] == rid
    assert entry["task_id"] == "t1"
    assert entry["agent_id"] == "a1"
    assert entry["reason"] == "quota"
    assert entry["metadata"] == {"key": "val"}
    assert isinstance(entry["created_at"], float)
    assert isinstance(entry["_seq"], int)


def test_block_metadata_deepcopy():
    s = AgentTaskBlocker()
    meta = {"items": [1, 2, 3]}
    rid = s.block("t1", "a1", metadata=meta)
    meta["items"].append(4)
    entry = s.get_block(rid)
    assert entry["metadata"]["items"] == [1, 2, 3]


def test_block_created_at_is_recent():
    before = time.time()
    s = AgentTaskBlocker()
    rid = s.block("t1", "a1")
    after = time.time()
    entry = s.get_block(rid)
    assert before <= entry["created_at"] <= after


# -- validation --

def test_block_empty_task_id():
    s = AgentTaskBlocker()
    assert s.block("", "a1") == ""


def test_block_empty_agent_id():
    s = AgentTaskBlocker()
    assert s.block("t1", "") == ""


def test_block_both_empty():
    s = AgentTaskBlocker()
    assert s.block("", "") == ""


# -- get_block --

def test_get_block_found():
    s = AgentTaskBlocker()
    rid = s.block("t1", "a1")
    entry = s.get_block(rid)
    assert entry["record_id"] == rid


def test_get_block_not_found():
    s = AgentTaskBlocker()
    assert s.get_block("atbl-nonexistent") == {}


def test_get_block_returns_copy():
    s = AgentTaskBlocker()
    rid = s.block("t1", "a1", metadata={"x": 1})
    entry = s.get_block(rid)
    entry["reason"] = "modified"
    original = s.get_block(rid)
    assert original["reason"] != "modified"


# -- get_blocks --

def test_get_blocks_all():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.block("t2", "a2")
    s.block("t3", "a1")
    results = s.get_blocks()
    assert len(results) == 3


def test_get_blocks_filter_agent():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.block("t2", "a2")
    s.block("t3", "a1")
    results = s.get_blocks(agent_id="a1")
    assert len(results) == 2
    assert all(r["agent_id"] == "a1" for r in results)


def test_get_blocks_filter_no_match():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    results = s.get_blocks(agent_id="a99")
    assert results == []


def test_get_blocks_newest_last():
    s = AgentTaskBlocker()
    r1 = s.block("t1", "a1")
    r2 = s.block("t2", "a1")
    results = s.get_blocks()
    assert results[0]["record_id"] == r1
    assert results[1]["record_id"] == r2


def test_get_blocks_respects_limit():
    s = AgentTaskBlocker()
    for i in range(10):
        s.block(f"t{i}", "a1")
    results = s.get_blocks()
    assert len(results) == 10


# -- get_block_count --

def test_get_block_count_all():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.block("t2", "a2")
    assert s.get_block_count() == 2


def test_get_block_count_filtered():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.block("t2", "a2")
    s.block("t3", "a1")
    assert s.get_block_count(agent_id="a1") == 2
    assert s.get_block_count(agent_id="a2") == 1
    assert s.get_block_count(agent_id="a99") == 0


# -- get_stats --

def test_get_stats():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.block("t2", "a2")
    s.block("t3", "a1")
    stats = s.get_stats()
    assert stats["total_blocks"] == 3
    assert stats["unique_agents"] == 2


def test_get_stats_empty():
    s = AgentTaskBlocker()
    stats = s.get_stats()
    assert stats["total_blocks"] == 0
    assert stats["unique_agents"] == 0


# -- callbacks --

def test_on_change_fires_on_block():
    events = []
    s = AgentTaskBlocker()
    s.on_change = lambda evt, data: events.append(evt)
    s.block("t1", "a1")
    assert "blocked" in events


def test_named_callback_fires():
    events = []
    s = AgentTaskBlocker()
    s._state.callbacks["cb1"] = lambda evt, data: events.append(evt)
    s.block("t1", "a1")
    assert "blocked" in events


def test_remove_callback_existing():
    s = AgentTaskBlocker()
    s._state.callbacks["cb1"] = lambda e, d: None
    assert s.remove_callback("cb1") is True
    assert "cb1" not in s._state.callbacks


def test_remove_callback_missing():
    s = AgentTaskBlocker()
    assert s.remove_callback("cb-nope") is False


# -- prune --

def test_prune_removes_oldest():
    s = AgentTaskBlocker()
    s.MAX_ENTRIES = 5
    ids = []
    for i in range(8):
        ids.append(s.block(f"t{i}", "a1"))
    assert s.get_block_count() == 5
    # oldest entries should be gone
    assert s.get_block(ids[0]) == {}
    assert s.get_block(ids[1]) == {}
    assert s.get_block(ids[2]) == {}


def test_prune_keeps_under_max():
    s = AgentTaskBlocker()
    s.MAX_ENTRIES = 5
    for i in range(3):
        s.block(f"t{i}", "a1")
    assert s.get_block_count() == 3


def test_prune_exactly_at_max():
    s = AgentTaskBlocker()
    s.MAX_ENTRIES = 5
    for i in range(5):
        s.block(f"t{i}", "a1")
    assert s.get_block_count() == 5


# -- reset --

def test_reset_clears_entries():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.block("t2", "a2")
    s.reset()
    assert s.get_block_count() == 0
    assert s.get_blocks() == []


def test_reset_clears_callbacks():
    s = AgentTaskBlocker()
    s._state.callbacks["cb1"] = lambda e, d: None
    s.on_change = lambda e, d: None
    s.reset()
    assert len(s._state.callbacks) == 0
    assert s.on_change is None


def test_reset_clears_stats():
    s = AgentTaskBlocker()
    s.block("t1", "a1")
    s.reset()
    stats = s.get_stats()
    assert stats["total_blocks"] == 0
    assert stats["unique_agents"] == 0


if __name__ == "__main__":
    tests = [
        test_block_returns_id_with_prefix,
        test_block_returns_unique_ids,
        test_block_stores_all_fields,
        test_block_metadata_deepcopy,
        test_block_created_at_is_recent,
        test_block_empty_task_id,
        test_block_empty_agent_id,
        test_block_both_empty,
        test_get_block_found,
        test_get_block_not_found,
        test_get_block_returns_copy,
        test_get_blocks_all,
        test_get_blocks_filter_agent,
        test_get_blocks_filter_no_match,
        test_get_blocks_newest_last,
        test_get_blocks_respects_limit,
        test_get_block_count_all,
        test_get_block_count_filtered,
        test_get_stats,
        test_get_stats_empty,
        test_on_change_fires_on_block,
        test_named_callback_fires,
        test_remove_callback_existing,
        test_remove_callback_missing,
        test_prune_removes_oldest,
        test_prune_keeps_under_max,
        test_prune_exactly_at_max,
        test_reset_clears_entries,
        test_reset_clears_callbacks,
        test_reset_clears_stats,
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
