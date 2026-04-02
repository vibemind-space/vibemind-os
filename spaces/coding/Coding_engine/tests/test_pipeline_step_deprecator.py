"""Tests for PipelineStepDeprecator."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_deprecator import PipelineStepDeprecator


class TestBasic:
    def test_returns_id(self):
        s = PipelineStepDeprecator()
        rid = s.deprecate("pipe-1", "step-a")
        assert rid.startswith("psdp-")

    def test_fields(self):
        s = PipelineStepDeprecator()
        rid = s.deprecate("pipe-1", "step-a", reason="old")
        rec = s.get_deprecation(rid)
        assert rec["pipeline_id"] == "pipe-1"
        assert rec["step_name"] == "step-a"
        assert rec["reason"] == "old"

    def test_default_reason(self):
        s = PipelineStepDeprecator()
        rid = s.deprecate("pipe-1", "step-a")
        rec = s.get_deprecation(rid)
        assert rec["reason"] == ""

    def test_metadata_deepcopy(self):
        s = PipelineStepDeprecator()
        meta = {"k": [1]}
        rid = s.deprecate("pipe-1", "step-a", metadata=meta)
        meta["k"].append(2)
        rec = s.get_deprecation(rid)
        assert rec["metadata"]["k"] == [1]

    def test_empty_pipeline(self):
        s = PipelineStepDeprecator()
        assert s.deprecate("", "step-a") == ""

    def test_empty_step(self):
        s = PipelineStepDeprecator()
        assert s.deprecate("pipe-1", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineStepDeprecator()
        rid = s.deprecate("pipe-1", "step-a")
        assert s.get_deprecation(rid) is not None

    def test_not_found(self):
        s = PipelineStepDeprecator()
        assert s.get_deprecation("nope") is None

    def test_copy(self):
        s = PipelineStepDeprecator()
        rid = s.deprecate("pipe-1", "step-a")
        r1 = s.get_deprecation(rid)
        r2 = s.get_deprecation(rid)
        assert r1 is not r2


class TestList:
    def test_all(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.deprecate("pipe-2", "step-b")
        assert len(s.get_deprecations()) == 2

    def test_filter(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.deprecate("pipe-2", "step-b")
        assert len(s.get_deprecations(pipeline_id="pipe-1")) == 1

    def test_newest_first(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        time.sleep(0.01)
        s.deprecate("pipe-1", "step-b")
        recs = s.get_deprecations(pipeline_id="pipe-1")
        assert recs[0]["step_name"] == "step-b"


class TestCount:
    def test_total(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.deprecate("pipe-2", "step-b")
        assert s.get_deprecation_count() == 2

    def test_filtered(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.deprecate("pipe-2", "step-b")
        assert s.get_deprecation_count("pipe-1") == 1


class TestStats:
    def test_data(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.deprecate("pipe-2", "step-b")
        st = s.get_stats()
        assert st["total_deprecations"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepDeprecator()
        called = []
        s.on_change = lambda a, d: called.append(a)
        s.deprecate("pipe-1", "step-a")
        assert len(called) == 1

    def test_remove_true(self):
        s = PipelineStepDeprecator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = PipelineStepDeprecator()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = PipelineStepDeprecator()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.deprecate(f"pipe-{i}", f"step-{i}")
        assert len(s._state.entries) < 8


class TestReset:
    def test_clears(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.on_change = lambda a, d: None
        s.reset()
        assert s.get_deprecation_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = PipelineStepDeprecator()
        s.deprecate("pipe-1", "step-a")
        s.reset()
        assert s._state._seq == 0
