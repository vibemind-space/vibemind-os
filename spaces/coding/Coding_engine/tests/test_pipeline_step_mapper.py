"""Tests for PipelineStepMapper service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_mapper import PipelineStepMapper


class TestCreateMapping:
    """Tests for creating mappings."""

    def test_create_mapping_returns_id(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "step1", ["a", "b"], ["c"])
        assert mid.startswith("psma-")
        assert len(mid) > 5

    def test_create_mapping_unique_ids(self):
        svc = PipelineStepMapper()
        id1 = svc.create_mapping("p1", "s1", ["a"], ["b"])
        id2 = svc.create_mapping("p1", "s1", ["a"], ["b"])
        assert id1 != id2

    def test_create_mapping_with_metadata(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"], metadata={"ver": 1})
        entry = svc.get_mapping(mid)
        assert entry["metadata"] == {"ver": 1}

    def test_create_mapping_default_metadata_empty(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        entry = svc.get_mapping(mid)
        assert entry["metadata"] == {}

    def test_create_mapping_stores_keys(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["x", "y"], ["z"])
        entry = svc.get_mapping(mid)
        assert entry["input_keys"] == ["x", "y"]
        assert entry["output_keys"] == ["z"]


class TestGetMapping:
    """Tests for retrieving a single mapping."""

    def test_get_mapping_existing(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        entry = svc.get_mapping(mid)
        assert entry is not None
        assert entry["mapping_id"] == mid
        assert entry["pipeline_id"] == "p1"
        assert entry["step_name"] == "s1"

    def test_get_mapping_nonexistent(self):
        svc = PipelineStepMapper()
        assert svc.get_mapping("psma-doesnotexist") is None

    def test_get_mapping_returns_deepcopy(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        e1 = svc.get_mapping(mid)
        e2 = svc.get_mapping(mid)
        assert e1 is not e2
        e1["input_keys"].append("mutated")
        e3 = svc.get_mapping(mid)
        assert "mutated" not in e3["input_keys"]


class TestGetMappings:
    """Tests for listing mappings."""

    def test_get_mappings_all(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.create_mapping("p2", "s2", ["c"], ["d"])
        results = svc.get_mappings()
        assert len(results) == 2

    def test_get_mappings_filter_pipeline(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.create_mapping("p2", "s2", ["c"], ["d"])
        results = svc.get_mappings(pipeline_id="p1")
        assert len(results) == 1
        assert results[0]["pipeline_id"] == "p1"

    def test_get_mappings_filter_step(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.create_mapping("p1", "s2", ["c"], ["d"])
        results = svc.get_mappings(step_name="s2")
        assert len(results) == 1
        assert results[0]["step_name"] == "s2"

    def test_get_mappings_newest_first(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.create_mapping("p1", "s2", ["c"], ["d"])
        results = svc.get_mappings()
        assert results[0]["_seq_num"] > results[1]["_seq_num"]

    def test_get_mappings_limit(self):
        svc = PipelineStepMapper()
        for i in range(10):
            svc.create_mapping("p1", f"s{i}", ["a"], ["b"])
        results = svc.get_mappings(limit=3)
        assert len(results) == 3


class TestRecordTransform:
    """Tests for recording transforms."""

    def test_record_transform_success(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        result = svc.record_transform(mid, {"a": 1}, {"b": 2})
        assert result is True

    def test_record_transform_nonexistent(self):
        svc = PipelineStepMapper()
        result = svc.record_transform("psma-nope", {"a": 1}, {"b": 2})
        assert result is False

    def test_record_transform_stored(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.record_transform(mid, {"a": 1}, {"b": 2})
        entry = svc.get_mapping(mid)
        assert len(entry["transforms"]) == 1
        assert entry["transforms"][0]["input_data"] == {"a": 1}
        assert entry["transforms"][0]["output_data"] == {"b": 2}

    def test_record_multiple_transforms(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.record_transform(mid, {"a": 1}, {"b": 2})
        svc.record_transform(mid, {"a": 3}, {"b": 4})
        entry = svc.get_mapping(mid)
        assert len(entry["transforms"]) == 2

    def test_record_transform_deepcopy(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        inp = {"a": [1, 2]}
        svc.record_transform(mid, inp, {"b": 3})
        inp["a"].append(999)
        entry = svc.get_mapping(mid)
        assert 999 not in entry["transforms"][0]["input_data"]["a"]


class TestGetMappingCount:
    """Tests for counting mappings."""

    def test_count_all(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.create_mapping("p2", "s2", ["c"], ["d"])
        assert svc.get_mapping_count() == 2

    def test_count_by_pipeline(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.create_mapping("p1", "s2", ["c"], ["d"])
        svc.create_mapping("p2", "s3", ["e"], ["f"])
        assert svc.get_mapping_count(pipeline_id="p1") == 2
        assert svc.get_mapping_count(pipeline_id="p2") == 1

    def test_count_empty(self):
        svc = PipelineStepMapper()
        assert svc.get_mapping_count() == 0


class TestGetStats:
    """Tests for stats."""

    def test_stats_empty(self):
        svc = PipelineStepMapper()
        stats = svc.get_stats()
        assert stats["total_mappings"] == 0
        assert stats["total_transforms"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_with_data(self):
        svc = PipelineStepMapper()
        m1 = svc.create_mapping("p1", "s1", ["a"], ["b"])
        m2 = svc.create_mapping("p2", "s2", ["c"], ["d"])
        svc.record_transform(m1, {"a": 1}, {"b": 2})
        svc.record_transform(m1, {"a": 3}, {"b": 4})
        svc.record_transform(m2, {"c": 5}, {"d": 6})
        stats = svc.get_stats()
        assert stats["total_mappings"] == 2
        assert stats["total_transforms"] == 3
        assert stats["unique_pipelines"] == 2


class TestReset:
    """Tests for reset."""

    def test_reset_clears_entries(self):
        svc = PipelineStepMapper()
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        svc.reset()
        assert svc.get_mapping_count() == 0

    def test_reset_clears_callbacks(self):
        svc = PipelineStepMapper()
        svc.on_change = lambda action, data: None
        svc.reset()
        assert len(svc.on_change) == 0


class TestCallbacks:
    """Tests for event callbacks."""

    def test_fire_on_create(self):
        svc = PipelineStepMapper()
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.create_mapping("p1", "s1", ["a"], ["b"])
        assert len(events) == 1
        assert events[0][0] == "mapping_created"

    def test_fire_on_transform(self):
        svc = PipelineStepMapper()
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.record_transform(mid, {"a": 1}, {"b": 2})
        assert len(events) == 1
        assert events[0][0] == "transform_recorded"

    def test_remove_callback(self):
        svc = PipelineStepMapper()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_error_silent(self):
        svc = PipelineStepMapper()
        svc.on_change = lambda action, data: (_ for _ in ()).throw(ValueError("boom"))
        mid = svc.create_mapping("p1", "s1", ["a"], ["b"])
        assert mid.startswith("psma-")


class TestPrune:
    """Tests for pruning."""

    def test_prune_over_max(self):
        svc = PipelineStepMapper()
        svc.MAX_ENTRIES = 5
        for i in range(8):
            svc.create_mapping(f"p{i}", f"s{i}", ["a"], ["b"])
        assert len(svc._state.entries) == 5
