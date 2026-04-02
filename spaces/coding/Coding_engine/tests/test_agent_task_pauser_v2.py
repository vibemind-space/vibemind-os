"""Tests for AgentTaskPauserV2 service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_pauser_v2 import AgentTaskPauserV2


class TestBasic:
    def test_prefix(self):
        assert AgentTaskPauserV2().pause_v2("t1", "a1").startswith("atpv-")

    def test_stores_fields(self):
        s = AgentTaskPauserV2()
        rid = s.pause_v2("t1", "a1", reason="waiting")
        e = s.get_pause(rid)
        assert e["task_id"] == "t1"
        assert e["agent_id"] == "a1"
        assert e["reason"] == "waiting"
        assert e["record_id"] == rid
        assert "created_at" in e
        assert "updated_at" in e
        assert "_seq" in e

    def test_default_reason_empty(self):
        s = AgentTaskPauserV2()
        rid = s.pause_v2("t1", "a1")
        assert s.get_pause(rid)["reason"] == ""

    def test_metadata_deepcopy(self):
        s = AgentTaskPauserV2()
        m = {"a": [1]}
        rid = s.pause_v2("t1", "a1", metadata=m)
        m["a"].append(2)
        assert s.get_pause(rid)["metadata"]["a"] == [1]

    def test_empty_task_id_returns_empty(self):
        assert AgentTaskPauserV2().pause_v2("", "a1") == ""

    def test_empty_agent_id_returns_empty(self):
        assert AgentTaskPauserV2().pause_v2("t1", "") == ""

    def test_unique_ids(self):
        s = AgentTaskPauserV2()
        ids = {s.pause_v2(f"t{i}", "a1") for i in range(20)}
        assert len(ids) == 20


class TestGet:
    def test_found(self):
        s = AgentTaskPauserV2()
        rid = s.pause_v2("t1", "a1")
        assert s.get_pause(rid) is not None

    def test_not_found_returns_none(self):
        assert AgentTaskPauserV2().get_pause("nonexistent") is None

    def test_returns_copy(self):
        s = AgentTaskPauserV2()
        rid = s.pause_v2("t1", "a1")
        a = s.get_pause(rid)
        b = s.get_pause(rid)
        assert a is not b
        assert a == b


class TestList:
    def test_all(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a2")
        assert len(s.get_pauses()) == 2

    def test_filter_by_agent_id(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a2")
        s.pause_v2("t3", "a1")
        result = s.get_pauses(agent_id="a1")
        assert len(result) == 2
        assert all(e["agent_id"] == "a1" for e in result)

    def test_newest_first_by_seq(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a1")
        s.pause_v2("t3", "a1")
        result = s.get_pauses(agent_id="a1")
        assert result[0]["task_id"] == "t3"
        assert result[-1]["task_id"] == "t1"

    def test_limit(self):
        s = AgentTaskPauserV2()
        for i in range(10):
            s.pause_v2(f"t{i}", "a1")
        assert len(s.get_pauses(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a2")
        assert s.get_pause_count() == 2

    def test_filtered_by_agent_id(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a2")
        s.pause_v2("t3", "a1")
        assert s.get_pause_count(agent_id="a1") == 2

    def test_empty(self):
        assert AgentTaskPauserV2().get_pause_count() == 0


class TestStats:
    def test_empty_stats(self):
        stats = AgentTaskPauserV2().get_stats()
        assert stats["total_pauses"] == 0
        assert stats["unique_agents"] == 0

    def test_stats_with_data(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a2")
        s.pause_v2("t3", "a1")
        stats = s.get_stats()
        assert stats["total_pauses"] == 3
        assert stats["unique_agents"] == 2


class TestCallbacks:
    def test_on_change_fires(self):
        s = AgentTaskPauserV2()
        events = []
        s._on_change = lambda action, data: events.append((action, data))
        s.pause_v2("t1", "a1")
        assert len(events) >= 1
        assert events[0][0] == "paused"
        assert "action" in events[0][1]

    def test_registered_callback_fires(self):
        s = AgentTaskPauserV2()
        events = []
        s._state.callbacks["cb1"] = lambda action, data: events.append(action)
        s.pause_v2("t1", "a1")
        assert "paused" in events

    def test_remove_callback_true(self):
        s = AgentTaskPauserV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_callback_false(self):
        assert AgentTaskPauserV2().remove_callback("nonexistent") is False


class TestPrune:
    def test_prune_removes_oldest(self):
        s = AgentTaskPauserV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.pause_v2(f"t{i}", "a1")
        assert s.get_pause_count() < 7


class TestReset:
    def test_clears_entries(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a2")
        s.reset()
        assert s.get_pause_count() == 0

    def test_on_change_none_after_reset(self):
        s = AgentTaskPauserV2()
        s._on_change = lambda a, d: None
        s.reset()
        assert s._on_change is None

    def test_seq_zero_after_reset(self):
        s = AgentTaskPauserV2()
        s.pause_v2("t1", "a1")
        s.pause_v2("t2", "a1")
        s.reset()
        assert s._state._seq == 0
