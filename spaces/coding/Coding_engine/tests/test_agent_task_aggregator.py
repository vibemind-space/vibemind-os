"""Tests for AgentTaskAggregator service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_aggregator import AgentTaskAggregator

class TestIdGeneration:
    def test_prefix(self):
        s = AgentTaskAggregator()
        assert s.aggregate(["t1"], "a1").startswith("atag-")
    def test_unique(self):
        s = AgentTaskAggregator()
        ids = {s.aggregate([f"t{i}"], "a1") for i in range(20)}
        assert len(ids) == 20

class TestAggregateBasic:
    def test_returns_id(self):
        s = AgentTaskAggregator()
        assert len(s.aggregate(["t1"], "a1")) > 0
    def test_stores_fields(self):
        s = AgentTaskAggregator()
        rid = s.aggregate(["t1", "t2"], "a1", label="batch1")
        e = s.get_aggregation(rid)
        assert e["task_ids"] == ["t1", "t2"]
        assert e["agent_id"] == "a1"
        assert e["label"] == "batch1"
    def test_with_metadata(self):
        s = AgentTaskAggregator()
        rid = s.aggregate(["t1"], "a1", metadata={"x": 1})
        assert s.get_aggregation(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentTaskAggregator()
        m = {"a": [1]}
        rid = s.aggregate(["t1"], "a1", metadata=m)
        m["a"].append(2)
        assert s.get_aggregation(rid)["metadata"]["a"] == [1]
    def test_task_ids_copy(self):
        s = AgentTaskAggregator()
        ids = ["t1", "t2"]
        rid = s.aggregate(ids, "a1")
        ids.append("t3")
        assert s.get_aggregation(rid)["task_ids"] == ["t1", "t2"]
    def test_created_at(self):
        s = AgentTaskAggregator()
        before = time.time()
        rid = s.aggregate(["t1"], "a1")
        assert s.get_aggregation(rid)["created_at"] >= before
    def test_empty_tasks_returns_empty(self):
        assert AgentTaskAggregator().aggregate([], "a1") == ""
    def test_empty_agent_returns_empty(self):
        assert AgentTaskAggregator().aggregate(["t1"], "") == ""

class TestGetAggregation:
    def test_found(self):
        s = AgentTaskAggregator()
        rid = s.aggregate(["t1"], "a1")
        assert s.get_aggregation(rid) is not None
    def test_not_found(self):
        assert AgentTaskAggregator().get_aggregation("xxx") is None
    def test_returns_copy(self):
        s = AgentTaskAggregator()
        rid = s.aggregate(["t1"], "a1")
        assert s.get_aggregation(rid) is not s.get_aggregation(rid)

class TestGetAggregations:
    def test_all(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.aggregate(["t2"], "a2")
        assert len(s.get_aggregations()) == 2
    def test_filter(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.aggregate(["t2"], "a2")
        assert len(s.get_aggregations(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.aggregate(["t2"], "a1")
        assert s.get_aggregations(agent_id="a1")[0]["task_ids"] == ["t2"]
    def test_limit(self):
        s = AgentTaskAggregator()
        for i in range(10): s.aggregate([f"t{i}"], "a1")
        assert len(s.get_aggregations(limit=3)) == 3

class TestGetAggregationCount:
    def test_total(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.aggregate(["t2"], "a2")
        assert s.get_aggregation_count() == 2
    def test_filtered(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.aggregate(["t2"], "a2")
        assert s.get_aggregation_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentTaskAggregator().get_aggregation_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskAggregator().get_stats()["total_aggregations"] == 0
    def test_with_data(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.aggregate(["t2"], "a2")
        st = s.get_stats()
        assert st["total_aggregations"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentTaskAggregator()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.aggregate(["t1"], "a1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentTaskAggregator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskAggregator().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentTaskAggregator()
        s.MAX_ENTRIES = 5
        for i in range(8): s.aggregate([f"t{i}"], "a1")
        assert s.get_aggregation_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.reset()
        assert s.get_aggregation_count() == 0
    def test_clears_callbacks(self):
        s = AgentTaskAggregator()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentTaskAggregator()
        s.aggregate(["t1"], "a1"); s.reset()
        assert s._state._seq == 0
