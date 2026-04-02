"""Tests for PipelineDataCoalescer service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_coalescer import PipelineDataCoalescer

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineDataCoalescer()
        assert s.coalesce("p1", ["k1","k2"], "merged").startswith("pdcl-")
    def test_unique(self):
        s = PipelineDataCoalescer()
        ids = {s.coalesce("p1", [f"k{i}"], f"m{i}") for i in range(20)}
        assert len(ids) == 20

class TestCoalesceBasic:
    def test_returns_id(self):
        s = PipelineDataCoalescer()
        assert len(s.coalesce("p1", ["k1"], "m")) > 0
    def test_stores_fields(self):
        s = PipelineDataCoalescer()
        rid = s.coalesce("p1", ["k1","k2"], "merged")
        e = s.get_coalescence(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_keys"] == ["k1","k2"]
        assert e["target_key"] == "merged"
    def test_data_keys_copy(self):
        s = PipelineDataCoalescer()
        keys = ["k1","k2"]
        rid = s.coalesce("p1", keys, "m")
        keys.append("k3")
        assert s.get_coalescence(rid)["data_keys"] == ["k1","k2"]
    def test_with_metadata(self):
        s = PipelineDataCoalescer()
        rid = s.coalesce("p1", ["k1"], "m", metadata={"x": 1})
        assert s.get_coalescence(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataCoalescer()
        m = {"a": [1]}
        rid = s.coalesce("p1", ["k1"], "m", metadata=m)
        m["a"].append(2)
        assert s.get_coalescence(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataCoalescer()
        before = time.time()
        rid = s.coalesce("p1", ["k1"], "m")
        assert s.get_coalescence(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineDataCoalescer().coalesce("", ["k1"], "m") == ""
    def test_empty_keys_returns_empty(self):
        assert PipelineDataCoalescer().coalesce("p1", [], "m") == ""
    def test_empty_target_returns_empty(self):
        assert PipelineDataCoalescer().coalesce("p1", ["k1"], "") == ""

class TestGetCoalescence:
    def test_found(self):
        s = PipelineDataCoalescer()
        rid = s.coalesce("p1", ["k1"], "m")
        assert s.get_coalescence(rid) is not None
    def test_not_found(self):
        assert PipelineDataCoalescer().get_coalescence("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataCoalescer()
        rid = s.coalesce("p1", ["k1"], "m")
        assert s.get_coalescence(rid) is not s.get_coalescence(rid)

class TestGetCoalescences:
    def test_all(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m1"); s.coalesce("p2", ["k2"], "m2")
        assert len(s.get_coalescences()) == 2
    def test_filter(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m1"); s.coalesce("p2", ["k2"], "m2")
        assert len(s.get_coalescences(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m1"); s.coalesce("p1", ["k2"], "m2")
        assert s.get_coalescences(pipeline_id="p1")[0]["target_key"] == "m2"
    def test_limit(self):
        s = PipelineDataCoalescer()
        for i in range(10): s.coalesce("p1", [f"k{i}"], f"m{i}")
        assert len(s.get_coalescences(limit=3)) == 3

class TestGetCoalescenceCount:
    def test_total(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m1"); s.coalesce("p2", ["k2"], "m2")
        assert s.get_coalescence_count() == 2
    def test_filtered(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m1"); s.coalesce("p2", ["k2"], "m2")
        assert s.get_coalescence_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataCoalescer().get_coalescence_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataCoalescer().get_stats()["total_coalescences"] == 0
    def test_with_data(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m1"); s.coalesce("p2", ["k2"], "m2")
        st = s.get_stats()
        assert st["total_coalescences"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataCoalescer()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.coalesce("p1", ["k1"], "m")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataCoalescer()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataCoalescer().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataCoalescer()
        s.MAX_ENTRIES = 5
        for i in range(8): s.coalesce("p1", [f"k{i}"], f"m{i}")
        assert s.get_coalescence_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m"); s.reset()
        assert s.get_coalescence_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataCoalescer()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataCoalescer()
        s.coalesce("p1", ["k1"], "m"); s.reset()
        assert s._state._seq == 0
