"""Tests for PipelineStepRetirer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_retirer import PipelineStepRetirer

class TestId:
    def test_prefix(self):
        assert PipelineStepRetirer().retire("p1", "s1").startswith("psrt-")
    def test_unique(self):
        s = PipelineStepRetirer()
        assert len({s.retire("p1", f"s{i}") for i in range(20)}) == 20

class TestBasic:
    def test_returns_id(self):
        assert len(PipelineStepRetirer().retire("p1", "s1")) > 0
    def test_fields(self):
        s = PipelineStepRetirer()
        e = s.get_retirement(s.retire("p1", "s1", reason="old"))
        assert e["pipeline_id"] == "p1" and e["step_name"] == "s1" and e["reason"] == "old"
    def test_deepcopy(self):
        s = PipelineStepRetirer(); m = {"a": [1]}
        rid = s.retire("p1", "s1", metadata=m); m["a"].append(2)
        assert s.get_retirement(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepRetirer(); b = time.time()
        assert s.get_retirement(s.retire("p1", "s1"))["created_at"] >= b
    def test_empty_pipeline(self):
        assert PipelineStepRetirer().retire("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepRetirer().retire("p1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineStepRetirer(); assert s.get_retirement(s.retire("p1", "s1")) is not None
    def test_not_found(self):
        assert PipelineStepRetirer().get_retirement("xxx") is None
    def test_copy(self):
        s = PipelineStepRetirer(); rid = s.retire("p1", "s1")
        assert s.get_retirement(rid) is not s.get_retirement(rid)

class TestList:
    def test_all(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p2", "s2")
        assert len(s.get_retirements()) == 2
    def test_filter(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p2", "s2")
        assert len(s.get_retirements(pipeline_id="p1")) == 1
    def test_newest(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p1", "s2")
        assert s.get_retirements(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepRetirer()
        for i in range(10): s.retire("p1", f"s{i}")
        assert len(s.get_retirements(limit=3)) == 3

class TestCount:
    def test_total(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p2", "s2")
        assert s.get_retirement_count() == 2
    def test_filtered(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p2", "s2")
        assert s.get_retirement_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepRetirer().get_retirement_count() == 0

class TestStats:
    def test_empty(self):
        assert PipelineStepRetirer().get_stats()["total_retirements"] == 0
    def test_data(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p2", "s2")
        assert s.get_stats()["total_retirements"] == 2
    def test_unique_pipelines(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p2", "s2")
        assert s.get_stats()["unique_pipelines"] == 2
    def test_unique_pipelines_dedup(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.retire("p1", "s2")
        assert s.get_stats()["unique_pipelines"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepRetirer(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.retire("p1", "s1")
        assert len(evts) >= 1
    def test_on_change_action(self):
        s = PipelineStepRetirer(); evts = []
        s.on_change = lambda a, d: evts.append(a); s.retire("p1", "s1")
        assert "retired" in evts
    def test_registered_callback(self):
        s = PipelineStepRetirer(); evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.retire("p1", "s1")
        assert len(evts) >= 1
    def test_remove_true(self):
        s = PipelineStepRetirer(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        assert PipelineStepRetirer().remove_callback("x") is False
    def test_callback_error_handled(self):
        s = PipelineStepRetirer()
        s._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError)
        rid = s.retire("p1", "s1")
        assert rid != ""

class TestPrune:
    def test_prune(self):
        s = PipelineStepRetirer(); s.MAX_ENTRIES = 5
        for i in range(8): s.retire("p1", f"s{i}")
        assert s.get_retirement_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.reset()
        assert s.get_retirement_count() == 0
    def test_callbacks(self):
        s = PipelineStepRetirer(); s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None
    def test_seq(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.reset()
        assert s._state._seq == 0
    def test_stats_after_reset(self):
        s = PipelineStepRetirer(); s.retire("p1", "s1"); s.reset()
        assert s.get_stats()["total_retirements"] == 0
