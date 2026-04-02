import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_data_decompiler import PipelineDataDecompiler

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataDecompiler()
        rid = s.decompile("v1", "v2")
        assert rid.startswith("pddc-")

    def test_fields(self):
        s = PipelineDataDecompiler()
        rid = s.decompile("v1", "v2", metadata={"k": "v"})
        e = s.get_decompilation(rid)
        assert e["pipeline_id"] == "v1"
        assert e["data_key"] == "v2"
        assert e["metadata"] == {"k": "v"}
        assert "created_at" in e

    def test_default_param(self):
        s = PipelineDataDecompiler()
        rid = s.decompile("v1", "v2")
        assert s.get_decompilation(rid)["target_format"] == "raw"

    def test_metadata_deepcopy(self):
        s = PipelineDataDecompiler()
        m = {"x": [1]}
        rid = s.decompile("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_decompilation(rid)["metadata"]["x"] == [1]

    def test_empty_p1(self):
        s = PipelineDataDecompiler()
        assert s.decompile("", "v2") == ""

    def test_empty_p2(self):
        s = PipelineDataDecompiler()
        assert s.decompile("v1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineDataDecompiler()
        rid = s.decompile("v1", "v2")
        assert s.get_decompilation(rid) is not None

    def test_not_found(self):
        s = PipelineDataDecompiler()
        assert s.get_decompilation("nope") is None

    def test_copy(self):
        s = PipelineDataDecompiler()
        rid = s.decompile("v1", "v2")
        e1 = s.get_decompilation(rid)
        e2 = s.get_decompilation(rid)
        assert e1 is not e2

class TestList:
    def test_all(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "v2")
        s.decompile("v3", "v4")
        assert len(s.get_decompilations()) == 2

    def test_filter(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "v2")
        s.decompile("v3", "v4")
        assert len(s.get_decompilations(pipeline_id="v1")) == 1

    def test_newest_first(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "a1")
        s.decompile("v1", "a2")
        items = s.get_decompilations(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "v2")
        s.decompile("v3", "v4")
        assert s.get_decompilation_count() == 2

    def test_filtered(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "v2")
        s.decompile("v3", "v4")
        assert s.get_decompilation_count("v1") == 1

class TestStats:
    def test_data(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "v2")
        s.decompile("v3", "v4")
        st = s.get_stats()
        assert st["total_decompilations"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataDecompiler()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.decompile("v1", "v2")
        assert len(calls) == 1

    def test_remove_true(self):
        s = PipelineDataDecompiler()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = PipelineDataDecompiler()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataDecompiler()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.decompile(f"p{i}", f"v{i}")
        assert s.get_decompilation_count() <= 6

class TestReset:
    def test_clears(self):
        s = PipelineDataDecompiler()
        s.on_change = lambda a, d: None
        s.decompile("v1", "v2")
        s.reset()
        assert s.get_decompilation_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = PipelineDataDecompiler()
        s.decompile("v1", "v2")
        s.reset()
        assert s._state._seq == 0
