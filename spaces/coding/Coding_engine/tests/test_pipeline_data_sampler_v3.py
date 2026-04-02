import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_data_sampler_v3 import PipelineDataSamplerV3

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataSamplerV3()
        rid = s.sample_v3("v1", "v2")
        assert rid.startswith("pds3-")
    def test_fields(self):
        s = PipelineDataSamplerV3()
        rid = s.sample_v3("v1", "v2", metadata={"k": "v"})
        e = s.get_sample(rid)
        assert e["pipeline_id"] == "v1"
        assert e["data_key"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = PipelineDataSamplerV3()
        rid = s.sample_v3("v1", "v2")
        assert s.get_sample(rid)["ratio"] == "0.1"
    def test_metadata_deepcopy(self):
        s = PipelineDataSamplerV3()
        m = {"x": [1]}
        rid = s.sample_v3("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_sample(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = PipelineDataSamplerV3()
        assert s.sample_v3("", "v2") == ""
    def test_empty_p2(self):
        s = PipelineDataSamplerV3()
        assert s.sample_v3("v1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineDataSamplerV3()
        rid = s.sample_v3("v1", "v2")
        assert s.get_sample(rid) is not None
    def test_not_found(self):
        s = PipelineDataSamplerV3()
        assert s.get_sample("nope") is None
    def test_copy(self):
        s = PipelineDataSamplerV3()
        rid = s.sample_v3("v1", "v2")
        assert s.get_sample(rid) is not s.get_sample(rid)

class TestList:
    def test_all(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "v2")
        s.sample_v3("v3", "v4")
        assert len(s.get_samples()) == 2
    def test_filter(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "v2")
        s.sample_v3("v3", "v4")
        assert len(s.get_samples(pipeline_id="v1")) == 1
    def test_newest_first(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "w1")
        s.sample_v3("v1", "w2")
        items = s.get_samples(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "v2")
        s.sample_v3("v3", "v4")
        assert s.get_sample_count() == 2
    def test_filtered(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "v2")
        s.sample_v3("v3", "v4")
        assert s.get_sample_count("v1") == 1

class TestStats:
    def test_data(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "v2")
        st = s.get_stats()
        assert st["total_samples"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataSamplerV3()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.sample_v3("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = PipelineDataSamplerV3()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = PipelineDataSamplerV3()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataSamplerV3()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.sample_v3(f"p{i}", f"v{i}")
        assert s.get_sample_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = PipelineDataSamplerV3()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.sample_v3("t1", "a1")
        assert captured[0]["action"] == "sample_v3"
        assert captured[0]["record_id"].startswith("pds3-")

class TestReset:
    def test_clears(self):
        s = PipelineDataSamplerV3()
        s.on_change = lambda a, d: None
        s.sample_v3("v1", "v2")
        s.reset()
        assert s.get_sample_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataSamplerV3()
        s.sample_v3("v1", "v2")
        s.reset()
        assert s._state._seq == 0
