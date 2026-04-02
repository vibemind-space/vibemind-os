"""Tests for PipelineStepThrottler service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_throttler import PipelineStepThrottler

class TestIdGeneration:
    def test_prefix(self):
        assert PipelineStepThrottler().throttle("p1", "s1").startswith("psth-")
    def test_unique(self):
        s = PipelineStepThrottler()
        ids = {s.throttle("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20

class TestThrottleBasic:
    def test_returns_id(self):
        assert len(PipelineStepThrottler().throttle("p1", "s1")) > 0
    def test_stores_fields(self):
        s = PipelineStepThrottler()
        rid = s.throttle("p1", "s1", max_rate=50)
        e = s.get_throttle(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "s1"
        assert e["max_rate"] == 50
    def test_default_rate(self):
        s = PipelineStepThrottler(); rid = s.throttle("p1", "s1")
        assert s.get_throttle(rid)["max_rate"] == 100
    def test_with_metadata(self):
        s = PipelineStepThrottler()
        rid = s.throttle("p1", "s1", metadata={"x": 1})
        assert s.get_throttle(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepThrottler(); m = {"a": [1]}
        rid = s.throttle("p1", "s1", metadata=m); m["a"].append(2)
        assert s.get_throttle(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepThrottler(); before = time.time()
        rid = s.throttle("p1", "s1")
        assert s.get_throttle(rid)["created_at"] >= before
    def test_empty_pipeline(self):
        assert PipelineStepThrottler().throttle("", "s1") == ""
    def test_empty_step(self):
        assert PipelineStepThrottler().throttle("p1", "") == ""

class TestGetThrottle:
    def test_found(self):
        s = PipelineStepThrottler(); rid = s.throttle("p1", "s1")
        assert s.get_throttle(rid) is not None
    def test_not_found(self):
        assert PipelineStepThrottler().get_throttle("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepThrottler(); rid = s.throttle("p1", "s1")
        assert s.get_throttle(rid) is not s.get_throttle(rid)

class TestGetThrottles:
    def test_all(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.throttle("p2","s2")
        assert len(s.get_throttles()) == 2
    def test_filter(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.throttle("p2","s2")
        assert len(s.get_throttles(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.throttle("p1","s2")
        assert s.get_throttles(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepThrottler()
        for i in range(10): s.throttle("p1", f"s{i}")
        assert len(s.get_throttles(limit=3)) == 3

class TestGetThrottleCount:
    def test_total(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.throttle("p2","s2")
        assert s.get_throttle_count() == 2
    def test_filtered(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.throttle("p2","s2")
        assert s.get_throttle_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepThrottler().get_throttle_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepThrottler().get_stats()["total_throttles"] == 0
    def test_with_data(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.throttle("p2","s2")
        st = s.get_stats()
        assert st["total_throttles"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepThrottler(); evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.throttle("p1", "s1"); assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepThrottler(); s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepThrottler().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepThrottler(); s.MAX_ENTRIES = 5
        for i in range(8): s.throttle("p1", f"s{i}")
        assert s.get_throttle_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.reset()
        assert s.get_throttle_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepThrottler(); s.on_change = lambda a,d: None; s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepThrottler(); s.throttle("p1","s1"); s.reset()
        assert s._state._seq == 0
