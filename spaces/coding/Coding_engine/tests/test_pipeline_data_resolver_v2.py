import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_data_resolver_v2 import PipelineDataResolverV2

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataResolverV2()
        rid = s.resolve_v2("v1", "v2")
        assert rid.startswith("pdrv-")
    def test_fields(self):
        s = PipelineDataResolverV2()
        rid = s.resolve_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_resolution(rid)
        assert e["pipeline_id"] == "v1"
        assert e["data_key"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = PipelineDataResolverV2()
        rid = s.resolve_v2("v1", "v2")
        assert s.get_resolution(rid)["strategy"] == "latest"
    def test_metadata_deepcopy(self):
        s = PipelineDataResolverV2()
        m = {"x": [1]}
        rid = s.resolve_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_resolution(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = PipelineDataResolverV2()
        assert s.resolve_v2("", "v2") == ""
    def test_empty_p2(self):
        s = PipelineDataResolverV2()
        assert s.resolve_v2("v1", "") == ""
class TestGet:
    def test_found(self):
        s = PipelineDataResolverV2()
        rid = s.resolve_v2("v1", "v2")
        assert s.get_resolution(rid) is not None
    def test_not_found(self):
        s = PipelineDataResolverV2()
        assert s.get_resolution("nope") is None
    def test_copy(self):
        s = PipelineDataResolverV2()
        rid = s.resolve_v2("v1", "v2")
        assert s.get_resolution(rid) is not s.get_resolution(rid)
class TestList:
    def test_all(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "v2")
        s.resolve_v2("v3", "v4")
        assert len(s.get_resolutions()) == 2
    def test_filter(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "v2")
        s.resolve_v2("v3", "v4")
        assert len(s.get_resolutions(pipeline_id="v1")) == 1
    def test_newest_first(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "w1")
        s.resolve_v2("v1", "w2")
        items = s.get_resolutions(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "v2")
        s.resolve_v2("v3", "v4")
        assert s.get_resolution_count() == 2
    def test_filtered(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "v2")
        s.resolve_v2("v3", "v4")
        assert s.get_resolution_count("v1") == 1
class TestStats:
    def test_data(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "v2")
        assert s.get_stats()["total_resolutions"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataResolverV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.resolve_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = PipelineDataResolverV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = PipelineDataResolverV2()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = PipelineDataResolverV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.resolve_v2(f"p{i}", f"v{i}")
        assert s.get_resolution_count() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = PipelineDataResolverV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.resolve_v2("t1", "a1")
        assert captured[0]["action"] == "resolve_v2"
        assert captured[0]["record_id"].startswith("pdrv-")
class TestReset:
    def test_clears(self):
        s = PipelineDataResolverV2()
        s.on_change = lambda a, d: None
        s.resolve_v2("v1", "v2")
        s.reset()
        assert s.get_resolution_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataResolverV2()
        s.resolve_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
