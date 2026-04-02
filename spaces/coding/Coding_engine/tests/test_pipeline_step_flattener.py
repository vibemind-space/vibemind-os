import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_step_flattener import PipelineStepFlattener

class TestBasic:
    def test_returns_id(self):
        s = PipelineStepFlattener()
        rid = s.flatten("v1", "v2")
        assert rid.startswith("psfl-")

    def test_fields(self):
        s = PipelineStepFlattener()
        rid = s.flatten("v1", "v2", metadata={"k": "v"})
        e = s.get_flatten(rid)
        assert e["pipeline_id"] == "v1"
        assert e["step_name"] == "v2"
        assert e["metadata"] == {"k": "v"}
        assert "created_at" in e

    def test_default_param(self):
        s = PipelineStepFlattener()
        rid = s.flatten("v1", "v2")
        assert s.get_flatten(rid)["depth"] == 1

    def test_metadata_deepcopy(self):
        s = PipelineStepFlattener()
        m = {"x": [1]}
        rid = s.flatten("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_flatten(rid)["metadata"]["x"] == [1]

    def test_empty_p1(self):
        s = PipelineStepFlattener()
        assert s.flatten("", "v2") == ""

    def test_empty_p2(self):
        s = PipelineStepFlattener()
        assert s.flatten("v1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineStepFlattener()
        rid = s.flatten("v1", "v2")
        assert s.get_flatten(rid) is not None

    def test_not_found(self):
        s = PipelineStepFlattener()
        assert s.get_flatten("nope") is None

    def test_copy(self):
        s = PipelineStepFlattener()
        rid = s.flatten("v1", "v2")
        e1 = s.get_flatten(rid)
        e2 = s.get_flatten(rid)
        assert e1 is not e2

class TestList:
    def test_all(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "v2")
        s.flatten("v3", "v4")
        assert len(s.get_flattens()) == 2

    def test_filter(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "v2")
        s.flatten("v3", "v4")
        assert len(s.get_flattens(pipeline_id="v1")) == 1

    def test_newest_first(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "a1")
        s.flatten("v1", "a2")
        items = s.get_flattens(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "v2")
        s.flatten("v3", "v4")
        assert s.get_flatten_count() == 2

    def test_filtered(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "v2")
        s.flatten("v3", "v4")
        assert s.get_flatten_count("v1") == 1

class TestStats:
    def test_data(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "v2")
        s.flatten("v3", "v4")
        st = s.get_stats()
        assert st["total_flattens"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepFlattener()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.flatten("v1", "v2")
        assert len(calls) == 1

    def test_remove_true(self):
        s = PipelineStepFlattener()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = PipelineStepFlattener()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepFlattener()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.flatten(f"p{i}", f"v{i}")
        assert s.get_flatten_count() <= 6

class TestReset:
    def test_clears(self):
        s = PipelineStepFlattener()
        s.on_change = lambda a, d: None
        s.flatten("v1", "v2")
        s.reset()
        assert s.get_flatten_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = PipelineStepFlattener()
        s.flatten("v1", "v2")
        s.reset()
        assert s._state._seq == 0
