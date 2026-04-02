"""Tests for PipelineDataQuarantiner service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_quarantiner import PipelineDataQuarantiner

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineDataQuarantiner()
        assert s.quarantine("p1", "k1").startswith("pdqr-")
    def test_unique(self):
        s = PipelineDataQuarantiner()
        ids = {s.quarantine("p1", f"k{i}") for i in range(20)}
        assert len(ids) == 20

class TestQuarantineBasic:
    def test_returns_id(self):
        s = PipelineDataQuarantiner()
        assert len(s.quarantine("p1", "k1")) > 0
    def test_stores_fields(self):
        s = PipelineDataQuarantiner()
        rid = s.quarantine("p1", "k1", reason="corrupt")
        e = s.get_quarantine(rid)
        assert e["pipeline_id"] == "p1"
        assert e["data_key"] == "k1"
        assert e["reason"] == "corrupt"
    def test_with_metadata(self):
        s = PipelineDataQuarantiner()
        rid = s.quarantine("p1", "k1", metadata={"x": 1})
        assert s.get_quarantine(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineDataQuarantiner()
        m = {"a": [1]}
        rid = s.quarantine("p1", "k1", metadata=m)
        m["a"].append(2)
        assert s.get_quarantine(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineDataQuarantiner()
        before = time.time()
        rid = s.quarantine("p1", "k1")
        assert s.get_quarantine(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineDataQuarantiner().quarantine("", "k1") == ""
    def test_empty_key_returns_empty(self):
        assert PipelineDataQuarantiner().quarantine("p1", "") == ""

class TestGetQuarantine:
    def test_found(self):
        s = PipelineDataQuarantiner()
        rid = s.quarantine("p1", "k1")
        assert s.get_quarantine(rid) is not None
    def test_not_found(self):
        assert PipelineDataQuarantiner().get_quarantine("xxx") is None
    def test_returns_copy(self):
        s = PipelineDataQuarantiner()
        rid = s.quarantine("p1", "k1")
        assert s.get_quarantine(rid) is not s.get_quarantine(rid)

class TestGetQuarantines:
    def test_all(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.quarantine("p2", "k2")
        assert len(s.get_quarantines()) == 2
    def test_filter(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.quarantine("p2", "k2")
        assert len(s.get_quarantines(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.quarantine("p1", "k2")
        assert s.get_quarantines(pipeline_id="p1")[0]["data_key"] == "k2"
    def test_limit(self):
        s = PipelineDataQuarantiner()
        for i in range(10): s.quarantine("p1", f"k{i}")
        assert len(s.get_quarantines(limit=3)) == 3

class TestGetQuarantineCount:
    def test_total(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.quarantine("p2", "k2")
        assert s.get_quarantine_count() == 2
    def test_filtered(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.quarantine("p2", "k2")
        assert s.get_quarantine_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineDataQuarantiner().get_quarantine_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineDataQuarantiner().get_stats()["total_quarantines"] == 0
    def test_with_data(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.quarantine("p2", "k2")
        st = s.get_stats()
        assert st["total_quarantines"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataQuarantiner()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.quarantine("p1", "k1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineDataQuarantiner()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineDataQuarantiner().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataQuarantiner()
        s.MAX_ENTRIES = 5
        for i in range(8): s.quarantine("p1", f"k{i}")
        assert s.get_quarantine_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.reset()
        assert s.get_quarantine_count() == 0
    def test_clears_callbacks(self):
        s = PipelineDataQuarantiner()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineDataQuarantiner()
        s.quarantine("p1", "k1"); s.reset()
        assert s._state._seq == 0
