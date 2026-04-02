import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_step_compressor import PipelineStepCompressor

class TestBasic:
    def test_returns_id(self):
        s = PipelineStepCompressor()
        rid = s.compress("v1", "v2")
        assert rid.startswith("pscp-")
    def test_fields(self):
        s = PipelineStepCompressor()
        rid = s.compress("v1", "v2", metadata={"k": "v"})
        e = s.get_compression(rid)
        assert e["pipeline_id"] == "v1"
        assert e["step_name"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = PipelineStepCompressor()
        rid = s.compress("v1", "v2")
        assert s.get_compression(rid)["algorithm"] == "gzip"
    def test_metadata_deepcopy(self):
        s = PipelineStepCompressor()
        m = {"x": [1]}
        rid = s.compress("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_compression(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = PipelineStepCompressor()
        assert s.compress("", "v2") == ""
    def test_empty_p2(self):
        s = PipelineStepCompressor()
        assert s.compress("v1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineStepCompressor()
        rid = s.compress("v1", "v2")
        assert s.get_compression(rid) is not None
    def test_not_found(self):
        s = PipelineStepCompressor()
        assert s.get_compression("nope") is None
    def test_copy(self):
        s = PipelineStepCompressor()
        rid = s.compress("v1", "v2")
        assert s.get_compression(rid) is not s.get_compression(rid)

class TestList:
    def test_all(self):
        s = PipelineStepCompressor()
        s.compress("v1", "v2")
        s.compress("v3", "v4")
        assert len(s.get_compressions()) == 2
    def test_filter(self):
        s = PipelineStepCompressor()
        s.compress("v1", "v2")
        s.compress("v3", "v4")
        assert len(s.get_compressions(pipeline_id="v1")) == 1
    def test_newest_first(self):
        s = PipelineStepCompressor()
        s.compress("v1", "a1")
        s.compress("v1", "a2")
        items = s.get_compressions(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = PipelineStepCompressor()
        s.compress("v1", "v2")
        s.compress("v3", "v4")
        assert s.get_compression_count() == 2
    def test_filtered(self):
        s = PipelineStepCompressor()
        s.compress("v1", "v2")
        s.compress("v3", "v4")
        assert s.get_compression_count("v1") == 1

class TestStats:
    def test_data(self):
        s = PipelineStepCompressor()
        s.compress("v1", "v2")
        st = s.get_stats()
        assert st["total_compressions"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepCompressor()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.compress("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = PipelineStepCompressor()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = PipelineStepCompressor()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepCompressor()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.compress(f"p{i}", f"v{i}")
        assert s.get_compression_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = PipelineStepCompressor()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.compress("t1", "a1")
        assert captured[0]["action"] == "compress"
        assert captured[0]["pipeline_id"] == "t1"

class TestReset:
    def test_clears(self):
        s = PipelineStepCompressor()
        s.on_change = lambda a, d: None
        s.compress("v1", "v2")
        s.reset()
        assert s.get_compression_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = PipelineStepCompressor()
        s.compress("v1", "v2")
        s.reset()
        assert s._state._seq == 0
