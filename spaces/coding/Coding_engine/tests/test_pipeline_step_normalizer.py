"""Tests for PipelineStepNormalizer."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_step_normalizer import PipelineStepNormalizer


class TestBasic:
    def test_returns_id(self):
        s = PipelineStepNormalizer()
        rid = s.normalize("v1", "v2")
        assert rid.startswith("psnm-")

    def test_fields(self):
        s = PipelineStepNormalizer()
        rid = s.normalize("v1", "v2", metadata={"k": "v"})
        e = s.get_normalization(rid)
        assert e["pipeline_id"] == "v1"
        assert e["step_name"] == "v2"
        assert e["metadata"] == {"k": "v"}

    def test_default_param(self):
        s = PipelineStepNormalizer()
        rid = s.normalize("v1", "v2")
        assert s.get_normalization(rid)["mode"] == "standard"

    def test_custom_mode(self):
        s = PipelineStepNormalizer()
        rid = s.normalize("v1", "v2", mode="strict")
        assert s.get_normalization(rid)["mode"] == "strict"

    def test_metadata_deepcopy(self):
        s = PipelineStepNormalizer()
        m = {"x": [1]}
        rid = s.normalize("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_normalization(rid)["metadata"]["x"] == [1]

    def test_empty_args(self):
        s = PipelineStepNormalizer()
        assert s.normalize("", "v2") == ""
        assert s.normalize("v1", "") == ""
        assert s.normalize("", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineStepNormalizer()
        rid = s.normalize("v1", "v2")
        assert s.get_normalization(rid) is not None

    def test_not_found(self):
        s = PipelineStepNormalizer()
        assert s.get_normalization("nope") is None

    def test_copy(self):
        s = PipelineStepNormalizer()
        rid = s.normalize("v1", "v2")
        assert s.get_normalization(rid) is not s.get_normalization(rid)


class TestList:
    def test_all(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "v2")
        s.normalize("v3", "v4")
        assert len(s.get_normalizations()) == 2

    def test_filter(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "v2")
        s.normalize("v3", "v4")
        assert len(s.get_normalizations(pipeline_id="v1")) == 1

    def test_newest_first(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "a1")
        s.normalize("v1", "a2")
        items = s.get_normalizations(pipeline_id="v1")
        assert items[0]["_seq"] > items[-1]["_seq"]



class TestCount:
    def test_total(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "v2")
        s.normalize("v3", "v4")
        assert s.get_normalization_count() == 2

    def test_filtered(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "v2")
        s.normalize("v3", "v4")
        assert s.get_normalization_count("v1") == 1


class TestStats:
    def test_data(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "v2")
        s.normalize("v3", "v4")
        st = s.get_stats()
        assert st["total_normalizations"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change_registers(self):
        s = PipelineStepNormalizer()
        assert s.on_change("cb1", lambda a, d: None) is True

    def test_callback_fires(self):
        s = PipelineStepNormalizer()
        events = []
        s.on_change("cb1", lambda a, d: events.append((a, d)))
        s.normalize("v1", "v2")
        assert len(events) == 1
        assert events[0][0] == "normalization_created"
        assert events[0][1]["action"] == "normalization_created"

    def test_remove_true(self):
        s = PipelineStepNormalizer()
        s.on_change("cb1", lambda a, d: None)
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = PipelineStepNormalizer()
        assert s.remove_callback("nope") is False


class TestPrune:
    def test_max_entries_enforced(self):
        s = PipelineStepNormalizer()
        orig = PipelineStepNormalizer.MAX_ENTRIES
        PipelineStepNormalizer.MAX_ENTRIES = 3
        try:
            s.normalize("p", "a")
            s.normalize("p", "b")
            s.normalize("p", "c")
            result = s.normalize("p", "d")
            assert result == ""
            assert s.get_normalization_count() == 3
        finally:
            PipelineStepNormalizer.MAX_ENTRIES = orig


class TestReset:
    def test_clears(self):
        s = PipelineStepNormalizer()
        s.on_change("cb1", lambda a, d: None)
        s.normalize("v1", "v2")
        s.reset()
        assert s.get_normalization_count() == 0
        assert s.get_stats()["total_normalizations"] == 0

    def test_seq(self):
        s = PipelineStepNormalizer()
        s.normalize("v1", "v2")
        s.reset()
        assert s._state._seq == 0
