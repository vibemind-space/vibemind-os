"""Tests for PipelineStepComposer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_composer import PipelineStepComposer


class TestCompose:
    """Tests for creating compositions."""

    def test_compose_returns_id(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["step1", "step2"])
        assert cid.startswith("pscp-")
        assert len(cid) > 5

    def test_compose_unique_ids(self):
        svc = PipelineStepComposer()
        id1 = svc.compose("p1", ["s1"])
        id2 = svc.compose("p1", ["s1"])
        assert id1 != id2

    def test_compose_with_label(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"], label="my-label")
        entry = svc.get_composition(cid)
        assert entry["label"] == "my-label"

    def test_compose_with_metadata(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"], metadata={"ver": 1})
        entry = svc.get_composition(cid)
        assert entry["metadata"] == {"ver": 1}

    def test_compose_default_metadata_empty(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"])
        entry = svc.get_composition(cid)
        assert entry["metadata"] == {}

    def test_compose_stores_steps(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["a", "b", "c"])
        entry = svc.get_composition(cid)
        assert entry["steps"] == ["a", "b", "c"]

    def test_compose_returns_dict_via_get(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"])
        entry = svc.get_composition(cid)
        assert isinstance(entry, dict)
        assert entry["composition_id"] == cid
        assert entry["pipeline_id"] == "p1"


class TestGetComposition:
    """Tests for retrieving a single composition."""

    def test_get_composition_existing(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1", "s2"])
        entry = svc.get_composition(cid)
        assert entry is not None
        assert entry["composition_id"] == cid
        assert entry["pipeline_id"] == "p1"
        assert entry["steps"] == ["s1", "s2"]

    def test_get_composition_nonexistent(self):
        svc = PipelineStepComposer()
        assert svc.get_composition("pscp-doesnotexist") is None

    def test_get_composition_returns_deepcopy(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"])
        e1 = svc.get_composition(cid)
        e2 = svc.get_composition(cid)
        assert e1 is not e2
        e1["steps"].append("mutated")
        e3 = svc.get_composition(cid)
        assert "mutated" not in e3["steps"]


class TestAppendStep:
    """Tests for appending steps."""

    def test_append_step_success(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"])
        result = svc.append_step(cid, "s2")
        assert result is True

    def test_append_step_nonexistent(self):
        svc = PipelineStepComposer()
        result = svc.append_step("pscp-nope", "s2")
        assert result is False

    def test_append_step_stored(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"])
        svc.append_step(cid, "s2")
        svc.append_step(cid, "s3")
        entry = svc.get_composition(cid)
        assert entry["steps"] == ["s1", "s2", "s3"]


class TestGetCompositions:
    """Tests for listing compositions."""

    def test_get_compositions_all(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1"])
        svc.compose("p2", ["s2"])
        results = svc.get_compositions()
        assert len(results) == 2

    def test_get_compositions_filter_pipeline(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1"])
        svc.compose("p2", ["s2"])
        results = svc.get_compositions(pipeline_id="p1")
        assert len(results) == 1
        assert results[0]["pipeline_id"] == "p1"

    def test_get_compositions_newest_first(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1"])
        svc.compose("p1", ["s2"])
        results = svc.get_compositions()
        assert results[0]["_seq_num"] > results[1]["_seq_num"]

    def test_get_compositions_limit(self):
        svc = PipelineStepComposer()
        for i in range(10):
            svc.compose("p1", [f"s{i}"])
        results = svc.get_compositions(limit=3)
        assert len(results) == 3


class TestGetCompositionCount:
    """Tests for counting compositions."""

    def test_count_all(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1"])
        svc.compose("p2", ["s2"])
        assert svc.get_composition_count() == 2

    def test_count_by_pipeline(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1"])
        svc.compose("p1", ["s2"])
        svc.compose("p2", ["s3"])
        assert svc.get_composition_count(pipeline_id="p1") == 2
        assert svc.get_composition_count(pipeline_id="p2") == 1

    def test_count_empty(self):
        svc = PipelineStepComposer()
        assert svc.get_composition_count() == 0


class TestGetStats:
    """Tests for stats."""

    def test_stats_empty(self):
        svc = PipelineStepComposer()
        stats = svc.get_stats()
        assert stats["total_compositions"] == 0
        assert stats["total_steps"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_with_data(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1", "s2"])
        svc.compose("p2", ["s3"])
        svc.compose("p1", ["s4", "s5", "s6"])
        stats = svc.get_stats()
        assert stats["total_compositions"] == 3
        assert stats["total_steps"] == 6
        assert stats["unique_pipelines"] == 2


class TestReset:
    """Tests for reset."""

    def test_reset_clears_entries(self):
        svc = PipelineStepComposer()
        svc.compose("p1", ["s1"])
        svc.reset()
        assert svc.get_composition_count() == 0

    def test_reset_clears_callbacks(self):
        svc = PipelineStepComposer()
        svc.on_change = lambda action, data: None
        svc.reset()
        assert len(svc.on_change) == 0


class TestCallbacks:
    """Tests for event callbacks."""

    def test_fire_on_compose(self):
        svc = PipelineStepComposer()
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.compose("p1", ["s1"])
        assert len(events) == 1
        assert events[0][0] == "composition_created"

    def test_fire_on_append_step(self):
        svc = PipelineStepComposer()
        cid = svc.compose("p1", ["s1"])
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.append_step(cid, "s2")
        assert len(events) == 1
        assert events[0][0] == "step_appended"

    def test_remove_callback(self):
        svc = PipelineStepComposer()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_error_silent(self):
        svc = PipelineStepComposer()
        svc.on_change = lambda action, data: (_ for _ in ()).throw(ValueError("boom"))
        cid = svc.compose("p1", ["s1"])
        assert cid.startswith("pscp-")

    def test_on_change_dict_setter(self):
        svc = PipelineStepComposer()
        cb = lambda a, d: None
        svc.on_change = {"my_cb": cb}
        assert "my_cb" in svc.on_change


class TestPrune:
    """Tests for pruning."""

    def test_prune_over_max(self):
        svc = PipelineStepComposer()
        svc.MAX_ENTRIES = 5
        for i in range(8):
            svc.compose(f"p{i}", [f"s{i}"])
        assert len(svc._state.entries) == 5
