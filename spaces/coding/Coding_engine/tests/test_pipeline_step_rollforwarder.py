"""Tests for PipelineStepRollforwarder."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_rollforwarder import PipelineStepRollforwarder


class TestBasic:
    def test_returns_id(self):
        s = PipelineStepRollforwarder()
        rid = s.rollforward("pipe-1", "step-a")
        assert rid.startswith("psrf-")

    def test_fields(self):
        s = PipelineStepRollforwarder()
        rid = s.rollforward("pipe-1", "step-a", target_version="v2")
        rec = s.get_rollforward(rid)
        assert rec["pipeline_id"] == "pipe-1"
        assert rec["step_name"] == "step-a"
        assert rec["target_version"] == "v2"

    def test_default_target_version(self):
        s = PipelineStepRollforwarder()
        rid = s.rollforward("pipe-1", "step-a")
        rec = s.get_rollforward(rid)
        assert rec["target_version"] == "latest"

    def test_metadata_deepcopy(self):
        s = PipelineStepRollforwarder()
        meta = {"k": [1]}
        rid = s.rollforward("pipe-1", "step-a", metadata=meta)
        meta["k"].append(2)
        rec = s.get_rollforward(rid)
        assert rec["metadata"]["k"] == [1]

    def test_empty_pipeline(self):
        s = PipelineStepRollforwarder()
        assert s.rollforward("", "step-a") == ""

    def test_empty_step(self):
        s = PipelineStepRollforwarder()
        assert s.rollforward("pipe-1", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineStepRollforwarder()
        rid = s.rollforward("pipe-1", "step-a")
        assert s.get_rollforward(rid) is not None

    def test_not_found(self):
        s = PipelineStepRollforwarder()
        assert s.get_rollforward("nope") is None

    def test_copy(self):
        s = PipelineStepRollforwarder()
        rid = s.rollforward("pipe-1", "step-a")
        r1 = s.get_rollforward(rid)
        r2 = s.get_rollforward(rid)
        assert r1 is not r2


class TestList:
    def test_all(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.rollforward("pipe-2", "step-b")
        assert len(s.get_rollforwards()) == 2

    def test_filter(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.rollforward("pipe-2", "step-b")
        assert len(s.get_rollforwards(pipeline_id="pipe-1")) == 1

    def test_newest_first(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        time.sleep(0.01)
        s.rollforward("pipe-1", "step-b")
        recs = s.get_rollforwards(pipeline_id="pipe-1")
        assert recs[0]["step_name"] == "step-b"


class TestCount:
    def test_total(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.rollforward("pipe-2", "step-b")
        assert s.get_rollforward_count() == 2

    def test_filtered(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.rollforward("pipe-2", "step-b")
        assert s.get_rollforward_count("pipe-1") == 1


class TestStats:
    def test_data(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.rollforward("pipe-2", "step-b")
        st = s.get_stats()
        assert st["total_rollforwards"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepRollforwarder()
        called = []
        s.on_change = lambda a, d: called.append(a)
        s.rollforward("pipe-1", "step-a")
        assert len(called) == 1

    def test_remove_true(self):
        s = PipelineStepRollforwarder()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = PipelineStepRollforwarder()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = PipelineStepRollforwarder()
        s.MAX_ENTRIES = 5
        for i in range(8):
            s.rollforward(f"pipe-{i}", f"step-{i}")
        assert len(s._state.entries) <= 6


class TestReset:
    def test_clears(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.on_change = lambda a, d: None
        s.reset()
        assert s.get_rollforward_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = PipelineStepRollforwarder()
        s.rollforward("pipe-1", "step-a")
        s.reset()
        assert s._state._seq == 0
