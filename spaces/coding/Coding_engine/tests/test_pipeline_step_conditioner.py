"""Tests for PipelineStepConditioner service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_conditioner import PipelineStepConditioner

class TestId:
    def test_prefix(self):
        assert PipelineStepConditioner().condition("p1", "s1").startswith("pscd-")
    def test_unique(self):
        s = PipelineStepConditioner()
        assert len({s.condition("p1", f"s{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(PipelineStepConditioner().condition("p1", "s1")) > 0
    def test_fields(self):
        s = PipelineStepConditioner()
        e = s.get_condition(s.condition("p1", "s1", expression="x>0"))
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["expression"] == "x>0"
    def test_deepcopy(self):
        s = PipelineStepConditioner(); m = {"a": [1]}
        rid = s.condition("p1", "s1", metadata=m); m["a"].append(2)
        assert s.get_condition(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepConditioner(); b = time.time()
        assert s.get_condition(s.condition("p1", "s1"))["created_at"] >= b
    def test_empty_pipeline(self):
        assert PipelineStepConditioner().condition("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepConditioner().condition("p1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineStepConditioner(); assert s.get_condition(s.condition("p1", "s1")) is not None
    def test_not_found(self):
        assert PipelineStepConditioner().get_condition("xxx") is None
    def test_copy(self):
        s = PipelineStepConditioner(); rid = s.condition("p1", "s1")
        assert s.get_condition(rid) is not s.get_condition(rid)

class TestList:
    def test_all(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.condition("p2", "s2")
        assert len(s.get_conditions()) == 2
    def test_filter(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.condition("p2", "s2")
        assert len(s.get_conditions(pipeline_id="p1")) == 1
    def test_newest(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.condition("p1", "s2")
        assert s.get_conditions(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepConditioner()
        for i in range(10): s.condition("p1", f"s{i}")
        assert len(s.get_conditions(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.condition("p2", "s2")
        assert s.get_condition_count() == 2
    def test_filtered(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.condition("p2", "s2")
        assert s.get_condition_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepConditioner().get_condition_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineStepConditioner().get_stats()["total_conditions"] == 0
    def test_data(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.condition("p2", "s2")
        assert s.get_stats()["total_conditions"] == 2 and s.get_stats()["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepConditioner(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.condition("p1", "s1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = PipelineStepConditioner(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepConditioner().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepConditioner(); s.MAX_ENTRIES = 5
        for i in range(8): s.condition("p1", f"s{i}")
        assert s.get_condition_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.reset()
        assert s.get_condition_count() == 0
    def test_callbacks(self):
        s = PipelineStepConditioner(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineStepConditioner(); s.condition("p1", "s1"); s.reset()
        assert s._state._seq == 0
