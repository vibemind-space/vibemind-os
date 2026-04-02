from __future__ import annotations

import copy

import pytest

from src.services.agent_task_blocker_v2 import AgentTaskBlockerV2, AgentTaskBlockerV2State


# ── helpers ──────────────────────────────────────────────────────────
def _make() -> AgentTaskBlockerV2:
    return AgentTaskBlockerV2()


# ── TestBasic ────────────────────────────────────────────────────────
class TestBasic:
    def test_prefix(self):
        b = _make()
        rid = b.block_v2("t1", "a1")
        assert rid.startswith("atbv-")

    def test_fields_stored(self):
        b = _make()
        rid = b.block_v2("t1", "a1", reason="busy", metadata={"k": 1})
        entry = b.get_block(rid)
        assert entry["task_id"] == "t1"
        assert entry["agent_id"] == "a1"
        assert entry["reason"] == "busy"
        assert entry["metadata"] == {"k": 1}
        assert "created_at" in entry
        assert "_seq" in entry

    def test_default_reason_empty(self):
        b = _make()
        rid = b.block_v2("t1", "a1")
        assert b.get_block(rid)["reason"] == ""

    def test_get_block_returns_deepcopy(self):
        b = _make()
        rid = b.block_v2("t1", "a1", metadata={"x": [1]})
        entry = b.get_block(rid)
        entry["metadata"]["x"].append(2)
        assert b.get_block(rid)["metadata"]["x"] == [1]

    def test_empty_task_id_returns_empty(self):
        b = _make()
        assert b.block_v2("", "a1") == ""

    def test_empty_agent_id_returns_empty(self):
        b = _make()
        assert b.block_v2("t1", "") == ""


# ── TestGet ──────────────────────────────────────────────────────────
class TestGet:
    def test_found(self):
        b = _make()
        rid = b.block_v2("t1", "a1")
        assert b.get_block(rid) is not None

    def test_not_found_returns_none(self):
        b = _make()
        assert b.get_block("nonexistent") is None

    def test_returns_copy(self):
        b = _make()
        rid = b.block_v2("t1", "a1")
        a = b.get_block(rid)
        bx = b.get_block(rid)
        assert a is not bx
        assert a == bx


# ── TestList ─────────────────────────────────────────────────────────
class TestList:
    def test_all(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.block_v2("t2", "a2")
        assert len(b.get_blocks()) == 2

    def test_filter_agent_id(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.block_v2("t2", "a2")
        b.block_v2("t3", "a1")
        results = b.get_blocks(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_newest_first(self):
        b = _make()
        r1 = b.block_v2("t1", "a1")
        r2 = b.block_v2("t2", "a1")
        blocks = b.get_blocks()
        assert blocks[0]["record_id"] == r2
        assert blocks[1]["record_id"] == r1


# ── TestCount ────────────────────────────────────────────────────────
class TestCount:
    def test_total(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.block_v2("t2", "a2")
        assert b.get_block_count() == 2

    def test_filtered(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.block_v2("t2", "a2")
        b.block_v2("t3", "a1")
        assert b.get_block_count(agent_id="a1") == 2


# ── TestStats ────────────────────────────────────────────────────────
class TestStats:
    def test_stats(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.block_v2("t2", "a2")
        b.block_v2("t3", "a1")
        stats = b.get_stats()
        assert stats["total_blocks"] == 3
        assert stats["unique_agents"] == 2


# ── TestCallbacks ────────────────────────────────────────────────────
class TestCallbacks:
    def test_on_change_called(self):
        calls = []
        b = AgentTaskBlockerV2(_on_change=lambda action, data: calls.append((action, data)))
        b.block_v2("t1", "a1")
        assert len(calls) == 1
        assert calls[0][0] == "block_v2"
        assert "action" in calls[0][1]

    def test_registered_callback(self):
        calls = []
        b = _make()
        b._state.callbacks["cb1"] = lambda action, data: calls.append((action, data))
        b.block_v2("t1", "a1")
        assert len(calls) == 1

    def test_remove_callback_true(self):
        calls = []
        b = _make()
        b._state.callbacks["cb1"] = lambda action, data: calls.append(data)
        b.block_v2("t1", "a1")
        del b._state.callbacks["cb1"]
        b.block_v2("t2", "a2")
        assert len(calls) == 1

    def test_remove_callback_false(self):
        calls = []
        b = _make()
        b._state.callbacks["cb1"] = lambda action, data: calls.append(data)
        b.block_v2("t1", "a1")
        b.block_v2("t2", "a2")
        assert len(calls) == 2


# ── TestPrune ────────────────────────────────────────────────────────
class TestPrune:
    def test_prune_at_max_plus_5(self):
        b = AgentTaskBlockerV2()
        b.MAX_ENTRIES = 5
        for i in range(10):
            b.block_v2(f"t{i}", f"a{i}")
        assert b.get_block_count() == 5

    def test_prune_at_max_plus_7(self):
        b = AgentTaskBlockerV2()
        b.MAX_ENTRIES = 3
        for i in range(10):
            b.block_v2(f"t{i}", f"a{i}")
        assert b.get_block_count() == 3


# ── TestReset ────────────────────────────────────────────────────────
class TestReset:
    def test_clears_entries(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.reset()
        assert b.get_block_count() == 0

    def test_on_change_none_after_reset(self):
        b = AgentTaskBlockerV2(_on_change=lambda a, d: None)
        b.reset()
        assert b._on_change is None

    def test_seq_zero_after_reset(self):
        b = _make()
        b.block_v2("t1", "a1")
        b.reset()
        assert b._state._seq == 0
