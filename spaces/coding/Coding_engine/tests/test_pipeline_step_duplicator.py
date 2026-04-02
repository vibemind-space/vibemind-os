"""Tests for PipelineStepDuplicator service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_duplicator import PipelineStepDuplicator


class TestIdGeneration:
    def test_prefix(self):
        assert PipelineStepDuplicator().duplicate("p1", "s1").startswith("psdu-")
    def test_unique(self):
        s = PipelineStepDuplicator()
        ids = {s.duplicate("p1", f"s{i}") for i in range(20)}
        assert len(ids) == 20
    def test_id_length(self):
        rid = PipelineStepDuplicator().duplicate("p1", "s1")
        assert len(rid) > len("psdu-")


class TestDuplicateBasic:
    def test_returns_id(self):
        assert len(PipelineStepDuplicator().duplicate("p1", "s1")) > 0
    def test_stores_pipeline_id(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "step_a")
        assert s.get_duplication(rid)["pipeline_id"] == "p1"
    def test_stores_step_name(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "step_a")
        assert s.get_duplication(rid)["step_name"] == "step_a"
    def test_stores_copies(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1", copies=3)
        assert s.get_duplication(rid)["copies"] == 3
    def test_default_copies(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1")
        assert s.get_duplication(rid)["copies"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepDuplicator()
        m = {"a": [1]}
        rid = s.duplicate("p1", "s1", metadata=m)
        m["a"].append(2)
        assert s.get_duplication(rid)["metadata"]["a"] == [1]
    def test_metadata_default_empty(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1")
        assert s.get_duplication(rid)["metadata"] == {}
    def test_created_at(self):
        s = PipelineStepDuplicator()
        before = time.time()
        rid = s.duplicate("p1", "s1")
        assert s.get_duplication(rid)["created_at"] >= before
    def test_has_seq(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1")
        assert "_seq" in s.get_duplication(rid)


class TestDuplicateValidation:
    def test_empty_pipeline_id(self):
        assert PipelineStepDuplicator().duplicate("", "s1") == ""
    def test_empty_step_name(self):
        assert PipelineStepDuplicator().duplicate("p1", "") == ""
    def test_both_empty(self):
        assert PipelineStepDuplicator().duplicate("", "") == ""


class TestGetDuplication:
    def test_found(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1")
        assert s.get_duplication(rid) is not None
    def test_not_found(self):
        assert PipelineStepDuplicator().get_duplication("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1")
        assert s.get_duplication(rid) is not s.get_duplication(rid)
    def test_record_id_field(self):
        s = PipelineStepDuplicator()
        rid = s.duplicate("p1", "s1")
        assert s.get_duplication(rid)["record_id"] == rid


class TestGetDuplications:
    def test_all(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.duplicate("p2", "s2")
        assert len(s.get_duplications()) == 2
    def test_filter_by_pipeline(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.duplicate("p2", "s2")
        assert len(s.get_duplications(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "first"); s.duplicate("p1", "second")
        assert s.get_duplications(pipeline_id="p1")[0]["step_name"] == "second"
    def test_limit(self):
        s = PipelineStepDuplicator()
        for i in range(10): s.duplicate("p1", f"s{i}")
        assert len(s.get_duplications(limit=3)) == 3
    def test_empty_result(self):
        assert len(PipelineStepDuplicator().get_duplications()) == 0
    def test_filter_no_match(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1")
        assert len(s.get_duplications(pipeline_id="none")) == 0


class TestGetDuplicationCount:
    def test_total(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.duplicate("p2", "s2")
        assert s.get_duplication_count() == 2
    def test_filtered(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.duplicate("p2", "s2")
        assert s.get_duplication_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepDuplicator().get_duplication_count() == 0
    def test_filter_no_match(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1")
        assert s.get_duplication_count(pipeline_id="none") == 0


class TestStats:
    def test_empty(self):
        stats = PipelineStepDuplicator().get_stats()
        assert stats["total_duplications"] == 0
        assert stats["unique_pipelines"] == 0
    def test_with_data(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.duplicate("p2", "s2")
        assert s.get_stats()["total_duplications"] == 2
        assert s.get_stats()["unique_pipelines"] == 2
    def test_same_pipeline(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.duplicate("p1", "s2")
        assert s.get_stats()["unique_pipelines"] == 1


class TestCallbacks:
    def test_on_change_fires(self):
        s = PipelineStepDuplicator()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.duplicate("p1", "s1")
        assert "duplicated" in evts
    def test_on_change_getter(self):
        s = PipelineStepDuplicator()
        assert s.on_change is None
        cb = lambda a, d: None
        s.on_change = cb
        assert s.on_change is cb
    def test_named_callback(self):
        s = PipelineStepDuplicator()
        evts = []
        s._state.callbacks["cb1"] = lambda a, d: evts.append(a)
        s.duplicate("p1", "s1")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepDuplicator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepDuplicator().remove_callback("x") is False
    def test_callback_exception_ignored(self):
        s = PipelineStepDuplicator()
        s._state.callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = s.duplicate("p1", "s1")
        assert rid != ""
    def test_on_change_exception_ignored(self):
        s = PipelineStepDuplicator()
        s.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = s.duplicate("p1", "s1")
        assert rid != ""


class TestPrune:
    def test_prune_reduces(self):
        s = PipelineStepDuplicator()
        s.MAX_ENTRIES = 5
        for i in range(8): s.duplicate("p1", f"s{i}")
        assert s.get_duplication_count() < 8
    def test_no_prune_under_limit(self):
        s = PipelineStepDuplicator()
        s.MAX_ENTRIES = 100
        for i in range(10): s.duplicate("p1", f"s{i}")
        assert s.get_duplication_count() == 10


class TestReset:
    def test_clears_entries(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.reset()
        assert s.get_duplication_count() == 0
    def test_clears_on_change(self):
        s = PipelineStepDuplicator()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepDuplicator()
        s.duplicate("p1", "s1"); s.reset()
        assert s._state._seq == 0
    def test_clears_callbacks(self):
        s = PipelineStepDuplicator()
        s._state.callbacks["cb1"] = lambda a, d: None
        s.reset()
        assert len(s._state.callbacks) == 0
